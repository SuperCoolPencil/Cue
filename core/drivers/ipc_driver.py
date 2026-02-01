import subprocess
import socket
import json
import os
import time
import sys
import logging
from typing import List, Optional, Any, Dict
from datetime import datetime

from core.interfaces import IPlayerDriver
from core.domain import PlaybackState

logger = logging.getLogger(__name__)

class PlayerDriver(IPlayerDriver):
    def __init__(self, executable_path: str = "celluloid"):
        self.executable_path = executable_path
        self.request_id = 0
        self._is_windows = sys.platform.startswith('win')

    def launch(self, playlist: List[str], start_index: int = 0, start_time: float = 0.0) -> PlaybackState:
        if not playlist:
            return PlaybackState()

        # 1. Setup Socket Path
        socket_path = self._get_socket_path()
        self._cleanup_socket(socket_path)

        # 2. Build and Start Process
        command = self._build_command(playlist, socket_path)
        logger.info(f"Launching player: {command}")
        
        process = subprocess.Popen(command)
        
        # 3. State Variables
        state = {
            "last_file": playlist[0],
            "position": start_time,
            "duration": 0.0,
            "finished": False
        }
        
        ipc_conn = None
        startup_complete = False
        start_wait_time = time.time()

        try:
            # 4. Connect IPC
            ipc_conn = self._connect_to_ipc(socket_path)
            if not ipc_conn:
                raise ConnectionError("Failed to establish IPC connection.")

            # 5. Main Monitoring Loop
            while process.poll() is None:
                try:
                    # A. Update Playback Metrics
                    self._update_playback_metrics(ipc_conn, state, playlist)

                    # B. Handle Startup (Index + Seek)
                    if not startup_complete:
                        startup_complete = self._handle_startup_sequence(
                            ipc_conn, start_index, start_time, state["duration"], start_wait_time
                        )

                    # C. Loop throttling
                    time.sleep(0.5)

                except (BrokenPipeError, ConnectionResetError):
                    break

            # 6. Finalize State
            if state["duration"] > 0 and (state["duration"] - state["position"]) < 10.0:
                state["finished"] = True

        except Exception as e:
            logger.error(f"Player Error: {e}")
        finally:
            if ipc_conn:
                ipc_conn.close()
            if process.poll() is None:
                process.terminate()
            self._cleanup_socket(socket_path)

        return PlaybackState(
            last_played_file=state["last_file"],
            position=state["position"],
            duration=state["duration"],
            is_finished=state["finished"]
        )

    # --- Helper Methods ---

    def _get_socket_path(self) -> str:
        if self._is_windows:
            return r'\\.\pipe\mpv_socket'
        return f"/tmp/mpv-socket-{os.getpid()}"

    def _cleanup_socket(self, path: str):
        if not self._is_windows and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

    def _build_command(self, playlist: List[str], socket_path: str) -> List[str]:
        """Constructs the command line arguments based on the player."""
        is_celluloid = "celluloid" in self.executable_path.lower()
        
        if is_celluloid:
            # Celluloid requires --mpv- prefix
            flags = [
                "--new-window",
                f"--mpv-input-ipc-server={socket_path}",
                "--mpv-idle=yes",
                "--mpv-sub-file-paths=.subs",
                "--mpv-pause"
            ]
        else:
            # Standard MPV
            flags = [
                "--no-terminal",
                f"--input-ipc-server={socket_path}",
                "--idle=yes",
                "--sub-file-paths=.subs",
                "--pause"
            ]
            
        return [self.executable_path] + flags + playlist

    def _connect_to_ipc(self, socket_path: str, timeout: int = 15) -> Optional[socket.socket]:
        """Attempts to connect to the IPC socket within a timeout."""
        start = time.time()
        while time.time() - start < timeout:
            if os.path.exists(socket_path):
                try:
                    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    sock.connect(socket_path)
                    return sock
                except (ConnectionRefusedError, FileNotFoundError, OSError):
                    pass
            time.sleep(0.2)
        return None

    def _update_playback_metrics(self, ipc, state: Dict, playlist: List[str]):
        """Fetches time, duration, and current file path from MPV."""
        # 1. Position
        pos = self._send_ipc(ipc, ["get_property", "time-pos"])
        if pos is not None:
            try: state["position"] = float(pos)
            except (ValueError, TypeError): pass

        # 2. Duration
        dur = self._send_ipc(ipc, ["get_property", "duration"])
        if dur is not None:
            try:
                d = float(dur)
                if d > 0: state["duration"] = d
            except (ValueError, TypeError): pass

        # 3. File Change Detection
        curr_path = self._send_ipc(ipc, ["get_property", "path"])
        if curr_path:
            matched = next((f for f in playlist if f in curr_path or curr_path in f), None)
            if matched and matched != state["last_file"]:
                state["last_file"] = matched
                state["duration"] = 0.0  # Reset duration on file change

    def _handle_startup_sequence(self, ipc, target_index: int, target_time: float, 
                               current_duration: float, start_ts: float) -> bool:
        """
        Manages the startup: Force Index -> Wait for Load -> Seek -> Unpause.
        Returns True when startup is complete.
        """
        # Safety Timeout (15s)
        if time.time() - start_ts > 15:
            self._send_ipc(ipc, ["set_property", "pause", False])
            return True

        # 1. Check Playlist Index
        idx_resp = self._send_ipc(ipc, ["get_property", "playlist-pos"])
        if idx_resp is not None:
            current_idx = int(idx_resp)
            if current_idx != target_index:
                self._send_ipc(ipc, ["set_property", "playlist-pos", target_index])
                return False # Keep waiting until index matches

        # 2. Wait for File Load (Duration > 0)
        if current_duration <= 0:
            return False # Keep waiting for metadata

        # 3. Seek and Unpause
        if target_time > 0:
            self._send_ipc(ipc, ["seek", str(target_time), "absolute"])
            #time.sleep(0.2) # Brief buffer for seek

        self._send_ipc(ipc, ["set_property", "pause", False])
        return True

    def _send_ipc(self, sock: socket.socket, command: List[Any]) -> Any:
        """Sends a JSON command to the socket and retrieves the data payload."""
        if not sock: return None
        
        self.request_id += 1
        req_id = self.request_id
        payload = json.dumps({"command": command, "request_id": req_id}) + "\n"

        try:
            sock.sendall(payload.encode('utf-8'))
            sock.settimeout(1.0)
            
            buffer = ""
            while True:
                chunk = sock.recv(4096).decode('utf-8')
                if not chunk: break
                buffer += chunk
                
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if not line: continue
                    try:
                        resp = json.loads(line)
                        if resp.get("request_id") == req_id and resp.get("error") == "success":
                            return resp.get("data")
                    except json.JSONDecodeError:
                        continue
        except (socket.timeout, BrokenPipeError, OSError):
            return None
        return None