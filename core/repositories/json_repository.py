import json
from pathlib import Path
from typing import Dict
from datetime import datetime

from core.interfaces import IRepository
from core.domain import Session, MediaMetadata, PlaybackState

class JSONEncoder(json.JSONEncoder):
    """Custom JSON encoder to handle datetime objects."""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

class JsonRepository(IRepository):
    """
    Concrete implementation of IRepository that saves and loads Session objects
    to a local JSON file.
    """
    def __init__(self, storage_file: Path):
        self.storage_file = storage_file
        self.sessions: Dict[str, Session] = self._load_from_file()

    def _load_from_file(self) -> Dict[str, Session]:
        """Loads sessions from the JSON file."""
        if not self.storage_file.exists():
            return {}
        
        with open(self.storage_file, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
        
        loaded_sessions = {}
        for filepath, data in raw_data.items():
            metadata = MediaMetadata(
                clean_title=data['metadata']['clean_title'],
                season_number=data['metadata'].get('season_number'),
                is_user_locked_title=data['metadata'].get('is_user_locked_title', False)
            )
            try:
                position = float(data['playback']['position'])
            except (ValueError, TypeError):
                position = 0.0
            
            try:
                duration = float(data['playback']['duration'])
            except (ValueError, TypeError):
                duration = 0.0

            playback = PlaybackState(
                last_played_file=data['playback']['last_played_file'],
                last_played_index=data['playback'].get('last_played_index', 0),
                position=position,
                duration=duration,
                is_finished=data['playback']['is_finished'],
                timestamp=datetime.fromisoformat(data['playback']['timestamp'])
            )
            loaded_sessions[filepath] = Session(
                filepath=filepath,
                metadata=metadata,
                playback=playback
            )
        return loaded_sessions

    def _save_to_file(self) -> None:
        """Saves current sessions to the JSON file."""
        # Convert dataclasses to dicts for JSON serialization
        serializable_data = {}
        for filepath, session in self.sessions.items():
            session_dict = {
                "filepath": session.filepath,
                "metadata": session.metadata.__dict__,
                "playback": session.playback.__dict__
            }
            serializable_data[filepath] = session_dict

        self.storage_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_file, 'w', encoding='utf-8') as f:
            json.dump(serializable_data, f, indent=4, cls=JSONEncoder)

    def load_all_sessions(self) -> Dict[str, Session]:
        """
        Returns all stored sessions.
        """
        return self.sessions

    def save_session(self, session: Session) -> None:
        """
        Saves a single session and updates the storage file.
        """
        self.sessions[session.filepath] = session
        self._save_to_file()

    def delete_session(self, filepath: str) -> None:
        """
        Deletes a session identified by its filepath and updates the storage file.
        """
        if filepath in self.sessions:
            del self.sessions[filepath]
            self._save_to_file()
