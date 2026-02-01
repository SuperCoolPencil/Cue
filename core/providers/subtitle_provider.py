
import os
import struct
import os
import struct
import hashlib
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from core.config import OPENSUBTITLES_API_KEY, OPENSUBTITLES_BASE_URL, OPENSUBTITLES_USER_AGENT

@dataclass
class SubtitleInfo:
    """Standardized subtitle metadata."""
    id: str
    language: str
    format: str
    download_count: int
    score: float
    filename: str
    is_hash_match: bool
    link: Optional[str] = None  # Direct download link if available

class ISubtitleProvider(ABC):
    """Abstract interface for subtitle providers."""
    
    @abstractmethod
    def search(self, filepath: str, language: str = "en") -> List[SubtitleInfo]:
        """Search for subtitles for a file."""
        pass
        
    @abstractmethod
    def download(self, subtitle_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Get the download details (url) for a subtitle. Returns (data, error_message)."""
        pass

class OpenSubtitlesProvider(ISubtitleProvider):
    """OpenSubtitles.com API implementation."""
    
    def __init__(self):
        self.api_key = OPENSUBTITLES_API_KEY
        self.base_url = OPENSUBTITLES_BASE_URL
        self.user_agent = OPENSUBTITLES_USER_AGENT
        self.token = None
        self.user_info = None
        self._load_auth()

    def _load_auth(self):
        from core.settings import load_settings
        settings = load_settings()
        auth = settings.get("opensubtitles_auth", {})
        self.token = auth.get("token")
        self.user_info = auth.get("user")

    def login(self, username, password) -> Tuple[bool, str]:
        import requests
        headers = {
            "Api-Key": self.api_key,
            "User-Agent": self.user_agent,
            "Content-Type": "application/json"
        }
        payload = {"username": username, "password": password}
        print(f"DEBUG [OpenSubtitles]: Attempting login for user: {username}")
        
        try:
            r = requests.post(f"{self.base_url}/login", json=payload, headers=headers)
            if r.status_code == 200:
                data = r.json()
                self.token = data.get("token")
                self.user_info = data.get("user")
                
                # Persist
                from core.settings import load_settings, save_settings
                settings = load_settings()
                settings["opensubtitles_auth"] = {
                    "token": self.token,
                    "user": self.user_info
                }
                save_settings(settings)
                return True, "Logged in successfully"
            else:
                return False, r.json().get("message", "Login failed")
        except Exception as e:
            return False, str(e)

    def logout(self) -> Tuple[bool, str]:
        # Clear local state
        self.token = None
        self.user_info = None
        
        # Clear persistence
        from core.settings import load_settings, save_settings
        settings = load_settings()
        if "opensubtitles_auth" in settings:
            del settings["opensubtitles_auth"]
            save_settings(settings)

        # Optional: Call API logout if needed, but local clear is enough usually
        # headers = ... requests.delete(..., headers=headers)
        return True, "Logged out"

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def calculate_hash(self, filepath: str) -> str:
        """Wrapper for shared hash calculation."""
        from core.utils import calculate_file_hash
        return calculate_file_hash(filepath)

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Api-Key": self.api_key,
            "User-Agent": self.user_agent,
            "Content-Type": "application/json"
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def search(self, filepath: str, language: str = "en") -> List[SubtitleInfo]:
        if not self.is_configured:
            print("OpenSubtitles API key not configured")
            return []
            
        moviehash = self.calculate_hash(filepath)
        filename = os.path.basename(filepath)
        
        print(f"DEBUG: Searching subtitles for {filename} (Hash: {moviehash})")
        
        import requests
        
        params = {
            "languages": language,
            "query": filename, # Fallback if hash fails
        }
        
        if moviehash:
            params["moviehash"] = moviehash
        
        try:
            print(f"DEBUG [OpenSubtitles]: Requesting subtitles with params: {params}")
            response = requests.get(
                f"{self.base_url}/subtitles",
                headers=self._get_headers(),
                params=params,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            results = []
            for item in data.get("data", []):
                attrs = item.get("attributes", {})
                files = attrs.get("files", [])
                file_id = files[0].get("file_id") if files else item.get("id")
                
                results.append(SubtitleInfo(
                    id=str(file_id),
                    language=attrs.get("language", language),
                    format=attrs.get("format", "srt"),
                    download_count=attrs.get("download_count", 0),
                    score=attrs.get("ratings", 0.0),
                    filename=files[0].get("file_name") if files else "Unknown",
                    is_hash_match=moviehash and attrs.get("moviehash_match", False) 
                ))
            
            # Sort: Hash match first, then download count
            results.sort(key=lambda x: (x.is_hash_match, x.download_count), reverse=True)
            return results
            
        except Exception as e:
            print(f"Error searching subtitles: {e}")
            return []

    def download(self, file_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Get download link. 
        """
        if not self.is_configured:
            return None, "Provider not configured"
            
        import requests
        
        try:
            print(f"DEBUG [OpenSubtitles]: Requesting download for file_id: {file_id}")
            payload = {"file_id": int(file_id)}
            response = requests.post(
                f"{self.base_url}/download",
                headers=self._get_headers(),
                json=payload,
                timeout=10
            )
            
            if response.status_code in [406, 429]:
                 data = response.json()
                 msg = data.get("message", "Quota exceeded")
                 return None, msg

            response.raise_for_status()
            return response.json(), None
        except Exception as e:
            print(f"Error requesting download link: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    err_data = e.response.json()
                    return None, err_data.get("message", str(e))
                except:
                    pass
            return None, str(e)

# Singleton
_opensubtitles_instance: Optional[OpenSubtitlesProvider] = None

def get_subtitle_provider() -> OpenSubtitlesProvider:
    global _opensubtitles_instance
    if _opensubtitles_instance is None:
        _opensubtitles_instance = OpenSubtitlesProvider()
    return _opensubtitles_instance

def get_all_providers() -> List[ISubtitleProvider]:
    """Returns all available subtitle providers."""
    # from core.providers.subdb_provider import SubDBProvider
    # SubDB is currently down/unreliable. Disabled to rely on OpenSubtitles Auth.
    return [get_subtitle_provider()]
