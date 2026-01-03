from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List


@dataclass
class WatchEvent:
    """Records a single viewing session for statistics tracking."""
    id: Optional[int] = None
    session_id: str = ""
    started_at: datetime = field(default_factory=datetime.now)
    ended_at: datetime = field(default_factory=datetime.now)
    position_start: float = 0.0
    position_end: float = 0.0
    episode_index: int = 0


@dataclass
class PlaybackState:
    """Represents the dynamic playback data for a media file."""
    last_played_file: str = ""
    last_played_index: int = 0
    position: float = 0.0  # Current playback position in seconds
    duration: float = 0.0  # Total duration of the media in seconds
    is_finished: bool = False
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class MediaMetadata:
    """Represents the static metadata for a media file."""
    clean_title: str
    season_number: Optional[int] = None
    is_user_locked_title: bool = False  # If true, title won't be auto-guessed
    genres: List[str] = field(default_factory=list)
    rating: Optional[float] = None
    description: Optional[str] = None
    poster_path: Optional[str] = None
    # Extended metadata from TMDB
    year: Optional[int] = None
    tmdb_id: Optional[int] = None
    backdrop_path: Optional[str] = None
    vote_average: Optional[float] = None
    vote_count: Optional[int] = None
    runtime_minutes: Optional[int] = None
    is_metadata_fetched: bool = False


@dataclass
class Session:
    """Aggregates playback state and media metadata for a specific media item."""
    id: str
    filepath: str
    metadata: MediaMetadata
    playback: PlaybackState = field(default_factory=PlaybackState)
    archived: bool = False
