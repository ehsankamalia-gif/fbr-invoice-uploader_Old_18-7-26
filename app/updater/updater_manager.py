import threading
import logging
from typing import Optional
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
from .update_checker import UpdateChecker
from .notification_ui import UpdateNotificationDialog
from .toast_notification import ToastNotification

logger = logging.getLogger(__name__)

class UpdaterManager(QObject):
    """
    High-level manager to orchestrate the update process.
    Designed to be used within a PyQt application.
    """
    update_available_signal = pyqtSignal(dict)
    no_update_signal = pyqtSignal()
    update_error_signal = pyqtSignal(str)

    def __init__(self, current_version: str, repo: str, github_token: Optional[str] = None, parent=None):
        """
        Args:
            current_version: Current installed version (e.g. "1.1.0")
            repo: GitHub repo to check, as "owner/repo"
            github_token: Optional Personal Access Token, only needed if
                          `repo` is private
            parent: Parent widget
        """
        super().__init__(parent)
        self.current_version = current_version
        self.repo = repo
        self.github_token = github_token
        self.parent_window = parent

        self.update_available_signal.connect(self._show_notification)

    def check_for_updates_async(self):
        """Runs the update check in a background thread. A failed check
        (network error, no releases published yet, a malformed release)
        emits update_error_signal - it is never reported as "no update
        available", which would silently hide the fact that the check
        didn't actually happen."""
        def run():
            try:
                logger.info("Starting background update check...")
                checker = UpdateChecker(self.repo, token=self.github_token)
                update_info = checker.check_for_update(self.current_version)

                # Check if the C++ object still exists before emitting signals
                try:
                    if update_info:
                        logger.info(f"Update found: {update_info['latest_version']}")
                        self.update_available_signal.emit(update_info)
                    else:
                        logger.info("Application is up to date.")
                        self.no_update_signal.emit()
                except RuntimeError as re:
                    if "deleted" in str(re):
                        logger.warning("UpdaterManager was deleted before signals could be emitted.")
                    else:
                        raise
            except Exception as e:
                logger.error(f"Error in update check thread: {e}")
                try:
                    self.update_error_signal.emit(str(e))
                except RuntimeError as re:
                    if "deleted" in str(re):
                        logger.warning("UpdaterManager was deleted before error signal could be emitted.")
                    else:
                        raise

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

    @pyqtSlot(dict)
    def _show_notification(self, update_info: dict):
        """Shows a non-intrusive toast first, then the dialog if clicked."""
        self.latest_update_info = update_info
        
        # Restore button states in main window if it's connected to no_update_signal logic
        # But since an update WAS found, we just handle the UI restoration here if needed
        if hasattr(self.parent_window, '_handle_no_update'):
            self.parent_window._handle_no_update()

        toast = ToastNotification(
            title="Software Update Available",
            message=f"Version {update_info['latest_version']} is now available. Click to view changelog and install.",
            parent=self.parent_window
        )
        toast.clicked.connect(self.show_update_dialog)
        toast.show_notification()

    def show_update_dialog(self):
        """Shows the detailed update dialog."""
        if hasattr(self, 'latest_update_info'):
            dialog = UpdateNotificationDialog(self.latest_update_info, self.parent_window)
            dialog.exec()
