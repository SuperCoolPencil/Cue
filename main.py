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
from core.repository import JsonRepository
from core.drivers.mpv_driver import MpvDriver
from core.drivers.vlc_driver import VlcDriver
from core.drivers.ipc_driver import PlayerDriver
from core.settings import load_settings, save_settings
from core.utils import format_seconds_to_human_readable

# === CONSTANTS & CONFIGURATION ===
PAGE_TITLE = "Cue"
PAGE_ICON = "⏯️"
DRIVER_DEFAULTS = {
    "mpv_native": "mpv",
    "ipc": "celluloid",
    "vlc_rc": "vlc"
}

# === CSS STYLING ===
MODERN_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&display=swap');
    
    /* === GLOBAL RESET === */
    .stApp {
        background: linear-gradient(135deg, #0a0a0f 0%, #1a0a1f 50%, #0a0a0f 100%);
        background-attachment: fixed;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    footer, #MainMenu, [data-testid="stBaseButton-header"] { visibility: hidden; height: 0; width: 0; overflow: hidden; }
    
    header { background: transparent !important; color: white !important; }
    
    .block-container { padding-top: 3rem !important; padding-bottom: 4rem !important; max-width: 900px !important; }
    
    /* === HERO HEADER === */
    .main-header {
        font-size: clamp(2.5rem, 8vw, 4.5rem);
        font-weight: 900;
        letter-spacing: -0.05em;
        background: linear-gradient(135deg, #ffffff 0%, #a78bfa 50%, #ec4899 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        margin-bottom: 0.5rem;
        line-height: 1;
        animation: shimmer 8s ease-in-out infinite;
        background-size: 200% 200%;
    }
    
    @keyframes shimmer {
        0%, 100% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
    }
    
    .sub-header {
        font-size: 0.875rem;
        font-weight: 500;
        color: #71717a;
        margin-bottom: 2rem;
        padding-bottom: 1.5rem;
        border-bottom: 1px solid rgba(63, 63, 70, 0.3);
        letter-spacing: 0.05em;
    }
    
    /* === CARD DESIGN === */
    .cue-card {
        background: linear-gradient(135deg, rgba(30, 27, 75, 0.4) 0%, rgba(25, 20, 45, 0.6) 100%);
        backdrop-filter: blur(20px);
        border: 1px solid rgba(139, 92, 246, 0.2);
        border-radius: 16px;
        padding: 18px 20px;
        margin-bottom: 0px;
        box-shadow: 0 8px 32px -8px rgba(139, 92, 246, 0.3), 0 0 0 1px rgba(255, 255, 255, 0.05) inset;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative;
        overflow: hidden;
        height: 100%;
    }

    .cue-card::before {
        content: '';
        position: absolute;
        top: 0; left: -100%; width: 100%; height: 100%;
        background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.1), transparent);
        transition: none;
    }

    .cue-card:hover {
        border-color: rgba(167, 139, 250, 0.6);
        box-shadow: 0 12px 40px -12px rgba(139, 92, 246, 0.5), 0 0 0 1px rgba(255, 255, 255, 0.1) inset;
        transform: translateY(-2px) scale(1.01);
    }

    .cue-card:hover::before { animation: shimmer-hover 1.5s infinite; }

    @keyframes shimmer-hover {
        0% { left: -100%; } 50% { left: 100%; } 100% { left: -100%; }
    }
    
    .card-title {
        font-size: 1.1rem; font-weight: 700; color: #fafafa; line-height: 1.3;
        margin-bottom: 8px; display: -webkit-box; -webkit-line-clamp: 2;
        -webkit-box-orient: vertical; overflow: hidden; text-overflow: ellipsis;
    }
    
    /* === BADGES === */
    .badge-container { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 10px; align-items: center; }
    
    .badge {
        font-size: 0.6rem; padding: 4px 10px; border-radius: 6px; font-weight: 700;
        letter-spacing: 0.08em; text-transform: uppercase; font-family: 'JetBrains Mono', monospace;
        white-space: nowrap; box-shadow: 0 2px 6px -2px currentColor;
    }
    
    .b-folder { background: linear-gradient(135deg, #27272a, #18181b); color: #a1a1aa; border: 1px solid #3f3f46; }
    .b-accent { background: linear-gradient(135deg, rgba(56, 189, 248, 0.2), rgba(59, 130, 246, 0.15)); color: #60a5fa; border: 1px solid rgba(56, 189, 248, 0.3); }
    .b-season { background: linear-gradient(135deg, rgba(236, 72, 153, 0.2), rgba(219, 39, 119, 0.15)); color: #f472b6; border: 1px solid rgba(236, 72, 153, 0.3); }
    .b-success { background: linear-gradient(135deg, rgba(52, 211, 153, 0.2), rgba(16, 185, 129, 0.15)); color: #6ee7b7; border: 1px solid rgba(52, 211, 153, 0.3); }
    
    .stats-row {
        display: flex; justify-content: space-between; align-items: center;
        font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; color: #a1a1aa;
        padding-top: 10px; border-top: 1px solid rgba(63, 63, 70, 0.3);
    }
    
    .time-remaining { color: #fbbf24; font-weight: 700; text-shadow: 0 0 20px rgba(251, 191, 36, 0.3); }
    
    /* === UI COMPONENTS === */
    div.stButton > button, [data-testid="stPopoverButton"] {
        width: 100%; border-radius: 10px !important; font-size: 0.85rem !important;
        font-weight: 600 !important; border: 1px solid rgba(139, 92, 246, 0.3) !important;
        background: linear-gradient(135deg, rgba(139, 92, 246, 0.15), rgba(109, 40, 217, 0.1)) !important;
        color: #e4e4e7 !important; transition: all 0.2s ease !important; margin-top: 2px;
    }

    div.stButton > button:hover, [data-testid="stPopoverButton"]:hover {
        border-color: rgba(167, 139, 250, 0.6) !important;
        background: linear-gradient(135deg, rgba(139, 92, 246, 0.3), rgba(109, 40, 217, 0.2)) !important;
        transform: translateY(-1px); color: white !important;
        box-shadow: 0 4px 12px -2px rgba(139, 92, 246, 0.4) !important;
    }
    
    div[data-baseweb="input"] > div { margin-bottom: 0 !important; }

    .stTextInput input {
        background: rgba(24, 24, 27, 0.6) !important; backdrop-filter: blur(10px) !important;
        border: 1px solid rgba(63, 63, 70, 0.5) !important; border-radius: 12px !important;
        color: #fafafa !important; padding: 0.75rem 1rem !important; font-size: 0.9rem !important;
        line-height: 1.5 !important; vertical-align: middle !important; height: auto !important;
    }
    
    div[data-testid="stHorizontalBlock"] { align-items: center; background: transparent; }
</style>
"""

# === INITIALIZATION ===
st.set_page_config(
    page_title=PAGE_TITLE, 
    page_icon=PAGE_ICON, 
    layout="centered", 
    initial_sidebar_state="expanded"
)
st.markdown(MODERN_CSS, unsafe_allow_html=True)

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
    storage_file = Path("sessions.json")
    repository = JsonRepository(storage_file)
    
    player_type = settings.get('player_type', 'mpv_native')
    player_executable = settings.get('player_executable', 'mpv')

    if player_type == 'vlc_rc':
        player_driver = VlcDriver()
    elif player_type == 'ipc':
        player_driver = PlayerDriver(player_executable)
    else:
        player_driver = MpvDriver(player_executable)
    
    return LibraryService(repository, player_driver)

def save_title_and_exit_edit_mode(path: str, k_id: int, library_service: LibraryService):
    """Persists metadata changes to the repository and session state."""
    new_title = st.session_state.get(f"new_title_{k_id}")
    new_season = st.session_state.get(f"new_season_{k_id}")

    library_service.update_session_metadata(path, clean_title=new_title, season_number=new_season)
    st.session_state.sessions[path].metadata.clean_title = new_title
    st.session_state.sessions[path].metadata.season_number = new_season

# === COMPONENT RENDERERS ===
def render_sidebar(settings: Dict):
    with st.sidebar:
        st.markdown("### Library")
        
        # File Operations
        if st.button("📂 Open Folder", use_container_width=True):
            if p := open_file_dialog(select_folder=True):
                st.session_state['pending_play'] = p
                st.rerun()
                
        if st.button("📄 Open File", use_container_width=True):
            if p := open_file_dialog(select_folder=False):
                st.session_state['pending_play'] = p
                st.rerun()
        
        # === UPDATED BUTTON ===
        if st.button("📝 Edit Database", use_container_width=True, help="Open sessions.json in default editor"):
            db_path = "sessions.json"
            if os.path.exists(db_path):
                open_file_in_default_app(db_path)
            else:
                st.warning("Database file not found. Play a video to create it.")
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Settings
        with st.expander("⚙️ Preferences"):
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
                
        if st.button("🛑 Quit", type="secondary", use_container_width=True): 
            os._exit(0)

def render_card(path: str, session, library_service: LibraryService):
    """Renders a single media card with playback info and controls."""
    display_name = session.metadata.clean_title
    pos, dur = session.playback.position, session.playback.duration
    
    is_folder = os.path.isdir(path)
    is_done = (pos / dur > 0.95) if dur else False
    k_id = hash(path)
    
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
            html_info = f"""
            <div class="cue-card">
                <div class="card-title">{display_name}</div>
                <div class="badge-container">{"".join(badges)}</div>
                <div class="stats-row">
                    <span>{format_seconds_to_human_readable(pos)} / {format_seconds_to_human_readable(dur)}</span>
                    <span class="time-remaining">{'Finished' if is_done else f"{format_seconds_to_human_readable(dur - pos)} left in episode"}</span>
                </div>
            </div>
            """
            st.markdown(html_info, unsafe_allow_html=True)
        
        # === ACTIONS COLUMN ===
        with col_actions:
            st.write("") # Spacer for vertical alignment
            
            # 1. Primary Action: Resume/Replay
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
                        save_title_and_exit_edit_mode(path, k_id, library_service)
                        st.rerun()

            # C. Delete
            with c_del:
                if st.session_state.get('confirm_del') == path:
                    if st.button("✓", key=f"y_{k_id}", use_container_width=True, help="Confirm Delete"):
                        library_service.repository.delete_session(path)
                        del st.session_state.sessions[path]
                        del st.session_state['confirm_del']
                        st.rerun()
                else:
                    if st.button("✕", key=f"del_{k_id}", use_container_width=True, help="Remove from Library"):
                        st.session_state['confirm_del'] = path
                        st.rerun()

    st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)

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
        for path, session in items: 
            render_card(path, session, library_service)

if __name__ == "__main__":
    main()
