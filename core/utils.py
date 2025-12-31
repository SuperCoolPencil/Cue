import os
import math
import subprocess
import json
from typing import List, Optional

def get_media_duration(filepath: str) -> float:
    """
    Gets the duration of a media file in seconds using mpv.
    Returns 0.0 if duration cannot be determined.
    """
    try:
        result = subprocess.run(
            [
                "mpv", 
                "--no-terminal", 
                "--no-video", 
                "--no-audio", 
                "--output-json", 
                "--identify", 
                filepath
            ],
            capture_output=True,
            text=True
        )
        # Parse the JSON output from --identify
        # Note: mpv output can be messy. We look for lines starting with "{"
        for line in result.stdout.splitlines():
            try:
                data = json.loads(line)
                if "duration" in data:
                    return float(data["duration"])
            except json.JSONDecodeError:
                continue
                
        # Fallback: sometimes duration is in the summary or stderr, 
        # but --output-json --identify usually works.
        # Let's try a simpler property probe if the above fails or is complex parsing
        # Actually, `mpv --no-terminal --quiet --print-text --command=print-property=duration FILE` is cleaner
        
        result_prop = subprocess.run(
            [
                "mpv",
                "--no-terminal",
                "--quiet",
                "--no-video",
                "--no-audio",
                "--command=print-text ${duration}", 
                filepath
            ],
             capture_output=True,
             text=True
        )
        if result_prop.returncode == 0:
             val = result_prop.stdout.strip()
             if val:
                 return float(val)

    except Exception as e:
        print(f"Error getting duration for {filepath}: {e}")
    
    return 0.0

def get_media_files(path: str) -> List[str]:
    """
    Returns a sorted list of media files in a given directory.
    """
    media_files = []
    if os.path.isdir(path):
        for root, _, files in os.walk(path):
            for file in files:
                if file.lower().endswith(('.mkv', '.mp4', '.avi', '.mov', '.webm')):
                    media_files.append(os.path.join(root, file))
    return sorted(media_files)

def format_seconds_to_human_readable(seconds: float) -> str:
    """
    Converts a float of seconds into a human-readable string (e.g., "1h 25m 30s").
    Handles hours, minutes, and seconds, omitting units if their value is zero.
    """
    if seconds is None:
        return "N/A"
    
    seconds = math.ceil(seconds) # Round up to the nearest whole second
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    remaining_seconds = seconds % 60

    parts = []
    if hours > 0:
        parts.append(f"{int(hours)}h")
    if minutes > 0:
        parts.append(f"{int(minutes)}m")
    if remaining_seconds > 0 or (hours == 0 and minutes == 0 and minutes == 0): # Always show seconds if total time is less than a minute
        parts.append(f"{int(remaining_seconds)}s")

    return " ".join(parts)
