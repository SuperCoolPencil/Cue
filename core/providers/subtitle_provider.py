
import os
import struct
import os
import struct
import hashlib
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
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
    def download(self, subtitle_id: str) -> Optional[str]:
        """Get the download details (url) for a subtitle."""
        pass

class OpenSubtitlesProvider(ISubtitleProvider):
    """OpenSubtitles.com API implementation."""
    
    def __init__(self):
        self.api_key = OPENSUBTITLES_API_KEY
        self.base_url = OPENSUBTITLES_BASE_URL
        self.user_agent = OPENSUBTITLES_USER_AGENT
        
    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def calculate_hash(self, filepath: str) -> str:
        """
        Calculate OpenSubtitles moviehash.
        Based on: https://trac.opensubtitles.org/projects/opensubtitles/wiki/HashSourceCodes
        """
        try:
            longlongformat = '<q'  # little-endian long long
            bytesize = struct.calcsize(longlongformat)
            
            with open(filepath, "rb") as f:
                filesize = os.path.getsize(filepath)
                hash_value = filesize
                
                if filesize < 65536 * 2:
                    return ""
                
                # Read first 64k
                for x in range(65536 // bytesize):
                    buffer = f.read(bytesize)
                    (l_value,) = struct.unpack(longlongformat, buffer)
                    hash_value += l_value
                    hash_value = hash_value & 0xFFFFFFFFFFFFFFFF
                
                # Read last 64k
                f.seek(max(0, filesize - 65536), 0)
                for x in range(65536 // bytesize):
                    buffer = f.read(bytesize)
                    (l_value,) = struct.unpack(longlongformat, buffer)
                    hash_value += l_value
                    hash_value = hash_value & 0xFFFFFFFFFFFFFFFF
                    
            return "%016x" % hash_value
        except Exception as e:
            print(f"Error calculating hash for {filepath}: {e}")
            return ""

    def search(self, filepath: str, language: str = "en") -> List[SubtitleInfo]:
        if not self.is_configured:
            print("OpenSubtitles API key not configured")
            return []
            
        moviehash = self.calculate_hash(filepath)
        filename = os.path.basename(filepath)
        
        print(f"DEBUG: Searching subtitles for {filename} (Hash: {moviehash})")
        
        import requests
        headers = {
            "Api-Key": self.api_key,
            "User-Agent": self.user_agent,
            "Content-Type": "application/json"
        }
        
        params = {
            "languages": language,
            "query": filename, # Fallback if hash fails
        }
        
        if moviehash:
            params["moviehash"] = moviehash
        
        try:
            response = requests.get(
                f"{self.base_url}/subtitles",
                headers=headers,
                params=params,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            results = []
            for item in data.get("data", []):
                attrs = item.get("attributes", {})
                
                # Check if this result matched via hash
                # The API typically returns "moviehash_match": true in the response or related logs,
                # but we can infer or trust the ranking. simpler to just store what we get.
                # Actually OpenSubtitles returns "moviehash_match" boolean inside attributes usually?
                # Let's check documentation or assume false for now, but prioritize in UI if needed.
                # Just mapping fields for now.
                
                files = attrs.get("files", [])
                file_id = files[0].get("file_id") if files else item.get("id") # Prefer file_id for download
                
                results.append(SubtitleInfo(
                    id=str(file_id), # Use file_id for download endpoint usually
                    language=attrs.get("language", language),
                    format=attrs.get("format", "srt"),
                    download_count=attrs.get("download_count", 0),
                    score=attrs.get("ratings", 0.0), # Simplification
                    filename=files[0].get("file_name") if files else "Unknown",
                    is_hash_match=moviehash and attrs.get("moviehash_match", False) 
                ))
            
            # Sort: Hash match first, then download count
            results.sort(key=lambda x: (x.is_hash_match, x.download_count), reverse=True)
            return results
            
        except Exception as e:
            print(f"Error searching subtitles: {e}")
            return []

    def download(self, file_id: str) -> Optional[dict]:
        """
        Get download link. 
        Note: The /download endpoint might require a separate POST request.
        """
        if not self.is_configured:
            return None
            
        import requests
        headers = {
            "Api-Key": self.api_key,
            "User-Agent": self.user_agent,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        try:
            # Need to POST to /download to get the temporary link
            payload = {"file_id": int(file_id)}
            response = requests.post(
                f"{self.base_url}/download",
                headers=headers,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            return response.json() # Should contain "link"
        except Exception as e:
            print(f"Error requesting download link: {e}")
            return None

# Singleton
_provider_instance: Optional[OpenSubtitlesProvider] = None

def get_subtitle_provider() -> OpenSubtitlesProvider:
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = OpenSubtitlesProvider()
    return _provider_instance
