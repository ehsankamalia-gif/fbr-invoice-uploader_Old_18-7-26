import ctypes
import sys
from pathlib import Path


def _show_startup_error(message: str, title: str = "Honda FBR Uploader") -> None:
    try:
        if sys.platform == "win32":
            ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)
            return
    except Exception:
        pass
    print(message, file=sys.stderr)


def bootstrap() -> bool:
    project_root = Path(__file__).resolve().parent.parent
    bootstrap_script = project_root / "app" / "core" / "bootstrap.py"

    if not bootstrap_script.exists():
        return True

    if str(project_root) not in sys.path:
        sys.path.append(str(project_root))

    try:
        from app.core.bootstrap import run_bootstrap

        if not run_bootstrap():
            _show_startup_error(
                "Environment setup failed. Please check the application logs and try again.",
                "Startup Error",
            )
            return False
        return True
    except Exception as exc:
        _show_startup_error(
            f"Failed to initialize the application bootstrapper.\n\n{exc}",
            "Startup Error",
        )
        return False


def main() -> None:
    if not bootstrap():
        raise SystemExit(1)

    from app.qt_main import main as qt_main

    qt_main()


if __name__ == "__main__":
    main()
