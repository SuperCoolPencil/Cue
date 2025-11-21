import os
import time
import datetime
import platform
import streamlit as st
import tkinter as tk
from tkinter import filedialog

# Import Modules
from core import settings as settings_mgr
from core import session as session_mgr
from core.utils import format_time, get_media_files
from drivers import play_media

# --- UI Styling ---
st.set_page_config(page_title="Cue", page_icon="⏯️", layout="centered")
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;800&display=swap');
    .main-title { font-family: 'Inter', sans-serif; font-size: 3rem; font-weight: 800; background: linear-gradient(90deg, #F59E0B, #EF4444); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 0px; }
    .subtitle { font-family: 'Inter', sans-serif; color: #888; margin-bottom: 20px; }
    .stProgress > div > div > div > div { background-color: #F59E0B; } 
    .session-card { background-color: #1F2937; border: 1px solid #374151; padding: 15px; border-radius: 12px; margin-bottom: 15px; }
    .stButton>button { border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# --- Initialization ---
# Load settings from disk
current_settings = settings_mgr.load_settings()
if 'selected_path' not in st.session_state: st.session_state['selected_path'] = None

# --- Helper: Auto-Switch Path Logic ---
def update_path_based_on_mode():
    """Callback to update the path input when mode changes"""
    new_mode = st.session_state.widget_mode
    is_win = platform.system() == "Windows"
    is_mac = platform.system() == "Darwin"
    
    new_path = "mpv" # Fallback
    
    if new_mode == "vlc_rc":
        if is_win: new_path = r"C:\Program Files\VideoLAN\VLC\vlc.exe"
        elif is_mac: new_path = "/Applications/VLC.app/Contents/MacOS/VLC"
        else: new_path = "vlc"
        
    elif new_mode == "mpv_native":
        if is_win: new_path = "mpv" # User might need full path, but mpv is common default
        else: new_path = "mpv"
        
    elif new_mode == "celluloid_ipc":
        if is_win: new_path = "INVALID_ON_WINDOWS"
        else: new_path = "celluloid"

    # Update the text input key directly
    st.session_state.widget_exe = new_path

# --- Helper: Play Logic ---
def handle_play(path, start_pos=0, idx=None, resume_f=None):
    with st.spinner("Launching player..."):
        # Reload settings from UI state in case they changed just now
        res = play_media(current_settings, path, start_pos, idx, resume_f)
        if res and res.get('position', 0) > 5:
            session_mgr.update_session(path, res, is_folder=os.path.isdir(path))
            return True
        elif not res:
            st.error("Player failed to launch. Check Settings path.")
    return False

# --- Sidebar ---
with st.sidebar:
    st.markdown("### ⏯️ Controls")
    if st.button("📂 Open Folder", use_container_width=True):
        root = tk.Tk(); root.withdraw(); root.attributes('-topmost', True)
        p = filedialog.askdirectory()
        root.destroy()
        if p: st.session_state['selected_path'] = p
        
    if st.button("📄 Open File", use_container_width=True):
        root = tk.Tk(); root.withdraw(); root.attributes('-topmost', True)
        p = filedialog.askopenfilename()
        root.destroy()
        if p: st.session_state['selected_path'] = p

    st.markdown("---")
    
    with st.expander("⚙️ Settings"):
        st.caption("Configuration")
        
        # 1. Setup Session State for widgets if not present
        if 'widget_exe' not in st.session_state:
            st.session_state.widget_exe = current_settings['player_executable']
        if 'widget_mode' not in st.session_state:
            st.session_state.widget_mode = current_settings['player_type']

        # 2. The Mode Radio Button (With Callback)
        options = ["mpv_native", "celluloid_ipc", "vlc_rc"]
        # Calculate index safely
        try:
            default_idx = options.index(st.session_state.widget_mode)
        except ValueError:
            default_idx = 0

        st.radio(
            "Driver Mode", 
            options, 
            index=default_idx,
            key="widget_mode",
            on_change=update_path_based_on_mode, # <--- THE MAGIC TRIGGER
            help="mpv_native (Win/Linux), celluloid_ipc (Linux GUI), vlc_rc (All)"
        )
        
        # 3. The Path Input (Linked to session state key)
        st.text_input(
            "Player Path", 
            key="widget_exe" 
        )
        
        if st.button("Save Settings"):
            # Update the dictionary from widget state
            current_settings['player_executable'] = st.session_state.widget_exe
            current_settings['player_type'] = st.session_state.widget_mode
            settings_mgr.save_settings(current_settings)
            st.success("Saved!")
            time.sleep(0.5)
            st.rerun()

    if st.button("🛑 Stop Cue", type="secondary"): os._exit(0)

# --- Main Content ---
st.markdown('<div class="main-title">Cue</div>', unsafe_allow_html=True)
st.markdown(f'<div class="subtitle">Resume exactly where you left off. <br><small>Using: {current_settings["player_executable"]}</small></div>', unsafe_allow_html=True)

# Trigger Play from File Picker
if st.session_state['selected_path']:
    path = st.session_state['selected_path']
    st.session_state['selected_path'] = None 
    if handle_play(path):
        st.rerun()

# History Feed
sessions = session_mgr.load_sessions()
col_s, col_b = st.columns([4,1])
search = col_s.text_input("Search history", placeholder="Movie name...", label_visibility="collapsed")

filtered = {k:v for k,v in sessions.items() if search.lower() in k.lower() or search.lower() in v.get('last_played_file','').lower()}
sorted_sess = sorted(filtered.items(), key=lambda i: i[1].get('last_played_timestamp',''), reverse=True)

if not sorted_sess:
    st.info("Your queue is empty. Open a file to begin.")
else:
    for orig_path, data in sorted_sess:
        fname = os.path.basename(data['last_played_file'])
        pos = data.get('last_played_position', 0)
        dur = data.get('total_duration', 0)
        prog = min(pos/dur, 1.0) if dur else 0
        finished = prog > 0.95
        
        with st.container():
            st.markdown(f"""
            <div class="session-card">
                <div style="display:flex; justify-content:space-between;">
                    <h3 style="margin:0; font-size:1.1rem; color:white;">{fname}</h3>
                    <span style="color:#6B7280; font-size:0.8rem;">{data.get('last_played_timestamp','')[:10]}</span>
                </div>
                <p style="color:#9CA3AF; font-size:0.8rem; margin-bottom:10px;">{orig_path}</p>
                <div style="display:flex; justify-content:space-between; color:#D1D5DB; font-size:0.9rem; margin-bottom:5px;">
                    <span>{'✅ Complete' if finished else '⏱ ' + format_time(pos) + ' / ' + format_time(dur)}</span>
                    <span>{int(prog*100)}%</span>
                </div>
            </div>""", unsafe_allow_html=True)
            
            if not finished: st.progress(prog)
            
            c1, c2 = st.columns([4,1])
            if c1.button(f"{'🔄 Replay' if finished else '▶️ Resume'}", key=f"p_{orig_path}", use_container_width=True):
                if not os.path.exists(orig_path):
                    st.error("Media not found.")
                else:
                    idx, res_f = None, None
                    if data['is_folder']:
                        files = get_media_files(orig_path)
                        last = data['last_played_file']
                        if last in files: idx = files.index(last); res_f = last
                    
                    if handle_play(orig_path, 0 if finished else pos, idx, res_f):
                        st.rerun()
            
            if c2.button("✕", key=f"d_{orig_path}", help="Remove"):
                session_mgr.delete_session(orig_path)
                st.rerun()