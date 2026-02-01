import os
import uuid
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple, Set, Callable

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


class AsyncMetadataFetcher:
    """
    Handles asynchronous TMDB metadata fetching using background threads.
    Tracks pending fetches and provides callbacks for completion.
    """
    
    def __init__(self):
        self._pending_fetches: Set[str] = set()  # Session IDs currently being fetched
        self._lock = threading.Lock()
        self._on_complete_callbacks: List[Callable[[str], None]] = []
    
    def is_fetching(self, session_id: str) -> bool:
        """Check if a session's metadata is currently being fetched."""
        with self._lock:
            return session_id in self._pending_fetches
    
    def add_completion_callback(self, callback: Callable[[str], None]) -> None:
        """Add a callback to be called when a fetch completes."""
        self._on_complete_callbacks.append(callback)
    
    def fetch_async(self, session: Session, repository: 'IRepository') -> None:
        """
        Start an async metadata fetch for the given session.
        Returns immediately; fetch happens in background thread.
        """
        if session.metadata.is_metadata_fetched:
            return
        
        with self._lock:
            if session.id in self._pending_fetches:
                return  # Already fetching
            self._pending_fetches.add(session.id)
        
        # Start background thread for the fetch
        thread = threading.Thread(
            target=self._do_fetch,
            args=(session, repository),
            daemon=True
        )
        thread.start()
    
    def _do_fetch(self, session: Session, repository: 'IRepository') -> None:
        """Perform the actual metadata fetch in background thread."""
        try:
            self._fetch_metadata(session)
            repository.save_session(session)
            
            # Notify callbacks
            for callback in self._on_complete_callbacks:
                try:
                    callback(session.id)
                except Exception as e:
                    print(f"Error in metadata fetch callback: {e}")
        except Exception as e:
            print(f"Error fetching metadata for {session.id}: {e}")
        finally:
            with self._lock:
                self._pending_fetches.discard(session.id)
    
    def _fetch_metadata(self, session: Session) -> None:
        """
        Fetch metadata from TMDB for the session.
        This is the core fetch logic, now running in a background thread.
        """
        print(f"DEBUG AsyncMetadataFetcher: Starting fetch for '{session.metadata.clean_title}'")
        
        provider = get_metadata_provider()
        if not provider.is_configured:
            print("DEBUG AsyncMetadataFetcher: TMDB API key not configured. Skipping.")
            session.metadata.is_metadata_fetched = True
            return
        
        # Use guessit to get year and media type hints
        year = None
        media_type = None
        
        if guessit:
            try:
                guessed = guessit(session.filepath)
                year = guessed.get('year')
                if guessed.get('type') == 'episode' or 'season' in guessed or 'episode' in guessed:
                    media_type = 'tv'
                else:
                    media_type = 'movie'
                print(f"DEBUG AsyncMetadataFetcher: Guessit result - year={year}, media_type={media_type}")
            except Exception as e:
                print(f"Guessit error during metadata fetch: {e}")
        
        try:
            print(f"DEBUG AsyncMetadataFetcher: Calling provider.search('{session.metadata.clean_title}')")
            info = provider.search(
                title=session.metadata.clean_title,
                year=year,
                media_type=media_type
            )
            
            if info:
                print(f"DEBUG AsyncMetadataFetcher: Got result - {info.title}, poster={info.poster_path}")
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
                print(f"DEBUG AsyncMetadataFetcher: Updated metadata - poster_path={session.metadata.poster_path}")
            else:
                session.metadata.is_metadata_fetched = True
                print(f"DEBUG AsyncMetadataFetcher: No TMDB results for: {session.metadata.clean_title}")
        except Exception as e:
            print(f"DEBUG AsyncMetadataFetcher: Error - {e}")
            session.metadata.is_metadata_fetched = True


# Global async fetcher instance
_async_fetcher: Optional[AsyncMetadataFetcher] = None


def get_async_fetcher() -> AsyncMetadataFetcher:
    """Get the singleton async metadata fetcher."""
    global _async_fetcher
    if _async_fetcher is None:
        _async_fetcher = AsyncMetadataFetcher()
    return _async_fetcher

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
        # Get the async metadata fetcher
        self._async_fetcher = get_async_fetcher()

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
        
        # Save the session first so it appears in the UI immediately
        self.repository.save_session(new_session)
        self.sessions[session_id] = new_session
        self._filepath_index[filepath] = session_id
        
        # Start async TMDB metadata fetch (non-blocking)
        self._async_fetcher.fetch_async(new_session, self.repository)
        
        return new_session

    def is_metadata_fetching(self, session_id: str) -> bool:
        """
        Check if metadata is currently being fetched for a session.
        Useful for showing loading indicators in the UI.
        """
        return self._async_fetcher.is_fetching(session_id)

    def refresh_metadata(self, session: Session) -> Session:
        """
        Force refresh metadata from TMDB, even if already fetched.
        Starts an async fetch and returns immediately.
        """
        # Clear the fetched flag to allow re-fetch
        session.metadata.is_metadata_fetched = False
        self.repository.save_session(session)
        
        # Start async fetch
        self._async_fetcher.fetch_async(session, self.repository)
        return session
    
    def refresh_metadata_sync(self, session: Session) -> Session:
        """
        Force refresh metadata from TMDB synchronously.
        Blocks until the fetch completes. Use for cases where
        you need the metadata immediately.
        """
        session.metadata.is_metadata_fetched = False
        self._async_fetcher._fetch_metadata(session)
        self.repository.save_session(session)
        return session

    def fetch_metadata_by_id(self, session: Session, tmdb_id: int, media_type: str = "movie") -> tuple[Session, bool, str]:
        """
        Fetch metadata from TMDB using a specific TMDB ID.
        This allows manual override when auto-search fails.
        
        Returns:
            Tuple of (session, success, message)
        """
        print(f"DEBUG fetch_metadata_by_id: Fetching {media_type}/{tmdb_id}")
        
        provider = get_metadata_provider()
        if not provider.is_configured:
            return session, False, "TMDB API key not configured"
        
        try:
            # Directly fetch details by ID
            details, error = provider._get(f"{media_type}/{tmdb_id}")
            
            if error:
                return session, False, error
            
            if details:
                title = details.get('title') or details.get('name')
                print(f"DEBUG fetch_metadata_by_id: Got result - {title}")
                
                # Get genres as names
                genres = [g.get('name') for g in details.get('genres', [])]
                
                # Extract year
                date_str = details.get('release_date') or details.get('first_air_date', '')
                year = int(date_str[:4]) if date_str and len(date_str) >= 4 else None
                
                # Get runtime
                if media_type == "movie":
                    runtime = details.get("runtime")
                else:
                    runtimes = details.get("episode_run_time", [])
                    runtime = runtimes[0] if runtimes else None
                
                # Update metadata
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
            print(f"DEBUG fetch_metadata_by_id: Error - {e}")
            return session, False, f"Error: {str(e)}"

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

        # Check if episode should be considered finished (either by flag or by threshold)
        completion = 0.0
        if session.playback.duration > 0:
            completion = session.playback.position / session.playback.duration
        
        episode_finished = session.playback.is_finished or (completion > EPISODE_COMPLETION_THRESHOLD)
        
        if episode_finished:
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

    # === Subtitle Support ===
    
    def search_subtitles(self, session: Session) -> List['SubtitleInfo']:
        """Search for subtitles for the current file."""
        from core.providers.subtitle_provider import get_subtitle_provider, SubtitleInfo
        
        provider = get_subtitle_provider()
        if not provider.is_configured:
            return []
            
        # Determine actual file path (helper for series)
        filepath = session.filepath
        series_files = self.get_series_files(session)
        if series_files and session.playback.last_played_index < len(series_files):
            filepath = series_files[session.playback.last_played_index]
            
        if not os.path.exists(filepath):
            return []
            
        return provider.search(filepath)

    def download_subtitle(self, session: Session, subtitle_id: str) -> Tuple[bool, str]:
        """
        Download a subtitle and save it into a .subs folder next to the media file.
        Returns: (Success, Message)
        """
        from core.providers.subtitle_provider import get_subtitle_provider
        import requests
        
        provider = get_subtitle_provider()
        if not provider.is_configured:
            return False, "Provider not configured"
            
        # Get download link
        data = provider.download(subtitle_id)
        if not data or 'link' not in data:
            return False, "Failed to get download link"
            
        download_url = data['link']
        
        # Determine target path
        filepath = session.filepath
        series_files = self.get_series_files(session)
        if series_files and session.playback.last_played_index < len(series_files):
            filepath = series_files[session.playback.last_played_index]
            
        media_dir = os.path.dirname(filepath)
        media_name = os.path.splitext(os.path.basename(filepath))[0]
        
        # Create .subs directory if it doesn't exist
        subs_dir = os.path.join(media_dir, ".subs")
        os.makedirs(subs_dir, exist_ok=True)
        
        # Save as .subs/[media_name].srt
        target_path = os.path.join(subs_dir, f"{media_name}.srt")
        
        try:
            print(f"Downloading subtitle to {target_path}...")
            r = requests.get(download_url)
            r.raise_for_status()
            
            with open(target_path, 'wb') as f:
                f.write(r.content)
                
            return True, f"Downloaded to .subs/{os.path.basename(target_path)}"
        except Exception as e:
            return False, f"Download failed: {str(e)}"

    def sync_subtitles(self, session: Session) -> Tuple[bool, str]:
        """
        Run ffsubsync on the current file's subtitle.
        """
        import shutil
        import subprocess
        
        # Check if ffsubsync is installed
        if not shutil.which("ffsubsync"):
            return False, "ffsubsync not found. Please install it: 'pip install ffsubsync'"
            
        # Determine target path
        filepath = session.filepath
        series_files = self.get_series_files(session)
        
        # If it's a folder/series, we might want to sync ALL files?
        # For now, let's sync the CURRENT file to be safe and fast.
        # User request said "use it on every file in folder", so let's try to loop if it's a series.
        
        files_to_sync = []
        if series_files:
            files_to_sync = series_files
        else:
            files_to_sync = [filepath]
            
        success_count = 0
        error_count = 0
        
        for video_path in files_to_sync:
            media_dir = os.path.dirname(video_path)
            media_name = os.path.splitext(os.path.basename(video_path))[0]
            subs_dir = os.path.join(media_dir, ".subs")
            sub_path = os.path.join(subs_dir, f"{media_name}.srt")
            
            if not os.path.exists(sub_path):
                continue
                
            try:
                print(f"Syncing subtitle for {video_path}...")
                # ffsubsync [video] -i [sub] -o [sub]
                cmd = ["ffsubsync", video_path, "-i", sub_path, "-o", sub_path]
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                success_count += 1
            except subprocess.CalledProcessError as e:
                print(f"Error syncing {media_name}: {e}")
                error_count += 1
            except Exception as e:
                print(f"Unexpected error syncing {media_name}: {e}")
                error_count += 1
                
        if success_count == 0 and error_count == 0:
            return False, "No subtitles found to sync"
        elif error_count > 0:
            return True, f"Synced {success_count} files, {error_count} failed"
        else:
            return True, f"Successfully synced {success_count} subtitles"

