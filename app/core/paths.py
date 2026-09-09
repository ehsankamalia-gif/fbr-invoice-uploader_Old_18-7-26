"""Single source of truth for filesystem locations.

Running from source, every helper here resolves to the project root - the exact
place these files already live today - so behaviour is unchanged for existing
installs. Only when running as a packaged EXE do writable files move to
%APPDATA%\\EhsanTraderFBR, because an installed app under Program Files cannot
write next to its executable without admin rights.
"""

import os
import sys
from pathlib import Path

APP_FOLDER_NAME = "EhsanTraderFBR"


def is_frozen() -> bool:
    """True when running from a PyInstaller-built executable."""
    return getattr(sys, "frozen", False)


def project_root() -> Path:
    """Source checkout root (app/core/paths.py -> two levels up)."""
    return Path(__file__).resolve().parent.parent.parent


def install_dir() -> Path:
    """Directory holding the running executable (frozen) or the source root."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return project_root()


def resource_dir() -> Path:
    """Read-only bundled resources (assets, templates shipped with the build)."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return install_dir()


def data_dir() -> Path:
    """Writable location for config, logs, and runtime state.

    Source runs keep using the project root so nothing moves for existing
    setups; packaged runs use the per-user AppData folder, which is also where
    the SQLite fallback database already lives.
    """
    if not is_frozen():
        return project_root()

    base = os.getenv("APPDATA") or os.getenv("LOCALAPPDATA") or str(Path.home())
    path = Path(base) / APP_FOLDER_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_path(*parts: str) -> Path:
    """Absolute path to a writable file/dir, creating parent dirs as needed."""
    path = data_dir().joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def resource_path(*parts: str) -> Path:
    """Absolute path to a bundled read-only resource."""
    return resource_dir().joinpath(*parts)


def ensure_runtime_dirs() -> None:
    """Create the working directories the app expects to exist."""
    for name in ("logs", "backups", "temp", "exports"):
        (data_dir() / name).mkdir(parents=True, exist_ok=True)
