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
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&display=swap');
    
    /* === GLOBAL RESET === */
    .stApp {
        background: linear-gradient(135deg, #0a0a0f 0%, #1a0a1f 50%, #0a0a0f 100%);
        background-attachment: fixed;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    header, #MainMenu, footer { visibility: hidden; height: 0; }
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
        margin-bottom: 12px;
        box-shadow: 
            0 8px 32px -8px rgba(139, 92, 246, 0.3),
            0 0 0 1px rgba(255, 255, 255, 0.05) inset;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative;
        overflow: hidden;
    }
    
    .cue-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: -100%;
        width: 100%;
        height: 100%;
        background: linear-gradient(90deg, transparent, rgba(167, 139, 250, 0.1), transparent);
        transition: left 0.5s;
    }
    
    .cue-card:hover {
        border-color: rgba(167, 139, 250, 0.5);
        transform: translateY(-2px);
        box-shadow: 
            0 16px 48px -8px rgba(139, 92, 246, 0.5),
            0 0 0 1px rgba(167, 139, 250, 0.2) inset;
    }
    
    .cue-card:hover::before {
        left: 100%;
    }
    
    /* === CARD HEADER === */
    .card-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 12px;
        margin-bottom: 12px;
    }
    
    .card-title {
        font-size: 1.1rem;
        font-weight: 700;
        color: #fafafa;
        line-height: 1.3;
        flex: 1;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    
    .card-actions {
        display: flex;
        gap: 6px;
        flex-shrink: 0;
    }
    
    .action-btn {
        padding: 8px 16px;
        border-radius: 10px;
        font-size: 0.85rem;
        font-weight: 600;
        border: 1px solid rgba(139, 92, 246, 0.3);
        background: linear-gradient(135deg, rgba(139, 92, 246, 0.15), rgba(109, 40, 217, 0.1));
        color: #e4e4e7;
        cursor: pointer;
        transition: all 0.2s ease;
        white-space: nowrap;
        text-decoration: none;
        display: inline-flex;
        align-items: center;
        gap: 4px;
    }
    
    .action-btn:hover {
        border-color: rgba(167, 139, 250, 0.6);
        background: linear-gradient(135deg, rgba(139, 92, 246, 0.3), rgba(109, 40, 217, 0.2));
        transform: translateY(-1px);
        box-shadow: 0 4px 12px -2px rgba(139, 92, 246, 0.4);
    }
    
    .action-btn.delete {
        padding: 8px 12px;
        background: rgba(239, 68, 68, 0.1);
        border-color: rgba(239, 68, 68, 0.3);
        color: #fca5a5;
    }
    
    .action-btn.delete:hover {
        background: rgba(239, 68, 68, 0.2);
        border-color: rgba(239, 68, 68, 0.5);
        box-shadow: 0 4px 12px -2px rgba(239, 68, 68, 0.4);
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
        animation: pulse 2s ease-in-out infinite;
    }
    
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.7; }
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
    
    /* === BUTTONS (for sidebar) === */
    button[kind="secondary"], button[kind="primary"] {
        border-radius: 12px !important;
        font-weight: 600 !important;
        font-size: 0.875rem !important;
        padding: 0.65rem 1.25rem !important;
        border: 1px solid rgba(139, 92, 246, 0.3) !important;
        background: linear-gradient(135deg, rgba(30, 27, 75, 0.6), rgba(25, 20, 45, 0.8)) !important;
        color: #e4e4e7 !important;
        transition: all 0.2s ease !important;
        box-shadow: 0 4px 12px -2px rgba(0, 0, 0, 0.3) !important;
    }
    
    button[kind="secondary"]:hover, button[kind="primary"]:hover {
        border-color: rgba(167, 139, 250, 0.6) !important;
        background: linear-gradient(135deg, rgba(139, 92, 246, 0.3), rgba(109, 40, 217, 0.2)) !important;
        color: #fafafa !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 20px -4px rgba(139, 92, 246, 0.4) !important;
    }
    
    /* === INPUTS === */
    div[data-baseweb="input"], .stTextInput input {
        background: rgba(24, 24, 27, 0.6) !important;
        backdrop-filter: blur(10px) !important;
        border: 1px solid rgba(63, 63, 70, 0.5) !important;
        border-radius: 12px !important;
        color: #fafafa !important;
        padding: 0.75rem 1rem !important;
        font-size: 0.9rem !important;
        transition: all 0.2s ease !important;
    }
    
    div[data-baseweb="input"]:focus-within, .stTextInput input:focus {
        border-color: rgba(139, 92, 246, 0.6) !important;
        box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.1) !important;
        outline: none !important;
    }
    
    /* === SIDEBAR === */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, rgba(12, 12, 14, 0.95) 0%, rgba(10, 10, 15, 0.98) 100%) !important;
        backdrop-filter: blur(20px) !important;
        border-right: 1px solid rgba(63, 63, 70, 0.3) !important;
    }
    
    section[data-testid="stSidebar"] .stMarkdown h3 {
        color: #e4e4e7;
        font-weight: 700;
        font-size: 0.875rem;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        margin-bottom: 1rem;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid rgba(139, 92, 246, 0.2);
    }
    
    /* === SPACING === */
    .element-container { margin-bottom: 0.5rem; }
    
    /* === INFO MESSAGES === */
    .stAlert {
        background: rgba(59, 130, 246, 0.1) !important;
        border: 1px solid rgba(59, 130, 246, 0.3) !important;
        border-radius: 12px !important;
        color: #93c5fd !important;
    }
    
    /* === RESPONSIVE === */
    @media (max-width: 768px) {
        .main-header { font-size: 2.5rem; }
        .cue-card { padding: 16px; }
        .card-title { font-size: 1rem; }
        .card-header { flex-direction: column; }
        .card-actions { width: 100%; justify-content: stretch; }
        .action-btn { flex: 1; justify-content: center; }
    }
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
            
            try:
                info = guessit(base_name)
            except Exception as e:
                print(f"Guessit error: {e}")
                info = {}
            
            if 'year' in info:
                clean = f"{info.get('title', base_name)} ({info['year']})"
            elif 'season' in info and 'episode' in info:
                clean = f"{info.get('title', base_name)} S{info['season']:02d}E{info['episode']:02d}"
            else:
                clean = info.get('title', os.path.splitext(base_name)[0])
            
            res['clean_title'] = clean
            
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
    
    badges.append(f'<span class="badge b-folder">{"SERIES" if is_folder else "MOVIE"}</span>')
    
    season_num = data.get('season_number')
    if not season_num:
        try:
            meta = guessit(os.path.basename(raw_file))
            season_num = meta.get('season')
        except:
            season_num = None
        
    if season_num:
        if isinstance(season_num, list): season_num = season_num[0]
        badges.append(f'<span class="badge b-season">SEASON {season_num:02d}</span>')

    if is_folder:
        stats = get_folder_stats(path, data['last_played_file'])
        if stats:
            curr, total = stats
            badges.append(f'<span class="badge b-accent">EP {curr}/{total}</span>')
    
    if is_done: 
        badges.append('<span class="badge b-success">✓ COMPLETED</span>')

    # Generate unique keys for buttons
    resume_key = f"resume_{hash(path)}"
    delete_key = f"delete_{hash(path)}"

        # Hidden buttons that get triggered by the card buttons
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("resume_hidden", key=resume_key, help="", type="secondary"):
            st.session_state['resume_data'] = (path, is_done, pos, is_folder, data['last_played_file'])
            st.rerun()

    with col2:
        if st.button("delete_hidden", key=delete_key):
             session_mgr.delete_session(path)
             st.rerun()


    html = f"""
    <div class="cue-card">
        <div class="card-header">
            <div class="card-title">{display_name}</div>
            <div class="card-actions">
                <button class="action-btn" onclick="document.getElementById('{resume_key}').click()">
                    {'↺ Replay' if is_done else '▶ Resume'}
                </button>
                <button class="action-btn delete" onclick="document.getElementById('{delete_key}').click()">
                    ✕
                </button>
            </div>
        </div>
        <div class="badge-container">{"".join(badges)}</div>
        <div class="stats-row">
            <span>{format_time(pos)} / {format_time(dur)}</span>
            <span class="time-remaining">{'Finished' if is_done else format_remaining(dur - pos, is_folder)}</span>
        </div>
    </div>
    """
    
    st.markdown(html, unsafe_allow_html=True)
    
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
    query = st.text_input("Search", placeholder="Filter your library...", label_visibility="collapsed")
    
    items = sorted(
        [i for i in sessions.items() if query.lower() in str(i).lower()],
        key=lambda x: x[1].get('last_played_timestamp', ''), reverse=True
    )

    if not items: 
        st.info("📚 Your library is empty. Click 'Open Folder' or 'Open File' to get started.")
    else: 
        for path, data in items: 
            render_card(path, data)

if __name__ == "__main__":
    main()