import subprocess
import socket
import json
import os
import time
import sys
from typing import Optional, List
from datetime import datetime

# Assuming these imports exist in your project structure
from core.interfaces import IPlayerDriver
from core.domain import PlaybackState

class MpvDriver(IPlayerDriver):
    def __init__(self, player_executable_path: str = "mpv"):
        self.player_executable_path = player_executable_path
        self.request_id_counter = 0

    def launch(self, playlist: List[str], start_index: int = 0, start_time: float = 0.0) -> PlaybackState:
        if not playlist:
            return PlaybackState()

        is_windows = sys.platform.startswith('win')
        socket_path = r'\\.\pipe\mpv_socket' if is_windows else f"/tmp/mpv-socket-{os.getpid()}"

        if not is_windows and os.path.exists(socket_path):
            os.remove(socket_path)

        command = [
            self.player_executable_path,
            "--no-terminal",
            f"--input-ipc-server={socket_path}",
            f"--playlist-start={start_index}",
            "--idle=no",
            "--pause",  # 1. Start paused
            "--sub-file-paths=.subs", # Look for subtitles in .subs folder
        ]
        command.extend(playlist)

        print(f"Launching MPV: {' '.join(command)}")
        
        process = subprocess.Popen(command)
        
        final_position = start_time
        total_duration = 0.0
        is_finished = False
        last_played_file = playlist[start_index] if start_index < len(playlist) else playlist[0]

        # Flag to ensure we only seek specifically for the FIRST file
        initial_seek_done = False 

        try:
            ipc = self._connect_ipc(socket_path, is_windows, timeout=5)
            if not ipc:
                raise ConnectionError("Failed to connect to MPV IPC socket.")
            
            while process.poll() is None:
                try:
                    # --- 1. CHECK DURATION FIRST (Required to know if file is loaded) ---
                    # We need to know the duration before we can safely seek.
                    current_dur = None
                    dur_resp = self._send_ipc_command(ipc, ["get_property", "duration"])
                    
                    if dur_resp is not None:
                        try:
                            current_dur = float(dur_resp)
                            # Only update total_duration if we haven't set it for this file yet
                            if total_duration == 0.0:
                                total_duration = current_dur
                        except (ValueError, TypeError):
                            pass

                    # --- 2. HANDLE INITIAL SEEK & UNPAUSE ---
                    # We only do this ONCE, and only after we confirmed the file is loaded (current_dur > 0)
                    if not initial_seek_done and current_dur is not None and current_dur > 0:
                        if start_time > 0:
                            print(f"File loaded. Seeking to {start_time}...")
                            self._send_ipc_command(ipc, ["seek", str(start_time), "absolute"])
                        
                        # Unpause now that we are ready
                        self._send_ipc_command(ipc, ["set_property", "pause", False])
                        initial_seek_done = True

                    # --- 3. DETECT NEXT EPISODE ---
                    current_path = self._send_ipc_command(ipc, ["get_property", "path"])
                    
                    if current_path and current_path != last_played_file:
                        print(f"Next episode detected: {current_path}")
                        last_played_file = current_path
                        total_duration = 0.0 # Reset duration
                        final_position = 0.0 
                        # Note: We do NOT reset initial_seek_done. 
                        # This ensures the 2nd file starts naturally at 00:00.

                    # --- 4. GET POSITION ---
                    pos = self._send_ipc_command(ipc, ["get_property", "time-pos"])
                    if pos is not None:
                        try:
                            final_position = float(pos)
                        except (ValueError, TypeError):
                            pass
                    
                    time.sleep(0.25)
                    
                except (BrokenPipeError, ConnectionResetError):
                    break
            
            if ipc:
                ipc.close()

            if total_duration > 0 and (total_duration - final_position) < 5.0:
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

    def _connect_ipc(self, path, is_windows, timeout=5):
        """Connects to the MPV IPC socket/pipe with a retry mechanism."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                if is_windows:
                    # This is a simplified placeholder. Production Windows support is more complex.
                    pass
                else:
                    if os.path.exists(path):
                        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                        s.connect(path)
                        return s
            except (ConnectionRefusedError, FileNotFoundError):
                time.sleep(0.1) # Wait a bit before retrying
            except Exception as e:
                print(f"Could not connect to IPC: {e}")
                return None
        print(f"IPC connection timed out after {timeout} seconds.")
        return None

    def _send_ipc_command(self, sock, command_list):
        """Sends a JSON command to MPV and waits for the specific response."""
        if not sock: return None
        
        self.request_id_counter += 1
        request_id = self.request_id_counter
        
        message = json.dumps({"command": command_list, "request_id": request_id}) + "\n"
        try:
            sock.sendall(message.encode('utf-8'))
            
            buffer = ""
            sock.settimeout(2.0)
            
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
        except Exception as e:
            print(f"Error sending IPC command or reading response: {e}")
            return None
        return None
