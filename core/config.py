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

# Streak level thresholds (minutes watched -> level 0-4)
# Used for heatmap intensity in the stats page
STREAK_LEVEL_THRESHOLDS = {
    0: 0,      # No watch
    1: 1,      # 1-29 minutes
    2: 30,     # 30-59 minutes
    3: 60,     # 60-119 minutes (1-2 hours)
    4: 120,    # 120+ minutes (2+ hours)
}

# Number of items to show in "Most Watched" list
MOST_WATCHED_LIMIT = 10

# Number of items to show in watch history
WATCH_HISTORY_LIMIT = 50
