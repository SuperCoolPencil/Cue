import os
import uuid
from typing import Dict, List, Optional, Tuple, Set, Callable
from datetime import datetime, timedelta

from core.config import RECAP_SUGGESTION_DAYS, EPISODE_COMPLETION_THRESHOLD
from core.domain import PlaybackState, MediaMetadata, Session, WatchEvent
from core.interfaces import IPlayerDriver, IRepository
from core.utils import get_media_files
from core.providers.subtitle_provider import SubtitleInfo

# Import new services
from .metadata import get_async_fetcher, AsyncMetadataFetcher
from .subtitles import SubtitleService
from .playback import PlaybackService

# Try to import guessit
try:
    from guessit import guessit
except ImportError:
    guessit = None

class LibraryService:
    """
    Manages the media library, handling session creation and persistence.
    Delegates specialized tasks (metadata, subtitles, playback) to dedicated services.
    """

    def __init__(self, repository: IRepository, player_driver: IPlayerDriver):
        self.repository = repository
        # We perform playback, so we need the driver. 
        # But we delegate the actual launch logic to PlaybackService.
        self.player_driver = player_driver
        
        self.sessions: Dict[str, Session] = self.repository.load_all_sessions() # Keyed by ID
        # Create a reverse index for fast lookup by filepath
        self._filepath_index: Dict[str, str] = {s.filepath: s.id for s in self.sessions.values()}
        
        # Initialize sub-services
        self._async_fetcher = get_async_fetcher()
        self._subtitle_service = SubtitleService()
        self._playback_service = PlaybackService(player_driver, repository)

    def get_or_create_session(self, filepath: str) -> Session:
        """
        Retrieves an existing session or creates a new one for the given filepath.
        Performs initial title guessing if a new session is created.
        """
        if filepath in self._filepath_index:
            session_id = self._filepath_index[filepath]
            if session_id in self.sessions:
                return self.sessions[session_id]
        
        if hasattr(self.repository, 'get_session_by_filepath'):
             existing = self.repository.get_session_by_filepath(filepath)
             if existing:
                 self.sessions[existing.id] = existing
                 self._filepath_index[existing.filepath] = existing.id
                 return existing

        # Create new session
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
            except Exception as e:
                print(f"Error guessing title for {filepath}: {e}")
        
        metadata = MediaMetadata(
            clean_title=initial_title,
            season_number=season_number,
            is_user_locked_title=False
        )
        new_session = Session(id=session_id, filepath=filepath, metadata=metadata)
        
        self.repository.save_session(new_session)
        self.sessions[session_id] = new_session
        self._filepath_index[filepath] = session_id
        
        # Start async TMDB metadata fetch
        self._async_fetcher.fetch_async(new_session, self.repository)
        
        return new_session

    def get_all_sessions(self) -> Dict[str, Session]:
        """Returns all sessions currently managed by the service."""
        return self.sessions

    def update_session_metadata(self, filepath: str, clean_title: Optional[str] = None, 
                                season_number: Optional[int] = None, 
                                is_user_locked_title: Optional[bool] = None) -> Session:
        """
        Updates the MediaMetadata for a given session. 
        """
        session = self.get_or_create_session(filepath)
        
        if clean_title is not None:
            if not session.metadata.is_user_locked_title or (is_user_locked_title is False):
                session.metadata.clean_title = clean_title
        
        if season_number is not None:
            session.metadata.season_number = season_number
        
        if is_user_locked_title is not None:
            session.metadata.is_user_locked_title = is_user_locked_title
        
        self.repository.save_session(session)
        return session

    def update_session_playback(self, filepath: str, playback_state: PlaybackState) -> Session:
        """Updates the PlaybackState for a given session."""
        session = self.get_or_create_session(filepath)
        session.playback = playback_state
        self.repository.save_session(session)
        return session
    
    def get_series_files(self, session: Session) -> List[str]:
        """Returns a sorted list of file paths for the same series as the given session."""
        series_path = session.filepath
        if os.path.isfile(series_path):
            series_path = os.path.dirname(series_path)
        return get_media_files(series_path)

    # === Metadata Delegation ===

    def is_metadata_fetching(self, session_id: str) -> bool:
        return self._async_fetcher.is_fetching(session_id)

    def refresh_metadata(self, session: Session) -> Session:
        session.metadata.is_metadata_fetched = False
        self.repository.save_session(session)
        self._async_fetcher.fetch_async(session, self.repository)
        return session
    
    def fetch_metadata_by_id(self, session: Session, tmdb_id: int, media_type: str = "movie") -> tuple[Session, bool, str]:
        # This was part of LibraryService but logically belongs to Metadata Fetcher.
        # However, AsyncMetadataFetcher is async.
        # We can move the synchronous logic here or to a helper in metadata.py.
        # For now, let's keep it here but in a cleaned up way or delegate if possible.
        # Ideally, we should add a sync method to metadata service or just keep it here as it interacts with provider directly.
        # But wait, I didn't extract `fetch_metadata_by_id` to metadata.py. I missed that.
        # It's fine, I can implement it here or import a helper.
        # A cleaner way is to keep it here for now as it modifies the session directly and saves it.
        
        # RE-IMPLEMENTATION based on original logic, but using updated imports?
        # Actually proper refactoring would move this logic to metadata.py BUT simpler to just keep it working here.
        # Let's copy the logic from the original file but use the provider directly.
        
        from core.providers.metadata_provider import get_metadata_provider
        
        print(f"DEBUG fetch_metadata_by_id: Fetching {media_type}/{tmdb_id}")
        provider = get_metadata_provider()
        
        if not provider.is_configured:
            return session, False, "TMDB API key not configured"
        
        try:
            details, error = provider._get(f"{media_type}/{tmdb_id}")
            if error:
                return session, False, error
            
            if details:
                title = details.get('title') or details.get('name')
                
                genres = [g.get('name') for g in details.get('genres', [])]
                
                date_str = details.get('release_date') or details.get('first_air_date', '')
                year = int(date_str[:4]) if date_str and len(date_str) >= 4 else None
                
                if media_type == "movie":
                    runtime = details.get("runtime")
                else:
                    runtimes = details.get("episode_run_time", [])
                    runtime = runtimes[0] if runtimes else None
                
                session.metadata.clean_title = title or session.metadata.clean_title
                session.metadata.description = details.get('overview')
                session.metadata.poster_path = provider.get_poster_url(details.get('poster_path')) if details.get('poster_path') else None
                session.metadata.backdrop_path = provider.get_backdrop_url(details.get('backdrop_path')) if details.get('backdrop_path') else None
                session.metadata.genres = genres
                session.metadata.vote_average = details.get('vote_average')
                session.metadata.vote_count = details.get('vote_count')
                session.metadata.year = year
                session.metadata.tmdb_id = tmdb_id
                session.metadata.runtime_minutes = runtime
                session.metadata.is_metadata_fetched = True
                
                self.repository.save_session(session)
                return session, True, f"Found: {title}"
            else:
                return session, False, f"No {media_type} found with ID {tmdb_id}"
        except Exception as e:
            return session, False, f"Error: {str(e)}"

    # === Playback Delegation ===

    def launch_media(self, filepath: str) -> PlaybackState:
        session = self.get_or_create_session(filepath)
        series_files = self.get_series_files(session)
        
        self._playback_service.launch_media(session, series_files)
        
        return session.playback

    def has_next_episode(self, session: Session) -> bool:
        series_files = self.get_series_files(session)
        if not series_files:
            return False
        return session.playback.last_played_index < len(series_files) - 1

    def get_next_episode_info(self, session: Session) -> Optional[Tuple[int, str]]:
        series_files = self.get_series_files(session)
        if not series_files:
            return None
        
        next_index = session.playback.last_played_index + 1
        if next_index < len(series_files):
            return (next_index, os.path.basename(series_files[next_index]))
        return None

    def get_resume_action(self, session: Session) -> str:
        now = datetime.now()
        days_since_last = (now - session.playback.timestamp).days
        
        completion = 0.0
        if session.playback.duration > 0:
            completion = session.playback.position / session.playback.duration
        
        if completion > EPISODE_COMPLETION_THRESHOLD:
            return "restart_or_next"
        elif days_since_last > RECAP_SUGGESTION_DAYS:
            return "show_recap"
        else:
            return "resume"

    # === Subtitle Delegation ===

    def search_subtitles(self, session: Session) -> List[SubtitleInfo]:
        series_files = self.get_series_files(session)
        return self._subtitle_service.search_subtitles(session, series_files)

    def download_subtitle(self, session: Session, subtitle_id: str) -> Tuple[bool, str]:
        series_files = self.get_series_files(session)
        return self._subtitle_service.download_subtitle(session, subtitle_id, series_files)

    def batch_download_subtitles(self, session: Session) -> Tuple[int, int, List[str]]:
        series_files = self.get_series_files(session)
        return self._subtitle_service.batch_download_subtitles(session, series_files)

    def sync_subtitles(self, session: Session) -> Tuple[bool, str]:
        series_files = self.get_series_files(session)
        return self._subtitle_service.sync_subtitles(session, series_files)
