import os
import json
import subprocess
import streamlit as st
import re
import datetime
import time
import socket
import uuid
import platform
import tkinter as tk
from tkinter import filedialog

# --- Constants & Paths ---
CACHE_PATH = os.path.expanduser("~/.cache/cue_media_sessions.json")
SETTINGS_PATH = os.path.expanduser("~/.config/cue_settings.json")

# Detect OS
IS_WINDOWS = platform.system() == "Windows"

# --- Settings Management ---

def load_settings():
    defaults = {
        "player_executable": "mpv" if IS_WINDOWS else "celluloid",
        "player_type": "mpv_native" if IS_WINDOWS else "celluloid_ipc",
    }
    
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, 'r') as f:
                saved = json.load(f)
                defaults.update(saved)
        except:
            pass
    return defaults

def save_settings(settings):
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, 'w') as f:
        json.dump(settings, f, indent=2)

# --- IPC Helper (For Socket-based Players) ---

def send_ipc_command(sock_path, command):
    if not os.path.exists(sock_path): return None
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(0.5)
        client.connect(sock_path)
        message = json.dumps(command) + "\n"
        client.sendall(message.encode('utf-8'))
        response = client.recv(4096)
        client.close()
        response_str = response.decode('utf-8').strip()
        # Parse potential multi-line JSON responses
        for line in response_str.split('\n'):
            try:
                j = json.loads(line)
                if 'data' in j or 'error' in j: return j
            except: continue
        return None
    except Exception:
        return None

def get_ipc_status(sock_path):
    pos_resp = send_ipc_command(sock_path, {"command": ["get_property", "time-pos"]})
    dur_resp = send_ipc_command(sock_path, {"command": ["get_property", "duration"]})
    path_resp = send_ipc_command(sock_path, {"command": ["get_property", "path"]})
    
    pos = pos_resp.get('data') if pos_resp else None
    dur = dur_resp.get('data') if dur_resp else None
    fpath = path_resp.get('data') if path_resp else None
    return fpath, pos, dur

# --- Drivers ---

def driver_mpv_native(executable, path, start_pos=None, playlist_idx=None, resume_file=None):
    """ Driver for CLI players that output status to stdout (mpv, mplayer) """
    cmd = [
        executable,
        "--force-window",
        "--term-status-msg=[Cue]PATH:${path}#POS:${playback-time}#DUR:${duration}"
    ]
    
    script_path = None
    # Playlist/Folder logic
    if resume_file and playlist_idx is not None and os.path.isdir(path):
        cmd.append(f"--playlist-start={playlist_idx}")
        # Lua script to seek only on the specific file load
        script_content = f'''
local sought = false
local target_time = {max(start_pos-2, 0)}
function on_file_loaded()
    if not sought then
        sought = true
        mp.commandv("seek", target_time, "absolute")
    end
end
mp.register_event("file-loaded", on_file_loaded)
'''
        import tempfile
        fd, script_path = tempfile.mkstemp(suffix=".lua")
        os.close(fd)
        with open(script_path, 'w') as f: f.write(script_content)
        cmd.append(f"--script={script_path}")
    elif start_pos:
         cmd.append(f"--start={start_pos}")

    cmd.append(path)

    try:
        startupinfo = None
        if IS_WINDOWS:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
        proc = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            encoding='utf-8', 
            errors='replace',
            startupinfo=startupinfo
        )
    except FileNotFoundError:
        st.error(f"Error: `{executable}` not found.")
        return None
    finally:
        if script_path and os.path.exists(script_path): os.remove(script_path)

    # Parse Output
    last_line = ""
    if proc.stdout:
        for line in proc.stdout.split('\n'):
            if "[Cue]" in line: last_line = line

    if not last_line: return None

    match = re.search(r"PATH:(.*?)#POS:([\d:.]+)#DUR:([\d:.]+)", last_line)
    if match:
        p_str, d_str = match.group(2), match.group(3)
        
        def parse_time(t):
            if ':' in str(t):
                parts = t.split(':')
                if len(parts) == 3: return float(parts[0])*3600 + float(parts[1])*60 + float(parts[2])
                elif len(parts) == 2: return float(parts[0])*60 + float(parts[1])
            return float(t) if t != "unknown" else 0

        return {"path": match.group(1), "position": parse_time(p_str), "duration": parse_time(d_str)}
    return None

def driver_celluloid_ipc(executable, path, start_pos=None, playlist_idx=None, resume_file=None):
    """ Driver for GUI wrappers (Celluloid) using Sockets """
    if IS_WINDOWS:
        st.error("IPC mode not supported on Windows.")
        return None

    socket_path = f"/tmp/cue_ipc_{uuid.uuid4().hex}.sock"
    
    cmd = [executable]
    # Pass arguments individually!
    cmd.append(f"--mpv-input-ipc-server={socket_path}")
    if start_pos: cmd.append(f"--mpv-start={start_pos}")
    if playlist_idx is not None: cmd.append(f"--mpv-playlist-start={playlist_idx}")
    cmd.append(path)

    # Print debug for user if it fails
    print(f"Cue Driver Executing: {cmd}")

    try:
        proc = subprocess.Popen(cmd)
    except FileNotFoundError:
        st.error(f"Error: `{executable}` not found.")
        return None

    last_pos, last_dur, last_path = 0, 0, None
    time.sleep(2.0) # Wait for app to launch

    while proc.poll() is None:
        fpath, pos, dur = get_ipc_status(socket_path)
        if pos: last_pos = pos
        if dur: last_dur = dur
        if fpath: last_path = fpath
        time.sleep(1)

    if os.path.exists(socket_path): os.remove(socket_path)

    final_path = last_path if last_path else path
    if os.path.isdir(path) and last_path:
        full = os.path.join(path, last_path)
        if os.path.exists(full): final_path = full
    
    return {"path": final_path, "position": last_pos, "duration": last_dur}

# --- Main Logic ---

def play(path, settings, start_pos=None, playlist_idx=None, resume_file=None):
    exe = settings['player_executable']
    mode = settings['player_type']
    
    if mode == "mpv_native":
        return driver_mpv_native(exe, path, start_pos, playlist_idx, resume_file)
    elif mode == "celluloid_ipc":
        return driver_celluloid_ipc(exe, path, start_pos, playlist_idx, resume_file)
    else:
        st.error(f"Unknown player mode: {mode}")
        return None

def get_media_files(folder):
    exts = ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.webm', '.mp3', '.wav', '.ogg')
    try:
        return sorted([os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(exts)])
    except: return []

def format_time(seconds):
    if not seconds: return "0:00:00"
    return str(datetime.timedelta(seconds=int(seconds)))

# --- UI ---

st.set_page_config(page_title="Cue", page_icon="⏯️", layout="centered")

# Custom CSS for the "Cue" branding
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;800&display=swap');
    
    .main-title {
        font-family: 'Inter', sans-serif;
        font-size: 3rem;
        font-weight: 800;
        background: linear-gradient(90deg, #F59E0B, #EF4444);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0px;
    }
    .subtitle {
        font-family: 'Inter', sans-serif;
        color: #888;
        margin-bottom: 20px;
    }
    .stProgress > div > div > div > div { background-color: #F59E0B; } 
    .session-card { 
        background-color: #1F2937; 
        border: 1px solid #374151; 
        padding: 15px; 
        border-radius: 12px; 
        margin-bottom: 15px; 
    }
    .stButton>button {
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)

# Load State
settings = load_settings()
sessions = {}
if os.path.exists(CACHE_PATH):
    try:
        with open(CACHE_PATH, 'r') as f: sessions = json.load(f)
    except: pass

# --- Sidebar: Settings & Controls ---
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
        new_exe = st.text_input("Player Path", value=settings['player_executable'])
        
        options = ["mpv_native", "celluloid_ipc"]
        idx = options.index(settings['player_type']) if settings['player_type'] in options else 0
        new_type = st.radio("Driver Mode", options, index=idx)
        
        st.caption("**Modes:**\n\n*mpv_native*: For Windows or CLI users.\n*celluloid_ipc*: For Linux GUI wrappers.")
        
        if st.button("Save Settings"):
            settings['player_executable'] = new_exe
            settings['player_type'] = new_type
            save_settings(settings)
            st.success("Saved!")
            time.sleep(0.5)
            st.rerun()

    if st.button("🛑 Stop Cue", type="secondary"): os._exit(0)

# --- Main Content ---

st.markdown('<div class="main-title">Cue</div>', unsafe_allow_html=True)
st.markdown(f'<div class="subtitle">Resume exactly where you left off. <br><small>Using: {settings["player_executable"]}</small></div>', unsafe_allow_html=True)

if 'selected_path' not in st.session_state: st.session_state['selected_path'] = None

# Handle New Playback
if st.session_state['selected_path']:
    p = st.session_state['selected_path']
    st.session_state['selected_path'] = None
    
    with st.spinner("Launching player..."):
        res = play(p, settings)
        
    if res and res.get('position', 0) > 5:
        sessions[p] = {
            "is_folder": os.path.isdir(p),
            "last_played_file": res['path'],
            "last_played_position": res['position'],
            "total_duration": res['duration'],
            "last_played_timestamp": datetime.datetime.now().isoformat()
        }
        save_settings(settings) # Ensure settings stick
        with open(CACHE_PATH, 'w') as f: json.dump(sessions, f, indent=2)
        st.rerun()

# Search & History
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
                        if last in files:
                            idx = files.index(last)
                            res_f = last
                    
                    res = play(orig_path, settings, start_pos=0 if finished else pos, playlist_idx=idx, resume_file=res_f)
                    
                    if res and res.get('position', 0) > 2:
                        sessions[orig_path].update({
                            "last_played_file": res['path'],
                            "last_played_position": res['position'],
                            "total_duration": res['duration'],
                            "last_played_timestamp": datetime.datetime.now().isoformat()
                        })
                        with open(CACHE_PATH, 'w') as f: json.dump(sessions, f, indent=2)
                        st.rerun()
            
            if c2.button("✕", key=f"d_{orig_path}", help="Remove"):
                del sessions[orig_path]
                with open(CACHE_PATH, 'w') as f: json.dump(sessions, f, indent=2)
                st.rerun()