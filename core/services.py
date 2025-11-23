import os
from pathlib import Path
from typing import Optional, Dict, List

# Try to import guessit, but make it optional
try:
    from guessit import guessit
except ImportError:
    guessit = None
    print("Warning: 'guessit' library not found. Title guessing will be disabled.")

from core.domain import PlaybackState, MediaMetadata, Session
from core.interfaces import IPlayerDriver, IRepository
from core.utils import get_media_files

class LibraryService:
    """
    Manages the media library, handling session creation, playback,
    metadata updates, and persistence.
    """

    def __init__(self, repository: IRepository, player_driver: IPlayerDriver):
        self.repository = repository
        self.player_driver = player_driver
        self.sessions: Dict[str, Session] = self.repository.load_all_sessions()

    def get_or_create_session(self, filepath: str) -> Session:
        """
        Retrieves an existing session or creates a new one for the given filepath.
        Performs initial title guessing if a new session is created and title is not locked.
        """
        if filepath in self.sessions:
            return self.sessions[filepath]
        
        # Create new session
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
        new_session = Session(filepath=filepath, metadata=metadata)
        self.repository.save_session(new_session) # Persist new session
        self.sessions[filepath] = new_session
        return new_session

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

        index_to_play = session.playback.last_played_index
        
        if session.playback.is_finished:
            next_index = index_to_play + 1
            if next_index < len(series_files):
                index_to_play = next_index
            else:
                print("End of series.")
                return session.playback

        start_time = 0.0 if session.playback.is_finished else session.playback.position
        
        final_playback_state_from_driver = self.player_driver.launch(
            playlist=series_files,
            start_index=index_to_play,
            start_time=start_time
        )
        
        # Update the session's playback state
        session.playback.position = final_playback_state_from_driver.position
        session.playback.duration = final_playback_state_from_driver.duration
        session.playback.is_finished = final_playback_state_from_driver.is_finished
        session.playback.timestamp = final_playback_state_from_driver.timestamp
        session.playback.last_played_file = final_playback_state_from_driver.last_played_file
        try:
            session.playback.last_played_index = series_files.index(final_playback_state_from_driver.last_played_file)
        except ValueError:
            session.playback.last_played_index = 0
        
        self.repository.save_session(session)
        
        return session.playback

    def get_all_sessions(self) -> Dict[str, Session]:
        """Returns all sessions currently managed by the service."""
        return self.sessions
