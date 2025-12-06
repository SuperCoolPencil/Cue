from pathlib import Path
from typing import Dict, Any, Optional
import os # For os.path.isdir
from datetime import datetime

from core.domain import PlaybackState, MediaMetadata, Session
from core.interfaces import IPlayerDriver, IRepository
from core.drivers.mpv_driver import MpvDriver
from core.drivers.vlc_driver import VlcDriver # Import VlcDriver for selection
from core.repository import JsonRepository
from core.services import LibraryService
from core import settings as settings_mgr # Import the new settings module

# --- Configuration (can be moved to a separate config file if needed) ---
# Load settings from the new settings module
current_settings = settings_mgr.load_settings()
current_settings = settings_mgr.load_settings()
DEFAULT_STORAGE_PATH = settings_mgr.SESSIONS_PATH

# Determine player driver based on settings
PLAYER_DRIVERS = {
    "mpv_native": MpvDriver,
    "vlc_rc": VlcDriver,
    # "celluloid_ipc": CelluloidDriver, # If we were to implement this
}
player_type = current_settings.get("player_type", "mpv_native")
DEFAULT_PLAYER_DRIVER: IPlayerDriver = PLAYER_DRIVERS.get(player_type, MpvDriver)()

# --- Initialize Core Services ---
cue_repository: IRepository = JsonRepository(DEFAULT_STORAGE_PATH)
cue_library_service = LibraryService(cue_repository, DEFAULT_PLAYER_DRIVER)

# --- Facade for existing main.py (to minimize UI changes) ---

# Expose settings manager directly
settings = settings_mgr # Alias for main.py's expected settings_mgr

class SessionManagerFacade:
    """
    Provides facade functions for session management, mapping old UI calls
    to the new LibraryService methods.
    """
    def load_sessions(self) -> Dict[str, Dict[str, Any]]:
        """
        Loads all sessions and converts them to the dictionary format expected by the old UI.
        """
        raw_sessions = cue_library_service.get_all_sessions()
        # Convert Session objects to dictionaries expected by the old UI
        # This might need adjustment based on exact data structure expected by main.py
        formatted_sessions = {}
        for filepath, session_obj in raw_sessions.items():
            formatted_sessions[filepath] = {
                "id": hash(filepath), # Add a simple ID for Streamlit keys
                "last_played_file": session_obj.playback.last_played_file,
                "last_played_position": session_obj.playback.position,
                "total_duration": session_obj.playback.duration,
                "is_finished": session_obj.playback.is_finished,
                "last_played_timestamp": session_obj.playback.timestamp.isoformat(),
                "clean_title": session_obj.metadata.clean_title,
                "season_number": session_obj.metadata.season_number,
                "is_user_locked_title": session_obj.metadata.is_user_locked_title,
                "is_folder": os.path.isdir(filepath) # Assuming this is determined at load time
            }
        return formatted_sessions

    def update_session(self, filepath: str, playback_data: Dict[str, Any], is_folder: bool = False) -> None:
        """
        Updates a session with new playback and metadata.
        This function is designed to mimic the old `session_mgr.update_session`
        by extracting relevant data from `playback_data` dict.
        """
        session = cue_library_service.get_or_create_session(filepath)

        # Update PlaybackState
        new_playback_state = PlaybackState(
            last_played_file=playback_data.get('last_played_file', filepath),
            position=playback_data.get('position', 0.0),
            duration=playback_data.get('duration', 0.0),
            is_finished=playback_data.get('is_finished', False),
            timestamp=playback_data.get('timestamp', datetime.now()) # Assumes datetime object or will be converted
        )
        # Note: The main.py seems to send 'res' which contains 'clean_title' and 'season_number'
        # along with playback data. So, we might need to update metadata here too.
        # This assumes 'res' dict contains 'clean_title' and 'season_number'
        
        # Update Metadata if provided in playback_data and not user-locked
        if 'clean_title' in playback_data:
            cue_library_service.update_session_metadata(
                filepath, 
                clean_title=playback_data['clean_title'],
                season_number=playback_data.get('season_number'),
                # Only unlock if explicitly told, otherwise respect existing lock
                is_user_locked_title=session.metadata.is_user_locked_title or False 
            )

        cue_library_service.update_session_playback(filepath, new_playback_state)

    def update_session_metadata(self, filepath: str, key: str, value: Any) -> None:
        """
        Updates a specific metadata field for a session.
        Mimics old `session_mgr.update_session_metadata(path, 'clean_title', new_title)`.
        """
        if key == 'clean_title':
            # This implicitly sets is_user_locked_title to True when user edits via UI
            cue_library_service.update_session_metadata(filepath, clean_title=value, is_user_locked_title=True)
        # Add other keys if needed, e.g., 'season_number'
        else:
            print(f"Warning: Attempted to update unsupported metadata key: {key}")


    def delete_session(self, filepath: str) -> None:
        """Deletes a session from the repository."""
        if filepath in cue_library_service.sessions:
            cue_repository.delete_session(filepath)
            # No need to del from cue_library_service.sessions directly
            # as it will be reloaded on next session load if needed.
            # However, for immediate consistency, we can update it:
            del cue_library_service.sessions[filepath]

# Instantiate the facade
session = SessionManagerFacade() # Alias for main.py's expected session_mgr

__all__ = [
    "settings",
    "session",
    "Session",
    "MediaMetadata",
    "PlaybackState"
]
