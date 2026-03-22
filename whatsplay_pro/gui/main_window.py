import sys
import logging
from typing import Dict, Any, List
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
    QLabel, QStackedWidget, QFrame, QScrollArea, QApplication, 
    QMessageBox, QStatusBar
)
from PyQt6.QtCore import Qt, pyqtSlot, QSize
from PyQt6.QtGui import QIcon, QPixmap, QColor, QFont
from whatsplay_pro.core.config import Config
from whatsplay_pro.core.signals import signals
from whatsplay_pro.gui.workers import WhatsAppWorker
from whatsplay_pro.gui.settings_panel import SettingsPanel

logger = logging.getLogger(__name__)

class SidebarButton(QPushButton):
    """Custom button for sidebar navigation with active/inactive states."""
    
    def __init__(self, text: str, icon_path: str = None, parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setFixedHeight(50)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("""
            SidebarButton {
                background-color: transparent;
                border: none;
                color: #ecf0f1;
                text-align: left;
                padding-left: 20px;
                font-size: 14px;
                font-weight: 500;
                border-left: 4px solid transparent;
            }
            SidebarButton:hover {
                background-color: #34495e;
            }
            SidebarButton:checked {
                background-color: #34495e;
                color: #2ecc71;
                border-left: 4px solid #2ecc71;
                font-weight: bold;
            }
        """)

class MainWindow(QMainWindow):
    """The central professional PyQt6 UI shell for WhatsPlay Pro."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{Config.APP_NAME} v{Config.VERSION}")
        self.setMinimumSize(1200, 800)
        
        # Initialize Background Workers
        self.wa_worker = None
        self._init_wa_worker()
        
        # UI Setup
        self._setup_ui()
        self._connect_signals()
        
        # Apply Global Dark Mode
        self.setStyleSheet("""
            QMainWindow { background-color: #2c3e50; }
            QWidget#MainContent { background-color: #f5f6fa; border-top-left-radius: 20px; }
            QLabel { color: #2c3e50; }
        """)
        
        # Set default page
        self._on_nav_clicked("dashboard")

    def _init_wa_worker(self):
        """Setup background thread for WhatsApp automation."""
        self.wa_worker = WhatsAppWorker(headless=Config.WHATSAPP_HEADLESS)
        self.wa_worker.start()

    def _setup_ui(self):
        """Create the professional sidebar + content area layout."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.main_layout = QHBoxLayout(central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # 1. Sidebar Panel
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(240)
        self.sidebar.setStyleSheet("background-color: #2c3e50; border: none;")
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 20, 0, 20)
        sidebar_layout.setSpacing(5)
        
        # Logo Area
        logo_label = QLabel(Config.APP_NAME)
        logo_label.setStyleSheet("color: white; font-size: 20px; font-weight: bold; padding: 20px;")
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sidebar_layout.addWidget(logo_label)
        sidebar_layout.addSpacing(20)
        
        # Navigation Buttons
        self.nav_btns: Dict[str, SidebarButton] = {}
        nav_items = [
            ("dashboard", "🏠 Dashboard"),
            ("chats", "💬 Live Chats"),
            ("bulk", "📢 Bulk Messaging"),
            ("crm", "👥 CRM Contacts"),
            ("scheduler", "📅 Scheduler"),
            ("settings", "⚙️ Settings")
        ]
        
        for key, text in nav_items:
            btn = SidebarButton(text)
            btn.clicked.connect(lambda checked, k=key: self._on_nav_clicked(k))
            sidebar_layout.addWidget(btn)
            self.nav_btns[key] = btn
            
        sidebar_layout.addStretch(1)
        
        # Version Info
        version_label = QLabel(f"Version {Config.VERSION}")
        version_label.setStyleSheet("color: #95a5a6; font-size: 11px; padding: 10px;")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sidebar_layout.addWidget(version_label)
        
        self.main_layout.addWidget(self.sidebar)
        
        # 2. Main Content Area
        self.content_container = QWidget()
        self.content_container.setObjectName("MainContent")
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(30, 30, 30, 30)
        
        # Header Info
        self.header_label = QLabel("Dashboard")
        self.header_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #2c3e50;")
        self.content_layout.addWidget(self.header_label)
        self.content_layout.addSpacing(20)
        
        # Stacked Widget for switching between panels
        self.pages = QStackedWidget()
        
        # Initialize Panels
        self.pages.addWidget(QLabel("Dashboard View Content...")) # Index 0
        self.pages.addWidget(QLabel("Chats View Content..."))     # Index 1
        self.pages.addWidget(QLabel("Bulk View Content..."))      # Index 2
        self.pages.addWidget(QLabel("CRM View Content..."))       # Index 3
        self.pages.addWidget(QLabel("Scheduler View Content...")) # Index 4
        
        # Real Settings Panel
        self.settings_panel = SettingsPanel()
        self.pages.addWidget(self.settings_panel) # Index 5
        
        self.content_layout.addWidget(self.pages)
        self.main_layout.addWidget(self.content_container)
        
        # 3. Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")
        self.status_bar.setStyleSheet("background-color: #ecf0f1; color: #2c3e50;")

    def _on_nav_clicked(self, key: str):
        """Switch current visible page and update sidebar states."""
        # Uncheck all buttons
        for btn in self.nav_btns.values():
            btn.setChecked(False)
            
        # Check active button
        self.nav_btns[key].setChecked(True)
        self.header_label.setText(self.nav_btns[key].text().split(' ')[1])
        
        # Map keys to indices
        indices = {"dashboard": 0, "chats": 1, "bulk": 2, "crm": 3, "scheduler": 4, "settings": 5}
        self.pages.setCurrentIndex(indices[key])

    def _connect_signals(self):
        """Connect global app signals to UI updates."""
        signals.wa_ready.connect(self._on_wa_ready)
        signals.wa_auth_required.connect(self._on_auth_required)
        signals.wa_error.connect(self._on_wa_error)
        signals.notify.connect(self._on_notification)

    @pyqtSlot()
    def _on_wa_ready(self):
        self.status_bar.showMessage("WhatsApp Connected ✅", 5000)
        self.status_bar.setStyleSheet("background-color: #2ecc71; color: white;")

    @pyqtSlot(str)
    def _on_auth_required(self, qr_b64: str):
        self.status_bar.showMessage("Authentication Required (Scan QR Code) 📱")
        self.status_bar.setStyleSheet("background-color: #f39c12; color: white;")
        # Logic to display QR dialog would go here

    @pyqtSlot(str)
    def _on_wa_error(self, error: str):
        QMessageBox.critical(self, "WhatsApp Error", f"Fatal error occurred: {error}")
        self.status_bar.showMessage("WhatsApp Connection Error ❌")

    @pyqtSlot(str, str)
    def _on_notification(self, type: str, msg: str):
        # Implementation for success/error popups
        pass

    def closeEvent(self, event):
        """Safe shutdown when closing the window."""
        logger.info("Application closing...")
        if self.wa_worker:
            self.wa_worker.stop()
        event.accept()

if __name__ == "__main__":
    # Ensure app-level requirements are met before launch
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
