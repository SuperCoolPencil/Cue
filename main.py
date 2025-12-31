import os
import sys
import tkinter as tk
from tkinter import filedialog
from pathlib import Path
from typing import Optional, Dict
import platform
import subprocess

import streamlit as st

# Third-party imports
try:
    from guessit import guessit
except ImportError:
    st.error("Library 'guessit' not found. Please run: pip install guessit")
    st.stop()

# Local application imports
from core.services import LibraryService
from core.sqlite_repository import SqliteRepository
from core.drivers.mpv_driver import MpvDriver
from core.drivers.vlc_driver import VlcDriver
from core.drivers.ipc_driver import PlayerDriver
from core.settings import load_settings, save_settings, SESSIONS_PATH, DATABASE_PATH
from core.utils import format_seconds_to_human_readable
from core.stats import StatsService

# === CONSTANTS & CONFIGURATION ===
PAGE_TITLE = "Cue"
PAGE_ICON = "⏯️"
DRIVER_DEFAULTS = {
    "mpv_native": "mpv",
    "ipc": "celluloid",
    "vlc_rc": "vlc"
}

# === INITIALIZATION ===
def load_css(file_name=os.path.join(os.path.abspath(os.path.dirname(__file__)), "styles.css")):
    with open(file_name) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

st.set_page_config(
    page_title=PAGE_TITLE, 
    page_icon=PAGE_ICON, 
    layout="centered", 
    initial_sidebar_state="expanded"
)

load_css()

# === HELPER FUNCTIONS ===
def open_file_dialog(select_folder: bool = False) -> Optional[str]:
    """Opens a system-native file or folder selection dialog."""
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        root.lift()
        root.update_idletasks()
        path = filedialog.askdirectory() if select_folder else filedialog.askopenfilename()
        root.destroy()
        return path if path else None
    except Exception:
        return None

def open_in_file_manager(path: str):
    """
    Opens the file manager at the specified path.
    If path is a file, it highlights the file.
    If path is a directory, it opens the directory.
    """
    path = os.path.abspath(path)
    system = platform.system()

    try:
        if system == "Windows":
            path = os.path.normpath(path)
            if os.path.isfile(path):
                subprocess.run(['explorer', '/select,', path])
            else:
                subprocess.run(['explorer', path])
        elif system == "Darwin":  # macOS
            if os.path.isfile(path):
                subprocess.run(['open', '-R', path])
            else:
                subprocess.run(['open', path])
        else:  # Linux
            # xdg-open usually opens the directory containing the file
            dir_path = os.path.dirname(path) if os.path.isfile(path) else path
            subprocess.run(['xdg-open', dir_path])
    except Exception as e:
        st.error(f"Could not open file manager: {e}")

def open_file_in_default_app(path: str):
    """Opens the file in the system's default application for that file type."""
    try:
        path = os.path.abspath(path)
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":  # macOS
            subprocess.run(['open', path])
        else:  # Linux
            subprocess.run(['xdg-open', path])
    except Exception as e:
        st.error(f"Error opening file: {e}")

def get_library_service(settings: Dict) -> LibraryService:
    """Configures and returns the LibraryService based on current settings."""
    repository = SqliteRepository(DATABASE_PATH)
    
    player_type = settings.get('player_type', 'mpv_native')
    player_executable = settings.get('player_executable', 'mpv')

    if player_type == 'vlc_rc':
        player_driver = VlcDriver()
    elif player_type == 'ipc':
        player_driver = PlayerDriver(player_executable)
    else:
        player_driver = MpvDriver(player_executable)
    
    return LibraryService(repository, player_driver)

def save_title_and_exit_edit_mode(session_id: str, k_id: int, library_service: LibraryService):
    """Persists metadata changes to the repository and session state."""
    new_title = st.session_state.get(f"new_title_{k_id}")
    new_season = st.session_state.get(f"new_season_{k_id}")
    
    session = st.session_state.sessions[session_id]
    path = session.filepath

    # Update backend
    library_service.update_session_metadata(path, clean_title=new_title, season_number=new_season, is_user_locked_title=True)
    
    # Update local state
    session.metadata.clean_title = new_title
    session.metadata.season_number = new_season

# === COMPONENT RENDERERS ===
def render_sidebar(settings: Dict):
    with st.sidebar:
        # Page Navigation
        if 'current_page' not in st.session_state:
            st.session_state.current_page = 'library'
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Library", use_container_width=True, 
                        type="primary" if st.session_state.current_page == 'library' else "secondary"):
                st.session_state.current_page = 'library'
                st.rerun()
        with col2:
            if st.button("Stats", use_container_width=True,
                        type="primary" if st.session_state.current_page == 'stats' else "secondary"):
                st.session_state.current_page = 'stats'
                st.rerun()
        
        st.markdown("---")
        
        # File Operations
        if st.button("Open Folder", use_container_width=True):
            if p := open_file_dialog(select_folder=True):
                st.session_state['pending_play'] = p
                st.session_state.current_page = 'library'
                st.rerun()
                
        if st.button("Open File", use_container_width=True):
            if p := open_file_dialog(select_folder=False):
                st.session_state['pending_play'] = p
                st.session_state.current_page = 'library'
                st.rerun()
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Settings
        with st.expander("Preferences"):
            # Initialize session state defaults for settings
            if 'w_exe' not in st.session_state: 
                st.session_state.w_exe = settings.get('player_executable', 'mpv')
            
            if 'w_mode' not in st.session_state:
                saved_type = settings.get('player_type', 'mpv_native')
                st.session_state.w_mode = 'ipc' if saved_type == 'celluloid_ipc' else saved_type

            def update_driver_path():
                new_mode = st.session_state.w_mode
                st.session_state.w_exe = DRIVER_DEFAULTS.get(new_mode, "")

            st.radio("Driver", ["mpv_native", "ipc", "vlc_rc"], key="w_mode", on_change=update_driver_path)
            st.text_input("Path", key="w_exe")
            
            if st.button("Save", use_container_width=True):
                settings['player_executable'] = st.session_state.w_exe
                settings['player_type'] = st.session_state.w_mode
                save_settings(settings)
                st.rerun()
                
        if st.button("Quit", type="secondary", use_container_width=True): 
            os._exit(0)

def render_card(session_id: str, session, library_service: LibraryService):
    """Renders a single media card with playback info and controls."""
    path = session.filepath
    display_name = session.metadata.clean_title
    pos, dur = session.playback.position, session.playback.duration
    
    is_folder = os.path.isdir(path)
    is_done = (pos / dur > 0.95) if dur else False
    k_id = hash(session_id)
    
    # Badge Generation
    badges = []
    badges.append(f'<span class="badge b-folder">{"SERIES" if is_folder else "MOVIE"}</span>')
    
    current_season = session.metadata.season_number
    if isinstance(current_season, list):
        current_season = current_season[0] if current_season else None
    if current_season:
        badges.append(f'<span class="badge b-season">SEASON {current_season:02d}</span>')

    if is_folder:
        series_files = library_service.get_series_files(session)
        if series_files:
            curr = session.playback.last_played_index + 1
            total = len(series_files)
            badges.append(f'<span class="badge b-accent">EP {curr}/{total}</span>')
    
    if is_done: 
        badges.append('<span class="badge b-success">✓ COMPLETED</span>')

    # Card Layout
    with st.container():
        col_info, col_actions = st.columns([0.72, 0.28], gap="small")
        
        # === INFORMATION COLUMN ===
        with col_info:
            html_info = f"""<div class="cue-card">
<div class="card-title">{display_name}</div>
<div class="badge-container">{"".join(badges)}</div>
<div class="stats-row">
<span>{format_seconds_to_human_readable(pos)} / {format_seconds_to_human_readable(dur)}</span>
<span class="time-remaining">{'Finished' if is_done else f"{format_seconds_to_human_readable(dur - pos)} left in episode"}</span>
</div>
</div>"""
            st.markdown(html_info, unsafe_allow_html=True)
        
        # === ACTIONS COLUMN ===
        with col_actions:
            st.write("") # Spacer for vertical alignment
            
            # 1. Primary Action: Intelligent Resume
            resume_action = library_service.get_resume_action(session)
            
            if resume_action == "restart_or_next":
                # Show next episode if available, otherwise restart option
                if is_folder and library_service.has_next_episode(session):
                    next_info = library_service.get_next_episode_info(session)
                    if next_info:
                        play_label = f"▶ Next: EP {next_info[0] + 1}"
                else:
                    play_label = "↺ Restart"
            elif resume_action == "show_recap":
                play_label = "▶ Resume (1w+ ago)"
            else:
                play_label = "↺ Replay" if is_done else "▶ Resume"
            
            if st.button(play_label, key=f"play_{k_id}", use_container_width=True):
                st.session_state['resume_data'] = path
                st.rerun()

            # 2. Secondary Actions Row (Folder | Edit | Delete)
            c_folder, c_edit, c_del = st.columns([1, 1, 1], gap="small")
            
            # A. Open Folder
            with c_folder:
                if st.button("📂", key=f"open_{k_id}", help="Show in File Manager", use_container_width=True):
                    open_in_file_manager(path)

            # B. Edit Metadata
            with c_edit:
                with st.popover("✎", use_container_width=True):
                    st.markdown("##### Edit Metadata")
                    st.text_input("Title", value=display_name, key=f"new_title_{k_id}", label_visibility="collapsed", placeholder="Enter new title")
                    st.number_input(
                        "Season Number", 
                        min_value=1, 
                        value=current_season if current_season is not None else 1, 
                        key=f"new_season_{k_id}", 
                        label_visibility="collapsed"
                    )
                    if st.button("Save", key=f"save_title_{k_id}", use_container_width=True):
                        save_title_and_exit_edit_mode(session_id, k_id, library_service)
                        st.rerun()

            # C. Delete
            with c_del:
                if st.session_state.get('confirm_del') == session_id:
                    if st.button("✓", key=f"y_{k_id}", use_container_width=True, help="Confirm Delete"):
                        library_service.repository.delete_session(session_id)
                        del st.session_state.sessions[session_id]
                        del st.session_state['confirm_del']
                        st.rerun()
                else:
                    if st.button("✕", key=f"del_{k_id}", use_container_width=True, help="Remove from Library"):
                        st.session_state['confirm_del'] = session_id
                        st.rerun()

    st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)


def render_stats_page(library_service: LibraryService):
    """Renders the statistics dashboard page."""
    st.markdown('<div class="main-header">Stats.</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Your viewing analytics and watch history</div>', unsafe_allow_html=True)
    
    stats_service = StatsService(library_service.repository)
    stats = stats_service.get_all_stats()
    
    # === Summary Metrics as Cards ===
    watch_time_str = stats_service.format_watch_time(stats.total_watch_time)
    completion_pct = f"{stats.completion_rate * 100:.0f}%"
    
    metrics_html = f'''<div class="stats-grid">
<div class="stat-card">
<div class="stat-value">{stats.library_size}</div>
<div class="stat-label">Library Items</div>
</div>
<div class="stat-card">
<div class="stat-value">{stats.completed_count}</div>
<div class="stat-label">Completed</div>
</div>
<div class="stat-card">
<div class="stat-value">{completion_pct}</div>
<div class="stat-label">Completion Rate</div>
</div>
<div class="stat-card">
<div class="stat-value">{watch_time_str if watch_time_str else "0s"}</div>
<div class="stat-label">Watch Time</div>
</div>
</div>'''
    st.markdown(metrics_html, unsafe_allow_html=True)
    
    st.markdown("<div style='height: 2rem'></div>", unsafe_allow_html=True)
    
    # === Watch Streak Calendar ===
    streak_header = '<div class="section-header">Activity</div>'
    st.markdown(streak_header, unsafe_allow_html=True)
    
    from datetime import datetime, timedelta
    
    current_streak = stats_service.get_current_streak(stats.watch_streak) if stats.watch_streak else 0
    
    today = datetime.now().date()
    start_date = today - timedelta(days=364)
    
    # Build week-based grid (GitHub style)
    calendar_html = f'''<div class="streak-container">
<div class="streak-info">
<span class="streak-count">{current_streak}</span>
<span class="streak-label">day streak</span>
</div>
<div class="streak-calendar">'''
    
    current_date = start_date
    while current_date.weekday() != 6:
        current_date -= timedelta(days=1)
    
    for week in range(53):
        calendar_html += '<div class="streak-week">'
        for day in range(7):
            date_str = current_date.isoformat()
            minutes = stats.watch_streak.get(date_str, 0) if stats.watch_streak else 0
            level = stats_service.get_streak_level(minutes)
            tooltip = f"{date_str}: {minutes}m" if minutes else date_str
            calendar_html += f'<div class="streak-day level-{level}" title="{tooltip}"></div>'
            current_date += timedelta(days=1)
        calendar_html += '</div>'
    
    calendar_html += '</div></div>'
    st.markdown(calendar_html, unsafe_allow_html=True)
    
    st.markdown("<div style='height: 2rem'></div>", unsafe_allow_html=True)
    
    # === Two Column Layout ===
    col_left, col_right = st.columns(2, gap="medium")
    
    # === Most Watched ===
    with col_left:
        st.markdown('<div class="section-header">Most Watched</div>', unsafe_allow_html=True)
        
        if stats.most_watched and any(t[1] > 0 for t in stats.most_watched):
            max_time = max(t[1] for t in stats.most_watched) if stats.most_watched else 1
            
            rankings_html = '<div class="rankings-list">'
            for i, (title, watch_time) in enumerate(stats.most_watched[:5], 1):
                if watch_time <= 0:
                    continue
                progress_pct = (watch_time / max_time * 100) if max_time > 0 else 0
                time_str = stats_service.format_watch_time(watch_time)
                rankings_html += f'''<div class="ranking-item">
<div class="ranking-header">
<span class="ranking-position">{i}</span>
<span class="ranking-title">{title}</span>
<span class="ranking-time">{time_str}</span>
</div>
<div class="ranking-bar-bg">
<div class="ranking-bar" style="width: {progress_pct}%"></div>
</div>
</div>'''
            rankings_html += '</div>'
            st.markdown(rankings_html, unsafe_allow_html=True)
        else:
            st.markdown('<div class="empty-state">No watch data recorded yet</div>', unsafe_allow_html=True)
    
    # === Viewing Patterns ===
    with col_right:
        st.markdown('<div class="section-header">Viewing Patterns</div>', unsafe_allow_html=True)
        
        if stats.viewing_patterns and any(v > 0 for v in stats.viewing_patterns.values()):
            max_minutes = max(stats.viewing_patterns.values())
            
            pattern_html = '<div class="patterns-container"><div class="viewing-patterns">'
            for hour in range(24):
                minutes = stats.viewing_patterns.get(hour, 0)
                height_pct = (minutes / max_minutes * 100) if max_minutes > 0 else 0
                time_label = f"{hour:02d}:00"
                pattern_html += f'''<div class="pattern-bar-container" title="{time_label}: {int(minutes)}m">
<div class="pattern-bar" style="height: {height_pct}%"></div>
</div>'''
            pattern_html += '</div>'
            pattern_html += '<div class="pattern-labels"><span>12am</span><span>6am</span><span>12pm</span><span>6pm</span><span>12am</span></div>'
            pattern_html += '</div>'
            st.markdown(pattern_html, unsafe_allow_html=True)
        else:
            st.markdown('<div class="empty-state">No viewing pattern data yet</div>', unsafe_allow_html=True)

    st.markdown("<div style='height: 2rem'></div>", unsafe_allow_html=True)

    # === Recent History ===
    st.markdown('<div class="section-header">Recent History</div>', unsafe_allow_html=True)
    
    if stats.recent_history:
        history_html = '<div class="history-list">'
        sessions = library_service.get_all_sessions()
        
        # Group by date
        current_date_tracker = None
        
        for event in stats.recent_history:
            # Date header
            event_date = event.started_at.date()
            if current_date_tracker != event_date:
                date_str = "Today" if event_date == datetime.now().date() else event_date.strftime("%B %d, %Y")
                history_html += f'<div class="history-date-header">{date_str}</div>'
                current_date_tracker = event_date
            
            # Resolve title
            title = "Unknown Title"
            if event.session_id in sessions:
                title = sessions[event.session_id].metadata.clean_title
                
            duration = event.ended_at - event.started_at
            duration_str = stats_service.format_watch_time(duration.total_seconds())
            time_str = event.started_at.strftime("%I:%M %p")
            
            history_html += f'''<div class="history-item">
<div class="history-time">{time_str}</div>
<div class="history-details">
<div class="history-title">{title}</div>
<div class="history-meta">Duration: {duration_str}</div>
</div>
</div>'''
        
        history_html += '</div>'
        st.markdown(history_html, unsafe_allow_html=True)
    else:
        st.markdown('<div class="empty-state">No recent watch history</div>', unsafe_allow_html=True)

# === MAIN ENTRY POINT ===
def main():
    settings = load_settings()
    library_service = get_library_service(settings)

    # State initialization
    if 'sessions' not in st.session_state:
        st.session_state.sessions = library_service.get_all_sessions()
    
    def reload_sessions_and_rerun():
        st.session_state.sessions = library_service.get_all_sessions()
        st.rerun()

    # Handle Playback Triggers
    if 'pending_play' in st.session_state:
        library_service.launch_media(st.session_state.pop('pending_play'))
        reload_sessions_and_rerun()
        
    if 'resume_data' in st.session_state:
        library_service.launch_media(st.session_state.pop('resume_data'))
        reload_sessions_and_rerun()

    # UI Rendering
    render_sidebar(settings)
    
    # Get current page (default to library)
    current_page = st.session_state.get('current_page', 'library')
    
    if current_page == 'stats':
        render_stats_page(library_service)
    else:
        # Library Page
        st.markdown('<div class="main-header">Cue.</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="sub-header">Resume where you left off • {len(st.session_state.sessions)} items</div>', unsafe_allow_html=True)

        sessions = st.session_state.sessions
        query = st.text_input("Search", placeholder="Filter your library...", label_visibility="collapsed")
        
        items = sorted(
            [i for i in sessions.items() if query.lower() in str(i).lower()],
            key=lambda x: x[1].playback.timestamp, 
            reverse=True
        )

        if not items: 
            st.info("📚 Your library is empty. Click 'Open Folder' or 'Open File' to get started.")
        else: 
            for session_id, session in items: 
                render_card(session_id, session, library_service)

if __name__ == "__main__":
    main()
