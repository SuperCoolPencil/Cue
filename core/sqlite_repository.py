"""SQLite repository implementation for Cue."""
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional

from core.interfaces import IRepository
from core.domain import Session, MediaMetadata, PlaybackState, WatchEvent
from core.database import Database


class SqliteRepository(IRepository):
    """SQLite-based repository for media sessions and watch statistics."""
    
    def __init__(self, db_path: Path):
        self.db = Database(db_path)
        self._sessions_cache: Optional[Dict[str, Session]] = None
    

    def _row_to_session(self, row) -> Session:
        """Convert a database row to a Session object."""
        genres = json.loads(row['genres']) if row['genres'] else []
        
        metadata = MediaMetadata(
            clean_title=row['clean_title'],
            season_number=row['season_number'],
            is_user_locked_title=bool(row['is_user_locked_title']),
            genres=genres,
            rating=row['rating'],
            description=row['description'],
            poster_path=row['poster_path']
        )
        
        playback = PlaybackState(
            last_played_file=row['last_played_file'] or "",
            last_played_index=row['last_played_index'] or 0,
            position=row['position'] or 0.0,
            duration=row['duration'] or 0.0,
            is_finished=bool(row['is_finished']),
            timestamp=datetime.fromisoformat(row['timestamp']) if row['timestamp'] else datetime.now()
        )
        
        return Session(id=row['id'], filepath=row['filepath'], metadata=metadata, playback=playback)
    
    def load_all_sessions(self) -> Dict[str, Session]:
        """Load all sessions from the database, keyed by ID."""
        if self._sessions_cache is not None:
            return self._sessions_cache
            
        sessions = {}
        with self.db.connection() as conn:
            rows = conn.execute("""
                SELECT s.id, s.filepath, s.clean_title, s.season_number, s.is_user_locked_title,
                       s.genres, s.rating, s.description, s.poster_path,
                       p.last_played_file, p.last_played_index, p.position, 
                       p.duration, p.is_finished, p.timestamp
                FROM sessions s
                LEFT JOIN playback p ON s.id = p.session_id
            """).fetchall()
            
            for row in rows:
                session = self._row_to_session(row)
                sessions[session.id] = session
        
        self._sessions_cache = sessions
        return sessions
    
    def get_session_by_filepath(self, filepath: str) -> Optional[Session]:
        """Retrieve a session by its filepath."""
        # Check cache first (optimization)
        if self._sessions_cache:
            for session in self._sessions_cache.values():
                if session.filepath == filepath:
                    return session
        
        with self.db.connection() as conn:
            row = conn.execute("""
                SELECT s.id, s.filepath, s.clean_title, s.season_number, s.is_user_locked_title,
                       s.genres, s.rating, s.description, s.poster_path,
                       p.last_played_file, p.last_played_index, p.position, 
                       p.duration, p.is_finished, p.timestamp
                FROM sessions s
                LEFT JOIN playback p ON s.id = p.session_id
                WHERE s.filepath = ?
            """, (filepath,)).fetchone()
            
            if row:
                return self._row_to_session(row)
        return None

    def save_session(self, session: Session) -> None:
        """Save a session to the database."""
        with self.db.connection() as conn:
            # Upsert session metadata
            conn.execute("""
                INSERT OR REPLACE INTO sessions 
                (id, filepath, clean_title, season_number, is_user_locked_title,
                 genres, rating, description, poster_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session.id,
                session.filepath,
                session.metadata.clean_title,
                session.metadata.season_number,
                int(session.metadata.is_user_locked_title),
                json.dumps(session.metadata.genres),
                session.metadata.rating,
                session.metadata.description,
                session.metadata.poster_path
            ))
            
            # Upsert playback state
            conn.execute("""
                INSERT OR REPLACE INTO playback
                (session_id, last_played_file, last_played_index, position, 
                 duration, is_finished, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                session.id,
                session.playback.last_played_file,
                session.playback.last_played_index,
                session.playback.position,
                session.playback.duration,
                int(session.playback.is_finished),
                session.playback.timestamp.isoformat()
            ))
        
        # Update cache
        if self._sessions_cache is not None:
            self._sessions_cache[session.id] = session
    
    def delete_session(self, session_id: str) -> None:
        """Delete a session from the database."""
        with self.db.connection() as conn:
            conn.execute("DELETE FROM playback WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        
        # Update cache
        if self._sessions_cache is not None and session_id in self._sessions_cache:
            del self._sessions_cache[session_id]
    
    # === Watch Event Methods ===
    
    def record_watch_event(self, event: WatchEvent) -> None:
        """Record a watch event for statistics tracking."""
        with self.db.connection() as conn:
            conn.execute("""
                INSERT INTO watch_events 
                (session_id, started_at, ended_at, position_start, position_end, episode_index)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                event.session_id,
                event.started_at.isoformat(),
                event.ended_at.isoformat(),
                event.position_start,
                event.position_end,
                event.episode_index
            ))
    
    # === Statistics Queries ===
    
    def get_total_watch_time(self) -> float:
        """Get total watch time in seconds across all sessions."""
        with self.db.connection() as conn:
            result = conn.execute("""
                SELECT COALESCE(SUM(position_end - position_start), 0) as total 
                FROM watch_events
            """).fetchone()
            return result['total']
    
    def get_most_watched(self, limit: int = 10) -> List[Tuple[str, float]]:
        """Get most watched shows/movies by total watch time."""
        with self.db.connection() as conn:
            rows = conn.execute("""
                SELECT s.clean_title, 
                       COALESCE(SUM(w.position_end - w.position_start), 0) as watch_time
                FROM sessions s
                LEFT JOIN watch_events w ON w.session_id = s.id
                GROUP BY s.id
                ORDER BY watch_time DESC
                LIMIT ?
            """, (limit,)).fetchall()
            return [(row['clean_title'], row['watch_time']) for row in rows]
    
    def get_streak_calendar(self, days: int = 365) -> Dict[str, int]:
        """Get watch streak calendar data (date -> minutes watched)."""
        with self.db.connection() as conn:
            rows = conn.execute("""
                SELECT DATE(started_at) as date, 
                       CAST(SUM(position_end - position_start) / 60 AS INTEGER) as minutes
                FROM watch_events
                WHERE DATE(started_at) >= DATE('now', ?)
                GROUP BY DATE(started_at)
            """, (f'-{days} days',)).fetchall()
            return {row['date']: row['minutes'] for row in rows}
    
    def get_viewing_patterns(self) -> Dict[int, float]:
        """Get viewing patterns by hour of day (hour -> minutes watched)."""
        with self.db.connection() as conn:
            rows = conn.execute("""
                SELECT CAST(strftime('%H', started_at) AS INTEGER) as hour,
                       COALESCE(SUM(position_end - position_start) / 60, 0) as minutes
                FROM watch_events
                GROUP BY hour
                ORDER BY hour
            """).fetchall()
            return {row['hour']: row['minutes'] for row in rows}
    
    def get_watch_history(self, limit: int = 50) -> List[WatchEvent]:
        """Get recent watch history timeline."""
        with self.db.connection() as conn:
            rows = conn.execute("""
                SELECT id, session_id, started_at, ended_at, 
                       position_start, position_end, episode_index
                FROM watch_events
                ORDER BY started_at DESC
                LIMIT ?
            """, (limit,)).fetchall()
            
            events = []
            for row in rows:
                events.append(WatchEvent(
                    id=row['id'],
                    session_id=row['session_id'],
                    started_at=datetime.fromisoformat(row['started_at']),
                    ended_at=datetime.fromisoformat(row['ended_at']),
                    position_start=row['position_start'],
                    position_end=row['position_end'],
                    episode_index=row['episode_index']
                ))
            return events
