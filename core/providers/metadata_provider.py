"""Metadata provider interface and TMDB implementation for fetching movie/TV metadata."""
import os
import requests
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List
from functools import lru_cache


@dataclass
class MediaInfo:
    """Standardized metadata result from any provider."""
    title: str
    year: Optional[int] = None
    tmdb_id: Optional[int] = None
    media_type: str = "movie"  # "movie" or "tv"
    overview: Optional[str] = None
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    genres: List[str] = None
    vote_average: Optional[float] = None
    vote_count: Optional[int] = None
    runtime_minutes: Optional[int] = None

    def __post_init__(self):
        if self.genres is None:
            self.genres = []


class IMetadataProvider(ABC):
    """Abstract interface for metadata providers."""

    @abstractmethod
    def search(self, title: str, year: Optional[int] = None, 
               media_type: Optional[str] = None) -> Optional[MediaInfo]:
        """
        Search for movie or TV show metadata.
        
        Args:
            title: The title to search for
            year: Optional year hint for better matching
            media_type: Optional "movie" or "tv" to narrow search
            
        Returns:
            MediaInfo if found, None otherwise
        """
        pass

    @abstractmethod
    def get_poster_url(self, poster_path: str, size: str = "w500") -> str:
        """Get full URL for a poster image."""
        pass

    @abstractmethod
    def get_backdrop_url(self, backdrop_path: str, size: str = "w1280") -> str:
        """Get full URL for a backdrop image."""
        pass


class TMDBProvider(IMetadataProvider):
    """TMDB (The Movie Database) metadata provider."""
    
    BASE_URL = "https://api.themoviedb.org/3"
    IMAGE_BASE_URL = "https://image.tmdb.org/t/p/"
    
    def __init__(self, api_key: Optional[str] = None):
        # Import from config to get the key set there
        from core.config import TMDB_API_KEY as CONFIG_API_KEY
        self.api_key = api_key or CONFIG_API_KEY or os.environ.get("TMDB_API_KEY", "")
        self._genre_cache: dict = {}
        print(f"DEBUG TMDBProvider: Initialized with API key: {'[SET]' if self.api_key else '[NOT SET]'}")
    
    @property
    def is_configured(self) -> bool:
        """Check if API key is available."""
        return bool(self.api_key)
    
    def _get(self, endpoint: str, params: dict = None) -> tuple[Optional[dict], Optional[str]]:
        """Make authenticated GET request to TMDB API with retry logic.
        
        Returns:
            Tuple of (data, error_message). If successful, error is None.
        """
        if not self.is_configured:
            print("DEBUG TMDBProvider._get: API key not configured, skipping request")
            return None, "TMDB API key not configured"
        
        import time
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
                url = f"{self.BASE_URL}/{endpoint}"
                params = params or {}
                params["api_key"] = self.api_key
                
                print(f"DEBUG TMDBProvider._get: Requesting {url} (attempt {attempt + 1})")
                response = requests.get(url, params=params, timeout=15)
                print(f"DEBUG TMDBProvider._get: Response status {response.status_code}")
                
                if response.status_code == 404:
                    return None, "Not found on TMDB"
                elif response.status_code == 401:
                    return None, "Invalid TMDB API key"
                elif response.status_code == 429:
                    return None, "TMDB rate limit exceeded - try again later"
                
                response.raise_for_status()
                return response.json(), None
            except requests.exceptions.Timeout:
                last_error = "Request timed out - TMDB may be slow"
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
            except requests.exceptions.ConnectionError as e:
                last_error = "Network connection error - check your internet"
                print(f"DEBUG TMDBProvider._get: Connection error (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
            except requests.RequestException as e:
                last_error = f"API error: {str(e)}"
                print(f"TMDB API error: {e}")
                break
        
        return None, last_error or "Unknown error"
    
    @lru_cache(maxsize=1)
    def _get_genre_map(self, media_type: str) -> dict:
        """Get genre ID to name mapping (cached)."""
        endpoint = f"genre/{media_type}/list"
        data, _ = self._get(endpoint)
        if data and "genres" in data:
            return {g["id"]: g["name"] for g in data["genres"]}
        return {}
    
    def _genres_from_ids(self, genre_ids: List[int], media_type: str) -> List[str]:
        """Convert genre IDs to names."""
        genre_map = self._get_genre_map(media_type)
        return [genre_map.get(gid, f"Unknown-{gid}") for gid in genre_ids if gid in genre_map]
    
    def search(self, title: str, year: Optional[int] = None,
               media_type: Optional[str] = None) -> Optional[MediaInfo]:
        """
        Search TMDB for movie or TV show.
        
        If media_type is not specified, searches both and returns best match.
        """
        print(f"DEBUG TMDBProvider.search: Searching for '{title}', year={year}, type={media_type}")
        
        if not self.is_configured:
            print("DEBUG TMDBProvider.search: API not configured")
            return None
        
        # Determine what to search
        types_to_search = [media_type] if media_type else ["movie", "tv"]
        best_result: Optional[MediaInfo] = None
        best_score = 0
        
        for mtype in types_to_search:
            result = self._search_type(title, year, mtype)
            if result:
                # Simple scoring: prefer exact year match
                score = 1
                if year and result.year == year:
                    score += 10
                if result.vote_count:
                    score += min(result.vote_count / 1000, 5)  # Popularity boost
                    
                if score > best_score:
                    best_score = score
                    best_result = result
        
        print(f"DEBUG TMDBProvider.search: Best result = {best_result.title if best_result else 'None'}")
        return best_result
    
    def _search_type(self, title: str, year: Optional[int], 
                     media_type: str) -> Optional[MediaInfo]:
        """Search for a specific media type."""
        params = {"query": title}
        if year:
            params["year" if media_type == "movie" else "first_air_date_year"] = year
        
        data, _ = self._get(f"search/{media_type}", params)
        if not data or not data.get("results"):
            return None
        
        # Take top result
        item = data["results"][0]
        
        # Get additional details for runtime
        details, _ = self._get(f"{media_type}/{item['id']}")
        runtime = None
        if details:
            if media_type == "movie":
                runtime = details.get("runtime")
            else:
                # For TV, use average episode runtime
                runtimes = details.get("episode_run_time", [])
                runtime = runtimes[0] if runtimes else None
        
        # Extract year from release/first air date
        date_field = "release_date" if media_type == "movie" else "first_air_date"
        date_str = item.get(date_field, "")
        parsed_year = int(date_str[:4]) if date_str and len(date_str) >= 4 else None
        
        return MediaInfo(
            title=item.get("title") or item.get("name", title),
            year=parsed_year,
            tmdb_id=item.get("id"),
            media_type=media_type,
            overview=item.get("overview"),
            poster_path=item.get("poster_path"),
            backdrop_path=item.get("backdrop_path"),
            genres=self._genres_from_ids(item.get("genre_ids", []), media_type),
            vote_average=item.get("vote_average"),
            vote_count=item.get("vote_count"),
            runtime_minutes=runtime
        )
    
    def get_poster_url(self, poster_path: str, size: str = "w500") -> str:
        """Get full poster URL."""
        if not poster_path:
            return ""
        return f"{self.IMAGE_BASE_URL}{size}{poster_path}"
    
    def get_backdrop_url(self, backdrop_path: str, size: str = "w1280") -> str:
        """Get full backdrop URL."""
        if not backdrop_path:
            return ""
        return f"{self.IMAGE_BASE_URL}{size}{backdrop_path}"


# Singleton instance for easy access
_provider_instance: Optional[TMDBProvider] = None


def get_metadata_provider() -> TMDBProvider:
    """Get the singleton metadata provider instance."""
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = TMDBProvider()
    return _provider_instance
