import os
import shutil
import subprocess
import requests
from typing import List, Tuple, Optional
from core.domain import Session
from core.providers.subtitle_provider import get_subtitle_provider, SubtitleInfo

class SubtitleService:
    """
    Handles subtitle searching, downloading, and synchronization.
    """
    
    def search_subtitles(self, session: Session, series_files: List[str] = None) -> List[SubtitleInfo]:
        """Search for subtitles for the current file."""
        provider = get_subtitle_provider()
        if not provider.is_configured:
            return []
            
        # Determine actual file path (helper for series)
        filepath = session.filepath
        if series_files and session.playback.last_played_index < len(series_files):
            filepath = series_files[session.playback.last_played_index]
            
        if not os.path.exists(filepath):
            return []
            
        return provider.search(filepath)

    def _download_to_path(self, download_url: str, filepath: str) -> Tuple[bool, str]:
        """Helper to download a subtitle URL to the correct location for a video file."""
        media_dir = os.path.dirname(filepath)
        media_name = os.path.splitext(os.path.basename(filepath))[0]
        
        # Create .subs directory if it doesn't exist
        subs_dir = os.path.join(media_dir, ".subs")
        os.makedirs(subs_dir, exist_ok=True)
        
        # Save as .subs/[media_name].srt
        target_path = os.path.join(subs_dir, f"{media_name}.srt")
        
        try:
            print(f"Downloading subtitle to {target_path}...")
            r = requests.get(download_url)
            r.raise_for_status()
            
            with open(target_path, 'wb') as f:
                f.write(r.content)
                
            return True, f"Downloaded to .subs/{os.path.basename(target_path)}"
        except Exception as e:
            return False, f"Download failed: {str(e)}"
    
    def download_best_subtitle(self, filepath: str) -> Tuple[bool, str]:
        """
        Automatically finds and downloads the best subtitle for a specific file.
        """
        provider = get_subtitle_provider()
        if not provider.is_configured:
            return False, "Provider not configured"
            
        # 1. Search
        results = provider.search(filepath)
        if not results:
            return False, "No subtitles found"
            
        # 2. Pick Best (already sorted by hash match then download count)
        best_sub = results[0]
        
        # 3. Get Link
        data = provider.download(best_sub.id)
        if not data or 'link' not in data:
            return False, "Failed to get download link"
            
        # 4. Download
        return self._download_to_path(data['link'], filepath)

    def batch_download_subtitles(self, session: Session, series_files: List[str] = None) -> Tuple[int, int, List[str]]:
        """
        Downloads and syncs subtitles for all files in a session (folder).
        Returns: (success_count, fail_count, logs)
        """
        files_to_process = series_files
        if not files_to_process:
            # Maybe it's a single file session
            if os.path.exists(session.filepath) and os.path.isfile(session.filepath):
                files_to_process = [session.filepath]
            else:
                return 0, 0, ["No files found to process"]
        
        success_count = 0
        fail_count = 0
        logs = []
        
        for filepath in files_to_process:
            filename = os.path.basename(filepath)
            logs.append(f"Processing: {filename}")
            
            # 1. Download
            ok, msg = self.download_best_subtitle(filepath)
            if not ok:
                logs.append(f"  ❌ Download failed: {msg}")
                fail_count += 1
                continue
            logs.append(f"  ✅ {msg}")
            
            # 2. Sync
            ok_sync, msg_sync = self._sync_single_file(filepath)
            if ok_sync:
                logs.append(f"  ✅ Synced")
            else:
                logs.append(f"  ⚠️ Sync skipped/failed: {msg_sync}")
                
            success_count += 1
            
        return success_count, fail_count, logs

    def _sync_single_file(self, video_path: str) -> Tuple[bool, str]:
        """Runs ffsubsync on a single video file's subtitle."""
        if not shutil.which("ffsubsync"):
            return False, "ffsubsync missing"
            
        media_dir = os.path.dirname(video_path)
        media_name = os.path.splitext(os.path.basename(video_path))[0]
        subs_dir = os.path.join(media_dir, ".subs")
        sub_path = os.path.join(subs_dir, f"{media_name}.srt")
        
        if not os.path.exists(sub_path):
            return False, "No subtitle file found"
            
        try:
            cmd = ["ffsubsync", video_path, "-i", sub_path, "-o", sub_path]
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return True, "Synced"
        except Exception as e:
            return False, str(e)

    def download_subtitle(self, session: Session, subtitle_id: str, series_files: List[str] = None) -> Tuple[bool, str]:
        """
        Download a subtitle and save it into a .subs folder next to the media file.
        Returns: (Success, Message)
        """
        provider = get_subtitle_provider()
        if not provider.is_configured:
            return False, "Provider not configured"
            
        # Get download link
        data = provider.download(subtitle_id)
        if not data or 'link' not in data:
            return False, "Failed to get download link"
            
        download_url = data['link']
        
        # Determine target path
        filepath = session.filepath
        if series_files and session.playback.last_played_index < len(series_files):
            filepath = series_files[session.playback.last_played_index]
            
        return self._download_to_path(download_url, filepath)

    def sync_subtitles(self, session: Session, series_files: List[str] = None) -> Tuple[bool, str]:
        """
        Run ffsubsync on the current file's subtitle.
        """
        # Check if ffsubsync is installed
        if not shutil.which("ffsubsync"):
            return False, "ffsubsync not found. Please install it: 'pip install ffsubsync'"
            
        # Determine target path
        filepath = session.filepath
        
        files_to_sync = []
        if series_files:
            files_to_sync = series_files
        else:
            files_to_sync = [filepath]
            
        success_count = 0
        error_count = 0
        
        for video_path in files_to_sync:
            media_dir = os.path.dirname(video_path)
            media_name = os.path.splitext(os.path.basename(video_path))[0]
            subs_dir = os.path.join(media_dir, ".subs")
            sub_path = os.path.join(subs_dir, f"{media_name}.srt")
            
            if not os.path.exists(sub_path):
                continue
                
            try:
                print(f"Syncing subtitle for {video_path}...")
                cmd = ["ffsubsync", video_path, "-i", sub_path, "-o", sub_path]
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                success_count += 1
            except subprocess.CalledProcessError as e:
                media_name = os.path.splitext(os.path.basename(video_path))[0]
                print(f"Error syncing {media_name}: {e}")
                error_count += 1
            except Exception as e:
                media_name = os.path.splitext(os.path.basename(video_path))[0]
                print(f"Unexpected error syncing {media_name}: {e}")
                error_count += 1
                
        if success_count == 0 and error_count == 0:
            return False, "No subtitles found to sync"
        elif error_count > 0:
            return True, f"Synced {success_count} files, {error_count} failed"
        else:
            return True, f"Successfully synced {success_count} subtitles"
