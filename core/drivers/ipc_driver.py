import subprocess
import socket
import json
import os
import time
import sys
from typing import List
from datetime import datetime

# Assuming these imports exist in your project structure
from core.interfaces import IPlayerDriver
from core.domain import PlaybackState

class PlayerDriver(IPlayerDriver):
    def __init__(self, executable_path: str = "celluloid"):
        self.executable_path = executable_path
        self.request_id_counter = 0

    def launch(self, playlist: List[str], start_index: int = 0, start_time: float = 0.0) -> PlaybackState:
        if not playlist:
            return PlaybackState()

        is_windows = sys.platform.startswith('win')
        socket_path = r'\\.\pipe\mpv_socket' if is_windows else f"/tmp/mpv-socket-{os.getpid()}"

        if not is_windows and os.path.exists(socket_path):
            os.remove(socket_path)

        # --- 1. COMMAND SETUP ---
        # We start paused so the user doesn't hear Ep1 start playing for a split second
        mpv_engine_flags = [
            f"--input-ipc-server={socket_path}",
            "--idle=yes",
            "--pause" 
        ]

        final_command = []
        if "celluloid" in self.executable_path.lower():
            mpv_opts_string = " ".join(mpv_engine_flags)
            final_command = [
                self.executable_path,
                "--new-window", 
                f"--mpv-options={mpv_opts_string}"
            ]
            final_command.extend(playlist)
        else:
            final_command = [self.executable_path, "--no-terminal"] + mpv_engine_flags + playlist

        print(f"Launching Player...")
        process = subprocess.Popen(final_command)
        
        # State tracking
        final_position = start_time
        total_duration = 0.0
        is_finished = False
        last_played_file = playlist[0] 

        # --- 2. THE STARTUP STATE MACHINE ---
        # Phases:
        # 0. WAIT_PLAYLIST_LOAD: Wait until MPV knows it has X files.
        # 1. FORCE_INDEX: Tell MPV to switch to start_index.
        # 2. WAIT_FILE_LOAD: Wait for that specific file to report a duration.
        # 3. SEEK_AND_PLAY: Jump to time and unpause.
        startup_phase = "WAIT_PLAYLIST_LOAD"
        
        # Safety timeout to prevent infinite loops if playlist loading fails
        startup_start_time = time.time()
        
        try:
            # Give Celluloid a bit more time to breathe on startup (timeout=15s)
            ipc = self._connect_ipc(socket_path, is_windows, timeout=15)
            if not ipc:
                raise ConnectionError("Failed to connect to IPC socket.")
            
            while process.poll() is None:
                try:
                    # --- A. ALWAYS GET VITAL STATS ---
                    # We need these to return valid state even if we crash/exit
                    curr_path = self._send_ipc_command(ipc, ["get_property", "path"])
                    curr_pos = self._send_ipc_command(ipc, ["get_property", "time-pos"])
                    
                    # Update file tracking
                    if curr_path:
                        matched_file = next((f for f in playlist if f in curr_path or curr_path in f), None)
                        if matched_file:
                            last_played_file = matched_file

                    # Update position tracking
                    if curr_pos is not None:
                        try: final_position = float(curr_pos)
                        except: pass

                    # --- B. STARTUP SEQUENCE ---
                    if startup_phase != "DONE":
                        
                        # Phase 0: Wait for Playlist Population
                        if startup_phase == "WAIT_PLAYLIST_LOAD":
                            # Ask MPV: "How many files do you see?"
                            count_resp = self._send_ipc_command(ipc, ["get_property", "playlist-count"])
                            if count_resp is not None:
                                count = int(count_resp)
                                # We need at least enough files to reach our index
                                if count > start_index:
                                    print(f"Playlist loaded ({count} files). Moving to index switch.")
                                    startup_phase = "FORCE_INDEX"
                                else:
                                    # Still loading files... wait.
                                    pass

                        # Phase 1: Force Index Switch
                        elif startup_phase == "FORCE_INDEX":
                            idx_resp = self._send_ipc_command(ipc, ["get_property", "playlist-pos"])
                            if idx_resp is not None and int(idx_resp) != start_index:
                                print(f"Switching from Index {idx_resp} to {start_index}...")
                                self._send_ipc_command(ipc, ["set_property", "playlist-pos", start_index])
                                time.sleep(0.5) # Allow switch to happen
                            elif idx_resp is not None and int(idx_resp) == start_index:
                                # We are at the right index
                                startup_phase = "WAIT_FILE_LOAD"

                        # Phase 2: Wait for Duration (File Load)
                        elif startup_phase == "WAIT_FILE_LOAD":
                            dur_resp = self._send_ipc_command(ipc, ["get_property", "duration"])
                            if dur_resp is not None:
                                try:
                                    d = float(dur_resp)
                                    if d > 0:
                                        total_duration = d
                                        startup_phase = "SEEK_AND_PLAY"
                                except: pass
                        
                        # Phase 3: Seek & Unpause
                        elif startup_phase == "SEEK_AND_PLAY":
                            if start_time > 0:
                                print(f"Seeking to {start_time}s...")
                                self._send_ipc_command(ipc, ["seek", str(start_time), "absolute"])
                            
                            print("Resuming playback.")
                            self._send_ipc_command(ipc, ["set_property", "pause", False])
                            startup_phase = "DONE"

                        # Timeout safeguard (15 seconds max for startup logic)
                        if time.time() - startup_start_time > 15:
                            print("Startup sequence timed out. Force unpausing.")
                            self._send_ipc_command(ipc, ["set_property", "pause", False])
                            startup_phase = "DONE"

                    # --- C. NORMAL PLAYBACK ---
                    else:
                        dur_resp = self._send_ipc_command(ipc, ["get_property", "duration"])
                        if dur_resp:
                            try: total_duration = float(dur_resp)
                            except: pass
                    
                    time.sleep(0.25) # Faster polling during startup
                    
                except (BrokenPipeError, ConnectionResetError):
                    break
            
            if ipc: ipc.close()

            # Finished check
            if total_duration > 0 and (total_duration - final_position) < 10.0:
                is_finished = True

        except Exception as e:
            print(f"IPC Error: {e}")
        finally:
            if process.poll() is None:
                process.terminate()
            if not is_windows and os.path.exists(socket_path):
                os.remove(socket_path)

        return PlaybackState(
            last_played_file=last_played_file,
            position=final_position,
            duration=total_duration,
            is_finished=is_finished,
            timestamp=datetime.now()
        )

    # (Keep _connect_ipc and _send_ipc_command exactly as they were in the previous step)
    def _connect_ipc(self, path, is_windows, timeout=5):
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                if is_windows:
                    time.sleep(1)
                    pass
                else:
                    if os.path.exists(path):
                        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                        s.connect(path)
                        return s
            except (ConnectionRefusedError, FileNotFoundError):
                time.sleep(0.2)
            except Exception as e:
                print(f"Could not connect to IPC: {e}")
                return None
        return None

    def _send_ipc_command(self, sock, command_list):
        if not sock: return None
        self.request_id_counter += 1
        request_id = self.request_id_counter
        
        message = json.dumps({"command": command_list, "request_id": request_id}) + "\n"
        try:
            sock.sendall(message.encode('utf-8'))
            sock.settimeout(2.0)
            buffer = ""
            
            while True:
                try:
                    chunk = sock.recv(4096).decode('utf-8')
                    if not chunk: return None
                    buffer += chunk
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        if not line: continue
                        try:
                            resp = json.loads(line)
                            if resp.get("request_id") == request_id:
                                return resp.get("data") if resp.get("error") == "success" else None
                        except json.JSONDecodeError:
                            pass
                except socket.timeout:
                    return None
        except Exception:
            return None
        return None