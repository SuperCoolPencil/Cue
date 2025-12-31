import os
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple

from core.config import (
    MIN_WATCH_DURATION_SECONDS,
    EPISODE_COMPLETION_THRESHOLD,
    RECAP_SUGGESTION_DAYS,
)

# Try to import guessit, but make it optional
try:
    from guessit import guessit
except ImportError:
    guessit = None
    print("Warning: 'guessit' library not found. Title guessing will be disabled.")

from core.domain import PlaybackState, MediaMetadata, Session, WatchEvent
from core.interfaces import IPlayerDriver, IRepository
from core.utils import get_media_files
from core.providers.metadata_provider import get_metadata_provider, TMDBProvider

class LibraryService:
    """
    Manages the media library, handling session creation, playback,
    metadata updates, and persistence.
    """

    def __init__(self, repository: IRepository, player_driver: IPlayerDriver):
        self.repository = repository
        self.player_driver = player_driver
        self.sessions: Dict[str, Session] = self.repository.load_all_sessions() # Keyed by ID
        # Create a reverse index for fast lookup by filepath
        self._filepath_index: Dict[str, str] = {s.filepath: s.id for s in self.sessions.values()}

    def get_or_create_session(self, filepath: str) -> Session:
        """
        Retrieves an existing session or creates a new one for the given filepath.
        Performs initial title guessing if a new session is created and title is not locked.
        """
        if filepath in self._filepath_index:
            session_id = self._filepath_index[filepath]
            if session_id in self.sessions:
                return self.sessions[session_id]
        
        # Check if repository has it (if cache missed for some reason or direct access needed)
        # Note: Repo methods now work with IDs primarily, but we added get_session_by_filepath
        if hasattr(self.repository, 'get_session_by_filepath'):
             existing = self.repository.get_session_by_filepath(filepath)
             if existing:
                 self.sessions[existing.id] = existing
                 self._filepath_index[existing.filepath] = existing.id
                 return existing

        # Create new session with UUID
        session_id = str(uuid.uuid4())
        initial_title = os.path.basename(filepath)
        season_number = None

        if guessit:
            try:
                guessed = guessit(filepath)
                if 'title' in guessed:
                    initial_title = guessed['title']
                if 'season' in guessed:
                    season_number = guessed['season'] if (type(guessed['season']) is int) else None
                print(f"Guessed title for {filepath}: {initial_title}, Season: {season_number}")
            except Exception as e:
                print(f"Error guessing title for {filepath}: {e}")
        else:
            print(f"Guessit not available. Using filename as title for {filepath}.")

        metadata = MediaMetadata(
            clean_title=initial_title,
            season_number=season_number,
            is_user_locked_title=False # Initially not locked
        )
        new_session = Session(id=session_id, filepath=filepath, metadata=metadata)
        
        # Try to fetch TMDB metadata for new sessions
        self._try_fetch_metadata(new_session)
        
        self.repository.save_session(new_session) # Persist new session
        self.sessions[session_id] = new_session
        self._filepath_index[filepath] = session_id
        return new_session

    def _try_fetch_metadata(self, session: Session) -> None:
        """
        Try to fetch metadata from TMDB for the session.
        Only fetches if not already fetched and title is not user-locked.
        """
        print(f"DEBUG _try_fetch_metadata: Starting for '{session.metadata.clean_title}'")
        print(f"DEBUG _try_fetch_metadata: is_fetched={session.metadata.is_metadata_fetched}, is_locked={session.metadata.is_user_locked_title}")
        
        if session.metadata.is_metadata_fetched:
            print("DEBUG _try_fetch_metadata: Skipping - already fetched")
            return
        
        provider = get_metadata_provider()
        if not provider.is_configured:
            print("DEBUG _try_fetch_metadata: TMDB API key not configured. Skipping.")
            return
        
        # Use guessit to get year and media type hints
        year = None
        media_type = None
        
        if guessit:
            try:
                guessed = guessit(session.filepath)
                year = guessed.get('year')
                # Determine if it's a TV show or movie based on guessit
                if guessed.get('type') == 'episode' or 'season' in guessed or 'episode' in guessed:
                    media_type = 'tv'
                else:
                    media_type = 'movie'
                print(f"DEBUG _try_fetch_metadata: Guessit result - year={year}, media_type={media_type}")
            except Exception as e:
                print(f"Guessit error during metadata fetch: {e}")
        
        try:
            print(f"DEBUG _try_fetch_metadata: Calling provider.search('{session.metadata.clean_title}')")
            info = provider.search(
                title=session.metadata.clean_title,
                year=year,
                media_type=media_type
            )
            
            if info:
                print(f"DEBUG _try_fetch_metadata: Got result - {info.title}, poster={info.poster_path}")
                # Update metadata with TMDB info
                session.metadata.description = info.overview
                session.metadata.poster_path = provider.get_poster_url(info.poster_path) if info.poster_path else None
                session.metadata.backdrop_path = provider.get_backdrop_url(info.backdrop_path) if info.backdrop_path else None
                session.metadata.genres = info.genres or []
                session.metadata.vote_average = info.vote_average
                session.metadata.vote_count = info.vote_count
                session.metadata.year = info.year
                session.metadata.tmdb_id = info.tmdb_id
                session.metadata.runtime_minutes = info.runtime_minutes
                session.metadata.is_metadata_fetched = True
                print(f"DEBUG _try_fetch_metadata: Updated metadata - poster_path={session.metadata.poster_path}")
            else:
                # Mark as fetched even if not found to avoid repeated API calls
                session.metadata.is_metadata_fetched = True
                print(f"DEBUG _try_fetch_metadata: No TMDB results for: {session.metadata.clean_title}")
        except Exception as e:
            print(f"DEBUG _try_fetch_metadata: Error - {e}")

    def refresh_metadata(self, session: Session) -> Session:
        """
        Force refresh metadata from TMDB, even if already fetched.
        """
        # Temporarily clear the fetched flag to allow re-fetch
        session.metadata.is_metadata_fetched = False
        self._try_fetch_metadata(session)
        self.repository.save_session(session)
        return session

    def update_session_metadata(self, filepath: str, clean_title: Optional[str] = None, 
                                season_number: Optional[int] = None, 
                                is_user_locked_title: Optional[bool] = None) -> Session:
        """
        Updates the MediaMetadata for a given session. 
        User-locked titles are preserved if is_user_locked_title is True.
        """
        session = self.get_or_create_session(filepath)
        
        if clean_title is not None:
            # Only update title if not user-locked, or if explicitly unlocking
            if not session.metadata.is_user_locked_title or (is_user_locked_title is False):
                session.metadata.clean_title = clean_title
        
        if season_number is not None:
            session.metadata.season_number = season_number
        
        if is_user_locked_title is not None:
            session.metadata.is_user_locked_title = is_user_locked_title
        
        self.repository.save_session(session)
        return session

    def update_session_playback(self, filepath: str, playback_state: PlaybackState) -> Session:
        """
        Updates the PlaybackState for a given session.
        """
        session = self.get_or_create_session(filepath)
        session.playback = playback_state
        self.repository.save_session(session)
        return session
    
    def get_series_files(self, session: Session) -> List[str]:
        """
        Returns a sorted list of file paths for the same series as the given session.
        """
        series_path = session.filepath
        if os.path.isfile(series_path):
            series_path = os.path.dirname(series_path)
        return get_media_files(series_path)

    def launch_media(self, filepath: str) -> PlaybackState:
        """
        Launches the media file using the configured player driver.
        Updates the session's playback state after playback.
        """
        session = self.get_or_create_session(filepath)
        
        series_files = self.get_series_files(session)
        if not series_files:
            print(f"No media files found for session: {filepath}")
            return session.playback

        last_played_index_from_session = session.playback.last_played_index
        position_from_session = session.playback.position
        
        index_to_play = last_played_index_from_session # Default to current
        start_time = position_from_session # Default to current position

        if session.playback.is_finished:
            next_index = last_played_index_from_session + 1
            if next_index < len(series_files):
                # There are more episodes, play the next one from the beginning
                index_to_play = next_index
                start_time = 0.0
            else:
                # Entire series is complete, restart from episode 1 from the beginning
                print("End of series. Restarting from episode 1.")
                index_to_play = 0
                start_time = 0.0
        
        watch_start_time = datetime.now()
        
        final_playback_state_from_driver = self.player_driver.launch(
            playlist=series_files,
            start_index=index_to_play,
            start_time=start_time
        )
        
        watch_end_time = datetime.now()
        
        # Calculate actual wall clock duration
        total_wall_clock_seconds = (watch_end_time - watch_start_time).total_seconds()
        
        # --- Record Single Watch Event with Wall Clock Time ---
        # We only care about total time spent, not per-episode breakdown
        if total_wall_clock_seconds > MIN_WATCH_DURATION_SECONDS:
            self.record_watch_event(
                session_id=session.id,
                started_at=watch_start_time,
                ended_at=watch_end_time,
                position_start=start_time,
                position_end=final_playback_state_from_driver.position,
                episode_index=final_playback_state_from_driver.last_played_index
            )
            print(f"DEBUG: Watch event recorded - Wall clock: {total_wall_clock_seconds:.1f}s")
        
        # Update the session's playback state
        session.playback.position = final_playback_state_from_driver.position
        session.playback.duration = final_playback_state_from_driver.duration
        session.playback.is_finished = final_playback_state_from_driver.is_finished
        session.playback.timestamp = final_playback_state_from_driver.timestamp
        session.playback.last_played_file = final_playback_state_from_driver.last_played_file
        
        # Robustly find the last_played_index, allowing for partial path matches
        # to prevent ValueError if paths don't exactly match (e.g., due to OS path differences, etc.)
        matched_index = 0
        if final_playback_state_from_driver.last_played_file:
            for i, file_in_series in enumerate(series_files):
                if (final_playback_state_from_driver.last_played_file in file_in_series) or \
                   (file_in_series in final_playback_state_from_driver.last_played_file):
                    matched_index = i
                    break
        session.playback.last_played_index = matched_index
        
        self.repository.save_session(session)
        
        return session.playback

    def get_all_sessions(self) -> Dict[str, Session]:
        """Returns all sessions currently managed by the service."""
        return self.sessions

    def get_resume_action(self, session: Session) -> str:
        """
        Determines the appropriate resume action based on context.
        
        Returns:
            'restart_or_next': If >95% complete, offer to start from beginning or next episode
            'show_recap': If away for >7 days, suggest showing a recap
            'resume': Normal resume from last position
        """
        now = datetime.now()
        days_since_last = (now - session.playback.timestamp).days
        
        # Calculate completion percentage
        completion = 0.0
        if session.playback.duration > 0:
            completion = session.playback.position / session.playback.duration
        
        if completion > EPISODE_COMPLETION_THRESHOLD:
            return "restart_or_next"
        elif days_since_last > RECAP_SUGGESTION_DAYS:
            return "show_recap"
        else:
            return "resume"

    def record_watch_event(self, session_id: str, started_at: datetime, 
                           ended_at: datetime, position_start: float, 
                           position_end: float, episode_index: int = 0) -> None:
        """
        Records a watch event for statistics tracking.
        Should be called when playback ends (either by user or end of media).
        """
        event = WatchEvent(
            session_id=session_id,
            started_at=started_at,
            ended_at=ended_at,
            position_start=position_start,
            position_end=position_end,
            episode_index=episode_index
        )
        
        # If repository supports watch events, record it
        if hasattr(self.repository, 'record_watch_event'):
            self.repository.record_watch_event(event)

    def has_next_episode(self, session: Session) -> bool:
        """Check if there's a next episode available."""
        series_files = self.get_series_files(session)
        if not series_files:
            return False
        return session.playback.last_played_index < len(series_files) - 1

    def get_next_episode_info(self, session: Session) -> Optional[Tuple[int, str]]:
        """Get next episode index and filename if available."""
        series_files = self.get_series_files(session)
        if not series_files:
            return None
        
        next_index = session.playback.last_played_index + 1
        if next_index < len(series_files):
            return (next_index, os.path.basename(series_files[next_index]))
        return None

