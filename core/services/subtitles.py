import os
import shutil
import subprocess
import requests
from typing import List, Tuple, Optional
from core.domain import Session
from core.providers.subtitle_provider import get_subtitle_provider, get_all_providers, SubtitleInfo

class SubtitleService:
    """
    Handles subtitle searching, downloading, and synchronization.
    """
    
    def search_subtitles(self, session: Session, series_files: List[str] = None) -> List[SubtitleInfo]:
        """Search for subtitles for the current file."""
        # Determine actual file path (helper for series)
        filepath = session.filepath
        if series_files and session.playback.last_played_index < len(series_files):
            filepath = series_files[session.playback.last_played_index]
            
        if not os.path.exists(filepath):
            return []
            
        # Query all providers
        print(f"DEBUG: Searching subtitles for {os.path.basename(filepath)}...")
        all_results = []
        for provider in get_all_providers():
            if provider.is_configured:
                try:
                    all_results.extend(provider.search(filepath))
                except Exception as e:
                    print(f"Error searching provider {type(provider).__name__}: {e}")
                    
        # Sort by hash match (True first), then download count (desc)
        all_results.sort(key=lambda x: (x.is_hash_match, x.download_count), reverse=True)
        return all_results

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
        # 0. Check if exists
        media_dir = os.path.dirname(filepath)
        media_name = os.path.splitext(os.path.basename(filepath))[0]
        sub_path = os.path.join(media_dir, ".subs", f"{media_name}.srt")
        if os.path.exists(sub_path):
            return True, "Subtitle already exists"

        # 1. Search (uses all providers)
        results = self.search_subtitles(Session(filepath, None, None), series_files=[filepath]) # Hacky session reconstruction or specialized search
        # Better: use helper search method logic without full session if needed, 
        # but self.search_subtitles requires session.
        # Let's just call providers directly or refactor search_subtitles.
        # Actually search_subtitles takes session just for filepath logic.
        # Let's refactor search_subtitles to take filepath optional?
        # For now, let's just duplicate the loop or construct a dummy session.
        # Duplicate loop is cleaner for now.
        
        provider_results = []
        for provider in get_all_providers():
            if provider.is_configured:
                 try:
                    provider_results.extend(provider.search(filepath))
                 except: pass
                 
        if not provider_results:
            return False, "No subtitles found"
            
        # Sort: Hash matches first
        provider_results.sort(key=lambda x: (x.is_hash_match, x.download_count), reverse=True)
        best_sub = provider_results[0]
        
        return self.download_subtitle(Session(filepath, None, None), best_sub.id, series_files=[filepath])

    def batch_download_subtitles(self, session: Session, series_files: List[str] = None, on_progress=None) -> Tuple[int, int, List[str]]:
        """
        Downloads and syncs subtitles for all files in a session (folder).
        Returns: (success_count, fail_count, logs)
        """
        def log(msg):
            logs.append(msg)
            if on_progress:
                on_progress(msg)

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
            log(f"Processing: {filename}")
            
            # 1. Download
            ok, msg = self.download_best_subtitle(filepath)
            if not ok:
                log(f"  ❌ Download failed: {msg}")
                fail_count += 1
                continue
            log(f"  ✅ {msg}")
            
            # 2. Sync
            ok_sync, msg_sync = self._sync_single_file(filepath)
            if ok_sync:
                log(f"  ✅ Synced")
            else:
                log(f"  ⚠️ Sync skipped/failed: {msg_sync}")
                
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
        # Determine provider based on ID
        selected_provider = None
        
        if subtitle_id.startswith("subdb:"):
            # Find SubDB provider
            for p in get_all_providers():
                if "SubDBProvider" in str(type(p)):
                    selected_provider = p
                    break
        else:
            # Assume OpenSubtitles (default)
            selected_provider = get_subtitle_provider()
            
        if not selected_provider or not selected_provider.is_configured:
            return False, "Provider not configured or found"
            
        # Get download link
        data, error = selected_provider.download(subtitle_id)
        if error:
            return False, f"Download failed: {error}"
            
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
