"""Migration utility from JSON to SQLite for Cue."""
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

from core.database import Database
from core.domain import Session, MediaMetadata, PlaybackState


def migrate_json_to_sqlite(json_path: Path, db_path: Path) -> bool:
    """
    Migrates existing sessions.json data to SQLite database.
    
    Returns:
        True if migration occurred, False if skipped (no JSON or already migrated)
    """
    if not json_path.exists():
        print(f"No JSON file found at {json_path}, skipping migration.")
        return False
    
    # Initialize database
    db = Database(db_path)
    
    # Check if database already has data
    with db.connection() as conn:
        count = conn.execute("SELECT COUNT(*) as c FROM sessions").fetchone()['c']
        if count > 0:
            print(f"Database already has {count} sessions, skipping migration.")
            return False
    
    # Load JSON data
    print(f"Loading data from {json_path}...")
    with open(json_path, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)
    
    if not raw_data:
        print("JSON file is empty, skipping migration.")
        return False
    
    print(f"Migrating {len(raw_data)} sessions to SQLite...")
    
    with db.connection() as conn:
        for filepath, data in raw_data.items():
            # Extract metadata
            metadata = data.get('metadata', {})
            clean_title = metadata.get('clean_title', Path(filepath).name)
            season_number = metadata.get('season_number')
            is_user_locked = metadata.get('is_user_locked_title', False)
            
            # Extract playback
            playback = data.get('playback', {})
            last_played_file = playback.get('last_played_file', '')
            last_played_index = playback.get('last_played_index', 0)
            position = float(playback.get('position', 0))
            duration = float(playback.get('duration', 0))
            is_finished = playback.get('is_finished', False)
            timestamp = playback.get('timestamp', datetime.now().isoformat())
            
            # Insert session
            conn.execute("""
                INSERT INTO sessions 
                (filepath, clean_title, season_number, is_user_locked_title, genres, rating, description, poster_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (filepath, clean_title, season_number, int(is_user_locked), '[]', None, None, None))
            
            # Insert playback
            conn.execute("""
                INSERT INTO playback 
                (filepath, last_played_file, last_played_index, position, duration, is_finished, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (filepath, last_played_file, last_played_index, position, duration, int(is_finished), timestamp))
    
    # Backup old JSON
    backup_path = json_path.with_suffix('.json.bak')
    json_path.rename(backup_path)
    print(f"Migration complete! Old JSON backed up to {backup_path}")
    
    return True


def run_migration_if_needed(json_path: Optional[Path] = None, db_path: Optional[Path] = None) -> None:
    """Run migration with default paths if not specified."""
    from core.settings import SESSIONS_PATH, DATABASE_PATH
    
    json_path = json_path or SESSIONS_PATH
    db_path = db_path or DATABASE_PATH
    
    migrate_json_to_sqlite(json_path, db_path)
