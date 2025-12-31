"""Watch statistics and analytics service for Cue."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from core.sqlite_repository import SqliteRepository
    from core.domain import Session, WatchEvent


@dataclass
class WatchStats:
    """Aggregated watch statistics."""
    total_watch_time: float  # in seconds
    most_watched: List[Tuple[str, float]]  # (title, seconds)
    watch_streak: Dict[str, int]  # date string -> minutes
    completion_rate: float  # 0.0 to 1.0
    viewing_patterns: Dict[int, float]  # hour (0-23) -> minutes
    library_size: int
    completed_count: int
    recent_history: List['WatchEvent']


class StatsService:
    """Calculates and aggregates watch statistics from the repository."""
    
    def __init__(self, repository: 'SqliteRepository'):
        self.repo = repository
    
    def get_all_stats(self) -> WatchStats:
        """Get all watch statistics in one call."""
        sessions = self.repo.load_all_sessions()
        completed = sum(1 for s in sessions.values() if s.playback.is_finished)
        
        return WatchStats(
            total_watch_time=self.repo.get_total_watch_time(),
            most_watched=self.repo.get_most_watched(limit=10),
            watch_streak=self.repo.get_streak_calendar(days=365),
            completion_rate=completed / len(sessions) if sessions else 0.0,
            viewing_patterns=self.repo.get_viewing_patterns(),
            library_size=len(sessions),
            completed_count=completed,
            recent_history=self.repo.get_watch_history(limit=50)
        )
    
    def get_streak_level(self, minutes: int) -> int:
        """
        Convert minutes watched to a streak level (0-4) for heatmap display.
        0: No activity
        1: < 30 min
        2: 30-60 min
        3: 1-2 hours
        4: > 2 hours
        """
        if minutes == 0:
            return 0
        elif minutes < 30:
            return 1
        elif minutes < 60:
            return 2
        elif minutes < 120:
            return 3
        else:
            return 4
    
    def get_current_streak(self, streak_calendar: Dict[str, int]) -> int:
        """Calculate current consecutive days streak."""
        if not streak_calendar:
            return 0
        
        today = datetime.now().date()
        streak = 0
        current_date = today
        
        while True:
            date_str = current_date.isoformat()
            if date_str in streak_calendar and streak_calendar[date_str] > 0:
                streak += 1
                current_date -= timedelta(days=1)
            else:
                # Allow one day gap (check yesterday if today not yet watched)
                if current_date == today:
                    current_date -= timedelta(days=1)
                    continue
                break
        
        return streak
    
    def format_watch_time(self, seconds: float) -> str:
        """Format seconds into human-readable duration."""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds / 60)}m"
        elif seconds < 86400:
            hours = int(seconds / 3600)
            minutes = int((seconds % 3600) / 60)
            return f"{hours}h {minutes}m"
        else:
            days = int(seconds / 86400)
            hours = int((seconds % 86400) / 3600)
            return f"{days}d {hours}h"
