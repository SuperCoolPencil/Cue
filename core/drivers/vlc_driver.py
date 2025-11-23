import subprocess
import socket
import os
import time
import sys
from typing import List
from datetime import datetime

from core.interfaces import IPlayerDriver
from core.domain import PlaybackState

class VlcDriver(IPlayerDriver):
    def __init__(self):
        self.host = '127.0.0.1'
        self.port = 42123 

    def _get_vlc_executable(self):
        """Attempts to find the VLC executable path."""
        # 1. Try simple command (works if in PATH)
        if self._is_command_available("vlc"):
            return "vlc"
            
        # 2. Check common Windows paths
        if sys.platform.startswith('win'):
            paths = [
                r"C:\Program Files\VideoLAN\VLC\vlc.exe",
                r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe"
            ]
            for p in paths:
                if os.path.exists(p):
                    return p
        
        # 3. Check common Mac paths
        if sys.platform == 'darwin':
            path = "/Applications/VLC.app/Contents/MacOS/VLC"
            if os.path.exists(path):
                return path

        return "vlc" # Fallback hope

    def _is_command_available(self, cmd):
        from shutil import which
        return which(cmd) is not None

    def launch(self, playlist: List[str], start_index: int = 0, start_time: float = 0.0) -> PlaybackState:
        if not playlist:
            return PlaybackState()

        effective_playlist = playlist[start_index:]
        
        import random
        self.port = random.randint(40000, 50000)

        vlc_bin = self._get_vlc_executable()

        cmd = [
            vlc_bin,
            "--extraintf=rc", 
            f"--rc-host={self.host}:{self.port}",
            # REMOVED: "--rc-quiet", (Causes crashes on some versions)
            # REMOVED: "--start-paused", (Causes 0s duration deadlock)
            "--no-loop",
            "--no-repeat",
            "--one-instance"
        ]
        cmd.extend(effective_playlist)

        print(f"Launching VLC on port {self.port} using binary: {vlc_bin}")
        
        process = None 
        sock = None
        
        final_position = start_time
        total_duration = 0.0
        is_finished = False
        last_known_title = None 
        current_filename = effective_playlist[0]
        initial_seek_done = False

        try:
            # Launch Process
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,  
                stderr=subprocess.PIPE,     
                text=True                   
            )

            # Connect to Socket
            sock = self._connect_socket(process, timeout=10)
            if not sock:
                if process.poll() is not None:
                    raise ConnectionError(f"VLC crashed on startup.")
                raise ConnectionError("VLC started but RC interface is unreachable.")

            # Monitoring Loop
            while process.poll() is None:
                try:
                    # A. Get Duration
                    # We accept 0 temporarily, but we need > 0 to seek
                    dur_resp = self._send_command(sock, "get_length")
                    try:
                        current_dur = float(dur_resp.strip()) if dur_resp and dur_resp.strip().isdigit() else 0.0
                        if current_dur > 0 and total_duration == 0.0:
                            total_duration = current_dur
                    except ValueError:
                        current_dur = 0.0

                    # B. Initial Seek Logic
                    # We only seek ONCE, and only when we have a valid duration
                    if not initial_seek_done and total_duration > 0:
                        if start_time > 0:
                            print(f"VLC Loaded. Seeking to {int(start_time)}")
                            self._send_command(sock, f"seek {int(start_time)}")
                        
                        # need to send "play" because we removed --start-paused
                        initial_seek_done = True

                    # C. Get Position
                    pos_resp = self._send_command(sock, "get_time")
                    if pos_resp and pos_resp.strip().isdigit():
                        final_position = float(pos_resp.strip())

                    # D. Detect Next Episode
                    title_resp = self._send_command(sock, "get_title")
                    clean_title = title_resp.strip() if title_resp else ""

                    if last_known_title is None and clean_title:
                        last_known_title = clean_title
                    
                    if clean_title and last_known_title and clean_title != last_known_title:
                        print(f"VLC: Next episode detected [{clean_title}]")
                        last_known_title = clean_title
                        current_filename = clean_title
                        total_duration = 0.0 
                        final_position = 0.0
                        # initial_seek_done remains True, so we don't seek the second file

                    time.sleep(1)

                except (BrokenPipeError, ConnectionResetError):
                    break

            if total_duration > 0 and (total_duration - final_position) < 10.0:
                is_finished = True

        except Exception as e:
            print(f"VLC Driver Error: {e}")
            if process and process.poll() is not None:
                try:
                    _, errs = process.communicate(timeout=1)
                    if errs: print(f"VLC Log: {errs}")
                except (ValueError, subprocess.TimeoutExpired):
                    print("Could not retrieve VLC error log.")

        finally:
            if sock: sock.close()
            if process and process.poll() is None:
                try:
                    process.terminate()
                except Exception:
                    pass

        return PlaybackState(
            last_played_file=current_filename,
            position=final_position,
            duration=total_duration,
            is_finished=is_finished,
            timestamp=datetime.now()
        )

    def _connect_socket(self, process, timeout=10):
        start = time.time()
        while time.time() - start < timeout:
            # Check if process is already dead before trying to connect
            if process.poll() is not None:
                return None
            
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect((self.host, self.port))
                s.settimeout(2.0)
                return s
            except ConnectionRefusedError:
                time.sleep(0.5)
        return None

    def _send_command(self, sock, cmd):
        if not sock: return None
        try:
            sock.sendall(f"{cmd}\n".encode('utf-8'))
            data = sock.recv(1024).decode('utf-8')
            lines = data.replace('>', '').split('\n')
            for line in reversed(lines):
                if line.strip():
                    return line.strip()
            return ""
        except (socket.timeout, UnicodeDecodeError):
            return None
        except Exception:
            return None