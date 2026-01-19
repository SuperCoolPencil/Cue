"""Watch statistics and analytics service for Cue."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, TYPE_CHECKING

from core.config import DEFAULT_STREAK_THRESHOLDS

if TYPE_CHECKING:
    from core.sqlite_repository import SqliteRepository
    from core.domain import Session, WatchEvent


@dataclass
class WatchStats:
    """Aggregated watch statistics."""
    total_watch_time: float  # in seconds
    most_watched: List[Tuple[str, float]]  # (title, seconds)
    watch_streak: Dict[str, int]  # date string -> minutes
    weekly_watch_time: float  # watch time in last 7 days (seconds)
    daily_average: float  # average watch time per active day (seconds)
    viewing_patterns: Dict[int, float]  # hour (0-23) -> minutes
    library_size: int
    recent_history: List['WatchEvent']


class StatsService:
    """Calculates and aggregates watch statistics from the repository."""
    
    def __init__(self, repository: 'SqliteRepository'):
        self.repo = repository
        self._streak_thresholds = None  # Cached dynamic thresholds
    
    def _calculate_dynamic_thresholds(self, watch_streak: Dict[str, int]) -> List[int]:
        """
        Calculate streak level thresholds dynamically based on user's watch history.
        Uses percentiles (25th, 50th, 75th, 90th) of non-zero daily watch times.
        Returns [0, p25, p50, p75, p90] for levels 0-4.
        """
        # Get all non-zero daily watch times
        daily_minutes = [v for v in watch_streak.values() if v > 0]
        
        if len(daily_minutes) < 5:
            # Not enough data, use defaults
            return DEFAULT_STREAK_THRESHOLDS
        
        # Sort for percentile calculation
        daily_minutes.sort()
        n = len(daily_minutes)
        
        def percentile(p):
            idx = int(n * p / 100)
            return daily_minutes[min(idx, n - 1)]
        
        return [
            0,                    # Level 0: no watch
            max(1, percentile(25)),   # Level 1: bottom quartile
            percentile(50),       # Level 2: median
            percentile(75),       # Level 3: upper quartile  
            percentile(90),       # Level 4: top 10%
        ]
    
    def get_all_stats(self) -> WatchStats:
        """Get all watch statistics in one call."""
        sessions = self.repo.load_all_sessions()
        watch_streak = self.repo.get_streak_calendar(days=365)
        
        # Calculate dynamic thresholds from watch history
        self._streak_thresholds = self._calculate_dynamic_thresholds(watch_streak)
        
        # Calculate weekly watch time (last 7 days)
        today = datetime.now().date()
        weekly_minutes = 0
        for i in range(7):
            date_str = (today - timedelta(days=i)).isoformat()
            weekly_minutes += watch_streak.get(date_str, 0)
        weekly_watch_time = weekly_minutes * 60  # Convert to seconds
        
        # Calculate daily average (only counting days with activity)
        active_days = [v for v in watch_streak.values() if v > 0]
        daily_avg_minutes = sum(active_days) / len(active_days) if active_days else 0
        daily_average = daily_avg_minutes * 60  # Convert to seconds
        
        return WatchStats(
            total_watch_time=self.repo.get_total_watch_time(),
            most_watched=self.repo.get_most_watched(limit=10),
            watch_streak=watch_streak,
            weekly_watch_time=weekly_watch_time,
            daily_average=daily_average,
            viewing_patterns=self.repo.get_viewing_patterns(),
            library_size=len(sessions),
            recent_history=self.repo.get_watch_history(limit=50)
        )
    
    def get_streak_level(self, minutes: int) -> int:
        """
        Convert minutes watched to a streak level (0-4) for heatmap display.
        Uses dynamically calculated thresholds based on user's watch history.
        """
        thresholds = self._streak_thresholds or DEFAULT_STREAK_THRESHOLDS
        
        if minutes == 0:
            return 0
        elif minutes < thresholds[2]:
            return 1
        elif minutes < thresholds[3]:
            return 2
        elif minutes < thresholds[4]:
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
