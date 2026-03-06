import threading
import logging
import socket


logger = logging.getLogger(__name__)


def _is_port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def start_reporting_server(host: str = "127.0.0.1", port: int = 9000) -> None:
    """Start the reporting FastAPI server in a background thread if not already running."""
    try:
        import uvicorn  # type: ignore
        from reporting.main import app  # type: ignore
    except ImportError as exc:
        logger.warning(
            "Reporting portal not started. "
            "Install 'fastapi' and 'uvicorn' to enable it. (%s)",
            exc,
        )
        return
    except Exception as exc:
        logger.error("Unexpected error while preparing reporting portal: %s", exc)
        return

    if _is_port_in_use(host, port):
        logger.info("Reporting portal already running on %s:%s", host, port)
        return

    def _run_server() -> None:
        try:
            config = uvicorn.Config(app, host=host, port=port, log_level="info")
            server = uvicorn.Server(config)
            server.run()
        except OSError as exc:
            logger.error("Failed to start reporting portal on %s:%s (%s)", host, port, exc)
        except Exception as exc:
            logger.exception("Unexpected error in reporting portal server: %s", exc)

    thread = threading.Thread(target=_run_server, daemon=True, name="ReportingPortalServer")
    thread.start()

