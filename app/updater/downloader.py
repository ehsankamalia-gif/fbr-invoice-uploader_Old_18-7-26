import os
import requests
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

class Downloader:
    """
    Handles secure HTTPS file downloads with progress monitoring.
    """
    
    def __init__(self, download_url: str, dest_path: str):
        self.download_url = download_url
        self.dest_path = dest_path

    def download(self, progress_callback: Optional[Callable[[int, int], None]] = None) -> bool:
        """
        Downloads the file from the download_url to dest_path.
        Args:
            progress_callback: Optional function(downloaded_bytes, total_bytes)
        Returns:
            bool: True if download was successful.
        """
        try:
            # Create destination directory if it doesn't exist
            dest_dir = os.path.dirname(self.dest_path)
            if dest_dir and not os.path.exists(dest_dir):
                os.makedirs(dest_dir)

            # Force secure HTTPS and stream the download
            response = requests.get(self.download_url, stream=True, timeout=30, verify=True)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0
            chunk_size = 1024 * 64 # 64KB chunks

            with open(self.dest_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        
                        if progress_callback:
                            progress_callback(downloaded_size, total_size)
                            
            logger.info(f"Successfully downloaded installer to {self.dest_path}")
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Download failed: {e}")
            if os.path.exists(self.dest_path):
                os.remove(self.dest_path)
            return False
        except Exception as e:
            logger.error(f"Unexpected error during download: {e}")
            if os.path.exists(self.dest_path):
                os.remove(self.dest_path)
            return False
