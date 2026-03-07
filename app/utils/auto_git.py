import os
import time
import subprocess
import threading
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import logging

logger = logging.getLogger(__name__)

class GitAutoPushHandler(FileSystemEventHandler):
    def __init__(self, debounce_seconds=5, on_sync_callback=None):
        self.debounce_seconds = debounce_seconds
        self.on_sync_callback = on_sync_callback
        self.last_modified = 0
        self.pending_sync = False
        self.ignore_patterns = [
            '.git', '__pycache__', '.pyc', '.pyo', '.pyd', 
            '.db', '.log', '.zip', 'updates/', 'backups/',
            '.venv', 'venv', '.idea', '.vscode', '.env'
        ]

    def on_any_event(self, event):
        if event.is_directory:
            return
        
        # Check if file should be ignored
        file_path = event.src_path.replace('\\', '/')
        if any(pattern in file_path for pattern in self.ignore_patterns):
            return

        # logger.info(f"Detected change in: {file_path}")
        self.last_modified = time.time()
        self.pending_sync = True

    def run_sync(self):
        if not self.pending_sync:
            return

        # Debounce: only sync if no changes in last X seconds
        if time.time() - self.last_modified < self.debounce_seconds:
            return

        self.pending_sync = False
        logger.info("Starting auto-push to Bitbucket...")

        try:
            # 1. Add all changes
            subprocess.run(['git', 'add', '.'], check=True, capture_output=True)
            
            # 2. Check if there are changes to commit
            status = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
            if not status.stdout.strip():
                return

            # 3. Commit
            commit_msg = f"Auto-sync: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            subprocess.run(['git', 'commit', '-m', commit_msg], check=True, capture_output=True)
            
            # 4. Push to Bitbucket (origin)
            result = subprocess.run(['git', 'push', 'origin', 'main'], capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info("Successfully pushed to Bitbucket.")
                if self.on_sync_callback:
                    self.on_sync_callback(True, "Success")
            else:
                logger.error(f"Push failed: {result.stderr}")
                if self.on_sync_callback:
                    self.on_sync_callback(False, result.stderr)

        except subprocess.CalledProcessError as e:
            msg = e.stderr.decode() if e.stderr else str(e)
            logger.error(f"Error during auto-sync: {msg}")
            if self.on_sync_callback:
                self.on_sync_callback(False, msg)
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            if self.on_sync_callback:
                self.on_sync_callback(False, str(e))

class AutoGitManager:
    def __init__(self, path='.', debounce_seconds=5, on_sync_callback=None):
        self.path = os.path.abspath(path)
        self.debounce_seconds = debounce_seconds
        self.on_sync_callback = on_sync_callback
        self.observer = None
        self.handler = None
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return

        self.handler = GitAutoPushHandler(
            debounce_seconds=self.debounce_seconds,
            on_sync_callback=self.on_sync_callback
        )
        self.observer = Observer()
        self.observer.schedule(self.handler, self.path, recursive=True)
        self.observer.start()
        
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info(f"Auto-Git Sync started for {self.path}")

    def stop(self):
        self._stop_event.set()
        if self.observer:
            self.observer.stop()
            self.observer.join()
        if self._thread:
            self._thread.join()
        logger.info("Auto-Git Sync stopped.")

    def _run_loop(self):
        while not self._stop_event.is_set():
            if self.handler:
                self.handler.run_sync()
            time.sleep(1)

# Singleton instance
auto_git_manager = AutoGitManager()

if __name__ == "__main__":
    # Ensure we are in the project root if run directly
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.chdir(project_root)
    
    logging.basicConfig(level=logging.INFO)
    mgr = AutoGitManager()
    mgr.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        mgr.stop()
