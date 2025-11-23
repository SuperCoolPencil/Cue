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

        # --- COMMAND SETUP ---
        final_command = []
        
        if "celluloid" in self.executable_path.lower():
            # CELLULOID SPECIFIC: Must use --mpv- prefix for all mpv options
            final_command = [
                self.executable_path, 
                "--new-window",
                # Syntax: --mpv-OPTION=VALUE
                f"--mpv-input-ipc-server={socket_path}",
                "--mpv-idle=yes",
                "--mpv-pause" 
            ]
            final_command.extend(playlist)
        else:
            # STANDARD MPV: Uses standard flags
            mpv_engine_flags = [
                f"--input-ipc-server={socket_path}",
                "--idle=yes",
                "--pause"
            ]
            final_command = [self.executable_path, "--no-terminal"] + mpv_engine_flags + playlist

        print(f"Launching Player with command: {final_command}")
        process = subprocess.Popen(final_command)

        final_position = start_time
        total_duration = 0.0
        is_finished = False
        last_played_file = playlist[0] 

        # STARTUP STATE MACHINE
        startup_phase = "WAIT_PLAYLIST_LOAD"
        startup_start_time = time.time()
        
        try:
            ipc = self._connect_ipc(socket_path, is_windows, timeout=15)
            if not ipc: raise ConnectionError("Failed to connect to IPC socket.")
            
            while process.poll() is None:
                try:
                    # --- 1. ALWAYS UPDATE POSITION ---
                    curr_pos = self._send_ipc_command(ipc, ["get_property", "time-pos"])
                    if curr_pos is not None:
                        try: final_position = float(curr_pos)
                        except (ValueError, TypeError): pass

                    # --- 2. ALWAYS UPDATE DURATION (THE FIX) ---
                    # We check this EVERY LOOP. Even if we already have it.
                    # This ensures if it starts at 0, it eventually corrects itself.
                    dur_resp = self._send_ipc_command(ipc, ["get_property", "duration"])
                    if dur_resp is not None:
                        try:
                            d = float(dur_resp)
                            print(f"DEBUG: IPC Driver - Raw Duration: {dur_resp}, Float Duration: {d}, Current total_duration: {total_duration}")
                            if d > 0: # Update if any positive duration is reported
                                total_duration = d
                        except (ValueError, TypeError):
                            print(f"DEBUG: IPC Driver - Error converting duration '{dur_resp}' to float.")
                            pass

                    # --- 3. TRACK FILE CHANGES ---
                    curr_path = self._send_ipc_command(ipc, ["get_property", "path"])
                    if curr_path:
                        matched_file = next((f for f in playlist if f in curr_path or curr_path in f), None)
                        if matched_file and matched_file != last_played_file:
                            print(f"DEBUG: IPC Driver - File changed from '{last_played_file}' to '{matched_file}'. Resetting duration.")
                            last_played_file = matched_file
                            # Crucial: If file changed, reset duration so we don't carry over old file's length
                            total_duration = 0.0 

                    # --- 4. STARTUP LOGIC ---
                    if startup_phase != "DONE":
                        
                        # Phase 0: Wait for Playlist
                        if startup_phase == "WAIT_PLAYLIST_LOAD":
                            count_resp = self._send_ipc_command(ipc, ["get_property", "playlist-count"])
                            if count_resp and int(count_resp) > start_index:
                                startup_phase = "FORCE_INDEX"

                        # Phase 1: Force Index
                        elif startup_phase == "FORCE_INDEX":
                            idx_resp = self._send_ipc_command(ipc, ["get_property", "playlist-pos"])
                            if idx_resp is not None and int(idx_resp) != start_index:
                                self._send_ipc_command(ipc, ["set_property", "playlist-pos", start_index])
                                time.sleep(0.5)
                            elif idx_resp is not None and int(idx_resp) == start_index:
                                startup_phase = "WAIT_FILE_LOAD"

                        # Phase 2: Wait for Duration (File Ready)
                        elif startup_phase == "WAIT_FILE_LOAD":
                            # We already updated total_duration in step 2 above.
                            # Just check if it's valid now.
                            if total_duration > 0: # Ensure duration is > 0 to be considered valid
                                startup_phase = "SEEK_AND_PLAY"
                        
                        # Phase 3: Seek & Unpause
                        elif startup_phase == "SEEK_AND_PLAY":
                            if start_time > 0 and total_duration > 0: # Only seek if duration is known and start_time > 0
                                print(f"Seeking to {start_time}s...")
                                self._send_ipc_command(ipc, ["seek", str(start_time), "absolute"])
                                # Wait a moment for seek to apply before unpausing
                                time.sleep(0.5)
                            
                            print("Resuming playback.")
                            self._send_ipc_command(ipc, ["set_property", "pause", False])
                            startup_phase = "DONE"

                        # Timeout safeguard
                        if time.time() - startup_start_time > 15:
                            startup_phase = "DONE" # Give up and let user control

                    
                    time.sleep(0.5)
                    
                except (BrokenPipeError, ConnectionResetError):
                    break
            
            if ipc: ipc.close()

            # Finished calculation
            if total_duration > 0 and (total_duration - final_position) < 10.0:
                is_finished = True

        except Exception as e:
            print(f"IPC Error: {e}")
        finally:
            if process.poll() is None: process.terminate()
            if not is_windows and os.path.exists(socket_path): os.remove(socket_path)

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
                        print("Connected to IPC socket.")
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
