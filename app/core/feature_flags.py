import json
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

class FeatureFlagManager:
    """
    Manages modular feature flags for the application.
    Allows enabling/disabling features without code changes.
    """
    FLAGS_FILE = Path("feature_flags.json")
    DEFAULT_FLAGS = {
        "new_dashboard": False,
        "advanced_reports": False,
        "bulk_sms_v2": False,
        "auto_updates": True,
        "performance_monitoring": True
    }

    @classmethod
    def get_all_flags(cls) -> Dict[str, bool]:
        """Returns all current feature flags."""
        if not cls.FLAGS_FILE.exists():
            cls.save_flags(cls.DEFAULT_FLAGS)
            return cls.DEFAULT_FLAGS
        
        try:
            with open(cls.FLAGS_FILE, "r") as f:
                flags = json.load(f)
                # Merge with defaults to ensure all flags exist
                return {**cls.DEFAULT_FLAGS, **flags}
        except Exception as e:
            logger.error(f"Failed to read feature flags: {e}")
            return cls.DEFAULT_FLAGS

    @classmethod
    def is_enabled(cls, feature_name: str) -> bool:
        """Checks if a specific feature is enabled."""
        flags = cls.get_all_flags()
        return flags.get(feature_name, False)

    @classmethod
    def set_flag(cls, feature_name: str, enabled: bool) -> bool:
        """Sets the state of a feature flag."""
        flags = cls.get_all_flags()
        flags[feature_name] = enabled
        return cls.save_flags(flags)

    @classmethod
    def save_flags(cls, flags: Dict[str, bool]) -> bool:
        """Saves feature flags to the configuration file."""
        try:
            with open(cls.FLAGS_FILE, "w") as f:
                json.dump(flags, f, indent=4)
            return True
        except Exception as e:
            logger.error(f"Failed to save feature flags: {e}")
            return False
