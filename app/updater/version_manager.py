from typing import Tuple, List

class VersionManager:
    """
    Handles version parsing and comparison using Semantic Versioning principles.
    Expected format: "major.minor.patch" (e.g., "1.2.5")
    """
    
    @staticmethod
    def parse_version(version_str: str) -> Tuple[int, int, int]:
        """Parses a version string into (major, minor, patch). Tolerates a
        leading "v"/"V" and extra trailing segments (e.g. a tag like
        "2.55.0.windows.5") by taking the first three numeric dot-separated
        components and ignoring anything after the first non-numeric one -
        rather than failing the whole tag and silently treating it as
        0.0.0, which could hide a genuinely available update just because
        the tag format wasn't the exact "major.minor.patch" this project
        uses for its own version.json."""
        parts: List[int] = []
        for segment in version_str.strip().lstrip("vV").split("."):
            try:
                parts.append(int(segment))
            except ValueError:
                break
            if len(parts) == 3:
                break
        while len(parts) < 3:
            parts.append(0)
        return (parts[0], parts[1], parts[2])

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
