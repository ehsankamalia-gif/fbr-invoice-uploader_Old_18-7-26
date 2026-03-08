import os
import threading
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTextEdit, QProgressBar, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from .downloader import Downloader
from .installer_launcher import InstallerLauncher

class UpdateNotificationDialog(QDialog):
    """
    Modern PyQt6 dialog to notify the user of a new update and handle the download process.
    """
    download_progress_signal = pyqtSignal(int, int)
    download_finished_signal = pyqtSignal(bool, str)

    def __init__(self, update_info: dict, parent=None):
        super().__init__(parent)
        self.update_info = update_info
        self.installer_path = os.path.join(os.environ.get('TEMP', '.'), 'app_installer_update.exe')
        
        self.setWindowTitle("Software Update Available")
        self.setMinimumSize(450, 350)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        
        self._init_ui()
        
        # Connect signals for thread-safe UI updates
        self.download_progress_signal.connect(self._on_download_progress)
        self.download_finished_signal.connect(self._on_download_finished)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header
        title_label = QLabel(f"A new version is available: {self.update_info['latest_version']}")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(title_label)

        # Release Date
        date_label = QLabel(f"Released on: {self.update_info['release_date']}")
        date_label.setStyleSheet("color: #7f8c8d;")
        layout.addWidget(date_label)

        # Changelog
        layout.addWidget(QLabel("What's New:"))
        self.changelog_box = QTextEdit()
        self.changelog_box.setReadOnly(True)
        self.changelog_box.setPlainText(self.update_info['changelog'])
        self.changelog_box.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; padding: 10px;")
        layout.addWidget(self.changelog_box)

        # Progress Bar (Hidden initially)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar { border: 1px solid #ced4da; border-radius: 5px; text-align: center; }
            QProgressBar::chunk { background-color: #3498db; }
        """)
        layout.addWidget(self.progress_bar)

        # Buttons
        button_layout = QHBoxLayout()
        
        self.update_btn = QPushButton("Download and Install Now")
        self.update_btn.setStyleSheet("background-color: #3498db; color: white; padding: 10px; font-weight: bold;")
        self.update_btn.clicked.connect(self._start_download)
        
        self.later_btn = QPushButton("Remind Me Later")
        self.later_btn.setStyleSheet("padding: 10px;")
        self.later_btn.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(self.later_btn)
        button_layout.addWidget(self.update_btn)
        layout.addLayout(button_layout)

    def _start_download(self):
        """Starts the download in a background thread."""
        self.update_btn.setEnabled(False)
        self.later_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        def download_thread():
            downloader = Downloader(self.update_info['download_url'], self.installer_path)
            success = downloader.download(progress_callback=self.download_progress_signal.emit)
            self.download_finished_signal.emit(success, self.installer_path)

        threading.Thread(target=download_thread, daemon=True).start()

    @pyqtSlot(int, int)
    def _on_download_progress(self, downloaded, total):
        if total > 0:
            percent = int((downloaded / total) * 100)
            self.progress_bar.setValue(percent)

    @pyqtSlot(bool, str)
    def _on_download_finished(self, success, path):
        if success:
            # Automatic Hand-off
            InstallerLauncher.launch_and_exit(path)
        else:
            QMessageBox.critical(self, "Update Error", "Failed to download the update. Please try again later.")
            self.update_btn.setEnabled(True)
            self.later_btn.setEnabled(True)
            self.progress_bar.setVisible(False)
