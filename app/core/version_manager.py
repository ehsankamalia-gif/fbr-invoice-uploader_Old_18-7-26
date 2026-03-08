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
        major = v.get('major', 1)
        minor = v.get('minor', 0)
        patch = v.get('patch', 0)
        build = v.get('build', 'stable')
        return f"v{major}.{minor}.{patch}-{build}"

    @classmethod
    def is_compatible(cls, remote_version: Dict[str, Any]) -> bool:
        """
        Checks if the remote version is compatible with the current application.
        Compatibility is determined based on major version and API version.
        """
        current = cls.get_current_version()
        
        # Safely extract major version from remote
        remote_major = remote_version.get('major')
        if remote_major is None and 'latest_version' in remote_version:
            try:
                remote_major = int(remote_version['latest_version'].split('.')[0])
            except (ValueError, IndexError):
                remote_major = 1

        # Major version changes indicate breaking changes
        if remote_major is not None and remote_major > current.get('major', 1):
            logger.warning(f"Remote major version ({remote_major}) is greater than current major version ({current.get('major', 1)}). Compatibility not guaranteed.")
            return False
        
        # API version must be compatible
        if remote_version.get('api_version', 1) > current.get('api_version', 1):
            logger.warning(f"Remote API version ({remote_version.get('api_version', 1)}) is greater than current API version ({current.get('api_version', 1)}). Compatibility not guaranteed.")
            return False
            
        return True

    @classmethod
    def needs_update(cls, remote_version: Dict[str, Any]) -> bool:
        """Checks if the remote version is newer than the current version."""
        current = cls.get_current_version()
        
        # Safely extract version components from remote
        if 'major' in remote_version:
            rm, rmi, rp = remote_version['major'], remote_version['minor'], remote_version['patch']
        elif 'latest_version' in remote_version:
            from app.updater.version_manager import VersionManager as ProfessionalVM
            rm, rmi, rp = ProfessionalVM.parse_version(remote_version['latest_version'])
        else:
            return False

        cm, cmi, cp = current.get('major', 1), current.get('minor', 0), current.get('patch', 0)
        
        if rm > cm: return True
        if rm < cm: return False
        
        if rmi > cmi: return True
        if rmi < cmi: return False
        
        if rp > cp: return True
        
        return False
