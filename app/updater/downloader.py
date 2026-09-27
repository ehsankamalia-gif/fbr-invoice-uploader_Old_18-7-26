import hashlib
import os
import requests
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class Downloader:
    """
    Handles secure HTTPS file downloads with progress monitoring and
    optional SHA-256 integrity verification.
    """

    def __init__(self, download_url: str, dest_path: str, expected_sha256: Optional[str] = None):
        self.download_url = download_url
        self.dest_path = dest_path
        self.expected_sha256 = expected_sha256.lower() if expected_sha256 else None

    def download(self, progress_callback: Optional[Callable[[int, int], None]] = None) -> None:
        """
        Downloads the file from download_url to dest_path, then verifies it
        against expected_sha256 if one was provided (see UpdateChecker -
        checksums are read from a GitHub release's asset digest, a sidecar
        ".sha256" file, or a "checksums.txt", when the release publishes
        one). Raises on any failure - a network error, or a checksum
        mismatch - rather than returning a bare bool, so the caller can
        show the user exactly what went wrong instead of a generic
        "download failed". Never leaves a partial or unverified file behind
        on failure.

        Args:
            progress_callback: Optional function(downloaded_bytes, total_bytes)
        """
        dest_dir = os.path.dirname(self.dest_path)
        if dest_dir and not os.path.exists(dest_dir):
            os.makedirs(dest_dir)

        try:
            response = requests.get(self.download_url, stream=True, timeout=30, verify=True)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0
            chunk_size = 1024 * 64  # 64KB chunks
            hasher = hashlib.sha256()

            with open(self.dest_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        hasher.update(chunk)
                        downloaded_size += len(chunk)

                        if progress_callback:
                            progress_callback(downloaded_size, total_size)

            logger.info(f"Successfully downloaded installer to {self.dest_path}")

            if self.expected_sha256:
                actual = hasher.hexdigest().lower()
                if actual != self.expected_sha256:
                    os.remove(self.dest_path)
                    raise ValueError(
                        "Checksum verification failed - the downloaded installer does not match "
                        "the one published in the release. It may be corrupted or tampered with."
                    )
                logger.info("Installer checksum verified successfully.")
            else:
                logger.warning("No checksum published for this release - skipping integrity verification.")

        except requests.exceptions.RequestException as e:
            if os.path.exists(self.dest_path):
                os.remove(self.dest_path)
            logger.error(f"Download failed: {e}")
            raise RuntimeError(f"Download failed: {e}") from e
        except (OSError, ValueError):
            if os.path.exists(self.dest_path):
                os.remove(self.dest_path)
            raise
        except Exception as e:
            if os.path.exists(self.dest_path):
                os.remove(self.dest_path)
            logger.error(f"Unexpected error during download: {e}")
            raise RuntimeError(f"Unexpected error during download: {e}") from e
