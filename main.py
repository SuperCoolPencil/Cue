import os
import json
import subprocess
import streamlit as st
import datetime
import time
import socket
import uuid
import tkinter as tk
from tkinter import filedialog

# Path to store last-played information
CACHE_PATH = os.path.expanduser("~/.cache/mpv_recall_sessions.json")

# --- IPC Helper Functions (The Magic for Celluloid) ---

def send_ipc_command(sock_path, command):
    """Connects to the MPV/Celluloid socket and sends a JSON command."""
    if not os.path.exists(sock_path):
        return None
    
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(0.5)
        client.connect(sock_path)
        
        message = json.dumps(command) + "\n"
        client.sendall(message.encode('utf-8'))
        
        response = client.recv(4096)
        client.close()
        
        response_str = response.decode('utf-8').strip()
        # MPV might send multiple event lines; we want the one with 'data' or 'error'
        for line in response_str.split('\n'):
            try:
                j = json.loads(line)
                if 'data' in j or 'error' in j:
                    return j
            except:
                continue
        return None
    except Exception:
        return None

def get_playback_status(sock_path):
    """Queries current position and duration."""
    pos_resp = send_ipc_command(sock_path, {"command": ["get_property", "time-pos"]})
    dur_resp = send_ipc_command(sock_path, {"command": ["get_property", "duration"]})
    path_resp = send_ipc_command(sock_path, {"command": ["get_property", "path"]})
    
    pos = pos_resp.get('data') if pos_resp else None
    dur = dur_resp.get('data') if dur_resp else None
    fpath = path_resp.get('data') if path_resp else None
    
    return fpath, pos, dur

# --- Core Functions ---

def format_time(seconds):
    """Formats seconds into H:MM:SS string."""
    if seconds is None: return "0:00:00"
    return str(datetime.timedelta(seconds=int(seconds)))

def load_all_sessions():
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def save_session_data(sessions):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, 'w') as f:
        json.dump(sessions, f, indent=2)

def pick_file_or_folder(mode="file"):
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    
    file_path = None
    try:
        if mode == "folder":
            file_path = filedialog.askdirectory(title="Select Media Folder")
        else:
            file_path = filedialog.askopenfilename(title="Select Media File")
    except Exception as e:
        st.error(f"Error opening file dialog: {e}")
    finally:
        root.destroy()
    return file_path
def play_celluloid(path_to_play, start_pos=None, playlist_start_index=None, resume_specific_file=None):
    """
    Plays media with Celluloid using IPC to track progress.
    UPDATED: Passes arguments individually to avoid parsing errors.
    """
    # Generate a unique socket path for this session
    socket_path = f"/tmp/mpv_recall_{uuid.uuid4().hex}.sock"
    
    # Start building the command list
    # If you are using Flatpak, change "celluloid" to:
    # "flatpak", "run", "io.github.celluloid_player.Celluloid"
    cmd = ["celluloid"] 

    # --- 1. Pass Options Individually ---
    # Instead of bundling them into --mpv-options="...", we use --mpv-[flag]
    
    # Set the IPC socket
    cmd.append(f"--mpv-input-ipc-server={socket_path}")
    
    # Handle Start Position
    if start_pos and start_pos > 0:
        cmd.append(f"--mpv-start={start_pos}")
    
    # Handle Playlist Logic
    if resume_specific_file and playlist_start_index is not None and os.path.isdir(path_to_play):
        cmd.append(f"--mpv-playlist-start={playlist_start_index}")

    # Add the file/folder path last
    cmd.append(path_to_play)

    # Debug: Print the exact command being sent (check your terminal if it fails)
    print("Executing:", " ".join(cmd))

    # --- 2. Execute ---
    try:
        proc = subprocess.Popen(cmd)
    except FileNotFoundError:
        st.error("Error: `celluloid` command not found. Is it installed and in your PATH?")
        return None

    # --- 3. Tracking Loop (Same as before) ---
    last_known_pos = 0
    last_known_dur = 0
    last_known_path = None
    
    # Wait a moment for Celluloid to initialize the socket
    time.sleep(2.0) 
    
    # If the process died immediately, return None
    if proc.poll() is not None:
        st.error("Celluloid closed immediately. Check terminal output for details.")
        return None

    st.info("🎬 Celluloid is running. Tracking playback via IPC...")
    
    while proc.poll() is None:
        fpath, pos, dur = get_playback_status(socket_path)
        
        if pos is not None: last_known_pos = pos
        if dur is not None: last_known_dur = dur
        if fpath is not None: last_known_path = fpath
            
        time.sleep(1) # Poll every second

    # Cleanup Socket
    if os.path.exists(socket_path):
        os.remove(socket_path)
        
    # Logic to determine what to save
    final_path = last_known_path if last_known_path else path_to_play
    
    if os.path.isdir(path_to_play) and last_known_path:
        # Ensure we save the full path
        full_check = os.path.join(path_to_play, last_known_path)
        if os.path.exists(full_check):
            final_path = full_check
        elif os.path.exists(last_known_path):
            final_path = last_known_path

    if last_known_pos > 5:
        return {
            "path": final_path,
            "position": last_known_pos, 
            "duration": last_known_dur
        }
    return None

def get_media_files(folder):
    media_extensions = ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.webm', '.mp3', '.wav', '.ogg')
    try:
        return sorted([
            os.path.join(folder, f) for f in os.listdir(folder)
            if os.path.isfile(os.path.join(folder, f)) and f.lower().endswith(media_extensions)
        ])
    except Exception:
        return []

# --- UI Layout ---

st.set_page_config(page_title="CelluloidRecall", page_icon="🎬", layout="centered")

st.markdown("""
<style>
    .stProgress > div > div > div > div { background-color: #57c264; } /* Green for Celluloid */
    .session-card {
        background-color: #262730;
        border: 1px solid #464b5d;
        padding: 15px;
        border-radius: 10px;
        margin-bottom: 15px;
    }
    .header-title {
        font-size: 2.5rem;
        font-weight: 800;
        background: -webkit-linear-gradient(45deg, #57c264, #2d7a37);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .meta-tag {
        background-color: #333;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.8rem;
        color: #aaa;
        margin-right: 8px;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="header-title">CelluloidRecall</div>', unsafe_allow_html=True)
st.markdown('Resume media using **Celluloid** (GNOME MPV).')

if 'selected_path' not in st.session_state:
    st.session_state['selected_path'] = None

all_sessions = load_all_sessions()

# --- Section 1: Filters ---
col_search, col_btn = st.columns([3, 1])
with col_search:
    search_query = st.text_input("🔍 Filter history...", placeholder="Search filename...")

filtered_sessions = {
    k: v for k, v in all_sessions.items() 
    if search_query.lower() in k.lower() or search_query.lower() in v.get('last_played_file', '').lower()
}

sorted_sessions = sorted(
    filtered_sessions.items(), 
    key=lambda item: item[1].get('last_played_timestamp', ''), 
    reverse=True
)

st.markdown("---")

# --- Section 2: History List ---
if not sorted_sessions:
    st.info("No playback history yet." if not search_query else "No matches.")
else:
    for original_path, session in sorted_sessions:
        last_file = session.get('last_played_file', '')
        last_pos = session.get('last_played_position', 0)
        total_dur = session.get('total_duration', 0)
        is_folder = session.get('is_folder', False)
        last_ts = session.get('last_played_timestamp', '')[:16].replace('T', ' ')
        
        filename = os.path.basename(last_file)
        
        progress_val = 0.0
        if total_dur > 0:
            progress_val = min(last_pos / total_dur, 1.0)
        
        percent_str = f"{int(progress_val * 100)}%"
        time_display = f"{format_time(last_pos)} / {format_time(total_dur)}"
        is_finished = progress_val > 0.95
        status_icon = "✅ Finished" if is_finished else f"⏱ {time_display}"

        with st.container():
            st.markdown(f"""
            <div class="session-card">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <h3 style="margin:0; padding:0;">{filename}</h3>
                    <span style="color:#aaa; font-size:0.9em;">{last_ts}</span>
                </div>
                <div style="margin-top:5px; color:#ddd;">
                    <span class="meta-tag">{'📁 Folder' if is_folder else '📄 File'}</span>
                    <span class="meta-tag">{status_icon}</span>
                </div>
                <div style="font-size:0.85em; color:#888; margin-top:5px; margin-bottom:10px;">
                    Source: {original_path}
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            if not is_finished:
                st.progress(progress_val)

            c1, c2 = st.columns([4, 1])
            with c1:
                btn_label = "🔄 Replay" if is_finished else f"▶️ Resume ({percent_str})"
                if st.button(btn_label, key=f"play_{original_path}", use_container_width=True):
                    idx = None
                    resume_f = None
                    start_sec = 0 if is_finished else last_pos

                    if is_folder:
                        files = get_media_files(original_path)
                        if last_file in files:
                            idx = files.index(last_file)
                            resume_f = last_file
                    
                    # PLAY USING CELLULOID FUNCTION
                    res = play_celluloid(original_path, start_pos=start_sec, playlist_start_index=idx, resume_specific_file=resume_f)
                    
                    if res:
                        all_sessions[original_path].update({
                            "last_played_file": res['path'],
                            "last_played_position": res['position'],
                            "total_duration": res['duration'],
                            "last_played_timestamp": datetime.datetime.now().isoformat()
                        })
                        save_session_data(all_sessions)
                        st.rerun()
            
            with c2:
                if st.button("❌", key=f"del_{original_path}"):
                    del all_sessions[original_path]
                    save_session_data(all_sessions)
                    st.rerun()

# --- Section 3: New Playback ---
with st.sidebar:
    st.header("Controls")
    if st.button("📂 Open Folder", use_container_width=True):
        p = pick_file_or_folder("folder")
        if p: st.session_state['selected_path'] = p
        
    if st.button("📄 Open File", use_container_width=True):
        p = pick_file_or_folder("file")
        if p: st.session_state['selected_path'] = p

    st.markdown("---")
    if st.button("🛑 Stop Server", type="primary", use_container_width=True):
        os._exit(0)

if st.session_state['selected_path']:
    new_path = st.session_state['selected_path']
    st.session_state['selected_path'] = None 
    
    res = play_celluloid(new_path)
    if res:
        all_sessions[new_path] = {
            "is_folder": os.path.isdir(new_path),
            "last_played_file": res['path'],
            "last_played_position": res['position'],
            "total_duration": res['duration'],
            "last_played_timestamp": datetime.datetime.now().isoformat()
        }
        save_session_data(all_sessions)
        st.rerun()