import threading
import logging
import logging.config
import socket
import sys
import time
from pathlib import Path
from typing import Optional, Tuple


logger = logging.getLogger(__name__)

_start_lock = threading.Lock()
_server_thread: threading.Thread | None = None
_last_startup_error: Optional[str] = None
_server_thread_exception: Optional[str] = None
_STARTUP_TIMEOUT_SECONDS = 15.0


def get_last_startup_error() -> Optional[str]:
    """Return the last startup error message, or None if startup succeeded."""
    return _last_startup_error


def get_server_thread_exception() -> Optional[str]:
    """Return any exception raised inside the server thread, or None."""
    return _server_thread_exception


def _is_port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _ensure_console_streams() -> None:
    """Ensure sys.stdout/sys.stderr are usable in windowless (pythonw.exe) mode.

    pythonw.exe on Windows launches with sys.stdout/sys.stderr set to None,
    which causes Uvicorn/httptools/uvloop default loggers to crash with
    AttributeError the first time they try a .write() call — preventing
    the TCP bind from ever completing.
    """
    logs_dir = Path(__file__).resolve().parent.parent / "logs"
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        logs_dir = Path.cwd()

    fallback_out = logs_dir / "reporting_portal.stdout.log"
    fallback_err = logs_dir / "reporting_portal.stderr.log"

    if sys.stdout is None or not hasattr(sys.stdout, "write"):
        try:
            sys.stdout = open(fallback_out, "a", encoding="utf-8", buffering=1)
        except Exception:
            import io
            sys.stdout = io.StringIO()

    if sys.stderr is None or not hasattr(sys.stderr, "write"):
        try:
            sys.stderr = open(fallback_err, "a", encoding="utf-8", buffering=1)
        except Exception:
            import io
            sys.stderr = io.StringIO()


def _build_uvicorn_log_config() -> dict:
    """Build a uvicorn logging config that routes through Python logging
    (so it honors pythonw.exe safe stdout/stderr from _ensure_console_streams)."""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "()": "uvicorn.logging.DefaultFormatter",
                "fmt": "%(asctime)s | %(levelprefix)s %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
                "use_colors": None,
            },
            "access": {
                "()": "uvicorn.logging.AccessFormatter",
                "fmt": '%(asctime)s | %(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s',
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
            },
            "access": {
                "formatter": "access",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"level": "INFO"},
            "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
        },
    }


def start_reporting_server(host: str = "127.0.0.1", port: int = 9000) -> Tuple[bool, str]:
    """Start the reporting FastAPI server in a background thread if not already running.

    Returns a tuple of (success: bool, message: str).
    """
    global _last_startup_error

    _ensure_console_streams()

    try:
        import uvicorn  # type: ignore
        from reporting.main import app  # type: ignore
    except ImportError as exc:
        msg = (
            "Reporting portal dependencies missing. "
            f"Install 'fastapi' and 'uvicorn'. Import error: {exc}"
        )
        logger.warning("%s", msg)
        _last_startup_error = msg
        return False, msg
    except Exception as exc:
        msg = f"Failed to load reporting portal app: {type(exc).__name__}: {exc}"
        logger.exception("Unexpected error while preparing reporting portal: %s", exc)
        _last_startup_error = msg
        return False, msg

    with _start_lock:
        global _server_thread

        # If a previous thread died without binding (e.g. pythonw crash on startup),
        # clear it so we can retry cleanly instead of looping against a dead thread.
        if _server_thread is not None and not _server_thread.is_alive():
            _server_thread = None

        if _server_thread and _server_thread.is_alive():
            if _is_port_in_use(host, port):
                _last_startup_error = None
                return True, "already_running"
            logger.warning("Server thread alive but port %s not bound yet — waiting a bit.", port)

        if _is_port_in_use(host, port):
            logger.info("Reporting portal already running on %s:%s", host, port)
            _last_startup_error = None
            return True, "port_already_bound"

        def _run_server() -> None:
            global _server_thread_exception
            try:
                _ensure_console_streams()
                log_config = _build_uvicorn_log_config()
                config = uvicorn.Config(
                    app,
                    host=host,
                    port=port,
                    log_level="info",
                    log_config=log_config,
                )
                server = uvicorn.Server(config)
                server.run()
            except OSError as exc:
                detail = f"Failed to bind reporting portal on {host}:{port} ({exc})"
                logger.error("%s", detail)
                _server_thread_exception = detail
            except Exception as exc:
                detail = f"Server thread crashed: {type(exc).__name__}: {exc}"
                logger.exception("Unexpected error in reporting portal server: %s", exc)
                _server_thread_exception = detail

        _server_thread_exception = None
        _server_thread = threading.Thread(target=_run_server, daemon=True, name="ReportingPortalServer")
        _server_thread.start()

    deadline = time.time() + _STARTUP_TIMEOUT_SECONDS
    while time.time() < deadline:
        if _is_port_in_use(host, port):
            _last_startup_error = None
            return True, "started_ok"
        if _server_thread_exception is not None:
            _last_startup_error = _server_thread_exception
            return False, _server_thread_exception
        if _server_thread is not None and not _server_thread.is_alive() and _server_thread_exception is None:
            _last_startup_error = "Server thread exited unexpectedly before binding port (see logs/reporting_portal.stderr.log)"
            return False, _last_startup_error
        time.sleep(0.1)

    if _server_thread_exception is not None:
        _last_startup_error = _server_thread_exception
        return False, _server_thread_exception

    if _server_thread is not None and not _server_thread.is_alive():
        _last_startup_error = f"Server thread died within {_STARTUP_TIMEOUT_SECONDS:.0f}s startup window. (Check logs/reporting_portal.stderr.log)"
        return False, _last_startup_error

    timeout_msg = (
        f"Reporting portal did not bind to {host}:{port} within "
        f"{_STARTUP_TIMEOUT_SECONDS:.0f} seconds. "
        "Check logs/reporting_portal.stdout.log / reporting_portal.stderr.log for details."
    )
    logger.error("%s", timeout_msg)
    _last_startup_error = timeout_msg
    return False, timeout_msg

