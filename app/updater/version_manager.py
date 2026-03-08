from typing import Tuple, List

class VersionManager:
    """
    Handles version parsing and comparison using Semantic Versioning principles.
    Expected format: "major.minor.patch" (e.g., "1.2.5")
    """
    
    @staticmethod
    def parse_version(version_str: str) -> Tuple[int, int, int]:
        """Parses a version string into a tuple of (major, minor, patch)."""
        try:
            parts = [int(p) for p in version_str.strip().split(".")]
            while len(parts) < 3:
                parts.append(0)
            return (parts[0], parts[1], parts[2])
        except (ValueError, IndexError):
            return (0, 0, 0)

    @staticmethod
    def is_update_available(current_version: str, latest_version: str) -> bool:
        """Compares current version with latest version and returns True if an update is needed."""
        curr = VersionManager.parse_version(current_version)
        late = VersionManager.parse_version(latest_version)
        
        # Simple tuple comparison (major, minor, patch)
        return late > curr

    @staticmethod
    def get_version_display(version_str: str) -> str:
        """Returns a user-friendly version string."""
        return f"v{version_str}"
