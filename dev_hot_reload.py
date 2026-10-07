"""Development-only hot-reload watcher for the desktop app.

NOT used by the production EXE build - it is not imported by main.py,
main.pyw, or referenced by either PyInstaller .spec file, so it is
physically absent from any packaged build. It also refuses to run at all
inside a frozen build, as a second layer of defense.

True in-process hot reload (patching code inside the already-running
QApplication/MainWindow without restarting) is not safe for this app: Qt
widgets are C++-backed, so importlib.reload() cannot retroactively update
an already-constructed window, and the app runs many background QTimers,
worker threads (upload/sync/SMS/WhatsApp/backup), and a reporting server
bound to a TCP port - tearing those down piecemeal risks duplicate timers,
duplicate background loops, and a port-already-in-use crash. Restarting
the whole process instead lets the OS reclaim every thread, timer, socket,
and DB connection automatically - the same strategy Flask's --debug and
`uvicorn --reload` use under the hood.

Usage (instead of `python main.py` while developing):
    python dev_hot_reload.py

Watches app/, reporting/, and main.py for .py changes and cleanly
restarts the application process whenever one changes. Note: a fresh
process means a fresh login and empty forms - in-progress state is not
preserved across a restart, same as manually closing and reopening the
app today, just automated.
"""
from __future__ import annotations

import atexit
import subprocess
import sys
import threading
import time
from pathlib import Path

if getattr(sys, "frozen", False):
    print("dev_hot_reload.py must not run inside a packaged build. Exiting.")
    sys.exit(1)

# Stdout defaults to block-buffered when not attached to a real terminal
# (e.g. redirected to a file/pipe), which can delay this script's own
# status messages well past when they actually happened.
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

PROJECT_ROOT = Path(__file__).resolve().parent
WATCHED_DIRS = [PROJECT_ROOT / "app", PROJECT_ROOT / "reporting"]
WATCHED_ROOT_FILES = {"main.py", "main.pyw"}
DEBOUNCE_SECONDS = 1.0
APP_ENTRY = PROJECT_ROOT / "main.py"


class _RestartSignal:
    """Coalesces a burst of file-save events (e.g. an editor writing
    several files in quick succession) into a single debounced restart."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending = False
        self._last_event_at = 0.0

    def mark(self) -> None:
        with self._lock:
            self._pending = True
            self._last_event_at = time.monotonic()

    def should_restart_now(self) -> bool:
        with self._lock:
            if not self._pending:
                return False
            if time.monotonic() - self._last_event_at < DEBOUNCE_SECONDS:
                return False
            self._pending = False
            return True


class _ChangeHandler(FileSystemEventHandler):
    def __init__(self, signal: _RestartSignal) -> None:
        self._signal = signal

    def _note(self, path: str, verb: str) -> None:
        if path.endswith(".py"):
            print(f"[hot-reload] {verb}: {path}")
            self._signal.mark()

    def on_modified(self, event) -> None:
        if not event.is_directory:
            self._note(event.src_path, "changed")

    def on_created(self, event) -> None:
        if not event.is_directory:
            self._note(event.src_path, "added")

    def on_deleted(self, event) -> None:
        if not event.is_directory:
            self._note(event.src_path, "removed")

    def on_moved(self, event) -> None:
        if not event.is_directory:
            self._note(event.dest_path, "renamed to")


class _RootFileFilterHandler(FileSystemEventHandler):
    """The project root is watched non-recursively (so edits to main.py
    are caught) without also re-triggering on every unrelated top-level
    file (logs, exports, the .spec files, etc.)."""

    def __init__(self, inner: _ChangeHandler) -> None:
        self._inner = inner

    def _relevant(self, path: str) -> bool:
        return Path(path).name in WATCHED_ROOT_FILES

    def on_modified(self, event) -> None:
        if not event.is_directory and self._relevant(event.src_path):
            self._inner.on_modified(event)

    def on_created(self, event) -> None:
        if not event.is_directory and self._relevant(event.src_path):
            self._inner.on_created(event)


def _start_app() -> subprocess.Popen:
    print("[hot-reload] starting application...")
    return subprocess.Popen([sys.executable, str(APP_ENTRY)], cwd=str(PROJECT_ROOT))


def _stop_app(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    print("[hot-reload] stopping application...")
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        print("[hot-reload] application did not exit in time, killing...")
        proc.kill()
        proc.wait(timeout=5)


def main() -> None:
    signal = _RestartSignal()
    change_handler = _ChangeHandler(signal)
    root_handler = _RootFileFilterHandler(change_handler)

    observer = Observer()
    for watched_dir in WATCHED_DIRS:
        if watched_dir.exists():
            observer.schedule(change_handler, str(watched_dir), recursive=True)
    observer.schedule(root_handler, str(PROJECT_ROOT), recursive=False)
    observer.start()

    proc = _start_app()
    # Backstop for any normal Python-level exit path other than the
    # explicit KeyboardInterrupt handling below (e.g. closing the console
    # window, or an unexpected exception escaping the loop) - `proc` is a
    # closure over the variable below, so this always targets whichever
    # process is current, even after a restart reassigns it. This cannot
    # help against the watcher itself being force-killed from outside
    # (Task Manager "End Task", `taskkill /F`) - no process can run
    # cleanup code after being forcibly killed, on any platform, by any
    # tool of this kind.
    atexit.register(lambda: _stop_app(proc))
    last_reported_dead = False
    watched_names = ", ".join(d.name for d in WATCHED_DIRS if d.exists())
    print(f"[hot-reload] watching for .py changes under {watched_names}/ and main.py. Ctrl+C to stop.")

    try:
        while True:
            time.sleep(0.25)

            if signal.should_restart_now():
                _stop_app(proc)
                proc = _start_app()
                last_reported_dead = False
                continue

            if proc.poll() is not None and not last_reported_dead:
                print(f"[hot-reload] application exited (code {proc.returncode}). Waiting for a code change to relaunch it...")
                last_reported_dead = True
    except KeyboardInterrupt:
        print("\n[hot-reload] shutting down...")
    finally:
        observer.stop()
        observer.join(timeout=5)
        _stop_app(proc)


if __name__ == "__main__":
    main()
