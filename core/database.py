"""SQLite database for Cue media library."""
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Generator

SCHEMA = """
-- Sessions table (main media items)
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    filepath TEXT UNIQUE NOT NULL,
    clean_title TEXT NOT NULL,
    season_number INTEGER,
    is_user_locked_title INTEGER DEFAULT 0,
    genres TEXT,
    rating REAL,
    description TEXT,
    poster_path TEXT
);

-- Playback state (current position per session)
CREATE TABLE IF NOT EXISTS playback (
    session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    last_played_file TEXT,
    last_played_index INTEGER DEFAULT 0,
    position REAL DEFAULT 0,
    duration REAL DEFAULT 0,
    is_finished INTEGER DEFAULT 0,
    timestamp TEXT
);

-- Watch history (for statistics)
CREATE TABLE IF NOT EXISTS watch_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    position_start REAL,
    position_end REAL,
    episode_index INTEGER DEFAULT 0
);

-- Indexes for efficient stat queries
CREATE INDEX IF NOT EXISTS idx_watch_events_date ON watch_events(started_at);
CREATE INDEX IF NOT EXISTS idx_watch_events_session_id ON watch_events(session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_filepath ON sessions(filepath);
"""


class Database:
    """SQLite database connection manager for Cue."""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_schema()
    
    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for database connections with auto-commit."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def _init_schema(self) -> None:
        """Initialize database schema."""
        with self.connection() as conn:
            conn.executescript(SCHEMA)
