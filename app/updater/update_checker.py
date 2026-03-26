import requests
import logging
import datetime as dt
from typing import Optional, Dict, Any
from .version_manager import VersionManager

logger = logging.getLogger(__name__)

class UpdateChecker:
    """
    Handles fetching and validating version.json from a remote server (e.g., Bitbucket).
    """
    
    def __init__(self, version_url: str, auth: Optional[tuple] = None):
        """
        Args:
            version_url: URL to version.json (e.g., Bitbucket raw URL)
            auth: Optional tuple (username, app_password) for private repositories
        """
        self.version_url = version_url
        self.auth = auth

    def fetch_latest_info(self, timeout: int = 15) -> Optional[Dict[str, Any]]:
        """
        Fetches the version.json from the remote server via HTTPS.
        Supports authentication for private Bitbucket repositories.
        """
        try:
            # Bitbucket Raw URLs sometimes need a 'nocache' parameter or specific headers 
            # to ensure we don't get a stale version.json
            params = {"t": dt.datetime.now().timestamp()} if "bitbucket.org" in self.version_url else {}
            
            response = requests.get(
                self.version_url, 
                params=params,
                auth=self.auth,
                timeout=timeout, 
                verify=True
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Validate required fields
            required_fields = ["latest_version", "download_url", "changelog", "release_date"]
            if all(field in data for field in required_fields):
                return data
            else:
                logger.error("version.json is missing required fields.")
                return None
                
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                # If it's a 404, we just log a concise warning instead of the full error
                logger.warning(f"Update check skipped: Remote version.json not found (HTTP 404).")
            else:
                logger.error(f"Failed to fetch version.json (HTTP {e.response.status_code}): {e}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch version.json: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in UpdateChecker: {e}")
            return None

    def check_for_update(self, current_version: str) -> Optional[Dict[str, Any]]:
        """
        Check if a new version is available.
        If yes, returns the latest info dictionary; otherwise returns None.
        """
        latest_info = self.fetch_latest_info()
        if latest_info:
            latest_ver = latest_info.get("latest_version")
            if VersionManager.is_update_available(current_version, latest_ver):
                return latest_info
        return None
