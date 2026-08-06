import threading
import logging
import socket
import time
from typing import Optional, Tuple


logger = logging.getLogger(__name__)

_start_lock = threading.Lock()
_server_thread: threading.Thread | None = None
_last_startup_error: Optional[str] = None
_server_thread_exception: Optional[str] = None


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


def start_reporting_server(host: str = "127.0.0.1", port: int = 9000) -> Tuple[bool, str]:
    """Start the reporting FastAPI server in a background thread if not already running.

    Returns a tuple of (success: bool, message: str).
    """
    global _last_startup_error

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

        if _server_thread and _server_thread.is_alive():
            if _is_port_in_use(host, port):
                _last_startup_error = None
                return True, "already_running"
            logger.warning("Server thread alive but port %s not bound yet", port)

        if _is_port_in_use(host, port):
            logger.info("Reporting portal already running on %s:%s", host, port)
            _last_startup_error = None
            return True, "port_already_bound"

        def _run_server() -> None:
            global _server_thread_exception
            try:
                config = uvicorn.Config(app, host=host, port=port, log_level="info")
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

    deadline = time.time() + 5.0
    last_loop_error: Optional[str] = None
    while time.time() < deadline:
        if _is_port_in_use(host, port):
            _last_startup_error = None
            return True, "started_ok"
        if _server_thread_exception is not None:
            _last_startup_error = _server_thread_exception
            return False, _server_thread_exception
        time.sleep(0.1)

    if _server_thread_exception is not None:
        _last_startup_error = _server_thread_exception
        return False, _server_thread_exception

    timeout_msg = (
        f"Reporting portal did not bind to {host}:{port} within 5 seconds. "
        "Check application logs (or run from console) for details."
    )
    logger.error("%s", timeout_msg)
    _last_startup_error = timeout_msg
    return False, timeout_msg

