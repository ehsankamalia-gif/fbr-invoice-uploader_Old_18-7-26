from __future__ import annotations

import argparse
import ctypes
import json
import os
import socket
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import uvicorn

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    # Detached launches execute this file directly, so add the project root
    # before importing package modules like `app.db.session`.
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.session import close_all_db_connections

RUNTIME_DIR = PROJECT_ROOT / "runtime"
STATUS_FILE = RUNTIME_DIR / "api_server_status.json"
LOG_FILE = RUNTIME_DIR / "api_server.log"
STOP_FILE = RUNTIME_DIR / "api_server_stop.request"

LOCAL_CHECK_HOST = "127.0.0.1"
RESTART_DELAY_SECONDS = 5
READY_TIMEOUT_SECONDS = 30
MUTEX_NAME = "Local\\FBRInvoiceUploaderPersistentApiServer"
ERROR_ALREADY_EXISTS = 183


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_runtime_dir() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def append_log(message: str) -> None:
    ensure_runtime_dir()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as log_file:
        log_file.write(f"[{timestamp}] {message}\n")


def write_status(state: str, message: str, **extra: Any) -> None:
    ensure_runtime_dir()
    payload = {
        "state": state,
        "message": message,
        "updated_at": utc_now(),
        "supervisor_pid": os.getpid(),
        **extra,
    }
    STATUS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def is_port_open(host: str, port: int, timeout: float = 0.75) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_for_port(host: str, port: int, timeout_seconds: int) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if is_port_open(host, port):
            return True
        time.sleep(0.5)
    return False


def acquire_single_instance_mutex() -> int | None:
    if sys.platform != "win32":
        return None

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())

    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return None

    return handle


def stop_requested() -> bool:
    return STOP_FILE.exists()


def clear_stop_request() -> None:
    try:
        STOP_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def cleanup_server_resources() -> None:
    try:
        close_all_db_connections()
        append_log("Closed API server database connections.")
    except Exception as exc:
        append_log(f"Database cleanup after API shutdown failed: {exc}")


def _run_uvicorn_server(host: str, port: int, error_box: list[BaseException]) -> None:
    try:
        config = uvicorn.Config(
            "app.api.server:app",
            host=host,
            port=port,
            log_level="info",
        )
        server = uvicorn.Server(config)
        server.install_signal_handlers = lambda: None
        watcher = threading.Thread(
            target=_watch_for_stop_request,
            args=(server,),
            daemon=True,
            name="ApiServerStopWatcher",
        )
        watcher.start()
        server.run()
    except BaseException as exc:  # pragma: no cover - safety net around server loop
        error_box.append(exc)


def _watch_for_stop_request(server: uvicorn.Server[Any]) -> None:
    while not getattr(server, "should_exit", False):
        if stop_requested():
            append_log("Graceful shutdown requested. Signaling uvicorn server to stop.")
            server.should_exit = True
            return
        time.sleep(0.5)


def run_server_once(host: str, port: int) -> tuple[bool, str]:
    error_box: list[BaseException] = []
    stop_status_written = False
    server_thread = threading.Thread(
        target=_run_uvicorn_server,
        args=(host, port, error_box),
        name="PersistentApiServerThread",
    )
    server_thread.start()

    deadline = time.time() + READY_TIMEOUT_SECONDS
    running_status_written = False

    while server_thread.is_alive():
        if stop_requested():
            append_log("Stop request received while waiting for API server readiness.")
            if not stop_status_written:
                write_status(
                    "stopping",
                    "Stopping API server and closing active connections...",
                    port=port,
                    server_pid=os.getpid(),
                )
                stop_status_written = True

        if is_port_open(LOCAL_CHECK_HOST, port):
            if not running_status_written:
                running_status_written = True
                append_log(f"API server is now listening on port {port} (PID {os.getpid()}).")
                write_status(
                    "running",
                    f"API server is running on port {port}.",
                    port=port,
                    server_pid=os.getpid(),
                )
            break

        if time.time() >= deadline:
            append_log(
                f"API server did not become ready within {READY_TIMEOUT_SECONDS} seconds. "
                "Waiting for the server thread to exit."
            )
            break

        time.sleep(0.25)

    while server_thread.is_alive():
        if stop_requested() and not stop_status_written:
            write_status(
                "stopping",
                "Stopping API server and closing active connections...",
                port=port,
                server_pid=os.getpid(),
            )
            stop_status_written = True
        time.sleep(0.5)

    server_thread.join(timeout=1.0)
    cleanup_server_resources()

    if error_box:
        raise error_box[0]

    if stop_requested():
        append_log("API server shutdown completed after stop request.")
        write_status(
            "stopped",
            "API server stopped successfully.",
            port=port,
            server_pid=os.getpid(),
        )
        return True, "API server stopped successfully."

    if running_status_written:
        return False, "API server exited unexpectedly."

    return False, "API server did not start successfully."


def run_supervisor(host: str, port: int) -> int:
    mutex_handle = acquire_single_instance_mutex()
    if sys.platform == "win32" and mutex_handle is None:
        write_status("running", "Another API supervisor instance is already active.")
        append_log("API supervisor launch skipped because another instance is already running.")
        return 0

    clear_stop_request()
    append_log("Persistent API supervisor started.")
    write_status("starting", "Persistent API supervisor started.", port=port)

    while True:
        if stop_requested():
            append_log("Stop request detected before launch. Supervisor will exit.")
            write_status("stopped", "API server stopped successfully.", port=port, server_pid=os.getpid())
            clear_stop_request()
            return 0

        if is_port_open(LOCAL_CHECK_HOST, port):
            write_status(
                "running",
                f"API server is running on port {port}.",
                port=port,
                server_pid=os.getpid(),
            )
            time.sleep(5)
            continue

        append_log("Launching API server runtime.")
        write_status("starting", "Launching API server process.", port=port, server_pid=os.getpid())

        stop_was_requested, outcome_message = run_server_once(host, port)
        if stop_was_requested:
            clear_stop_request()
            return 0

        restart_message = f"{outcome_message} Restarting in {RESTART_DELAY_SECONDS} seconds."
        append_log(restart_message)
        write_status(
            "restart_scheduled",
            restart_message,
            port=port,
            server_pid=os.getpid(),
            last_error=outcome_message,
        )
        time.sleep(RESTART_DELAY_SECONDS)


def main() -> int:
    parser = argparse.ArgumentParser(description="Persistent supervisor for the FastAPI server.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    try:
        return run_supervisor(args.host, args.port)
    except Exception as exc:
        error_message = f"Persistent API supervisor crashed: {exc}"
        append_log(error_message)
        append_log(traceback.format_exc())
        write_status("stopped", error_message, last_error=error_message)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
