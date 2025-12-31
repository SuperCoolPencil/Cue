"""
Centralized configuration for Cue application.
All magic numbers and thresholds are defined here.
"""

# === Watch Event Configuration ===

# Minimum duration (seconds) for a watch session to be recorded
# Sessions shorter than this are considered accidental opens
MIN_WATCH_DURATION_SECONDS = 5.0

# Time window (minutes) for merging consecutive watch events
# If you resume watching the same show within this window, events are merged
WATCH_EVENT_MERGE_WINDOW_MINUTES = 5

# === Playback Thresholds ===

# Completion threshold (0.0 - 1.0)
# If position/duration exceeds this, the episode is considered "finished"
EPISODE_COMPLETION_THRESHOLD = 0.95

# Days since last watch to trigger "show recap" prompt
RECAP_SUGGESTION_DAYS = 7

# === Stats Display Configuration ===

# Number of days for streak calendar display
STREAK_CALENDAR_DAYS = 365

# Default streak level thresholds (minutes) - used when no watch data exists
# Actual thresholds are calculated dynamically based on user's watch history
DEFAULT_STREAK_THRESHOLDS = [0, 15, 30, 60, 120]  # levels 0-4

# Number of items to show in "Most Watched" list
MOST_WATCHED_LIMIT = 10

# Number of items to show in watch history
WATCH_HISTORY_LIMIT = 50

# === Metadata Configuration ===

# TMDB API settings - can be overridden via TMDB_API_KEY environment variable
import os
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()

TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "1f79ab14926c11fa2a58f30d05e4dada")
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/"
TMDB_POSTER_SIZE = "w500"
TMDB_BACKDROP_SIZE = "w1280"

# Days before re-fetching metadata (0 = never re-fetch)
METADATA_CACHE_DAYS = 30

