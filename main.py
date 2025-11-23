import os
import sys
import platform
import tkinter as tk
from tkinter import filedialog
import streamlit as st
from pathlib import Path

try:
    from guessit import guessit
except ImportError:
    st.error("Library 'guessit' not found. Please run: pip install guessit")
    st.stop()

from core.services import LibraryService
from core.repository import JsonRepository
from core.drivers.mpv_driver import MpvDriver
from core.drivers.vlc_driver import VlcDriver
from core. drivers.ipc_driver import PlayerDriver
from core.settings import load_settings, save_settings

PAGE_TITLE = "Cue"
PAGE_ICON = "⏯️"

# === UPDATED CSS ===
MODERN_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&display=swap');
    
    /* === GLOBAL RESET === */
    .stApp {
        background: linear-gradient(135deg, #0a0a0f 0%, #1a0a1f 50%, #0a0a0f 100%);
        background-attachment: fixed;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    footer { visibility: hidden; height: 0; }
    #MainMenu { visibility: hidden; height: 0; } /* Hide Streamlit's main menu */
    /* Hide the deploy button */
    [data-testid="stBaseButton-header"] {
        visibility: hidden;
        height: 0;
        width: 0;
        overflow: hidden;
    }

    /* Make the Streamlit header transparent */
    header {
        background: transparent !important;
        color: white !important; /* Ensure text/icons in header are visible */
    }
    
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
    
    /* === COMPACT CARD DESIGN === */
    .cue-card {
        background: linear-gradient(135deg, rgba(30, 27, 75, 0.4) 0%, rgba(25, 20, 45, 0.6) 100%);
        backdrop-filter: blur(20px);
        border: 1px solid rgba(139, 92, 246, 0.2);
        border-radius: 16px;
        padding: 18px 20px;
        margin-bottom: 0px; /* Removed bottom margin as buttons are now adjacent */
        box-shadow: 
            0 8px 32px -8px rgba(139, 92, 246, 0.3),
            0 0 0 1px rgba(255, 255, 255, 0.05) inset;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative;
        overflow: hidden;
        height: 100%; /* Fill column height */
    }

    .cue-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: -100%;
        width: 100%;
        height: 100%;
        background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.1), transparent);
        transition: none; /* Override parent transition */
    }

    .cue-card:hover {
        border-color: rgba(167, 139, 250, 0.6);
        box-shadow: 
            0 12px 40px -12px rgba(139, 92, 246, 0.5),
            0 0 0 1px rgba(255, 255, 255, 0.1) inset;
        transform: translateY(-2px) scale(1.01);
    }

    .cue-card:hover::before {
        animation: shimmer-hover 1.5s infinite;
    }

    @keyframes shimmer-hover {
        0% { left: -100%; }
        50% { left: 100%; }
        100% { left: -100%; }
    }
    
    /* === CARD CONTENT === */
    .card-title {
        font-size: 1.1rem;
        font-weight: 700;
        color: #fafafa;
        line-height: 1.3;
        margin-bottom: 8px;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    
    /* === BADGES === */
    .badge-container {
        display: flex;
        gap: 6px;
        flex-wrap: wrap;
        margin-bottom: 10px;
        align-items: center;
    }
    
    .badge {
        font-size: 0.6rem;
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        font-family: 'JetBrains Mono', monospace;
        white-space: nowrap;
        box-shadow: 0 2px 6px -2px currentColor;
    }
    
    .b-folder {
        background: linear-gradient(135deg, #27272a, #18181b);
        color: #a1a1aa;
        border: 1px solid #3f3f46;
    }
    
    .b-accent {
        background: linear-gradient(135deg, rgba(56, 189, 248, 0.2), rgba(59, 130, 246, 0.15));
        color: #60a5fa;
        border: 1px solid rgba(56, 189, 248, 0.3);
    }
    
    .b-season {
        background: linear-gradient(135deg, rgba(236, 72, 153, 0.2), rgba(219, 39, 119, 0.15));
        color: #f472b6;
        border: 1px solid rgba(236, 72, 153, 0.3);
    }
    
    .b-success {
        background: linear-gradient(135deg, rgba(52, 211, 153, 0.2), rgba(16, 185, 129, 0.15));
        color: #6ee7b7;
        border: 1px solid rgba(52, 211, 153, 0.3);
    }
    
    /* === STATS ROW === */
    .stats-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.7rem;
        color: #a1a1aa;
        padding-top: 10px;
        border-top: 1px solid rgba(63, 63, 70, 0.3);
    }
    
    .time-remaining {
        color: #fbbf24;
        font-weight: 700;
        text-shadow: 0 0 20px rgba(251, 191, 36, 0.3);
    }
    
    /* === NATIVE BUTTON STYLING === */
    /* Override Streamlit buttons to match the custom look */
    div.stButton > button {
        width: 100%;
        border-radius: 10px !important;
        font-size: 0.85rem !important;
        font-weight: 600 !important;
        border: 1px solid rgba(139, 92, 246, 0.3) !important;
        background: linear-gradient(135deg, rgba(139, 92, 246, 0.15), rgba(109, 40, 217, 0.1)) !important;
        color: #e4e4e7 !important;
        transition: all 0.2s ease !important;
        margin-top: 2px;
    }

    div.stButton > button:hover {
        border-color: rgba(167, 139, 250, 0.6) !important;
        background: linear-gradient(135deg, rgba(139, 92, 246, 0.3), rgba(109, 40, 217, 0.2)) !important;
        transform: translateY(-1px);
        color: white !important;
        box-shadow: 0 4px 12px -2px rgba(139, 92, 246, 0.4) !important;
    }
    
    /* Delete/Confirm specific styling overrides */
    /* We can't easily target specific buttons in CSS without keys, 
       but we can make all secondary (outline) buttons reddish if we wanted.
       For now, we keep the purple theme but standard layout. */

    /* === INPUTS === */
    div[data-baseweb="input"] > div { /* Target the inner div that wraps the actual input */
        margin-bottom: 0 !important; /* Remove any default margin that might cause misalignment */
    }

    .stTextInput input {
        background: rgba(24, 24, 27, 0.6) !important;
        backdrop-filter: blur(10px) !important;
        border: 1px solid rgba(63, 63, 70, 0.5) !important;
        border-radius: 12px !important;
        color: #fafafa !important;
        padding: 0.75rem 1rem !important;
        font-size: 0.9rem !important;
        line-height: 1.5 !important; /* Adjust line height for better vertical alignment of text */
        vertical-align: middle !important; /* Ensure vertical alignment */
        height: auto !important; /* Allow height to adjust based on content and padding */
    }
    
    /* Remove gap between columns for the card effect */
    div[data-testid="stHorizontalBlock"] {
        align-items: center;
        background: transparent;
    }
</style>
"""

st.set_page_config(
    page_title=PAGE_TITLE, 
    page_icon=PAGE_ICON, 
    layout="centered", 
    initial_sidebar_state="expanded" # This forces the sidebar open
)
st.markdown(MODERN_CSS, unsafe_allow_html=True)

def open_file_dialog(select_folder=False):
    try:
        root = tk.Tk(); root.withdraw(); root.attributes('-topmost', True)
        root.lift() # Bring the window to the front
        root.update_idletasks() # Ensure window is updated
        path = filedialog.askdirectory() if select_folder else filedialog.askopenfilename()
        root.destroy()
        return path
    except: return None

DRIVER_DEFAULTS = {
    "mpv_native": "mpv",
    "ipc": "celluloid",
    "vlc_rc": "vlc"
}

def get_library_service(settings: dict): # Add settings parameter
    storage_file = Path("sessions.json")
    repository = JsonRepository(storage_file)
    player_driver_type = settings.get('player_type', 'mpv_native') # Default to mpv
    player_executable_path = settings.get('player_executable', 'mpv') # Default to mpv executable

    if player_driver_type == 'vlc_rc':
        player_driver = VlcDriver()

    if player_driver_type == 'ipc':
        player_driver = PlayerDriver(player_executable_path)

    else:
        player_driver = MpvDriver(player_executable_path)
    
    return LibraryService(repository, player_driver)

def render_sidebar(settings):
    with st.sidebar:
        st.markdown("### Library")
        if st.button("📂 Open Folder", use_container_width=True):
            if p := open_file_dialog(True):
                st.session_state['pending_play'] = p
                st.rerun() # Explicitly trigger rerun after path is selected
        if st.button("📄 Open File", use_container_width=True):
            if p := open_file_dialog(False):
                st.session_state['pending_play'] = p
                st.rerun() # Explicitly trigger rerun after path is selected
        
        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("⚙️ Preferences"):
            if 'w_exe' not in st.session_state: 
                st.session_state.w_exe = settings.get('player_executable', 'mpv')
            if 'w_mode' not in st.session_state:
                # Map 'celluloid_ipc' to 'ipc' for compatibility with st.radio options
                player_type_from_settings = settings.get('player_type', 'mpv_native')
                if player_type_from_settings == 'celluloid_ipc':
                    st.session_state.w_mode = 'ipc'
                else:
                    st.session_state.w_mode = player_type_from_settings
            
            # === CHANGE 3: Dynamic Path Update ===
            def update_driver_path():
                # Updates the path input when radio button changes
                new_mode = st.session_state.w_mode
                st.session_state.w_exe = DRIVER_DEFAULTS.get(new_mode, "")

            st.radio("Driver", ["mpv_native", "ipc", "vlc_rc"], key="w_mode", on_change=update_driver_path)
            st.text_input("Path", key="w_exe")
            
            if st.button("Save", use_container_width=True):
                settings['player_executable'] = st.session_state.w_exe
                settings['player_type'] = st.session_state.w_mode
                save_settings(settings)
                st.rerun()
        if st.button("🛑 Quit", type="secondary", use_container_width=True): os._exit(0)

def save_title_and_exit_edit_mode(path, k_id, library_service):
    # Grab updated title
    new_title_key = f"new_title_{k_id}"
    new_title = st.session_state.get(new_title_key)

    # Save to backend / session
    library_service.update_session_metadata(path, clean_title=new_title)
    st.session_state.sessions[path].metadata.clean_title = new_title

    # Exit edit mode
    st.session_state[f"edit_state_{k_id}"] = False

def render_card(path, session, library_service):
    display_name = session.metadata.clean_title
    
    pos, dur = session.playback.position, session.playback.duration
    is_folder = os.path.isdir(path)
    is_done = (pos/dur > 0.95) if dur else False
    
    badges = []
    badges.append(f'<span class="badge b-folder">{"SERIES" if is_folder else "MOVIE"}</span>')
    
    season_num = session.metadata.season_number
        
    if season_num:
        if isinstance(season_num, list): season_num = season_num[0]
        badges.append(f'<span class="badge b-season">SEASON {season_num:02d}</span>')

    if is_folder:
        series_files = library_service.get_series_files(session)
        if series_files:
            curr = session.playback.last_played_index + 1
            total = len(series_files)
            badges.append(f'<span class="badge b-accent">EP {curr}/{total}</span>')
    
    if is_done: 
        badges.append('<span class="badge b-success">✓ COMPLETED</span>')

    # Generate unique key suffix for this item
    k_id = hash(path)

    # === REFACTORED CARD LAYOUT ===
    with st.container():
        col_info, col_actions = st.columns([0.75, 0.25], gap="small")
        
        with col_info:
            html_info = f"""
            <div class="cue-card">
                <div class="card-title">{display_name}</div>
                <div class="badge-container">{"".join(badges)}</div>
                <div class="stats-row">
                    <span>{pos:.0f}s / {dur:.0f}s</span>
                    <span class="time-remaining">{'Finished' if is_done else f"{(dur - pos) / 60:.0f}m left"}</span>
                </div>
            </div>
            """
            st.markdown(html_info, unsafe_allow_html=True)
        
        with col_actions:
            # Vertically align with the card
            st.write("") # Spacer
            
            # 1. RESUME BUTTON
            play_label = "↺ Replay" if is_done else "▶ Resume"
            if st.button(play_label, key=f"play_{k_id}", use_container_width=True):
                st.session_state['resume_data'] = path
                st.rerun()

            col1, col2 = st.columns(2)
            
            with col1:
                # 2. EDIT TITLE BUTTON + INPUT
                edit_button_key = f"edit_btn_{k_id}"
                edit_state_key = f"edit_state_{k_id}"

                # Ensure edit state exists
                if edit_state_key not in st.session_state:
                    st.session_state[edit_state_key] = False

                # -------------------------
                #       EDIT MODE
                # -------------------------
                if st.session_state[edit_state_key]:

                    new_title = st.text_input(
                        "New Title",
                        value=display_name,
                        key=f"new_title_{k_id}",
                        label_visibility="collapsed",
                        on_change=lambda: save_title_and_exit_edit_mode(path, k_id, library_service)
                    )

                else:
                    # -------------------------
                    #    EDIT BUTTON MODE
                    # -------------------------
                    if st.button("Edit", key=edit_button_key, use_container_width=True):
                        st.session_state[edit_state_key] = True
                        st.session_state.is_user_locked_title = True # Set the flag to true
                        st.rerun()

            with col2:
                # 3. DELETE BUTTON (With Confirmation)
                # Check if this specific path is in confirmation mode
                if st.session_state.get('confirm_del') == path:
                    # Show Confirm / Cancel options
                    c1, c2 = st.columns(2)
                    if c1.button("✓", key=f"y_{k_id}", use_container_width=True, help="Confirm Delete"):
                        library_service.repository.delete_session(path)
                        del st.session_state.sessions[path] # Update state
                        del st.session_state['confirm_del']
                        st.rerun()
                    if c2.button("✕", key=f"n_{k_id}", use_container_width=True, help="Cancel"):
                        del st.session_state['confirm_del']
                        st.rerun()
                else:
                    # Show normal delete button
                    if st.button("Delete", key=f"del_{k_id}", use_container_width=True):
                        st.session_state['confirm_del'] = path
                        st.rerun()

    st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)

def main():
    settings = load_settings()
    library_service = get_library_service(settings) # Pass settings to the function

    if 'sessions' not in st.session_state:
        st.session_state.sessions = library_service.get_all_sessions()
    if 'is_user_locked_title' not in st.session_state:
        st.session_state.is_user_locked_title = False

    def reload_sessions_and_rerun():
        st.session_state.sessions = library_service.get_all_sessions()
        st.rerun()

    if 'pending_play' in st.session_state:
        library_service.launch_media(st.session_state.pop('pending_play'))
        reload_sessions_and_rerun()
        
    if 'resume_data' in st.session_state:
        path = st.session_state.pop('resume_data')
        library_service.launch_media(path)
        reload_sessions_and_rerun()

    render_sidebar(settings)
    st.markdown('<div class="main-header">Cue.</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sub-header">Resume where you left off • {len(st.session_state.sessions)} items</div>', unsafe_allow_html=True)

    sessions = st.session_state.sessions
    query = st.text_input("Search", placeholder="Filter your library...", label_visibility="collapsed")
    
    items = sorted(
        [i for i in sessions.items() if query.lower() in str(i).lower()],
        key=lambda x: x[1].playback.timestamp, reverse=True
    )

    if not items: 
        st.info("📚 Your library is empty. Click 'Open Folder' or 'Open File' to get started.")
    else: 
        for path, session in items: 
            render_card(path, session, library_service)

if __name__ == "__main__":
    main()
