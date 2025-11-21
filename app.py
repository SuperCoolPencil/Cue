import os
import sys
import platform
import tkinter as tk
from tkinter import filedialog
import streamlit as st

try:
    from guessit import guessit
except ImportError:
    st.error("Library 'guessit' not found. Please run: pip install guessit")
    st.stop()

try:
    from core import settings as settings_mgr
    from core import session as session_mgr
    from core.utils import format_time, get_media_files, format_remaining, get_folder_stats
    from drivers import play_media
except ImportError:
    st.error("Core modules missing.")
    st.stop()

PAGE_TITLE = "Cue"
PAGE_ICON = "⏯️"

MODERN_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;800&family=JetBrains+Mono:wght@400;500&display=swap');
    .stApp { background-color: #09090b; font-family: 'Inter', sans-serif; }
    header { visibility: hidden; }
    .main-header {
        font-size: 3.5rem; font-weight: 800;
        background: linear-gradient(to right, #fff, #94a3b8);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        line-height: 1.1;
    }
    .sub-header { font-size: 0.9rem; color: #52525b; margin-bottom: 2rem; border-bottom: 1px solid #27272a; padding-bottom: 1rem; }
    .cue-card {
        background: linear-gradient(180deg, #18181b 0%, #0e0e11 100%);
        border: 1px solid #27272a; border-radius: 16px; padding: 20px;
        box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.5); transition: all 0.2s ease;
    }
    .cue-card:hover { border-color: #3f3f46; transform: translateY(-2px); }
    .card-title { font-size: 1.15rem; font-weight: 600; color: #f4f4f5; margin-bottom: 10px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: flex; align-items: center; gap: 8px; }
    .badge-container { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 16px; }
    
    /* --- BADGES --- */
    .badge { font-size: 0.65rem; padding: 4px 10px; border-radius: 99px; font-weight: 600; letter-spacing: 0.5px; text-transform: uppercase; }
    .b-folder { background: #27272a; color: #a1a1aa; border: 1px solid #3f3f46; }
    .b-accent { background: rgba(56, 189, 248, 0.1); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.2); } /* Blue */
    .b-season { background: rgba(236, 72, 153, 0.1); color: #ec4899; border: 1px solid rgba(236, 72, 153, 0.2); } /* Pink */
    .b-success { background: rgba(52, 211, 153, 0.1); color: #34d399; border: 1px solid rgba(52, 211, 153, 0.2); } /* Green */
    
    .stats-row { display: flex; justify-content: space-between; font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: #71717a; margin-top: 8px; }
    .time-remaining { color: #fbbf24; font-weight: 600; }
    .stProgress > div > div > div > div { height: 4px !important; border-radius: 4px; background: linear-gradient(90deg, #38bdf8, #818cf8); }
    button[kind="secondary"] { border: 1px solid #27272a; background: #18181b; color: #a1a1aa; border-radius: 8px; }
    button[kind="secondary"]:hover { border-color: #52525b; color: #fff; background: #27272a; }
    div[data-baseweb="input"] { background-color: #18181b; border: 1px solid #27272a; border-radius: 10px; color: white; }
    section[data-testid="stSidebar"] { background-color: #0c0c0e; border-right: 1px solid #27272a; }
</style>
"""

st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON, layout="centered")
st.markdown(MODERN_CSS, unsafe_allow_html=True)

def open_file_dialog(select_folder=False):
    try:
        root = tk.Tk(); root.withdraw(); root.attributes('-topmost', True)
        path = filedialog.askdirectory() if select_folder else filedialog.askopenfilename()
        root.destroy()
        return path
    except: return None

def launch_media(path, settings, start=0, idx=None, resume_f=None):
    with st.spinner(f"Opening {os.path.basename(path)}..."):
        res = play_media(settings, path, start, idx, resume_f)
        
        if res and res.get('position', 0) > 5:
            target_file = resume_f if resume_f else path
            base_name = os.path.basename(target_file)
            
            # --- LOGIC: Extract Info & Save to Session ---
            info = guessit(base_name)
            
            # 1. Title
            if 'year' in info:
                clean = f"{info.get('title', base_name)} ({info['year']})"
            elif 'season' in info and 'episode' in info:
                # For files, we keep SxxExx in title, but we also save them separately for tags
                clean = f"{info.get('title', base_name)} S{info['season']:02d}E{info['episode']:02d}"
            else:
                clean = info.get('title', base_name)
            
            res['clean_title'] = clean
            
            # 2. Save Season Number specifically
            if 'season' in info:
                res['season_number'] = info['season']

            session_mgr.update_session(path, res, os.path.isdir(path))
            return True
    return False

def render_sidebar(settings):
    with st.sidebar:
        st.markdown("### Library")
        if st.button("📂 Open Folder", use_container_width=True):
            if p := open_file_dialog(True): st.session_state['pending_play'] = p
        if st.button("📄 Open File", use_container_width=True):
            if p := open_file_dialog(False): st.session_state['pending_play'] = p
        
        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("⚙️ Preferences"):
            if 'w_exe' not in st.session_state: st.session_state.w_exe = settings.get('player_executable', 'mpv')
            if 'w_mode' not in st.session_state: st.session_state.w_mode = settings.get('player_type', 'mpv_native')
            st.radio("Driver", ["mpv_native", "celluloid_ipc", "vlc_rc"], key="w_mode")
            st.text_input("Path", key="w_exe")
            if st.button("Save", use_container_width=True):
                settings.update({'player_executable': st.session_state.w_exe, 'player_type': st.session_state.w_mode})
                settings_mgr.save_settings(settings)
                st.rerun()
        if st.button("🛑 Quit", type="secondary", use_container_width=True): os._exit(0)

def render_card(path, data):
    raw_file = data.get('last_played_file', 'Unknown')
    display_name = data.get('clean_title', os.path.basename(raw_file))
    
    pos, dur = data.get('last_played_position', 0), data.get('total_duration', 0)
    is_folder = data.get('is_folder', False)
    is_done = (pos/dur > 0.95) if dur else False
    
    badges = []
    
    # 1. Type Badge
    badges.append(f'<span class="badge b-folder">{"SERIES" if is_folder else "MOVIE"}</span>')
    
    # 2. Season Badge (The new tag!)
    # Try to get from saved session first, else guess it on the fly
    season_num = data.get('season_number')
    if not season_num:
        # Fallback for old sessions
        meta = guessit(os.path.basename(raw_file))
        season_num = meta.get('season')
        
    if season_num:
        # e.g. SEASON 01
        if isinstance(season_num, list): season_num = season_num[0] # Handle multi-season packs
        badges.append(f'<span class="badge b-season">SEASON {season_num:02d}</span>')

    # 3. Episode / Progress Badge
    if is_folder:
        stats = get_folder_stats(path, data['last_played_file'])
        if stats:
            curr, total = stats
            badges.append(f'<span class="badge b-accent">EP {curr}/{total}</span>')
    
    if is_done: 
        badges.append('<span class="badge b-success">COMPLETED</span>')

    # Render
    html = f"""
    <div class="cue-card">
        <div class="card-title" title="{os.path.basename(raw_file)}">{display_name}</div>
        <div class="badge-container">{"".join(badges)}</div>
        <div class="stats-row">
            <span>{format_time(pos)} / {format_time(dur)}</span>
            <span class="time-remaining">{'Finished' if is_done else format_remaining(dur - pos, is_folder)}</span>
        </div>
    </div>
    """
    
    st.markdown(html, unsafe_allow_html=True)
    if not is_done: st.progress(min(pos/dur, 1.0) if dur else 0)
    else: st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)

    c1, c2 = st.columns([0.85, 0.15])
    with c1:
        if st.button("↺ Replay" if is_done else "▶ Resume", key=f"p_{path}", use_container_width=True):
            st.session_state['resume_data'] = (path, is_done, pos, is_folder, data['last_played_file'])
            st.rerun()
    with c2:
        if st.button("✕", key=f"d_{path}"):
            session_mgr.delete_session(path)
            st.rerun()
    st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)

def main():
    settings = settings_mgr.load_settings()
    
    if 'pending_play' in st.session_state:
        if launch_media(st.session_state.pop('pending_play'), settings): st.rerun()
        
    if 'resume_data' in st.session_state:
        path, done, pos, is_dir, last_f = st.session_state.pop('resume_data')
        if os.path.exists(path):
            idx, res_f = None, None
            if is_dir:
                files = get_media_files(path)
                if last_f in files: idx, res_f = files.index(last_f), last_f
            if launch_media(path, settings, 0 if done else pos, idx, res_f): st.rerun()

    render_sidebar(settings)
    st.markdown('<div class="main-header">Cue.</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sub-header">Playback History • {len(session_mgr.load_sessions())} items</div>', unsafe_allow_html=True)

    sessions = session_mgr.load_sessions()
    query = st.text_input("Search", placeholder="Filter...", label_visibility="collapsed")
    
    items = sorted(
        [i for i in sessions.items() if query.lower() in str(i).lower()],
        key=lambda x: x[1].get('last_played_timestamp', ''), reverse=True
    )

    if not items: st.info("Library is empty.")
    else: 
        for path, data in items: render_card(path, data)

if __name__ == "__main__":
    main()