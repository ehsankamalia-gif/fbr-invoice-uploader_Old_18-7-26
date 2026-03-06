import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class VersionManager:
    """
    Manages the application version and compatibility checks.
    """
    VERSION_FILE = Path("version.json")
    DEFAULT_VERSION = {
        "major": 1,
        "minor": 0,
        "patch": 0,
        "build": "stable",
        "api_version": 1,
        "db_version": 1
    }

    @classmethod
    def get_current_version(cls) -> Dict[str, Any]:
        """Reads the current version from the version.json file."""
        if not cls.VERSION_FILE.exists():
            cls.save_version(cls.DEFAULT_VERSION)
            return cls.DEFAULT_VERSION
        
        try:
            with open(cls.VERSION_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read version file: {e}")
            return cls.DEFAULT_VERSION

    @classmethod
    def save_version(cls, version_data: Dict[str, Any]) -> bool:
        """Saves the version data to the version.json file."""
        try:
            with open(cls.VERSION_FILE, "w") as f:
                json.dump(version_data, f, indent=4)
            return True
        except Exception as e:
            logger.error(f"Failed to save version file: {e}")
            return False

    @classmethod
    def get_version_string(cls) -> str:
        """Returns the version as a formatted string."""
        v = cls.get_current_version()
        return f"v{v['major']}.{v['minor']}.{v['patch']}-{v['build']}"

    @classmethod
    def is_compatible(cls, remote_version: Dict[str, Any]) -> bool:
        """
        Checks if the remote version is compatible with the current application.
        Compatibility is determined based on major version and API version.
        """
        current = cls.get_current_version()
        
        # Major version changes indicate breaking changes
        if remote_version['major'] > current['major']:
            logger.warning(f"Remote major version ({remote_version['major']}) is greater than current major version ({current['major']}). Compatibility not guaranteed.")
            return False
        
        # API version must be compatible
        if remote_version.get('api_version', 1) > current.get('api_version', 1):
            logger.warning(f"Remote API version ({remote_version['api_version']}) is greater than current API version ({current['api_version']}). Compatibility not guaranteed.")
            return False
            
        return True

    @classmethod
    def needs_update(cls, remote_version: Dict[str, Any]) -> bool:
        """Checks if the remote version is newer than the current version."""
        current = cls.get_current_version()
        
        if remote_version['major'] > current['major']: return True
        if remote_version['major'] < current['major']: return False
        
        if remote_version['minor'] > current['minor']: return True
        if remote_version['minor'] < current['minor']: return False
        
        if remote_version['patch'] > current['patch']: return True
        
        return False
