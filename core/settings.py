import json
from pathlib import Path
from typing import Dict, Any

DEFAULT_SETTINGS_PATH = Path("~/.cue/settings.json").expanduser()
SESSIONS_PATH = Path("~/.cue/sessions.json").expanduser()
DATABASE_PATH = Path("~/.cue/cue.db").expanduser()

def load_settings(settings_path: Path = DEFAULT_SETTINGS_PATH) -> Dict[str, Any]:
    """Loads application settings from a JSON file."""
    if not settings_path.exists():
        return {
            "player_executable": "mpv",
            "player_type": "mpv_native" # mpv_native, celluloid_ipc, vlc_rc
        }
    
    with open(settings_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_settings(settings: Dict[str, Any], settings_path: Path = DEFAULT_SETTINGS_PATH) -> None:
    """Saves application settings to a JSON file."""
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    with open(settings_path, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=4)
