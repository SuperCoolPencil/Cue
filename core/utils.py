import os
import math
import struct
import subprocess
import json
from typing import List, Optional

def calculate_file_hash(filepath: str) -> str:
    """
    Calculate 64k moviehash (used by OpenSubtitles and SubDB).
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

def get_media_duration(filepath: str) -> float:
    """
    Gets the duration of a media file in seconds using ffprobe.
    Returns 0.0 if duration cannot be determined.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe", 
                "-v", "error", 
                "-show_entries", "format=duration", 
                "-of", "default=noprint_wrappers=1:nokey=1", 
                filepath
            ],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            val = result.stdout.strip()
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
