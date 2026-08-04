from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional runtime dependency
    psutil = None


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIR = PROJECT_ROOT / "runtime"
STATUS_FILE = RUNTIME_DIR / "api_server_status.json"
LOG_FILE = RUNTIME_DIR / "api_server.log"
STOP_FILE = RUNTIME_DIR / "api_server_stop.request"
SUPERVISOR_SCRIPT = PROJECT_ROOT / "app" / "api" / "persistent_server.py"

API_HOST = "127.0.0.1"
API_BIND_HOST = "0.0.0.0"
API_PORT = 8000
STALE_STATUS_SECONDS = 15
STOP_WAIT_SECONDS = 10


def _ensure_runtime_dir() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def _read_status_file() -> dict[str, Any]:
    if not STATUS_FILE.exists():
        return {}

    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_status_file(payload: dict[str, Any]) -> None:
    _ensure_runtime_dir()
    STATUS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _is_port_open(host: str = API_HOST, port: int = API_PORT, timeout: float = 0.75) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _is_status_stale(updated_at: Any, max_age_seconds: int = STALE_STATUS_SECONDS) -> bool:
    if not updated_at:
        return True

    try:
        timestamp = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
    except Exception:
        return True

    age_seconds = (datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds()
    return age_seconds > max_age_seconds


def _resolve_python_command() -> list[str]:
    candidates = [
        PROJECT_ROOT / "venv" / "Scripts" / "python.exe",
        Path(sys.executable),
    ]

    for candidate in candidates:
        if candidate and candidate.exists() and "python" in candidate.name.lower():
            return [str(candidate)]

    python_on_path = shutil.which("python")
    if python_on_path:
        return [python_on_path]

    py_launcher = shutil.which("py")
    if py_launcher:
        return [py_launcher]

    raise RuntimeError(
        "No Python interpreter was found for the background API server. "
        "Expected venv\\Scripts\\python.exe or a system Python installation."
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find_port_pids(port: int = API_PORT) -> set[int]:
    if psutil is None:
        return set()

    pids: set[int] = set()
    try:
        for connection in psutil.net_connections(kind="inet"):
            local_addr = getattr(connection, "laddr", None)
            conn_pid = getattr(connection, "pid", None)
            if local_addr and getattr(local_addr, "port", None) == port and conn_pid:
                pids.add(int(conn_pid))
    except Exception:
        return set()
    return pids


def _wait_for_stopped(timeout_seconds: float = STOP_WAIT_SECONDS) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        status = get_api_server_status()
        if not status.get("running") and status.get("state") == "stopped":
            return True
        time.sleep(0.5)
    return not _is_port_open()


def _terminate_pid(pid: int, timeout_seconds: float = 5) -> None:
    if pid <= 0:
        return

    if psutil is not None:
        try:
            process = psutil.Process(pid)
        except Exception:
            return

        processes = [process]
        try:
            processes.extend(process.children(recursive=True))
        except Exception:
            pass

        for proc in reversed(processes):
            try:
                proc.terminate()
            except Exception:
                pass

        gone, alive = psutil.wait_procs(processes, timeout=timeout_seconds)
        if alive:
            for proc in alive:
                try:
                    proc.kill()
                except Exception:
                    pass
            psutil.wait_procs(alive, timeout=timeout_seconds)
        return

    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def get_api_server_status() -> dict[str, Any]:
    status = _read_status_file()
    port_open = _is_port_open()

    state = str(status.get("state") or "stopped")
    message = str(status.get("message") or "").strip()
    status_is_stale = _is_status_stale(status.get("updated_at"))

    if port_open:
        state = "running"
        if not message:
            message = "API server is running on port 8000."
    elif status_is_stale or state not in {"starting", "restart_scheduled", "stopping"}:
        state = "stopped"
        if not message:
            message = "API server is not running."

    return {
        "running": port_open,
        "state": state,
        "message": message,
        "status_file": str(STATUS_FILE),
        "log_file": str(LOG_FILE),
        "docs_url": f"http://{API_HOST}:{API_PORT}/docs",
        "base_url": f"http://{API_HOST}:{API_PORT}",
        "last_error": status.get("last_error", ""),
        "supervisor_pid": status.get("supervisor_pid"),
        "server_pid": status.get("server_pid"),
        "updated_at": status.get("updated_at", ""),
    }


def start_api_server() -> dict[str, Any]:
    _ensure_runtime_dir()
    if STOP_FILE.exists():
        STOP_FILE.unlink(missing_ok=True)

    current_status = get_api_server_status()
    if current_status["running"]:
        return {
            "started": False,
            "already_running": True,
            "message": "API server is already running.",
            **current_status,
        }

    if not SUPERVISOR_SCRIPT.exists():
        raise RuntimeError(f"API supervisor script not found at {SUPERVISOR_SCRIPT}")

    command = [
        *_resolve_python_command(),
        str(SUPERVISOR_SCRIPT),
        "--host",
        API_BIND_HOST,
        "--port",
        str(API_PORT),
    ]

    creation_flags = 0
    startupinfo = None

    if sys.platform == "win32":
        creation_flags = getattr(subprocess, "DETACHED_PROCESS", 0)
        creation_flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        creation_flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
        creation_flags |= getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    with LOG_FILE.open("a", encoding="utf-8") as log_stream:
        process = subprocess.Popen(
            command,
            cwd=str(PROJECT_ROOT),
            stdin=subprocess.DEVNULL,
            stdout=log_stream,
            stderr=subprocess.STDOUT,
            close_fds=True,
            creationflags=creation_flags,
            startupinfo=startupinfo,
        )

    time.sleep(1.5)

    if process.poll() is not None:
        return {
            "started": False,
            "already_running": False,
            "message": (
                "The API background supervisor exited immediately. "
                f"Check {LOG_FILE} for details."
            ),
            **get_api_server_status(),
        }

    return {
        "started": True,
        "already_running": False,
        "message": (
            "API server launch requested. It will continue running independently "
            "after this application closes."
        ),
        **get_api_server_status(),
    }


def stop_api_server() -> dict[str, Any]:
    _ensure_runtime_dir()
    status = get_api_server_status()

    pids_to_stop: set[int] = set()
    for key in ("supervisor_pid", "server_pid"):
        value = status.get(key)
        if isinstance(value, int) and value > 0:
            pids_to_stop.add(value)
        elif isinstance(value, str) and value.isdigit():
            pids_to_stop.add(int(value))

    pids_to_stop.update(_find_port_pids(API_PORT))

    if not status.get("running") and not pids_to_stop:
        stopped_status = {
            "state": "stopped",
            "message": "API server is already stopped.",
            "updated_at": _utc_now(),
        }
        _write_status_file(stopped_status)
        return {
            "stopped": False,
            "already_stopped": True,
            "message": "API server is already stopped.",
            **get_api_server_status(),
        }

    STOP_FILE.write_text(_utc_now(), encoding="utf-8")
    _write_status_file(
        {
            "state": "stopping",
            "message": "Stopping API server and closing active API processes...",
            "updated_at": _utc_now(),
            "supervisor_pid": status.get("supervisor_pid"),
            "server_pid": status.get("server_pid"),
        }
    )

    if _wait_for_stopped():
        STOP_FILE.unlink(missing_ok=True)
        return {
            "stopped": True,
            "already_stopped": False,
            "message": "API server stopped successfully.",
            **get_api_server_status(),
        }

    for pid in sorted(pids_to_stop, reverse=True):
        _terminate_pid(pid)

    STOP_FILE.unlink(missing_ok=True)
    _write_status_file(
        {
            "state": "stopped",
            "message": "API server stopped successfully.",
            "updated_at": _utc_now(),
        }
    )

    return {
        "stopped": not _is_port_open(),
        "already_stopped": False,
        "message": (
            "API server stopped successfully."
            if not _is_port_open()
            else "API server shutdown was requested, but port 8000 still appears active."
        ),
        **get_api_server_status(),
    }
