import threading
from typing import Optional, List, Set, Callable
from core.domain import Session
from core.interfaces import IRepository
from core.providers.metadata_provider import get_metadata_provider

# Try to import guessit, but make it optional
try:
    from guessit import guessit
except ImportError:
    guessit = None
    print("Warning: 'guessit' library not found. Title guessing will be disabled.")

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
