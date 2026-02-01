from datetime import datetime
from typing import List, Optional
from core.domain import Session, WatchEvent
from core.interfaces import IPlayerDriver, IRepository
from core.config import (
    MIN_WATCH_DURATION_SECONDS,
    EPISODE_COMPLETION_THRESHOLD,
)

class PlaybackService:
    """
    Handles media playback launch and watch event recording.
    """
    
    def __init__(self, player_driver: IPlayerDriver, repository: IRepository):
        self.player_driver = player_driver
        self.repository = repository
        
    def launch_media(self, session: Session, series_files: List[str]) -> None:
        """
        Launches the media file using the configured player driver.
        Updates the session's playback state after playback.
        """
        if not series_files:
            print(f"No media files found for session: {session.filepath}")
            return

        last_played_index_from_session = session.playback.last_played_index
        position_from_session = session.playback.position
        
        index_to_play = last_played_index_from_session # Default to current
        start_time = position_from_session # Default to current position

        # Check if episode should be considered finished
        completion = 0.0
        if session.playback.duration > 0:
            completion = session.playback.position / session.playback.duration
        
        episode_finished = session.playback.is_finished or (completion > EPISODE_COMPLETION_THRESHOLD)
        
        if episode_finished:
            next_index = last_played_index_from_session + 1
            if next_index < len(series_files):
                # Play the next one from the beginning
                index_to_play = next_index
                start_time = 0.0
            else:
                # Entire series is complete, restart from episode 1
                print("End of series. Restarting from episode 1.")
                index_to_play = 0
                start_time = 0.0
        
        watch_start_time = datetime.now()
        
        final_playback_state_from_driver = self.player_driver.launch(
            playlist=series_files,
            start_index=index_to_play,
            start_time=start_time
        )
        
        watch_end_time = datetime.now()
        
        # Calculate actual wall clock duration
        total_wall_clock_seconds = (watch_end_time - watch_start_time).total_seconds()
        
        # Record Watch Event
        if total_wall_clock_seconds > MIN_WATCH_DURATION_SECONDS:
            self.record_watch_event(
                session_id=session.id,
                started_at=watch_start_time,
                ended_at=watch_end_time,
                position_start=start_time,
                position_end=final_playback_state_from_driver.position,
                episode_index=final_playback_state_from_driver.last_played_index
            )
            print(f"DEBUG: Watch event recorded - Wall clock: {total_wall_clock_seconds:.1f}s")
        
        # Update session playback state
        session.playback.position = final_playback_state_from_driver.position
        session.playback.duration = final_playback_state_from_driver.duration
        session.playback.is_finished = final_playback_state_from_driver.is_finished
        session.playback.timestamp = final_playback_state_from_driver.timestamp
        session.playback.last_played_file = final_playback_state_from_driver.last_played_file
        
        # Robustly find the last_played_index
        matched_index = 0
        if final_playback_state_from_driver.last_played_file:
            for i, file_in_series in enumerate(series_files):
                if (final_playback_state_from_driver.last_played_file in file_in_series) or \
                   (file_in_series in final_playback_state_from_driver.last_played_file):
                    matched_index = i
                    break
        session.playback.last_played_index = matched_index
        
        self.repository.save_session(session)

    def record_watch_event(self, session_id: str, started_at: datetime, 
                           ended_at: datetime, position_start: float, 
                           position_end: float, episode_index: int = 0) -> None:
        """
        Records a watch event for statistics tracking.
        """
        event = WatchEvent(
            session_id=session_id,
            started_at=started_at,
            ended_at=ended_at,
            position_start=position_start,
            position_end=position_end,
            episode_index=episode_index
        )
        
        if hasattr(self.repository, 'record_watch_event'):
            self.repository.record_watch_event(event)

