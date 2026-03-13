from __future__ import annotations

from typing import Dict, List, Callable
from dataclasses import dataclass

import io
import re
import requests
import qrcode
import datetime as dt
import threading
import os
import sys
import subprocess
from PIL import Image
from tenacity import RetryError

from PyQt6.QtCore import (
    Qt, 
    QAbstractTableModel, 
    QModelIndex, 
    QStringListModel, 
    QTimer, 
    QDate, 
    pyqtSignal, 
    QObject, 
    QEvent,
    QThread
)
from PyQt6.QtGui import QPixmap, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QSizePolicy,
    QTableView,
    QLineEdit,
    QComboBox,
    QScrollArea,
    QGridLayout,
    QSpinBox,
    QDoubleSpinBox,
    QMessageBox,
    QPushButton,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QApplication,
    QFrame,
    QDateEdit,
    QButtonGroup,
    QCheckBox,
    QTextEdit,
    QFileDialog,
    QTableWidget,
    QTableWidgetItem,
    QProgressDialog,
)

from app.core.config import settings
from app.db.session import SessionLocal, close_all_db_connections
from app.services.report_service import report_service, SalesFilter
from app.db.models import (
    Motorcycle,
    ProductModel,
    Price,
    Customer,
    Invoice,
    SpareLedgerTransaction,
    CustomerType,
    CapturedData,
)
from app.api.schemas import InvoiceCreate, InvoiceItemCreate
from app.services.invoice_service import invoice_service
from app.services.price_service import price_service
from app.services.settings_service import settings_service
from app.services.dealer_service import dealer_service
from app.services.form_capture_service import form_capture_service
from app.services.backup_service import backup_service
from app.qt_ui.dealer_search_dialog import DealerSearchDialog
from app.qt_ui.web_import_dialog import WebImportDialog
from app.core.logger import logger
from app.core.version_manager import VersionManager
from app.updater.updater_manager import UpdaterManager


@dataclass
class CampaignRow:
    id: int
    name: str
    status: str
    sent: int
    failed: int
    total: int
    created_at: dt.datetime


class BackupWorker(QObject):
    """Professional worker for background backup operations."""
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def run(self):
        try:
            logger.info("BackupWorker started manual backup process.")
            result = backup_service.create_backup(is_manual=True)
            self.finished.emit(result)
        except Exception as e:
            logger.error(f"BackupWorker encountered a critical error: {e}", exc_info=True)
            self.error.emit(str(e))


class MySQLRestoreWorker(QObject):
    """Professional worker for background MySQL restore operations."""
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, backup_path: str):
        super().__init__()
        self.backup_path = backup_path

    def run(self):
        try:
            logger.info("MySQLRestoreWorker started background restore.")
            result = backup_service.restore_backup(self.backup_path)
            self.finished.emit(result)
        except Exception as e:
            logger.error(f"MySQLRestoreWorker failed: {e}", exc_info=True)
            self.error.emit(str(e))
    error_message: str = ""

@dataclass
class CapturedDataRow:
    id: int
    chassis_number: str
    engine_number: str
    model: str
    color: str
    name: str
    cnic: str
    created_at: dt.datetime

class CapturedDataTableModel(QAbstractTableModel):
    def __init__(self, rows: List[CapturedDataRow] | None = None) -> None:
        super().__init__()
        self._rows = rows or []
        self._headers = ["CHASSIS", "ENGINE", "MODEL", "COLOR", "CUSTOMER", "CNIC", "CAPTURED AT"]

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._headers)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> any:
        if not index.isValid():
            return None
            
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

        if role != Qt.ItemDataRole.DisplayRole:
            return None
        
        row = self._rows[index.row()]
        col = index.column()
        
        if col == 0: return str(row.chassis_number or "")
        if col == 1: return str(row.engine_number or "")
        if col == 2: return str(row.model or "")
        if col == 3: return str(row.color or "")
        if col == 4: return str(row.name or "")
        if col == 5: return str(row.cnic or "")
        if col == 6: return row.created_at.strftime("%Y-%m-%d %H:%M") if row.created_at else ""
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> any:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self._headers[section]
        return None

    def update_rows(self, rows: List[CapturedData]) -> None:
        self.beginResetModel()
        self._rows = [
            CapturedDataRow(
                id=r.id,
                chassis_number=r.chassis_number,
                engine_number=r.engine_number,
                model=r.model,
                color=r.color,
                name=r.name,
                cnic=r.cnic,
                created_at=r.created_at
            ) for r in rows
        ]
        self.endResetModel()

class NavigationButton(QPushButton):
    def __init__(self, icon_text: str, title: str, page_key: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.icon_text = icon_text
        self.title = title
        self.page_key = page_key
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setText(f"{icon_text}  {title}")

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed:
            self.setText(self.icon_text)
            self.setToolTip(self.title)
            self.setStyleSheet("""
                NavigationButton {
                    background-color: transparent;
                    color: #bdc3c7;
                    border: none;
                    border-left: 4px solid transparent;
                    text-align: center;
                    padding: 10px 0px;
                    font-size: 18px;
                    border-radius: 0;
                }
                NavigationButton:hover {
                    background-color: #3e4f5f;
                    color: white;
                }
                NavigationButton:checked {
                    background-color: #3498db;
                    color: white;
                    border-left: 4px solid #2980b9;
                }
            """)
        else:
            self.setText(f"{self.icon_text}  {self.title}")
            self.setToolTip("")
            self.setStyleSheet("""
                NavigationButton {
                    background-color: transparent;
                    color: #bdc3c7;
                    border: none;
                    border-left: 4px solid transparent;
                    text-align: left;
                    padding: 10px 15px;
                    font-size: 13px;
                    border-radius: 0;
                }
                NavigationButton:hover {
                    background-color: #3e4f5f;
                    color: white;
                }
                NavigationButton:checked {
                    background-color: #3498db;
                    color: white;
                    border-left: 4px solid #2980b9;
                }
            """)


class GroupHeaderButton(QPushButton):
    def __init__(self, arrow: str, group_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.arrow = arrow
        self.group_name = group_name
        self.setCheckable(True)
        self.setChecked(True) # Expanded by default
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setText(f"{arrow} {group_name}")
        self.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #7f8c8d;
                border: none;
                text-align: left;
                padding: 15px 20px 5px 20px;
                font-size: 10px;
                font-weight: bold;
                letter-spacing: 1px;
            }
            QPushButton:hover {
                color: white;
            }
        """)

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed:
            self.setText("") # Hide group headers in collapsed mode
            self.setMaximumHeight(0)
        else:
            self.setText(f"{self.arrow} {self.group_name}")
            self.setMaximumHeight(16777215)


class AutocompleteLineEdit(QLineEdit):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.is_navigating = False
        self.on_completion_accept: Callable[[str], None] | None = None

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            completer = self.completer()
            popup = completer.popup() if completer is not None else None
            if completer is not None and popup is not None and popup.isVisible():
                self.is_navigating = True
                QApplication.sendEvent(popup, event)
                return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            completer = self.completer()
            if completer is not None:
                popup = completer.popup()
                if popup is not None and popup.isVisible():
                    index = popup.currentIndex()
                    if index.isValid():
                        value = index.data(Qt.ItemDataRole.DisplayRole)
                        if isinstance(value, str) and self.on_completion_accept is not None:
                            self.on_completion_accept(value)
                    popup.hide()
                    # Explicitly emit returnPressed after completion
                    self.returnPressed.emit()
                    event.accept()
                    return
            
            # Allow the Enter key to trigger returnPressed for navigation
            super().keyPressEvent(event)
            return

        # Handle all other keys normally to allow typing
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            self.is_navigating = False
        super().keyReleaseEvent(event)


class MainWindow(QMainWindow):
    sms_result_signal = pyqtSignal(bool, str)
    conn_test_result_signal = pyqtSignal(bool, str) # Added for connection tests
    campaign_progress_signal = pyqtSignal(int, int, int, int) # camp_id, sent, failed, total
    campaign_complete_signal = pyqtSignal(int, bool, str) # camp_id, success, message

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ehsan Trader FBR System")
        self.resize(1100, 700)

        self._pages: Dict[str, QWidget] = {}
        self._nav_buttons: Dict[str, NavigationButton] = {}
        self._dealer_completer_map: Dict[str, int] = {}
        self._is_dealer_selected: bool = False
        self._is_sidebar_collapsed: bool = False # Track sidebar state

        # SMS Signal connection
        self.sms_result_signal.connect(self._handle_sms_result)
        self.conn_test_result_signal.connect(self._handle_conn_test_result)
        self.campaign_progress_signal.connect(self._handle_campaign_progress)
        self.campaign_complete_signal.connect(self._handle_campaign_complete)

        # Auto-refresh timer for Captured Data
        self._captured_data_timer = QTimer(self)
        self._captured_data_timer.setInterval(3000) # Faster refresh: 3 seconds
        self._captured_data_timer.timeout.connect(self._reload_captured_data)

        # Auto-refresh timer for SMS Campaigns
        self._sms_campaigns_timer = QTimer(self)
        self._sms_campaigns_timer.setInterval(5000) # Every 5 seconds
        self._sms_campaigns_timer.timeout.connect(self._auto_refresh_campaigns)

        # Register Data Capture Callback
        form_capture_service.on_data_captured = self._on_browser_data_captured

        # Initialize Professional Updater
        self._init_updater()

        self._init_ui()
        
        # Auto-refresh timer for Captured Data
        
        # Load active branding
        active_settings = settings_service.get_active_settings()
        self._update_app_branding(active_settings.get("business_name", "Ehsan Trader"))

    def _on_manual_update_check(self):
        """Triggered manually by user from Settings page or Sidebar Footer."""
        if hasattr(self, 'manual_update_btn'):
            self.manual_update_btn.setEnabled(False)
            self.manual_update_btn.setText("⌛ Checking...")
        if hasattr(self, 'footer_update_btn'):
            self.footer_update_btn.setEnabled(False)
            self.footer_update_btn.setText("⌛ Checking...")
            
        self.updater_manager.check_for_updates_async()

    def _handle_no_update(self):
        """Restores UI state and shows an 'Up to Date' toast."""
        if hasattr(self, 'manual_update_btn'):
            self.manual_update_btn.setEnabled(True)
            self.manual_update_btn.setText("🔄 Check for Updates Now")
        if hasattr(self, 'footer_update_btn'):
            self.footer_update_btn.setEnabled(True)
            self.footer_update_btn.setText("🔄 Check for Updates")
        
        # Show a professional toast for 'Up to Date' status
        from app.updater.toast_notification import ToastNotification
        toast = ToastNotification(
            title="System Up to Date",
            message="You are already using the latest version of the FBR Invoice Uploader.",
            show_action=False, # No details button needed for "Up to Date"
            bg_color="#27ae60", # Professional green for success
            duration_ms=5000,
            parent=self
        )
        toast.show_notification()

    def _handle_update_error(self, error_msg: str):
        """Restores UI state and shows error when update check fails."""
        if hasattr(self, 'manual_update_btn'):
            self.manual_update_btn.setEnabled(True)
            self.manual_update_btn.setText("🔄 Check for Updates Now")
        if hasattr(self, 'footer_update_btn'):
            self.footer_update_btn.setEnabled(True)
            self.footer_update_btn.setText("🔄 Check for Updates")
        
        # Show a professional toast for 'Error' status
        from app.updater.toast_notification import ToastNotification
        toast = ToastNotification(
            title="Update Check Failed",
            message=f"Unable to reach the update server. Please check your internet connection.",
            show_action=False,
            bg_color="#c0392b", # Professional red for errors
            duration_ms=6000,
            parent=self
        )
        toast.show_notification()
        logger.error(f"Update check failed: {error_msg}")

    def _init_updater(self):
        """Initializes the professional update system."""
        current_v = VersionManager.get_current_version()
        
        # Safely handle different version formats
        if "major" in current_v:
            version_str = f"{current_v['major']}.{current_v['minor']}.{current_v['patch']}"
        elif "latest_version" in current_v:
            version_str = current_v["latest_version"]
        else:
            version_str = "1.0.0"
        
        # Bitbucket Raw URL for version.json
        version_url = "https://bitbucket.org/python_desktop/python_repository/raw/main/version.json"
        
        self.updater_manager = UpdaterManager(
            current_version=version_str,
            version_url=version_url,
            parent=self
        )
        
        # Connect additional signals for UI feedback
        self.updater_manager.no_update_signal.connect(self._handle_no_update)
        self.updater_manager.update_error_signal.connect(self._handle_update_error)
        
        # Check for updates immediately on startup (async)
        self.updater_manager.check_for_updates_async()
        
        # Also setup a periodic check every 4 hours
        self._update_check_timer = QTimer(self)
        self._update_check_timer.setInterval(4 * 60 * 60 * 1000)
        self._update_check_timer.timeout.connect(self.updater_manager.check_for_updates_async)
        self._update_check_timer.start()

        # Start backup scheduler if enabled
        backup_service.start_scheduler()
        
        # Professional Auto-Backup on Startup (if it hasn't been done in the last 24h)
        self._perform_startup_backup()

    def _perform_startup_backup(self):
        """Background backup on startup to ensure data safety."""
        def run_backup():
            try:
                # Check if we should backup (last backup date)
                backups = backup_service.list_backups()
                should_backup = True
                if backups:
                    last_backup_date = dt.datetime.strptime(backups[0]["date"], "%Y-%m-%d %H:%M:%S")
                    if (dt.datetime.now() - last_backup_date).total_seconds() < 12 * 3600: # 12 hours
                        should_backup = False
                
                if should_backup:
                    logger.info("Performing professional startup backup...")
                    backup_service.create_backup(is_manual=False)
            except Exception as e:
                logger.error(f"Startup backup failed: {e}")

        threading.Thread(target=run_backup, daemon=True).start()

    def _init_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)

        # Global Stylesheet for professional look
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f8f9fa;
            }
            #navWidget {
                background-color: #2c3e50;
                border-right: 1px solid #dee2e6;
                min-width: 200px;
            }
            #pageHeader {
                font-size: 24px;
                font-weight: bold;
                color: #2c3e50;
                margin-bottom: 10px;
            }
            QLabel {
                font-size: 13px;
                color: #495057;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
                padding: 8px;
                border: 1px solid #ced4da;
                border-radius: 4px;
                background-color: white;
                selection-background-color: #3498db;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #3498db;
            }
            QPushButton {
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            #primaryButton {
                background-color: #3498db;
                color: white;
                border: none;
            }
            #primaryButton:hover {
                background-color: #2980b9;
            }
            #primaryButton:disabled {
                background-color: #bdc3c7;
            }
            #resetButton {
                background-color: #f8f9fa;
                color: #6c757d;
                border: 1px solid #dee2e6;
            }
            #resetButton:hover {
                background-color: #e2e6ea;
            }
            QFrame#formGroup {
                background-color: white;
                border: 1px solid #e9ecef;
                border-radius: 8px;
            }
            QLabel#groupTitle {
                font-weight: bold;
                color: #34495e;
                font-size: 14px;
                text-transform: uppercase;
                letter-spacing: 1px;
                margin-bottom: 5px;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background: #f1f1f1;
                width: 10px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #ccc;
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.nav_widget = QWidget(central)
        self.nav_widget.setObjectName("navWidget")
        self.nav_widget.setFixedWidth(200) # Set initial fixed width
        nav_layout = QVBoxLayout(self.nav_widget)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(0)

        # Nav Header
        nav_header_container = QWidget()
        nav_header_container.setStyleSheet("background-color: #1a252f;")
        self.nav_header_layout = QHBoxLayout(nav_header_container)
        self.nav_header_layout.setContentsMargins(15, 15, 15, 15)
        self.nav_header_layout.setSpacing(10)
        
        # Toggle Button (Hamburger Menu)
        self.sidebar_toggle_btn = QPushButton("≡")
        self.sidebar_toggle_btn.setFixedSize(40, 40) # Slightly larger
        self.sidebar_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sidebar_toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: white;
                border: none;
                font-size: 28px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #34495e;
                border-radius: 4px;
            }
        """)
        self.sidebar_toggle_btn.clicked.connect(self._toggle_sidebar)
        self.nav_header_layout.addWidget(self.sidebar_toggle_btn)
        
        self.nav_header_label = QLabel("EHSAN TRADER")
        self.nav_header_label.setStyleSheet("color: white; font-size: 16px; font-weight: bold; border: none;")
        
        self.nav_header_layout.addWidget(self.nav_header_label, 1)
        nav_layout.addWidget(nav_header_container)

        self.stack = QStackedWidget(central)

        root_layout.addWidget(self.nav_widget)
        root_layout.addWidget(self.stack, 1)

        self._add_page("dashboard", self._create_dashboard_page(), "Dashboard")
        self._add_page("reports", self._create_reports_page(), "Reports")
        self._add_page("invoice", self._create_invoice_page(), "Invoice")
        self._add_page("inventory", self._create_inventory_page(), "Inventory")
        self._add_page("captured_data", self._create_captured_data_page(), "Captured Data")
        self._add_page("prices", self._create_prices_page(), "Prices")
        self._add_page("customers", self._create_customers_page(), "Customers")
        self._add_page("dealers", self._create_dealers_page(), "Dealers")
        self._add_page("spare_ledger", self._create_spare_ledger_page(), "Spare Ledger")
        self._add_page("sms", self._create_sms_page(), "SMS Module")
        self._add_page("settings", self._create_settings_page(), "Settings")
        self._add_page("welcome", self._create_welcome_page(), "Welcome")

        nav_layout.addSpacing(10)
        
        self.nav_icons = {
            "dashboard": "📊",
            "reports": "📈",
            "invoice": "📝",
            "inventory": "📦",
            "prices": "💰",
            "customers": "👥",
            "dealers": "🏢",
            "spare_ledger": "📒",
            "sms": "💬",
            "settings": "⚙️",
            "welcome": "👋",
            "captured_data": "📁",
        }

        self.menu_groups = {
            "GENERAL": ["dashboard", "welcome"],
            "SALES": ["invoice", "reports"],
            "INVENTORY": ["inventory", "prices", "spare_ledger", "captured_data"],
            "DIRECTORY": ["customers", "dealers"],
            "SYSTEM": ["sms", "settings"]
        }

        self._group_headers: Dict[str, GroupHeaderButton] = {}
        self._group_buttons: Dict[str, List[NavigationButton]] = {}
        self._group_header_manager = QButtonGroup(self)
        self._group_header_manager.setExclusive(False) # We'll handle exclusivity manually for more control

        for i, (group_name, keys) in enumerate(self.menu_groups.items()):
            # Group Header
            is_first = (i == 0)
            arrow = "▼" if is_first else "▶"
            header = GroupHeaderButton(arrow, group_name, self.nav_widget)
            header.setChecked(is_first)
            header.clicked.connect(self._on_group_header_clicked)
            self._group_header_manager.addButton(header)
            nav_layout.addWidget(header)
            self._group_headers[group_name] = header
            self._group_buttons[group_name] = []

            for key in keys:
                title = self._pages[key].windowTitle()
                icon = self.nav_icons.get(key, "🔹")
                button = NavigationButton(icon, title, key, self.nav_widget)
                button.setStyleSheet("""
                    NavigationButton {
                        background-color: transparent;
                        color: #bdc3c7;
                        border: none;
                        border-left: 4px solid transparent;
                        text-align: left;
                        padding: 10px 15px;
                        font-size: 13px;
                        border-radius: 0;
                    }
                    NavigationButton:hover {
                        background-color: #3e4f5f;
                        color: white;
                    }
                    NavigationButton:checked {
                        background-color: #3498db;
                        color: white;
                        border-left: 4px solid #2980b9;
                    }
                """)
                button.clicked.connect(self._on_nav_clicked)  # type: ignore[arg-type]
                button.setVisible(is_first) # Only first group visible by default
                nav_layout.addWidget(button)
                self._nav_buttons[key] = button
                self._group_buttons[group_name].append(button)

        nav_layout.addStretch(1)

        # Update Button (Footer)
        self.footer_update_btn = QPushButton("🔄 Check for Updates")
        self.footer_update_btn.setToolTip("Check for latest version and new features")
        self.footer_update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.footer_update_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #bdc3c7;
                border: none;
                border-left: 4px solid transparent;
                text-align: left;
                padding: 15px 20px;
                font-size: 13px;
                border-radius: 0;
            }
            QPushButton:hover {
                background-color: #34495e;
                color: white;
                border-left: 4px solid #3498db;
            }
        """)
        self.footer_update_btn.clicked.connect(self._on_manual_update_check)
        nav_layout.addWidget(self.footer_update_btn)

        # Exit Button
        self.exit_btn = QPushButton("🚪 Exit Application")
        self.exit_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #e74c3c;
                border: none;
                border-left: 4px solid transparent;
                text-align: left;
                padding: 15px 20px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 0;
            }
            QPushButton:hover {
                background-color: #c0392b;
                color: white;
            }
        """)
        self.exit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.exit_btn.clicked.connect(self.close)
        nav_layout.addWidget(self.exit_btn)

        self._select_page("dashboard")
        self._update_fbr_submitted_counter() # Initial load of counter state

        # Connect global focus signal to automatic scrolling logic
        QApplication.instance().focusChanged.connect(self._on_focus_changed)

        # Ensure the dashboard and welcome stats refresh their data once the application is fully ready
        QTimer.singleShot(100, self._refresh_dashboard)
        QTimer.singleShot(100, self._refresh_welcome_stats)

    def _on_nav_clicked(self, checked: bool) -> None:
        button = self.sender()
        if not isinstance(button, NavigationButton):
            return
        self._select_page(button.page_key)

    def _toggle_sidebar(self) -> None:
        """Toggles the sidebar between collapsed and expanded states."""
        self._is_sidebar_collapsed = not self._is_sidebar_collapsed
        
        # Target width
        width = 60 if self._is_sidebar_collapsed else 200
        
        # Update Nav Widget Width
        self.nav_widget.setFixedWidth(width)
        
        # Update Nav Header Label visibility
        self.nav_header_label.setVisible(not self._is_sidebar_collapsed)
        
        # Adjust Header Margins for Centering
        if self._is_sidebar_collapsed:
            self.nav_header_layout.setContentsMargins(0, 15, 0, 15)
            self.nav_header_layout.setSpacing(0)
            self.nav_header_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            self.nav_header_layout.setContentsMargins(15, 15, 15, 15)
            self.nav_header_layout.setSpacing(10)
            self.nav_header_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        # Update Footer buttons text and style
        if self._is_sidebar_collapsed:
            self.footer_update_btn.setText("🔄")
            self.footer_update_btn.setToolTip("Check for Updates")
            self.footer_update_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #bdc3c7;
                    border: none;
                    border-left: 4px solid transparent;
                    text-align: center;
                    padding: 15px 0px;
                    font-size: 18px;
                    border-radius: 0;
                }
                QPushButton:hover {
                    background-color: #34495e;
                    color: white;
                    border-left: 4px solid #3498db;
                }
            """)
            self.exit_btn.setText("🚪")
            self.exit_btn.setToolTip("Exit Application")
            self.exit_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #e74c3c;
                    border: none;
                    border-left: 4px solid transparent;
                    text-align: center;
                    padding: 15px 0px;
                    font-size: 18px;
                    font-weight: bold;
                    border-radius: 0;
                }
                QPushButton:hover {
                    background-color: #c0392b;
                    color: white;
                }
            """)
        else:
            self.footer_update_btn.setText("🔄 Check for Updates")
            self.footer_update_btn.setToolTip("")
            self.footer_update_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #bdc3c7;
                    border: none;
                    border-left: 4px solid transparent;
                    text-align: left;
                    padding: 15px 20px;
                    font-size: 13px;
                    border-radius: 0;
                }
                QPushButton:hover {
                    background-color: #34495e;
                    color: white;
                    border-left: 4px solid #3498db;
                }
            """)
            self.exit_btn.setText("🚪 Exit Application")
            self.exit_btn.setToolTip("")
            self.exit_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #e74c3c;
                    border: none;
                    border-left: 4px solid transparent;
                    text-align: left;
                    padding: 15px 20px;
                    font-size: 14px;
                    font-weight: bold;
                    border-radius: 0;
                }
                QPushButton:hover {
                    background-color: #c0392b;
                    color: white;
                }
            """)

        # Update Group Headers and Nav Buttons
        for group_name, header in self._group_headers.items():
            header.set_collapsed(self._is_sidebar_collapsed)
            
            # Update buttons in this group
            for btn in self._group_buttons[group_name]:
                btn.set_collapsed(self._is_sidebar_collapsed)
                
                if self._is_sidebar_collapsed:
                    # Show all icons when collapsed
                    btn.setVisible(True)
                else:
                    # Restore group-based visibility when expanded
                    btn.setVisible(header.isChecked())

    def _select_page(self, key: str) -> None:
        if key not in self._pages:
            return
        self.stack.setCurrentWidget(self._pages[key])
        
        # Ensure the group containing this page is expanded (Accordion behavior)
        for group_name, keys in self.menu_groups.items():
            if key in keys:
                header = self._group_headers.get(group_name)
                if header and not header.isChecked():
                    # Clicking the header would trigger the toggle logic
                    header.setChecked(True)
                    self._expand_group(header)
                break

        for k, btn in self._nav_buttons.items():
            btn.setChecked(k == key)
        
        # Always stop auto-refresh unless we are on captured_data page
        if hasattr(self, "_captured_data_timer"):
            self._captured_data_timer.stop()

        # Trigger refresh if page has a refresh method
        if key == "welcome":
            self._refresh_welcome_stats()
        elif key == "dashboard":
            self._refresh_dashboard()
        elif key == "reports":
            self._reload_sales()
        elif key == "inventory":
            self._reload_inventory()
        elif key == "customers":
            self._reload_customers()
        elif key == "dealers":
            self._reload_dealers()
        elif key == "captured_data":
            self._reload_captured_data()
            self._captured_data_timer.start() # Start auto-refresh while on this page

    def _on_focus_changed(self, old: QWidget | None, now: QWidget | None) -> None:
        """Automatically scrolls the invoice form to ensure the focused widget is visible."""
        if not now:
            return
            
        # Check if the invoice page is currently active
        if self.stack.currentWidget() != self._pages.get("invoice"):
            return
            
        # Check if the focused widget is a child of the invoice scroll area
        if hasattr(self, "invoice_scroll_area") and self.invoice_scroll_area.widget():
            # SPECIAL CASE: If Chassis input is focused, ensure Pricing Summary is also visible
            if now == self.invoice_chassis_input:
                if hasattr(self, "invoice_pricing_group"):
                    # Scroll to ensure the bottom of the pricing group is visible
                    self.invoice_scroll_area.ensureWidgetVisible(self.invoice_pricing_group, 50, 50)
                    return

            # isAncestorOf is more reliable for nested widgets (like QComboBox's line edit)
            if self.invoice_scroll_area.widget().isAncestorOf(now):
                # Scroll to the widget with a 100px vertical margin for better context
                self.invoice_scroll_area.ensureWidgetVisible(now, 50, 100)

    def _add_page(self, key: str, widget: QWidget, title: str) -> None:
        widget.setWindowTitle(title)
        index = self.stack.addWidget(widget)
        self._pages[key] = widget
        if index == 0:
            self.stack.setCurrentIndex(0)

    def _create_dashboard_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(25)

        # Header
        header_layout = QHBoxLayout()
        header = QLabel("Dashboard Overview")
        header.setObjectName("pageHeader")
        header_layout.addWidget(header)
        header_layout.addStretch(1)
        
        refresh_btn = QPushButton("Refresh Data")
        refresh_btn.setObjectName("resetButton")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self._refresh_dashboard)
        header_layout.addWidget(refresh_btn)
        layout.addLayout(header_layout)

        # Stats Cards Row
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(20)

        self.dash_total_card = self._create_stat_card("TOTAL INVOICES", "0", "#3498db")
        self.dash_synced_card = self._create_stat_card("SYNCED (FBR)", "0", "#2ecc71")
        self.dash_pending_card = self._create_stat_card("PENDING SYNC", "0", "#f39c12")
        self.dash_failed_card = self._create_stat_card("FAILED SYNC", "0", "#e74c3c")

        stats_layout.addWidget(self.dash_total_card)
        stats_layout.addWidget(self.dash_synced_card)
        stats_layout.addWidget(self.dash_pending_card)
        stats_layout.addWidget(self.dash_failed_card)
        layout.addLayout(stats_layout)

        # Recent Invoices Section
        recent_label = QLabel("RECENT SUBMISSIONS")
        recent_label.setObjectName("groupTitle")
        layout.addWidget(recent_label)

        self.dash_table_model = SalesTableModel()
        self.dash_table_view = QTableView()
        self.dash_table_view.setModel(self.dash_table_model)
        self.dash_table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.dash_table_view.horizontalHeader().setStretchLastSection(True)
        self.dash_table_view.setAlternatingRowColors(True)
        self.dash_table_view.verticalHeader().setVisible(False)
        self.dash_table_view.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        
        layout.addWidget(self.dash_table_view, 1)

        return page

    def _create_stat_card(self, title: str, value: str, color: str) -> QFrame:
        card = QFrame()
        card.setObjectName("formGroup")
        card.setMinimumHeight(120)
        card.setStyleSheet(f"""
            QFrame#formGroup {{
                border-top: 4px solid {color};
                background-color: white;
            }}
        """)
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(5)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("color: #7f8c8d; font-size: 11px; font-weight: bold; letter-spacing: 0.5px;")
        
        val_lbl = QLabel(value)
        val_lbl.setObjectName("statValue")
        val_lbl.setStyleSheet(f"color: {color}; font-size: 28px; font-weight: bold;")
        
        layout.addWidget(title_lbl)
        layout.addWidget(val_lbl)
        layout.addStretch(1)
        
        # Store label reference on the card object for easy updating
        card.value_label = val_lbl
        return card

    def _refresh_dashboard(self) -> None:
        db = SessionLocal()
        try:
            # Fetch counts for stats cards
            total = db.query(Invoice).count()
            synced = db.query(Invoice).filter(Invoice.fbr_invoice_number != None).count()
            # Pending are those not fiscalized and not failed
            pending = db.query(Invoice).filter(
                Invoice.fbr_invoice_number == None,
                Invoice.sync_status != "FAILED"
            ).count()
            # Failed are those with explicit failed status
            failed = db.query(Invoice).filter(Invoice.sync_status == "FAILED").count()

            # Update UI labels
            self.dash_total_card.value_label.setText(str(total))
            self.dash_synced_card.value_label.setText(str(synced))
            self.dash_pending_card.value_label.setText(str(pending))
            self.dash_failed_card.value_label.setText(str(failed))

            # Update Recent Table (Top 10)
            flt = SalesFilter(limit=10)
            rows = report_service.get_sales(db, flt)
            
            data: List[SalesRow] = []
            for inv in rows:
                if inv.fbr_invoice_number:
                    status = "Synced"
                elif inv.sync_status == "FAILED":
                    status = "Failed"
                else:
                    status = "Pending"

                buyer = inv.customer.name if getattr(inv, "customer", None) else "N/A"

                chassis_list: List[str] = []
                engine_list: List[str] = []
                for item in getattr(inv, "items", []) or []:
                    mc = getattr(item, "motorcycle", None)
                    if mc:
                        if mc.chassis_number:
                            chassis_list.append(mc.chassis_number)
                        if mc.engine_number:
                            engine_list.append(mc.engine_number)

                data.append(
                    SalesRow(
                        date_value=inv.datetime,
                        invoice_number=inv.invoice_number or "",
                        buyer=buyer,
                        chassis=", ".join(chassis_list),
                        engine=", ".join(engine_list),
                        total=float(inv.total_amount or 0),
                        status=status,
                    )
                )

            self.dash_table_model.update_rows(data)
            
            # Also update the FBR counter in header if we're here
            if hasattr(self, "invoice_fbr_stat_value"):
                self.invoice_fbr_stat_value.setText(str(synced))

        except Exception as e:
            logger.error(f"Dashboard refresh error: {e}", exc_info=True)
        finally:
            db.close()

    def _create_reports_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(25)

        # Global Page Style
        page.setStyleSheet("""
            QWidget {
                background-color: #f8f9fa;
            }
            QLabel#pageHeader {
                font-size: 26px;
                font-weight: bold;
                color: #2c3e50;
                margin-bottom: 5px;
            }
            QFrame#filterCard {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 12px;
            }
            QLabel.filterLabel {
                color: #7f8c8d;
                font-weight: bold;
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            QLineEdit, QComboBox {
                padding: 10px 15px;
                border: 1px solid #dee2e6;
                border-radius: 8px;
                background-color: #ffffff;
                font-size: 13px;
                min-width: 150px;
            }
            QLineEdit:hover, QComboBox:hover {
                border: 1px solid #bdc3c7;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 2px solid #3498db;
                background-color: #ffffff;
            }
            QPushButton#primaryButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 8px;
                font-weight: bold;
                padding: 12px 24px;
                font-size: 13px;
            }
            QPushButton#primaryButton:hover {
                background-color: #2980b9;
            }
            QPushButton#resetButton {
                background-color: white;
                color: #2c3e50;
                border: 1px solid #dee2e6;
                border-radius: 8px;
                font-weight: bold;
                padding: 12px 24px;
                font-size: 13px;
            }
            QPushButton#resetButton:hover {
                background-color: #f8f9fa;
                border: 1px solid #bdc3c7;
            }
            QTableView {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 12px;
                gridline-color: #f1f1f1;
                outline: 0;
                font-size: 13px;
                selection-background-color: #e3f2fd;
                selection-color: #1976d2;
                alternate-background-color: #fafafa;
            }
            QHeaderView::section {
                background-color: #f8f9fa;
                color: #5a6268;
                padding: 15px;
                font-weight: bold;
                text-transform: uppercase;
                font-size: 11px;
                border: none;
                border-bottom: 2px solid #e9ecef;
            }
            QScrollBar:vertical {
                border: none;
                background: #f1f1f1;
                width: 8px;
                margin: 0px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #bdc3c7;
                min-height: 20px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: #95a5a6;
            }
        """)

        # Header Section
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        header_v_box = QVBoxLayout()
        header = QLabel("Sales & FBR Submission Report")
        header.setObjectName("pageHeader")
        header_v_box.addWidget(header)
        
        header_subtitle = QLabel("Comprehensive view of all submitted invoices and their FBR sync status.")
        header_subtitle.setStyleSheet("color: #7f8c8d; font-size: 13px;")
        header_v_box.addWidget(header_subtitle)
        
        header_layout.addLayout(header_v_box)
        header_layout.addStretch(1)
        
        self.report_total_count_label = QLabel("Total Records: 0")
        self.report_total_count_label.setStyleSheet("""
            color: #1976d2; 
            font-weight: bold; 
            font-size: 12px; 
            background: #e3f2fd; 
            padding: 10px 25px; 
            border: 1px solid #bbdefb;
            border-radius: 20px;
        """)
        header_layout.addWidget(self.report_total_count_label, 0, Qt.AlignmentFlag.AlignVCenter)
        
        layout.addWidget(header_widget)

        # Filter Card
        filter_card = QFrame()
        filter_card.setObjectName("filterCard")
        filter_layout = QHBoxLayout(filter_card)
        filter_layout.setContentsMargins(25, 20, 25, 20)
        filter_layout.setSpacing(25)

        # Search Group
        search_box = QVBoxLayout()
        search_box.setSpacing(8)
        search_lbl = QLabel("Search Keywords")
        search_lbl.setProperty("class", "filterLabel")
        search_box.addWidget(search_lbl)
        self.sales_search_input = QLineEdit()
        self.sales_search_input.setPlaceholderText("Invoice, Buyer, Chassis...")
        self.sales_search_input.setFixedWidth(280)
        self.sales_search_input.textChanged.connect(self._reload_sales)
        search_box.addWidget(self.sales_search_input)
        filter_layout.addLayout(search_box)

        # Status Group
        status_box = QVBoxLayout()
        status_box.setSpacing(8)
        status_lbl = QLabel("Submission Status")
        status_lbl.setProperty("class", "filterLabel")
        status_box.addWidget(status_lbl)
        self.sales_status_combo = QComboBox()
        self.sales_status_combo.addItems(["All Statuses", "Synced", "Pending", "Failed"])
        self.sales_status_combo.currentTextChanged.connect(self._reload_sales)
        status_box.addWidget(self.sales_status_combo)
        filter_layout.addLayout(status_box)

        # Period Group
        period_box = QVBoxLayout()
        period_box.setSpacing(8)
        period_lbl = QLabel("Time Period")
        period_lbl.setProperty("class", "filterLabel")
        period_box.addWidget(period_lbl)
        self.sales_period_combo = QComboBox()
        self.sales_period_combo.addItems(["All Time", "Today", "This Month"])
        self.sales_period_combo.currentTextChanged.connect(self._reload_sales)
        period_box.addWidget(self.sales_period_combo)
        filter_layout.addLayout(period_box)

        filter_layout.addStretch(1)
        
        refresh_btn = QPushButton("↻ Refresh Data")
        refresh_btn.setObjectName("resetButton")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self._reload_sales)
        filter_layout.addWidget(refresh_btn, 0, Qt.AlignmentFlag.AlignBottom)
        
        layout.addWidget(filter_card)

        # Table Section
        table_container = QFrame()
        table_container.setStyleSheet("background-color: white; border: 1px solid #e0e0e0; border-radius: 12px;")
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(1, 1, 1, 1)

        self.sales_table_view = QTableView()
        self.sales_table_model = SalesTableModel()
        self.sales_table_view.setModel(self.sales_table_model)
        self.sales_table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.sales_table_view.setAlternatingRowColors(True)
        self.sales_table_view.horizontalHeader().setStretchLastSection(True)
        self.sales_table_view.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft)
        self.sales_table_view.verticalHeader().setVisible(False)
        self.sales_table_view.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.sales_table_view.setShowGrid(False)
        self.sales_table_view.setMouseTracking(True)
        self.sales_table_view.doubleClicked.connect(self._on_sales_row_double_clicked)
        
        # Adjust column widths
        self.sales_table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.sales_table_view.horizontalHeader().resizeSection(0, 140) # Date
        self.sales_table_view.horizontalHeader().resizeSection(1, 120) # Invoice
        self.sales_table_view.horizontalHeader().resizeSection(2, 200) # Buyer
        self.sales_table_view.horizontalHeader().resizeSection(3, 150) # Chassis
        self.sales_table_view.horizontalHeader().resizeSection(4, 150) # Engine
        self.sales_table_view.horizontalHeader().resizeSection(5, 120) # Total
        
        table_layout.addWidget(self.sales_table_view)
        layout.addWidget(table_container, 1)

        self._reload_sales()

        return page

        self._reload_sales()

        return page

    def _on_sales_row_double_clicked(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        row_data = self.sales_table_model._rows[index.row()]
        self._open_invoice_detail_dialog(row_data)

    def _open_invoice_detail_dialog(self, row_data: SalesRow) -> None:
        # We need the full invoice object to show details
        db = SessionLocal()
        try:
            invoice = db.query(Invoice).filter(Invoice.invoice_number == row_data.invoice_number).first()
            if not invoice:
                self._show_error("Error", "Could not find invoice details in database.")
                return

            dialog = QDialog(self)
            dialog.setWindowTitle(f"Invoice Detail - {invoice.invoice_number}")
            dialog.setMinimumSize(700, 800)
            dialog.setStyleSheet("""
                QDialog { 
                    background-color: #f8f9fa; 
                }
                QLabel#dialogHeader {
                    font-size: 22px;
                    font-weight: bold;
                    color: #2c3e50;
                }
                QFrame.detailCard {
                    background-color: white;
                    border: 1px solid #e0e0e0;
                    border-radius: 12px;
                    padding: 20px;
                }
                QLabel.sectionTitle {
                    font-weight: bold;
                    font-size: 14px;
                    color: #34495e;
                    text-transform: uppercase;
                    letter-spacing: 1px;
                    margin-bottom: 10px;
                }
                QLabel.fieldLabel {
                    color: #7f8c8d;
                    font-weight: bold;
                    font-size: 12px;
                }
                QLabel.fieldValue {
                    color: #2c3e50;
                    font-size: 13px;
                }
                QPushButton#closeButton {
                    background-color: #3498db;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    font-weight: bold;
                    padding: 10px 20px;
                }
            """)

            main_layout = QVBoxLayout(dialog)
            main_layout.setContentsMargins(30, 30, 30, 30)
            main_layout.setSpacing(20)

            # Header with Status Badge
            header_layout = QHBoxLayout()
            header_lbl = QLabel(f"Invoice #{invoice.invoice_number}")
            header_lbl.setObjectName("dialogHeader")
            header_layout.addWidget(header_lbl)
            header_layout.addStretch(1)
            
            status_text = "Synced" if invoice.fbr_invoice_number else "Pending"
            if invoice.sync_status == "FAILED": status_text = "Failed"
            
            status_color = "#2ecc71" if status_text == "Synced" else "#f39c12"
            if status_text == "Failed": status_color = "#e74c3c"
            
            status_badge = QLabel(status_text.upper())
            status_badge.setStyleSheet(f"""
                background-color: {status_color};
                color: white;
                font-weight: bold;
                font-size: 10px;
                padding: 5px 15px;
                border-radius: 12px;
            """)
            header_layout.addWidget(status_badge)
            main_layout.addLayout(header_layout)

            # Scroll Area for content
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
            content_widget = QWidget()
            content_layout = QVBoxLayout(content_widget)
            content_layout.setContentsMargins(0, 0, 10, 0)
            content_layout.setSpacing(20)
            scroll.setWidget(content_widget)
            main_layout.addWidget(scroll)

            # --- Customer & General Info Card ---
            info_card = QFrame()
            info_card.setProperty("class", "detailCard")
            info_card.setObjectName("detailCard")
            info_card.setStyleSheet("QFrame#detailCard { background-color: white; border: 1px solid #e0e0e0; border-radius: 12px; }")
            info_layout = QVBoxLayout(info_card)
            
            info_title = QLabel("General Information")
            info_title.setProperty("class", "sectionTitle")
            info_layout.addWidget(info_title)
            
            info_grid = QGridLayout()
            info_grid.setSpacing(15)
            
            def add_detail(label, value, row, col):
                lbl = QLabel(label)
                lbl.setProperty("class", "fieldLabel")
                val = QLabel(str(value) if value else "N/A")
                val.setProperty("class", "fieldValue")
                info_grid.addWidget(lbl, row, col)
                info_grid.addWidget(val, row, col + 1)

            add_detail("Date/Time:", invoice.datetime.strftime("%Y-%m-%d %H:%M") if invoice.datetime else "N/A", 0, 0)
            add_detail("FBR ID:", invoice.fbr_invoice_number if invoice.fbr_invoice_number else "Not Synced", 0, 2)
            add_detail("Buyer Name:", invoice.customer.name if invoice.customer else "N/A", 1, 0)
            add_detail("CNIC:", invoice.customer.cnic if invoice.customer else "N/A", 1, 2)
            add_detail("Phone:", invoice.customer.phone if invoice.customer else "N/A", 2, 0)
            add_detail("NTN:", invoice.customer.ntn if invoice.customer else "N/A", 2, 2)
            
            info_layout.addLayout(info_grid)
            content_layout.addWidget(info_card)

            # --- Product Details Card ---
            items_card = QFrame()
            items_card.setProperty("class", "detailCard")
            items_card.setObjectName("itemsCard")
            items_card.setStyleSheet("QFrame#itemsCard { background-color: white; border: 1px solid #e0e0e0; border-radius: 12px; }")
            items_layout = QVBoxLayout(items_card)
            
            items_title = QLabel("Product Details")
            items_title.setProperty("class", "sectionTitle")
            items_layout.addWidget(items_title)
            
            for item in invoice.items:
                mc = item.motorcycle
                item_box = QFrame()
                item_box.setStyleSheet("background-color: #f8f9fa; border-radius: 8px; padding: 12px; border: 1px solid #f1f1f1;")
                item_layout = QGridLayout(item_box)
                
                model_name = mc.product_model.model_name if mc and mc.product_model else 'Motorcycle'
                name_lbl = QLabel(model_name)
                name_lbl.setStyleSheet("font-weight: bold; color: #2c3e50; font-size: 14px;")
                item_layout.addWidget(name_lbl, 0, 0, 1, 2)
                
                if mc:
                    def add_mc_detail(l, v, r, c):
                        lbl = QLabel(l)
                        lbl.setStyleSheet("color: #7f8c8d; font-size: 11px; font-weight: bold;")
                        val = QLabel(str(v))
                        val.setStyleSheet("color: #2c3e50; font-size: 12px;")
                        item_layout.addWidget(lbl, r, c)
                        item_layout.addWidget(val, r, c+1)

                    add_mc_detail("CHASSIS:", mc.chassis_number, 1, 0)
                    add_mc_detail("ENGINE:", mc.engine_number, 1, 2)
                    add_mc_detail("COLOR:", mc.color, 2, 0)
                    add_mc_detail("QTY:", item.quantity, 2, 2)
                
                items_layout.addWidget(item_box)
            
            content_layout.addWidget(items_card)

            # --- Financial Summary Card ---
            price_card = QFrame()
            price_card.setProperty("class", "detailCard")
            price_card.setObjectName("priceCard")
            price_card.setStyleSheet("QFrame#priceCard { background-color: white; border: 1px solid #e0e0e0; border-radius: 12px; }")
            price_layout = QVBoxLayout(price_card)
            
            price_title = QLabel("Financial Summary")
            price_title.setProperty("class", "sectionTitle")
            price_layout.addWidget(price_title)
            
            price_grid = QGridLayout()
            price_grid.setSpacing(12)
            
            def add_price_row(label, value, row, is_bold=False):
                lbl = QLabel(label)
                lbl.setStyleSheet("color: #7f8c8d;" if not is_bold else "color: #2c3e50; font-weight: bold;")
                val = QLabel(f"Rs. {float(value or 0):,.2f}")
                val.setStyleSheet("color: #2c3e50;" if not is_bold else "color: #2c3e50; font-weight: bold; font-size: 15px;")
                val.setAlignment(Qt.AlignmentFlag.AlignRight)
                price_grid.addWidget(lbl, row, 0)
                price_grid.addWidget(val, row, 1)

            add_price_row("Sale Value (Excl. Tax):", invoice.total_sale_value, 0)
            add_price_row("Sales Tax:", invoice.total_tax_charged, 1)
            add_price_row("Further Tax:", invoice.total_further_tax, 2)
            
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setFrameShadow(QFrame.Shadow.Sunken)
            line.setStyleSheet("background-color: #f1f1f1;")
            price_grid.addWidget(line, 3, 0, 1, 2)
            
            add_price_row("Total Payable Amount:", invoice.total_amount, 4, True)
            
            price_layout.addLayout(price_grid)
            content_layout.addWidget(price_card)

            # Footer Actions
            footer_layout = QHBoxLayout()
            footer_layout.addStretch(1)
            
            close_btn = QPushButton("Close Details")
            close_btn.setObjectName("primaryButton")
            close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            close_btn.clicked.connect(dialog.accept)
            footer_layout.addWidget(close_btn)
            
            main_layout.addLayout(footer_layout)

            dialog.exec()

        finally:
            db.close()

    def _create_invoice_page(self) -> QWidget:
        page = QWidget(self)
        root_layout = QVBoxLayout(page)
        root_layout.setContentsMargins(30, 30, 30, 30)
        root_layout.setSpacing(20)

        # Header layout to include title and counter
        header_widget = QWidget(page)
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)

        header = QLabel("Create New Invoice")
        header.setObjectName("pageHeader")
        header_layout.addWidget(header)
        header_layout.addStretch(1)

        # FBR Stat Widget (Professional Design)
        fbr_stat_widget = QFrame(header_widget)
        fbr_stat_widget.setObjectName("fbrStatBox")
        fbr_stat_widget.setStyleSheet("""
            #fbrStatBox {
                background-color: #e74c3c;
                border-radius: 8px;
                min-width: 140px;
            }
        """)
        fbr_stat_layout = QVBoxLayout(fbr_stat_widget)
        fbr_stat_layout.setContentsMargins(15, 10, 15, 10)
        fbr_stat_layout.setSpacing(2)

        fbr_stat_label = QLabel("FBR SUBMITTED")
        fbr_stat_label.setStyleSheet("font-weight: bold; font-size: 10px; color: rgba(255,255,255,0.8); text-transform: uppercase;")
        fbr_stat_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.invoice_fbr_stat_value = QLabel("0")
        self.invoice_fbr_stat_value.setStyleSheet("font-weight: bold; font-size: 24px; color: white;")
        self.invoice_fbr_stat_value.setAlignment(Qt.AlignmentFlag.AlignCenter)

        fbr_stat_layout.addWidget(fbr_stat_label)
        fbr_stat_layout.addWidget(self.invoice_fbr_stat_value)
        header_layout.addWidget(fbr_stat_widget)

        # Environment Badge (Green Rectangle Area)
        self.invoice_env_badge = QFrame(header_widget)
        self.invoice_env_badge.setFixedSize(160, 60)
        self.invoice_env_badge.setStyleSheet("""
            QFrame {
                border: 2px solid #27ae60;
                border-radius: 8px;
                background-color: white;
            }
        """)
        env_badge_layout = QVBoxLayout(self.invoice_env_badge)
        env_badge_layout.setContentsMargins(10, 5, 10, 5)
        env_badge_layout.setSpacing(2)

        env_label_title = QLabel("ENVIRONMENT")
        env_label_title.setStyleSheet("font-weight: bold; font-size: 10px; color: #7f8c8d; text-transform: uppercase;")
        env_label_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.invoice_env_value_label = QLabel("UNKNOWN")
        self.invoice_env_value_label.setStyleSheet("font-weight: bold; font-size: 18px; color: #2c3e50;")
        self.invoice_env_value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        env_badge_layout.addWidget(env_label_title)
        env_badge_layout.addWidget(self.invoice_env_value_label)
        
        # Insert before the FBR stat widget
        header_layout.insertWidget(2, self.invoice_env_badge)

        root_layout.addWidget(header_widget)

        self.invoice_scroll_area = QScrollArea(page)
        self.invoice_scroll_area.setWidgetResizable(True)
        root_layout.addWidget(self.invoice_scroll_area, 1)

        container = QWidget()
        self.invoice_scroll_area.setWidget(container)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 10, 0)
        container_layout.setSpacing(20)

        # --- Group 1: Invoice & Customer Info ---
        group1 = QFrame()
        group1.setObjectName("formGroup")
        group1_layout = QGridLayout(group1)
        group1_layout.setContentsMargins(20, 25, 20, 20)
        group1_layout.setHorizontalSpacing(20)
        group1_layout.setVerticalSpacing(15)

        g1_title = QLabel("Invoice & Customer Information")
        g1_title.setObjectName("groupTitle")
        group1_layout.addWidget(g1_title, 0, 0, 1, 4)

        # Invoice Number
        group1_layout.addWidget(QLabel("Invoice Number"), 1, 0)
        inv_num_layout = QHBoxLayout()
        inv_num_layout.setSpacing(0)
        self.invoice_number_input = QLineEdit()
        self.invoice_number_input.setReadOnly(True)
        self.invoice_number_input.setPlaceholderText("Generating...")
        self.invoice_number_input.setStyleSheet("border-top-right-radius: 0px; border-bottom-right-radius: 0px; border-right: none;")
        
        generate_btn = QPushButton("↺")
        generate_btn.setFixedSize(40, 36)
        generate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        generate_btn.setToolTip("Generate New Number")
        generate_btn.setStyleSheet("""
            QPushButton {
                background-color: #f8f9fa;
                color: #2c3e50;
                border: 1px solid #ced4da;
                border-top-left-radius: 0px;
                border-bottom-left-radius: 0px;
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
                font-size: 20px;
                font-weight: bold;
                padding: 0;
            }
            QPushButton:hover {
                background-color: #e9ecef;
                color: #3498db;
            }
            QPushButton:pressed {
                background-color: #dee2e6;
            }
        """)
        generate_btn.clicked.connect(self._generate_invoice_number)  # type: ignore[arg-type]
        inv_num_layout.addWidget(self.invoice_number_input)
        inv_num_layout.addWidget(generate_btn)
        group1_layout.addLayout(inv_num_layout, 1, 1)

        # QR Code Placeholder (Now properly placed without overlap)
        self.invoice_qr_label = QLabel()
        self.invoice_qr_label.setFixedSize(100, 100)
        self.invoice_qr_label.setStyleSheet("border: 1px dashed #ced4da; border-radius: 4px; background: #fdfdfd;")
        self.invoice_qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.invoice_qr_label.setText("QR CODE")
        group1_layout.addWidget(self.invoice_qr_label, 1, 3)

        # CNIC
        group1_layout.addWidget(QLabel("ID Card (CNIC)"), 2, 0)
        self.invoice_buyer_cnic_input = QLineEdit()
        self.invoice_buyer_cnic_input.setPlaceholderText("12345-1234567-1")
        group1_layout.addWidget(self.invoice_buyer_cnic_input, 2, 1)

        def format_invoice_cnic_input():
            text = self.invoice_buyer_cnic_input.text()
            digits = "".join(c for c in text if c.isdigit())
            formatted = digits
            if len(digits) > 5:
                formatted = digits[:5] + "-" + digits[5:]
            if len(digits) > 12:
                formatted = formatted[:13] + "-" + formatted[13:]
            if len(formatted) > 15:
                formatted = formatted[:15]
            if formatted != text:
                self.invoice_buyer_cnic_input.setText(formatted)
            
            # Real-time CNIC validation for invoice
            if len(formatted) == 15:
                db_check = SessionLocal()
                try:
                    existing = db_check.query(Customer).filter(Customer.cnic == formatted).first()
                    if existing:
                        from app.updater.toast_notification import ToastNotification
                        msg = f"A {existing.type.lower()} named '{existing.name}' with this CNIC already exists."
                        toast = ToastNotification(
                                title="Existing Customer Found",
                                message=msg,
                                parent=self,
                                duration_ms=5000,
                                show_action=False,
                                bg_color="#3498db", # Informative Blue
                                position="top-right"
                            )
                        toast.show_notification()
                finally:
                    db_check.close()

        self.invoice_buyer_cnic_input.textChanged.connect(format_invoice_cnic_input)

        # NTN
        group1_layout.addWidget(QLabel("NTN (Optional)"), 2, 2)
        self.invoice_buyer_ntn_input = QLineEdit()
        group1_layout.addWidget(self.invoice_buyer_ntn_input, 2, 3)

        # Buyer Name & Father Name (Side by Side)
        group1_layout.addWidget(QLabel("Buyer Name"), 3, 0)
        
        buyer_name_layout = QHBoxLayout()
        buyer_name_layout.setSpacing(0)
        self.invoice_buyer_name_input = AutocompleteLineEdit()
        self.invoice_buyer_name_input.setPlaceholderText("Full Name (F2 to search dealers)")
        self.invoice_buyer_name_input.setStyleSheet("border-top-right-radius: 0px; border-bottom-right-radius: 0px; border-right: none;")
        buyer_name_layout.addWidget(self.invoice_buyer_name_input)
        
        # Allow only alphabetics and spaces for name
        def format_invoice_name_input():
            text = self.invoice_buyer_name_input.text()
            filtered = "".join(c for c in text if c.isalpha() or c.isspace())
            if filtered != text:
                self.invoice_buyer_name_input.setText(filtered)
        self.invoice_buyer_name_input.textChanged.connect(format_invoice_name_input)

        search_dealer_btn = QPushButton("🔍")
        search_dealer_btn.setFixedSize(40, 36)
        search_dealer_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        search_dealer_btn.setToolTip("Search Dealers (F2)")
        search_dealer_btn.setStyleSheet("""
            QPushButton {
                background-color: #f8f9fa;
                color: #2c3e50;
                border: 1px solid #ced4da;
                border-top-left-radius: 0px;
                border-bottom-left-radius: 0px;
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
                font-size: 18px;
                font-weight: bold;
                padding: 0;
            }
            QPushButton:hover {
                background-color: #e9ecef;
                color: #3498db;
            }
            QPushButton:pressed {
                background-color: #dee2e6;
            }
        """)
        search_dealer_btn.clicked.connect(self._open_dealer_search_dialog)
        buyer_name_layout.addWidget(search_dealer_btn)
        
        group1_layout.addLayout(buyer_name_layout, 3, 1)

        group1_layout.addWidget(QLabel("Father Name"), 3, 2)
        self.invoice_buyer_father_input = QLineEdit()
        group1_layout.addWidget(self.invoice_buyer_father_input, 3, 3)

        # Allow only alphabetics and spaces for father name
        def format_invoice_father_input():
            text = self.invoice_buyer_father_input.text()
            filtered = "".join(c for c in text if c.isalpha() or c.isspace())
            if filtered != text:
                self.invoice_buyer_father_input.setText(filtered)
        self.invoice_buyer_father_input.textChanged.connect(format_invoice_father_input)

        # Phone & Address
        group1_layout.addWidget(QLabel("Cell (Phone)"), 4, 0)
        self.invoice_buyer_phone_input = QLineEdit()
        self.invoice_buyer_phone_input.setPlaceholderText("03021234567")
        group1_layout.addWidget(self.invoice_buyer_phone_input, 4, 1)
        
        # Auto-format Phone Number as user types
        def format_invoice_phone_input():
            text = self.invoice_buyer_phone_input.text()
            # Allow only digits and limit to 11
            digits = "".join(c for c in text if c.isdigit())
            if len(digits) > 11:
                digits = digits[:11]
            if digits != text:
                self.invoice_buyer_phone_input.setText(digits)

        self.invoice_buyer_phone_input.textChanged.connect(format_invoice_phone_input)

        group1_layout.addWidget(QLabel("Address"), 4, 2)
        self.invoice_buyer_address_input = QLineEdit()
        group1_layout.addWidget(self.invoice_buyer_address_input, 4, 3)

        container_layout.addWidget(group1)

        # --- Group 2: Product & Payment ---
        group2 = QFrame()
        group2.setObjectName("formGroup")
        group2_layout = QGridLayout(group2)
        group2_layout.setContentsMargins(20, 25, 20, 20)
        group2_layout.setHorizontalSpacing(20)
        group2_layout.setVerticalSpacing(15)

        g2_title = QLabel("Product & Payment Details")
        g2_title.setObjectName("groupTitle")
        group2_layout.addWidget(g2_title, 0, 0, 1, 4)

        # Model & Color
        group2_layout.addWidget(QLabel("Model"), 1, 0)
        self.invoice_model_combo = QComboBox()
        group2_layout.addWidget(self.invoice_model_combo, 1, 1)

        group2_layout.addWidget(QLabel("Color"), 1, 2)
        self.invoice_color_combo = QComboBox()
        group2_layout.addWidget(self.invoice_color_combo, 1, 3)

        # Chassis & Engine
        group2_layout.addWidget(QLabel("Chassis Number"), 2, 0)
        self.invoice_chassis_input = AutocompleteLineEdit()
        group2_layout.addWidget(self.invoice_chassis_input, 2, 1)

        group2_layout.addWidget(QLabel("Engine Number"), 2, 2)
        self.invoice_engine_input = QLineEdit()
        group2_layout.addWidget(self.invoice_engine_input, 2, 3)

        # Payment Mode & Quantity
        group2_layout.addWidget(QLabel("Payment Mode"), 3, 0)
        self.invoice_payment_mode_combo = QComboBox()
        self.invoice_payment_mode_combo.addItems(["Cash", "Credit", "Cheque", "Online"])
        group2_layout.addWidget(self.invoice_payment_mode_combo, 3, 1)

        group2_layout.addWidget(QLabel("Quantity"), 3, 2)
        self.invoice_quantity_spin = QSpinBox()
        self.invoice_quantity_spin.setRange(1, 999)
        group2_layout.addWidget(self.invoice_quantity_spin, 3, 3)

        container_layout.addWidget(group2)

        # --- Group 3: Pricing & Summary ---
        self.invoice_pricing_group = QFrame()
        self.invoice_pricing_group.setObjectName("formGroup")
        group3_layout = QGridLayout(self.invoice_pricing_group)
        group3_layout.setContentsMargins(20, 25, 20, 20)
        group3_layout.setHorizontalSpacing(20)
        group3_layout.setVerticalSpacing(15)

        g3_title = QLabel("Pricing Summary")
        g3_title.setObjectName("groupTitle")
        group3_layout.addWidget(g3_title, 0, 0, 1, 4)

        # Amount & Tax
        group3_layout.addWidget(QLabel("Amount (Excl. Tax)"), 1, 0)
        self.invoice_amount_spin = QDoubleSpinBox()
        self.invoice_amount_spin.setRange(0, 99999999)
        group3_layout.addWidget(self.invoice_amount_spin, 1, 1)

        group3_layout.addWidget(QLabel("Sale Tax"), 1, 2)
        self.invoice_tax_spin = QDoubleSpinBox()
        self.invoice_tax_spin.setRange(0, 99999999)
        group3_layout.addWidget(self.invoice_tax_spin, 1, 3)

        # Further Tax & Total
        group3_layout.addWidget(QLabel("Further Tax"), 2, 0)
        self.invoice_further_tax_spin = QDoubleSpinBox()
        self.invoice_further_tax_spin.setRange(0, 99999999)
        group3_layout.addWidget(self.invoice_further_tax_spin, 2, 1)

        group3_layout.addWidget(QLabel("Total Price (Incl. Tax)"), 2, 2)
        self.invoice_total_spin = QDoubleSpinBox()
        self.invoice_total_spin.setRange(0, 99999999)
        self.invoice_total_spin.setStyleSheet("font-weight: bold; color: #2c3e50; font-size: 15px;")
        group3_layout.addWidget(self.invoice_total_spin, 2, 3)

        container_layout.addWidget(self.invoice_pricing_group)

        # Bottom Button Bar
        button_bar = QWidget(page)
        button_layout = QHBoxLayout(button_bar)
        button_layout.setContentsMargins(0, 10, 0, 0)
        button_layout.setSpacing(15)
        
        self.invoice_fbr_label = QLabel("Ready to submit")
        self.invoice_fbr_label.setStyleSheet("color: #7f8c8d; font-style: italic;")
        button_layout.addWidget(self.invoice_fbr_label)
        
        button_layout.addStretch(1)
        
        reset_btn = QPushButton("Reset Form")
        reset_btn.setObjectName("resetButton")
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.clicked.connect(self._reset_invoice_form)  # type: ignore[arg-type]
        button_layout.addWidget(reset_btn)

        self.invoice_submit_btn = QPushButton("Submit to FBR")
        self.invoice_submit_btn.setObjectName("primaryButton")
        self.invoice_submit_btn.setMinimumWidth(180)
        self.invoice_submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.invoice_submit_btn.setEnabled(False)
        self.invoice_submit_btn.clicked.connect(self._submit_invoice)  # type: ignore[arg-type]
        button_layout.addWidget(self.invoice_submit_btn)
        
        root_layout.addWidget(button_bar)

        # Autocomplete setup for Buyer Name
        self._dealer_completer_model = QStringListModel(self)
        self.invoice_dealer_completer = QCompleter(self._dealer_completer_model, self)
        self.invoice_dealer_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.invoice_dealer_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.invoice_dealer_completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.invoice_dealer_completer.setMaxVisibleItems(10)
        self.invoice_buyer_name_input.setCompleter(self.invoice_dealer_completer)
        self.invoice_buyer_name_input.on_completion_accept = self._on_dealer_business_selected

        self._dealer_completer_timer = QTimer(self)
        self._dealer_completer_timer.setSingleShot(True)
        self._dealer_completer_timer.setInterval(200)
        self._dealer_completer_timer.timeout.connect(self._perform_dealer_search)

        dealer_search_shortcut = QShortcut(QKeySequence(Qt.Key.Key_F2), self.invoice_buyer_name_input)
        dealer_search_shortcut.activated.connect(self._open_dealer_search_dialog)

        # Autocomplete setup for Chassis
        self._chassis_completer_model = QStringListModel(self)
        self.invoice_chassis_completer = QCompleter(self._chassis_completer_model, self)
        self.invoice_chassis_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.invoice_chassis_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.invoice_chassis_completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.invoice_chassis_completer.setMaxVisibleItems(10)
        self.invoice_chassis_input.setCompleter(self.invoice_chassis_completer)
        self.invoice_chassis_input.on_completion_accept = self._on_chassis_selected

        self._chassis_completer_timer = QTimer(self)
        self._chassis_completer_timer.setSingleShot(True)
        self._chassis_completer_timer.setInterval(200)
        self._chassis_completer_timer.timeout.connect(self._perform_chassis_search)

        # Connect all fields to live validation
        for widget in [
            self.invoice_buyer_cnic_input,
            self.invoice_buyer_name_input,
            self.invoice_buyer_father_input,
            self.invoice_buyer_phone_input,
            self.invoice_buyer_address_input,
            self.invoice_chassis_input,
            self.invoice_engine_input
        ]:
            widget.textChanged.connect(self._check_invoice_form_completeness)

        self.invoice_model_combo.currentTextChanged.connect(self._on_invoice_model_changed)  # type: ignore[arg-type]
        self.invoice_model_combo.currentTextChanged.connect(self._check_invoice_form_completeness)
        self.invoice_color_combo.currentTextChanged.connect(self._on_invoice_color_changed)  # type: ignore[arg-type]
        self.invoice_color_combo.currentTextChanged.connect(self._check_invoice_form_completeness)
        self.invoice_payment_mode_combo.currentTextChanged.connect(self._check_invoice_form_completeness)
        self.invoice_quantity_spin.valueChanged.connect(self._recalculate_invoice_totals)  # type: ignore[arg-type]
        self.invoice_amount_spin.valueChanged.connect(self._recalculate_invoice_totals)  # type: ignore[arg-type]
        self.invoice_buyer_name_input.textEdited.connect(self._on_invoice_buyer_name_changed)  # type: ignore[arg-type]
        self.invoice_chassis_input.textEdited.connect(self._on_invoice_chassis_changed)  # type: ignore[arg-type]
        self.invoice_buyer_father_input.textChanged.connect(self._on_invoice_father_name_changed)  # type: ignore[arg-type]
        self.invoice_buyer_phone_input.textChanged.connect(self._on_invoice_cell_changed)  # type: ignore[arg-type]
        self.invoice_buyer_cnic_input.textChanged.connect(self._on_invoice_cnic_changed)  # type: ignore[arg-type]

        # ENTER KEY NAVIGATION (CNIC to Engine Number)
        def setup_enter_nav(widget: QWidget):
            if isinstance(widget, QLineEdit):
                widget.returnPressed.connect(self.focusNextChild)
            elif isinstance(widget, QComboBox):
                # QComboBox needs a custom filter or event override to handle Enter
                widget.installEventFilter(self)

        for widget in [
            self.invoice_buyer_cnic_input,
            self.invoice_buyer_ntn_input,
            self.invoice_buyer_name_input,
            self.invoice_buyer_father_input,
            self.invoice_buyer_phone_input,
            self.invoice_buyer_address_input,
            self.invoice_model_combo,
            self.invoice_color_combo,
            self.invoice_payment_mode_combo,
            self.invoice_chassis_input,
            self.invoice_engine_input,
        ]:
            setup_enter_nav(widget)

        # Trigger data lookup when Enter is pressed on Chassis input
        self.invoice_chassis_input.returnPressed.connect(lambda: self._on_chassis_selected(self.invoice_chassis_input.text()))

        # Engine Number triggers submission to FBR when Enter is pressed
        try:
            self.invoice_engine_input.returnPressed.disconnect()
        except:
            pass
        self.invoice_engine_input.returnPressed.connect(self._submit_invoice)  # type: ignore[arg-type]

        # Set explicit Tab Order for the entire invoice form (Visual top-to-bottom, left-to-right)
        self.setTabOrder(self.invoice_buyer_cnic_input, self.invoice_buyer_ntn_input)
        self.setTabOrder(self.invoice_buyer_ntn_input, self.invoice_buyer_name_input)
        self.setTabOrder(self.invoice_buyer_name_input, self.invoice_buyer_father_input)
        self.setTabOrder(self.invoice_buyer_father_input, self.invoice_buyer_phone_input)
        self.setTabOrder(self.invoice_buyer_phone_input, self.invoice_buyer_address_input)
        self.setTabOrder(self.invoice_buyer_address_input, self.invoice_model_combo)
        self.setTabOrder(self.invoice_model_combo, self.invoice_color_combo)
        # Move from Color (Row 1 Right) to Chassis (Row 2 Left)
        self.setTabOrder(self.invoice_color_combo, self.invoice_chassis_input)
        self.setTabOrder(self.invoice_chassis_input, self.invoice_engine_input)
        # Move from Engine (Row 2 Right) to Payment Mode (Row 3 Left)
        self.setTabOrder(self.invoice_engine_input, self.invoice_payment_mode_combo)
        self.setTabOrder(self.invoice_payment_mode_combo, self.invoice_quantity_spin)
        self.setTabOrder(self.invoice_quantity_spin, self.invoice_submit_btn)

        self._invoice_current_price = None
        self._load_invoice_models()
        self._generate_invoice_number()

        # Set initial environment badge
        active_env = settings_service.get_active_environment()
        self.invoice_env_value_label.setText(active_env.upper())
        color = "#e67e22" if active_env.upper() == "SANDBOX" else "#27ae60"
        self.invoice_env_badge.setStyleSheet(f"QFrame {{ border: 2px solid {color}; border-radius: 8px; background-color: white; }}")

        return page

    def _create_settings_page(self) -> QWidget:
        page = QWidget(self)
        root_layout = QVBoxLayout(page)
        root_layout.setContentsMargins(30, 30, 30, 30)
        root_layout.setSpacing(20)

        header = QLabel("Application Settings")
        header.setObjectName("pageHeader")
        root_layout.addWidget(header)

        scroll = QScrollArea(page)
        scroll.setWidgetResizable(True)
        root_layout.addWidget(scroll, 1)

        container = QWidget()
        scroll.setWidget(container)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 10, 0)
        container_layout.setSpacing(20)

        # --- Group 1: FBR Configuration ---
        fbr_group = QFrame()
        fbr_group.setObjectName("formGroup")
        fbr_layout = QGridLayout(fbr_group)
        fbr_layout.setContentsMargins(20, 25, 20, 20)
        fbr_layout.setHorizontalSpacing(20)
        fbr_layout.setVerticalSpacing(15)

        fbr_title = QLabel("FBR API CONFIGURATION")
        fbr_title.setObjectName("groupTitle")
        fbr_layout.addWidget(fbr_title, 0, 0, 1, 2)

        fbr_layout.addWidget(QLabel("Environment"), 1, 0)
        self.settings_env_combo = QComboBox()
        self.settings_env_combo.addItems(["SANDBOX", "PRODUCTION"])
        self.settings_env_combo.currentTextChanged.connect(self._load_settings_for_env)
        fbr_layout.addWidget(self.settings_env_combo, 1, 1)

        fbr_layout.addWidget(QLabel("API Base URL"), 2, 0)
        self.settings_api_url = QLineEdit()
        fbr_layout.addWidget(self.settings_api_url, 2, 1)

        fbr_layout.addWidget(QLabel("POS ID"), 3, 0)
        self.settings_pos_id = QLineEdit()
        fbr_layout.addWidget(self.settings_pos_id, 3, 1)

        fbr_layout.addWidget(QLabel("USIN"), 4, 0)
        self.settings_usin = QLineEdit()
        fbr_layout.addWidget(self.settings_usin, 4, 1)

        fbr_layout.addWidget(QLabel("Auth Token"), 5, 0)
        self.settings_auth_token = QLineEdit()
        self.settings_auth_token.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        fbr_layout.addWidget(self.settings_auth_token, 5, 1)

        container_layout.addWidget(fbr_group)

        # --- Group 2: Business & Tax Rules ---
        tax_group = QFrame()
        tax_group.setObjectName("formGroup")
        tax_layout = QGridLayout(tax_group)
        tax_layout.setContentsMargins(20, 25, 20, 20)
        tax_layout.setHorizontalSpacing(20)
        tax_layout.setVerticalSpacing(15)

        tax_title = QLabel("BUSINESS & TAX RULES")
        tax_title.setObjectName("groupTitle")
        tax_layout.addWidget(tax_title, 0, 0, 1, 4)

        tax_layout.addWidget(QLabel("Default Sales Tax (%)"), 1, 0)
        self.settings_tax_rate = QDoubleSpinBox()
        self.settings_tax_rate.setRange(0, 100)
        self.settings_tax_rate.setDecimals(1)
        tax_layout.addWidget(self.settings_tax_rate, 1, 1)

        tax_layout.addWidget(QLabel("PCT Code"), 1, 2)
        self.settings_pct_code = QLineEdit()
        tax_layout.addWidget(self.settings_pct_code, 1, 3)

        tax_layout.addWidget(QLabel("Item Code Prefix"), 2, 0)
        self.settings_item_code = QLineEdit()
        tax_layout.addWidget(self.settings_item_code, 2, 1)

        tax_layout.addWidget(QLabel("Default Item Name"), 2, 2)
        self.settings_item_name = QLineEdit()
        tax_layout.addWidget(self.settings_item_name, 2, 3)

        tax_layout.addWidget(QLabel("Default Invoice Type"), 3, 0)
        self.settings_invoice_type = QComboBox()
        self.settings_invoice_type.addItems(["Standard", "Debit Note", "Credit Note"])
        tax_layout.addWidget(self.settings_invoice_type, 3, 1)

        tax_layout.addWidget(QLabel("Default Discount (%)"), 3, 2)
        self.settings_discount = QDoubleSpinBox()
        self.settings_discount.setRange(0, 100)
        tax_layout.addWidget(self.settings_discount, 3, 3)

        tax_layout.addWidget(QLabel("Business Name"), 4, 0)
        self.settings_business_name = QLineEdit()
        tax_layout.addWidget(self.settings_business_name, 4, 1, 1, 3) # Span 3 columns

        container_layout.addWidget(tax_group)

        # --- Group 3: Application Updates ---
        update_group = QFrame()
        update_group.setObjectName("formGroup")
        update_layout = QGridLayout(update_group)
        update_layout.setContentsMargins(20, 25, 20, 20)
        update_layout.setHorizontalSpacing(20)
        update_layout.setVerticalSpacing(15)

        update_title = QLabel("APPLICATION UPDATES")
        update_title.setObjectName("groupTitle")
        update_layout.addWidget(update_title, 0, 0, 1, 2)

        from app.core.version_manager import VersionManager
        update_layout.addWidget(QLabel("Current Version:"), 1, 0)
        self.settings_version_label = QLabel(VersionManager.get_version_string())
        self.settings_version_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        update_layout.addWidget(self.settings_version_label, 1, 1)

        self.manual_update_btn = QPushButton("🔄 Check for Updates Now")
        self.manual_update_btn.setFixedWidth(200)
        self.manual_update_btn.clicked.connect(self._on_manual_update_check)
        update_layout.addWidget(self.manual_update_btn, 2, 0, 1, 2)

        container_layout.addWidget(update_group)

        # --- Group 4: Database Backup & Restore ---
        backup_group = QFrame()
        backup_group.setObjectName("formGroup")
        backup_layout = QVBoxLayout(backup_group)
        backup_layout.setContentsMargins(20, 25, 20, 20)
        backup_layout.setSpacing(15)

        backup_title_layout = QHBoxLayout()
        backup_title = QLabel("DATABASE BACKUP & RESTORE")
        backup_title.setObjectName("groupTitle")
        backup_title.setStyleSheet("color: #2c3e50; font-weight: bold;")
        backup_title_layout.addWidget(backup_title)
        backup_title_layout.addStretch(1)
        
        self.manual_backup_btn = QPushButton("💾 Create Backup Now")
        self.manual_backup_btn.setStyleSheet("background-color: #27ae60; color: white; padding: 5px 15px;")
        self.manual_backup_btn.clicked.connect(self._on_create_manual_backup)
        backup_title_layout.addWidget(self.manual_backup_btn)

        self.restore_external_btn = QPushButton("📂 Restore from File...")
        self.restore_external_btn.setStyleSheet("background-color: #3498db; color: white; padding: 5px 15px;")
        self.restore_external_btn.clicked.connect(self._on_restore_external_file)
        backup_title_layout.addWidget(self.restore_external_btn)
        
        backup_layout.addLayout(backup_title_layout)

        # Settings sub-layout
        backup_settings_grid = QGridLayout()
        backup_settings_grid.setSpacing(15)

        backup_settings_grid.addWidget(QLabel("Backup Location:"), 0, 0)
        backup_path_layout = QHBoxLayout()
        self.backup_path_input = QLineEdit()
        self.backup_path_input.setReadOnly(True)
        backup_path_layout.addWidget(self.backup_path_input)
        
        self.browse_backup_btn = QPushButton("📂 Browse")
        self.browse_backup_btn.setFixedWidth(80)
        self.browse_backup_btn.clicked.connect(self._on_browse_backup_path)
        backup_path_layout.addWidget(self.browse_backup_btn)
        backup_settings_grid.addLayout(backup_path_layout, 0, 1)

        self.backup_auto_enabled = QCheckBox("Enable Automatic Scheduled Backups")
        self.backup_auto_enabled.stateChanged.connect(self._on_backup_settings_changed)
        backup_settings_grid.addWidget(self.backup_auto_enabled, 1, 0, 1, 2)

        backup_settings_grid.addWidget(QLabel("Backup Interval:"), 2, 0)
        self.backup_interval_combo = QComboBox()
        self.backup_interval_combo.addItems(["daily", "weekly", "monthly"])
        self.backup_interval_combo.currentTextChanged.connect(self._on_backup_settings_changed)
        backup_settings_grid.addWidget(self.backup_interval_combo, 2, 1)

        backup_settings_grid.addWidget(QLabel("Backup Time (HH:MM):"), 3, 0)
        self.backup_time_input = QLineEdit()
        self.backup_time_input.setPlaceholderText("00:00")
        self.backup_time_input.textChanged.connect(self._on_backup_settings_changed)
        backup_settings_grid.addWidget(self.backup_time_input, 3, 1)

        backup_settings_grid.addWidget(QLabel("Retention (Days):"), 4, 0)
        self.backup_retention_spin = QSpinBox()
        self.backup_retention_spin.setRange(1, 365)
        self.backup_retention_spin.setValue(30)
        self.backup_retention_spin.valueChanged.connect(self._on_backup_settings_changed)
        backup_settings_grid.addWidget(self.backup_retention_spin, 4, 1)

        self.backup_encrypt_enabled = QCheckBox("Encrypt Backup Files (Professional Security)")
        self.backup_encrypt_enabled.setChecked(True)
        self.backup_encrypt_enabled.stateChanged.connect(self._on_backup_settings_changed)
        backup_settings_grid.addWidget(self.backup_encrypt_enabled, 5, 0, 1, 2)

        backup_layout.addLayout(backup_settings_grid)

        # Recent Backups Table
        backup_list_label = QLabel("RECENT BACKUPS")
        backup_list_label.setStyleSheet("font-weight: bold; color: #7f8c8d; font-size: 11px; margin-top: 10px;")
        backup_layout.addWidget(backup_list_label)

        self.backup_table = QTableWidget()
        self.backup_table.setColumnCount(4)
        self.backup_table.setHorizontalHeaderLabels(["Date", "File Name", "Size (MB)", "Actions"])
        self.backup_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.backup_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.backup_table.verticalHeader().setVisible(False)
        self.backup_table.setFixedHeight(200)
        self.backup_table.setStyleSheet("""
            QTableWidget { border: 1px solid #dee2e6; border-radius: 4px; background-color: #fcfcfc; }
            QHeaderView::section { background-color: #f1f1f1; padding: 5px; border: none; font-weight: bold; }
        """)
        backup_layout.addWidget(self.backup_table)

        container_layout.addWidget(backup_group)

        # Action Buttons
        btn_bar = QWidget()
        btn_layout = QHBoxLayout(btn_bar)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.addStretch(1)

        save_btn = QPushButton("Save Settings")
        save_btn.setObjectName("primaryButton")
        save_btn.clicked.connect(self._save_settings)
        btn_layout.addWidget(save_btn)

        container_layout.addWidget(btn_bar)
        container_layout.addStretch(1)

        # Initial load
        active_env = settings_service.get_active_environment()
        self.settings_env_combo.setCurrentText(active_env)
        self._load_settings_for_env(active_env)
        self._load_backup_ui()

        return page

    def _load_settings_for_env(self, env: str) -> None:
        data = settings_service.get_environment(env)
        if not data:
            return
        
        self.settings_api_url.setText(data.get("base_url", ""))
        self.settings_pos_id.setText(data.get("pos_id", ""))
        self.settings_usin.setText(data.get("usin", ""))
        self.settings_auth_token.setText(data.get("token", ""))
        self.settings_tax_rate.setValue(float(data.get("tax_rate", 18.0)))
        self.settings_pct_code.setText(data.get("pct_code", "8711.2010"))
        self.settings_item_code.setText(data.get("item_code", "MOTO"))
        self.settings_item_name.setText(data.get("item_name", "Motorcycle"))
        self.settings_invoice_type.setCurrentText(data.get("invoice_type", "Standard"))
        self.settings_discount.setValue(float(data.get("discount", 0.0)))
        self.settings_business_name.setText(data.get("business_name", "Ehsan Trader"))

    def _save_settings(self) -> None:
        env = self.settings_env_combo.currentText()
        business_name = self.settings_business_name.text().strip() or "Ehsan Trader"
        try:
            settings_service.save_environment(
                env=env,
                base_url=self.settings_api_url.text(),
                pos_id=self.settings_pos_id.text(),
                usin=self.settings_usin.text(),
                token=self.settings_auth_token.text(),
                tax_rate=str(self.settings_tax_rate.value()),
                pct_code=self.settings_pct_code.text(),
                invoice_type=self.settings_invoice_type.currentText(),
                discount=str(self.settings_discount.value()),
                item_code=self.settings_item_code.text(),
                item_name=self.settings_item_name.text(),
                business_name=business_name
            )
            settings_service.set_active_environment(env)
            self._update_app_branding(business_name)
            
            # Update environment badge on invoice page if it exists
            if hasattr(self, "invoice_env_value_label"):
                self.invoice_env_value_label.setText(env.upper())
                color = "#e67e22" if env.upper() == "SANDBOX" else "#27ae60"
                self.invoice_env_badge.setStyleSheet(f"QFrame {{ border: 2px solid {color}; border-radius: 8px; background-color: white; }}")
            
            self._show_success("Settings Saved", f"Configuration for {env} has been updated and set as active.")
        except Exception as e:
            self._show_error("Save Error", str(e))

    def _load_backup_ui(self):
        """Load backup settings into UI elements."""
        config = backup_service.config
        self.backup_path_input.setText(config.local_path)
        self.backup_auto_enabled.setChecked(config.enabled)
        self.backup_interval_combo.setCurrentText(config.interval)
        self.backup_time_input.setText(config.time_str)
        self.backup_retention_spin.setValue(config.retention_days)
        self.backup_encrypt_enabled.setChecked(config.encrypt)
        self._reload_backup_list()

    def _on_backup_settings_changed(self):
        """Update backup service config when UI elements change."""
        backup_service.config.enabled = self.backup_auto_enabled.isChecked()
        backup_service.config.interval = self.backup_interval_combo.currentText()
        backup_service.config.time_str = self.backup_time_input.text()
        backup_service.config.retention_days = self.backup_retention_spin.value()
        backup_service.config.encrypt = self.backup_encrypt_enabled.isChecked()
        backup_service.save_config()
        
        # Restart scheduler if enabled
        if backup_service.config.enabled:
            backup_service.start_scheduler()
        else:
            backup_service.stop_scheduler()

    def _on_browse_backup_path(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Backup Directory", self.backup_path_input.text())
        if dir_path:
            self.backup_path_input.setText(dir_path)
            backup_service.config.local_path = dir_path
            backup_service.save_config()
            self._reload_backup_list()

    def _on_create_manual_backup(self):
        """Professionally launches a manual backup in a separate thread."""
        self.manual_backup_btn.setEnabled(False)
        self.manual_backup_btn.setText("⏳ Backing up...")
        logger.info("Manual backup requested by user.")
        
        # 1. Setup Thread and Worker
        self._backup_thread = QThread()
        self._backup_worker = BackupWorker()
        self._backup_worker.moveToThread(self._backup_thread)
        
        # 2. Connect Signals
        self._backup_thread.started.connect(self._backup_worker.run)
        self._backup_worker.finished.connect(self._handle_backup_result)
        self._backup_worker.error.connect(lambda msg: self._handle_backup_result({"success": False, "message": msg}))
        
        # 3. Cleanup on completion
        self._backup_worker.finished.connect(self._backup_thread.quit)
        self._backup_worker.finished.connect(self._backup_worker.deleteLater)
        self._backup_thread.finished.connect(self._backup_thread.deleteLater)
        
        # 4. Start Thread
        self._backup_thread.start()

    def _handle_backup_result(self, result: Dict):
        """Restores the backup button state and provides user feedback."""
        self.manual_backup_btn.setEnabled(True)
        self.manual_backup_btn.setText("💾 Create Backup Now")
        logger.info(f"Manual backup completed with success: {result.get('success', False)}")
        
        if result.get("success"):
            self._show_success("Backup Successful", result.get("message", "Database backed up successfully."))
            self._reload_backup_list()
        else:
            error_msg = result.get("message", "Unknown error occurred.")
            logger.error(f"Manual backup failed: {error_msg}")
            self._show_error("Backup Failed", error_msg)

    def _reload_backup_list(self):
        backups = backup_service.list_backups()
        self.backup_table.setRowCount(len(backups))
        
        for i, b in enumerate(backups):
            self.backup_table.setItem(i, 0, QTableWidgetItem(b["date"]))
            self.backup_table.setItem(i, 1, QTableWidgetItem(b["name"]))
            self.backup_table.setItem(i, 2, QTableWidgetItem(str(b["size_mb"])))
            
            # Action buttons
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(5, 2, 5, 2)
            actions_layout.setSpacing(10)
            
            restore_btn = QPushButton("Restore")
            restore_btn.setStyleSheet("background-color: #3498db; color: white; padding: 2px 8px; font-size: 11px;")
            restore_btn.clicked.connect(lambda checked, path=b["path"]: self._on_restore_backup(path))
            
            delete_btn = QPushButton("Delete")
            delete_btn.setStyleSheet("background-color: #e74c3c; color: white; padding: 2px 8px; font-size: 11px;")
            delete_btn.clicked.connect(lambda checked, path=b["path"]: self._on_delete_backup(path))
            
            actions_layout.addWidget(restore_btn)
            actions_layout.addWidget(delete_btn)
            self.backup_table.setCellWidget(i, 3, actions_widget)

    def _on_restore_external_file(self):
        """Allows selecting an external backup file for restore."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "Select Backup File", 
            "", 
            "Backup Files (*.zip *.enc);;All Files (*)"
        )
        if file_path:
            self._on_restore_backup(file_path)

    def _on_restore_backup(self, path: str):
        """Professionally handles the restore process by launching an external utility."""
        backup_file = os.path.basename(path)
        
        # Professional Custom Warning Dialog
        msg = (
            f"You are about to restore the database from: <b>{backup_file}</b><br><br>"
            "<span style='color: #e74c3c;'><b>⚠️ CRITICAL WARNING:</b></span><br>"
            "1. This will <b>COMPLETELY OVERWRITE</b> your current database.<br>"
            "2. All current transactions, invoices, and customers will be replaced.<br>"
            "3. This action is <b>IRREVERSIBLE</b>.<br><br>"
            "The application will <b>CLOSE</b> now to perform the restore safely, and then restart automatically."
        )
        
        reply = QMessageBox.warning(
            self, 
            "Database Restore Confirmation", 
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Check if we are using MySQL or SQLite
            is_mysql = "mysql" in settings.DB_URL.lower()
            
            if is_mysql:
                # For MySQL, we don't need the external utility as much because there's no file lock
                # We use the professional BackupWorker for MySQL as well
                progress = QProgressDialog("Restoring MySQL Database...", None, 0, 0, self)
                progress.setWindowTitle("Professional Database Restore")
                progress.setWindowModality(Qt.WindowModality.WindowModal)
                progress.setMinimumWidth(400)
                progress.setCancelButton(None)
                progress.setStyleSheet("""
                    QProgressDialog {
                        background-color: white;
                        border: 1px solid #ced4da;
                        border-radius: 8px;
                    }
                    QLabel {
                        font-size: 14px;
                        color: #2c3e50;
                        padding: 10px;
                    }
                    QProgressBar {
                        border: 1px solid #ced4da;
                        border-radius: 4px;
                        text-align: center;
                        height: 20px;
                    }
                    QProgressBar::chunk {
                        background-color: #3498db;
                    }
                """)
                progress.show()
                QApplication.processEvents()
                
                close_all_db_connections()
                
                # 1. Setup Thread and Worker
                self._restore_thread = QThread()
                self._restore_worker = MySQLRestoreWorker(path)
                self._restore_worker.moveToThread(self._restore_thread)
                
                # 2. Connect Signals
                self._restore_thread.started.connect(self._restore_worker.run)
                self._restore_worker.finished.connect(lambda result: self._handle_restore_result(result, progress))
                self._restore_worker.error.connect(lambda msg: self._handle_restore_result({"success": False, "message": msg}, progress))
                
                # 3. Cleanup
                self._restore_worker.finished.connect(self._restore_thread.quit)
                self._restore_worker.finished.connect(self._restore_worker.deleteLater)
                self._restore_thread.finished.connect(self._restore_thread.deleteLater)
                
                # 4. Start Thread
                self._restore_thread.start()
                return

            # SQLite logic (Use External Utility to avoid file locks)
            db_path = backup_service.get_db_path()
            if not db_path:
                logger.error(f"Could not determine SQLite path from URL: {settings.DB_URL}")
                self._show_error("Restore Error", 
                    f"Could not determine database path.<br><br>"
                    f"<b>Current DB URL:</b> {settings.DB_URL}<br><br>"
                    "Please ensure your .env file is configured correctly for SQLite.")
                return
                
            encryption_key = backup_service.config.encryption_key if backup_service.config.encrypt else "None"
            
            # Determine how to restart the main app
            if getattr(sys, 'frozen', False):
                main_app_entry = os.path.abspath(sys.executable)
            else:
                main_app_entry = os.path.abspath(sys.argv[0]) # Usually run.py or main.py
            
            # Path to the utility script
            project_root = Path(__file__).resolve().parent.parent.parent
            util_script = project_root / "restore_util.py"
            
            try:
                # Launch the external restorer in a new terminal/window
                if sys.platform == "win32":
                    # Use sys.executable to ensure we use the same Python environment
                    python_exe = os.path.abspath(sys.executable)
                    cmd = f'"{python_exe}" "{util_script}" "{path}" "{db_path}" "{encryption_key}" "{main_app_entry}"'
                    subprocess.Popen(f'start cmd /k {cmd}', shell=True)
                else:
                    subprocess.Popen([sys.executable, str(util_script), str(path), str(db_path), encryption_key, main_app_entry])
                
                # Exit the main process immediately to release ALL locks
                os._exit(0)
                
            except Exception as e:
                self._show_error("Restore Launch Failed", str(e))

    def _handle_restore_result(self, result: Dict, progress_dialog: QProgressDialog):
        # Close the progress dialog
        progress_dialog.close()
        
        self.restore_external_btn.setEnabled(True)
        self.restore_external_btn.setText("📂 Restore from File...")
        
        if result.get("success"):
            QMessageBox.information(
                self, 
                "Restore Successful", 
                "The database has been restored successfully.<br><br>The application will now restart."
            )
            self._restart_application()
        else:
            # Re-start background tasks if failed
            if hasattr(self, '_update_check_timer'):
                self._update_check_timer.start()
            backup_service.start_scheduler()
            
            self._show_error("Restore Failed", result.get("message", "Unknown error during restore."))

    def _restart_application(self):
        """Robust application restart mechanism."""
        try:
            # Close application
            QApplication.quit()
            
            # Prepare restart command
            if getattr(sys, 'frozen', False):
                # If packaged as exe
                executable = sys.executable
                os.startfile(executable)
            else:
                # If running as script, use module-based launch to avoid ModuleNotFoundError
                python = sys.executable
                # The root directory is the parent of the 'app' directory
                project_root = Path(__file__).resolve().parent.parent.parent
                subprocess.Popen([python, "-m", "app.main"], cwd=str(project_root))
            
            # Force immediate exit to release all file handles
            os._exit(0)
        except Exception as e:
            logger.error(f"Restart failed: {e}")
            # Fallback message
            print(f"Please restart the application manually: {e}")

    def _on_delete_backup(self, path: str):
        reply = QMessageBox.question(
            self, "Confirm Delete", 
            "Are you sure you want to delete this backup file?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                os.remove(path)
                self._reload_backup_list()
            except Exception as e:
                self._show_error("Delete Error", str(e))

    def _update_app_branding(self, business_name: str) -> None:
        """Dynamically update window title and sidebar branding."""
        self.setWindowTitle(f"{business_name} FBR System")
        if hasattr(self, "nav_header_label"):
            self.nav_header_label.setText(business_name.upper())

    def _create_welcome_page(self) -> QWidget:
        page = QWidget(self)
        page.setStyleSheet("background-color: #f8f9fa;")
        
        # Main layout for the page with a scroll area
        main_layout = QVBoxLayout(page)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(30)

        # Main Banner
        banner = QFrame()
        banner.setObjectName("welcomeBanner")
        banner.setStyleSheet("""
            QFrame#welcomeBanner {
                background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 #1a252f, stop:1 #2c3e50);
                border-radius: 15px;
            }
        """)
        banner_layout = QVBoxLayout(banner)
        banner_layout.setContentsMargins(30, 30, 30, 30)

        title = QLabel(f"Welcome back to {self.windowTitle()}!")
        title.setStyleSheet("color: white; font-size: 28px; font-weight: bold; background: transparent;")
        title.setWordWrap(True)
        
        subtitle = QLabel("Your complete solution for FBR Invoice Management and Sales Tracking.")
        subtitle.setStyleSheet("color: #bdc3c7; font-size: 16px; background: transparent;")
        subtitle.setWordWrap(True)
        
        banner_layout.addWidget(title)
        banner_layout.addWidget(subtitle)
        banner_layout.addStretch()
        
        layout.addWidget(banner)

        # Quick Actions Grid
        actions_header = QLabel("Quick Actions")
        actions_header.setStyleSheet("font-size: 18px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(actions_header)

        # Using QGridLayout for better responsiveness in small screens
        actions_container = QWidget()
        actions_grid = QGridLayout(actions_container)
        actions_grid.setContentsMargins(0, 0, 0, 0)
        actions_grid.setSpacing(20)

        actions_grid.addWidget(self._create_action_card("📝", "Create Invoice", "Generate a new tax invoice", "invoice"), 0, 0)
        actions_grid.addWidget(self._create_action_card("📦", "Inventory", "Manage motorcycle stock", "inventory"), 0, 1)
        actions_grid.addWidget(self._create_action_card("📈", "Sales Reports", "View sales performance", "reports"), 0, 2)
        actions_grid.addWidget(self._create_action_card("⚙️", "Settings", "Configure API & Business", "settings"), 0, 3)
        
        # Ensure columns grow equally
        for i in range(4):
            actions_grid.setColumnStretch(i, 1)

        layout.addWidget(actions_container)

        # Statistics Summary
        stats_header = QLabel("Today's Overview")
        stats_header.setStyleSheet("font-size: 18px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(stats_header)

        stats_container = QWidget()
        stats_grid = QGridLayout(stats_container)
        stats_grid.setContentsMargins(0, 0, 0, 0)
        stats_grid.setSpacing(20)

        self.welcome_total_invoices_lbl = QLabel("0")
        stats_grid.addWidget(self._create_stat_widget("Total Invoices", self.welcome_total_invoices_lbl), 0, 0)

        self.welcome_fbr_synced_lbl = QLabel("0")
        stats_grid.addWidget(self._create_stat_widget("FBR Synced", self.welcome_fbr_synced_lbl), 0, 1)

        self.welcome_pending_sync_lbl = QLabel("0")
        stats_grid.addWidget(self._create_stat_widget("Pending Sync", self.welcome_pending_sync_lbl), 0, 2)
        
        for i in range(3):
            stats_grid.setColumnStretch(i, 1)

        layout.addWidget(stats_container)

        # App Info / Status
        info_frame = QFrame()
        info_frame.setStyleSheet("background-color: white; border: 1px solid #e0e0e0; border-radius: 12px; padding: 20px;")
        info_layout = QHBoxLayout(info_frame)
        
        status_dot = QLabel("●")
        status_dot.setStyleSheet("color: #27ae60; font-size: 20px;")
        
        active_env = settings_service.get_active_environment()
        status_text = QLabel(f"System Status: <b>Online</b>  |  Environment: <b>{active_env}</b>")
        status_text.setStyleSheet("color: #2c3e50; font-size: 14px;")
        
        info_layout.addWidget(status_dot)
        info_layout.addWidget(status_text)
        info_layout.addStretch()
        
        layout.addWidget(info_frame)
        layout.addStretch()
        
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)
        
        return page

    def _create_action_card(self, icon: str, title: str, desc: str, page_key: str) -> QFrame:
        card = QFrame()
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 12px;
                min-width: 180px;
                min-height: 150px;
            }
            QFrame:hover {
                border: 2px solid #3498db;
                background-color: #f7fbfe;
            }
        """)
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 32px; border: none; background: transparent;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50; border: none; background: transparent;")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        desc_lbl = QLabel(desc)
        desc_lbl.setStyleSheet("font-size: 12px; color: #7f8c8d; border: none; background: transparent;")
        desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_lbl.setWordWrap(True)
        
        layout.addWidget(icon_lbl)
        layout.addWidget(title_lbl)
        layout.addWidget(desc_lbl)
        
        # Make card clickable
        card.mousePressEvent = lambda e: self._select_page(page_key)
        
        return card

    def _create_stat_widget(self, title: str, val_lbl: QLabel) -> QFrame:
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 12px;
                padding: 15px;
            }
        """)
        layout = QVBoxLayout(card)
        layout.setSpacing(5)
        
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("color: #7f8c8d; font-size: 11px; text-transform: uppercase; font-weight: bold; border: none;")
        
        val_lbl.setStyleSheet("color: #2c3e50; font-size: 24px; font-weight: bold; border: none;")
        
        layout.addWidget(title_lbl)
        layout.addWidget(val_lbl)
        return card

    def _refresh_welcome_stats(self) -> None:
        """Update statistics on the welcome page."""
        if not hasattr(self, "welcome_total_invoices_lbl"):
            return
            
        db = SessionLocal()
        try:
            today = dt.date.today()
            # Start of today (00:00:00)
            start_of_day = dt.datetime.combine(today, dt.time.min)
            
            # Note: Invoice model uses 'datetime' column for creation time
            total = db.query(Invoice).filter(Invoice.datetime >= start_of_day).count()
            synced = db.query(Invoice).filter(
                Invoice.datetime >= start_of_day,
                Invoice.fbr_invoice_number != None
            ).count()
            pending = total - synced
            
            self.welcome_total_invoices_lbl.setText(str(total))
            self.welcome_fbr_synced_lbl.setText(str(synced))
            self.welcome_pending_sync_lbl.setText(str(pending))
            
        except Exception as e:
            logger.error(f"Error refreshing welcome stats: {e}")
        finally:
            db.close()

    def _create_sms_page(self) -> QWidget:
        """Creates the SMS management page with tabs for Config and Bulk SMS."""
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Tab Header Container
        tab_header = QWidget()
        tab_header.setStyleSheet("background-color: white; border-bottom: 1px solid #dee2e6;")
        tab_header_layout = QHBoxLayout(tab_header)
        tab_header_layout.setContentsMargins(30, 0, 30, 0)
        tab_header_layout.setSpacing(0)

        self.sms_tab_stack = QStackedWidget()
        
        def create_tab_btn(text, target_index):
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedSize(150, 50)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #7f8c8d;
                    border: none;
                    border-bottom: 3px solid transparent;
                    font-weight: bold;
                    font-size: 13px;
                }
                QPushButton:hover { color: #2c3e50; }
                QPushButton:checked {
                    color: #3498db;
                    border-bottom: 3px solid #3498db;
                }
            """)
            btn.clicked.connect(lambda: self._on_sms_tab_clicked(btn, target_index))
            return btn

        self.sms_config_tab_btn = create_tab_btn("⚙️ CONFIGURATION", 0)
        self.sms_bulk_tab_btn = create_tab_btn("📤 BULK SMS", 1)
        self.sms_campaigns_tab_btn = create_tab_btn("📋 CAMPAIGNS", 2)
        
        self.sms_tab_group = QButtonGroup(self)
        self.sms_tab_group.addButton(self.sms_config_tab_btn)
        self.sms_tab_group.addButton(self.sms_bulk_tab_btn)
        self.sms_tab_group.addButton(self.sms_campaigns_tab_btn)
        self.sms_config_tab_btn.setChecked(True)

        tab_header_layout.addWidget(self.sms_config_tab_btn)
        tab_header_layout.addWidget(self.sms_bulk_tab_btn)
        tab_header_layout.addWidget(self.sms_campaigns_tab_btn)
        tab_header_layout.addStretch(1)
        
        layout.addWidget(tab_header)
        layout.addWidget(self.sms_tab_stack, 1)

        # Add Sub-pages
        self.sms_tab_stack.addWidget(self._create_sms_config_subpage())
        self.sms_tab_stack.addWidget(self._create_sms_bulk_subpage())
        self.sms_tab_stack.addWidget(self._create_sms_campaigns_subpage())

        return page

    def _on_sms_tab_clicked(self, btn, index):
        self.sms_tab_stack.setCurrentIndex(index)
        if index == 2:
            self._reload_sms_campaigns()
            self._sms_campaigns_timer.start()
        else:
            self._sms_campaigns_timer.stop()

    def _auto_refresh_campaigns(self):
        """Timer-based refresh for the campaigns table."""
        # Only refresh if the Campaigns tab is visible
        if self.sms_tab_stack.currentIndex() == 2:
            self._reload_sms_campaigns()

    def _create_sms_config_subpage(self) -> QWidget:
        """The original SMS configuration UI."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 20, 30, 30)
        layout.setSpacing(20)
        
        # Main Content Scroll Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(20)

        # 1. WiFi Gateway Settings
        wifi_group = QFrame()
        wifi_group.setObjectName("formGroup")
        wifi_group.setStyleSheet("QFrame#formGroup { background-color: white; border: 1px solid #e0e0e0; border-radius: 12px; }")
        wifi_layout = QVBoxLayout(wifi_group)
        wifi_layout.setContentsMargins(20, 20, 20, 20)
        wifi_layout.setSpacing(15)

        wifi_title = QLabel("SMS Gateway Configuration")
        wifi_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50;")
        wifi_layout.addWidget(wifi_title)

        self.sms_enabled_check = QCheckBox("Enable SMS Module")
        self.sms_enabled_check.setStyleSheet("font-weight: bold; color: #2c3e50;")
        wifi_layout.addWidget(self.sms_enabled_check)

        # Gateway Type Switcher
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Gateway Type:"))
        self.sms_gateway_type = QComboBox()
        self.sms_gateway_type.addItems(["WIFI", "CLOUD"])
        self.sms_gateway_type.currentTextChanged.connect(self._on_gateway_type_changed)
        type_layout.addWidget(self.sms_gateway_type)
        type_layout.addStretch(1)
        wifi_layout.addLayout(type_layout)

        # ----------------- WiFi Specific Fields -----------------
        self.wifi_settings_widget = QWidget()
        wifi_fields_layout = QGridLayout(self.wifi_settings_widget)
        wifi_fields_layout.setContentsMargins(0, 0, 0, 0)
        
        wifi_fields_layout.addWidget(QLabel("Phone IP Address:"), 0, 0)
        self.sms_gateway_ip = QLineEdit()
        self.sms_gateway_ip.setPlaceholderText("e.g. 192.168.1.10")
        wifi_fields_layout.addWidget(self.sms_gateway_ip, 0, 1)

        wifi_fields_layout.addWidget(QLabel("Gateway Port:"), 1, 0)
        self.sms_gateway_port = QLineEdit()
        self.sms_gateway_port.setPlaceholderText("e.g. 8080")
        self.sms_gateway_port.setFixedWidth(100)
        wifi_fields_layout.addWidget(self.sms_gateway_port, 1, 1)

        wifi_fields_layout.addWidget(QLabel("Gateway Username:"), 2, 0)
        self.sms_gateway_username = QLineEdit()
        self.sms_gateway_username.setPlaceholderText("Username for the Gateway App")
        wifi_fields_layout.addWidget(self.sms_gateway_username, 2, 1)

        wifi_fields_layout.addWidget(QLabel("Gateway Password:"), 3, 0)
        self.sms_gateway_password = QLineEdit()
        self.sms_gateway_password.setPlaceholderText("Password for the Gateway App")
        self.sms_gateway_password.setEchoMode(QLineEdit.EchoMode.Password)
        wifi_fields_layout.addWidget(self.sms_gateway_password, 3, 1)

        self.sms_use_https = QCheckBox("Use HTTPS (for public IP/Secured Gateways)")
        wifi_fields_layout.addWidget(self.sms_use_https, 4, 1)
        
        wifi_layout.addWidget(self.wifi_settings_widget)

        # ----------------- Cloud Specific Fields -----------------
        self.cloud_settings_widget = QWidget()
        cloud_fields_layout = QGridLayout(self.cloud_settings_widget)
        cloud_fields_layout.setContentsMargins(0, 0, 0, 0)
        
        cloud_fields_layout.addWidget(QLabel("Cloud API URL:"), 0, 0)
        self.sms_cloud_url = QLineEdit()
        self.sms_cloud_url.setPlaceholderText("https://api.yourgateway.com/v1/send")
        cloud_fields_layout.addWidget(self.sms_cloud_url, 0, 1)

        cloud_fields_layout.addWidget(QLabel("Cloud Username:"), 1, 0)
        self.sms_cloud_username = QLineEdit()
        self.sms_cloud_username.setPlaceholderText("Username for Cloud API")
        cloud_fields_layout.addWidget(self.sms_cloud_username, 1, 1)

        cloud_fields_layout.addWidget(QLabel("Cloud Password:"), 2, 0)
        password_container = QWidget()
        password_layout = QHBoxLayout(password_container)
        password_layout.setContentsMargins(0, 0, 0, 0)
        password_layout.setSpacing(5)
        
        self.sms_cloud_password = QLineEdit()
        self.sms_cloud_password.setPlaceholderText("Password for Cloud API")
        self.sms_cloud_password.setEchoMode(QLineEdit.EchoMode.Password)
        password_layout.addWidget(self.sms_cloud_password)
        
        self.show_cloud_pwd_btn = QPushButton("👁️")
        self.show_cloud_pwd_btn.setCheckable(True)
        self.show_cloud_pwd_btn.setFixedWidth(40)
        self.show_cloud_pwd_btn.setStyleSheet("padding: 5px; background-color: #f1f1f1; border: 1px solid #ced4da; border-radius: 4px;")
        self.show_cloud_pwd_btn.clicked.connect(self._toggle_cloud_password_visibility)
        password_layout.addWidget(self.show_cloud_pwd_btn)
        
        cloud_fields_layout.addWidget(password_container, 2, 1)

        cloud_fields_layout.addWidget(QLabel("API Key / Bearer Token:"), 3, 0)
        self.sms_api_key = QLineEdit()
        self.sms_api_key.setPlaceholderText("Enter API Key or Token if required")
        cloud_fields_layout.addWidget(self.sms_api_key, 3, 1)
        
        wifi_layout.addWidget(self.cloud_settings_widget)

        # ----------------- Common Fields (Bulk Delay) -----------------
        common_layout = QGridLayout()
        common_layout.addWidget(QLabel("Bulk Delay (Seconds):"), 0, 0)
        self.sms_bulk_delay = QSpinBox()
        self.sms_bulk_delay.setRange(1, 120)
        self.sms_bulk_delay.setValue(5)
        self.sms_bulk_delay.setFixedWidth(100)
        common_layout.addWidget(self.sms_bulk_delay, 0, 1)
        
        wifi_layout.addLayout(common_layout)
        
        self.test_conn_btn = QPushButton("🔌 Test Connection")
        self.test_conn_btn.setFixedWidth(150)
        self.test_conn_btn.clicked.connect(self._on_test_sms_connection)
        wifi_layout.addWidget(self.test_conn_btn)

        container_layout.addWidget(wifi_group)

        # 2. SMS Templates
        template_group = QFrame()
        template_group.setObjectName("formGroup")
        template_group.setStyleSheet("QFrame#formGroup { background-color: white; border: 1px solid #e0e0e0; border-radius: 12px; }")
        template_layout = QVBoxLayout(template_group)
        template_layout.setContentsMargins(20, 20, 20, 20)
        template_layout.setSpacing(15)

        template_title = QLabel("SMS Templates")
        template_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50;")
        template_layout.addWidget(template_title)

        template_layout.addWidget(QLabel("Invoice SMS Template:"))
        self.sms_invoice_template = QTextEdit()
        self.sms_invoice_template.setMaximumHeight(80)
        self.sms_invoice_template.setPlaceholderText("Enter message template... (Placeholders: {customer}, {invoice_no})")
        self.sms_invoice_template.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.sms_invoice_template.setStyleSheet("""
            QTextEdit {
                font-family: 'Jameel Noori Nastaleeq', 'Urdu Typesetting', 'Tahoma', 'Arial';
                font-size: 18px;
                line-height: 1.6;
                padding: 10px;
                border: 1px solid #ced4da;
                border-radius: 4px;
            }
        """)
        template_layout.addWidget(self.sms_invoice_template)
        
        template_hint = QLabel("Placeholders: {customer}, {invoice_no}, {amount}, {fbr_id}")
        template_hint.setStyleSheet("color: #7f8c8d; font-size: 11px; font-style: italic;")
        template_layout.addWidget(template_hint)

        container_layout.addWidget(template_group)

        # 3. Test SMS
        test_group = QFrame()
        test_group.setObjectName("formGroup")
        test_group.setStyleSheet("QFrame#formGroup { background-color: white; border: 1px solid #e0e0e0; border-radius: 12px; }")
        test_layout = QVBoxLayout(test_group)
        test_layout.setContentsMargins(20, 20, 20, 20)
        test_layout.setSpacing(15)

        test_title = QLabel("Test SMS")
        test_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50;")
        test_layout.addWidget(test_title)

        test_inputs = QHBoxLayout()
        self.sms_test_phone = QLineEdit()
        self.sms_test_phone.setPlaceholderText("Enter Phone Number (e.g. 03001234567)")
        test_inputs.addWidget(self.sms_test_phone)
        
        self.send_test_btn = QPushButton("📤 Send Test SMS")
        self.send_test_btn.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; padding: 10px;")
        self.send_test_btn.clicked.connect(self._on_send_test_sms)
        test_inputs.addWidget(self.send_test_btn)
        test_layout.addLayout(test_inputs)

        container_layout.addWidget(test_group)
        
        # Save Button
        save_sms_btn = QPushButton("💾 Save SMS Configuration")
        save_sms_btn.setObjectName("primaryButton")
        save_sms_btn.setFixedHeight(45)
        save_sms_btn.clicked.connect(self._on_save_sms_config)
        container_layout.addWidget(save_sms_btn)

        container_layout.addStretch(1)
        scroll.setWidget(container)
        layout.addWidget(scroll)

        # Load initial config
        self._load_sms_config()
        
        return page

    def _create_sms_bulk_subpage(self) -> QWidget:
        """UI for uploading Excel and mapping bulk SMS."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 20, 30, 30)
        layout.setSpacing(20)
        
        # 1. Excel Upload Card
        upload_card = QFrame()
        upload_card.setObjectName("formGroup")
        upload_card.setStyleSheet("QFrame#formGroup { background-color: white; border: 1px solid #e0e0e0; border-radius: 12px; }")
        upload_layout = QVBoxLayout(upload_card)
        upload_layout.setContentsMargins(20, 20, 20, 20)
        
        upload_title = QLabel("Step 1: Upload Excel File")
        upload_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50;")
        upload_layout.addWidget(upload_title)
        
        upload_h_box = QHBoxLayout()
        self.bulk_file_path_input = QLineEdit()
        self.bulk_file_path_input.setReadOnly(True)
        self.bulk_file_path_input.setPlaceholderText("Select .xlsx or .xlsm file...")
        upload_h_box.addWidget(self.bulk_file_path_input)
        
        browse_btn = QPushButton("📂 Browse File")
        browse_btn.clicked.connect(self._on_bulk_browse_clicked)
        upload_h_box.addWidget(browse_btn)

        download_template_btn = QPushButton("📥 Download Template")
        # Add a more descriptive object name for styling if needed
        download_template_btn.setObjectName("secondaryButton") 
        download_template_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        download_template_btn.clicked.connect(self._on_download_template_clicked)
        upload_h_box.addWidget(download_template_btn)

        upload_layout.addLayout(upload_h_box)

        # Sheet Selector (Newly Added)
        sheet_layout = QHBoxLayout()
        sheet_layout.addWidget(QLabel("Select Sheet:"))
        self.bulk_sheet_selector = QComboBox()
        self.bulk_sheet_selector.setPlaceholderText("Select Excel file first")
        self.bulk_sheet_selector.setEnabled(False)
        sheet_layout.addWidget(self.bulk_sheet_selector)
        upload_layout.addLayout(sheet_layout)
        
        self.bulk_file_info_lbl = QLabel("No file selected.")
        self.bulk_file_info_lbl.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        upload_layout.addWidget(self.bulk_file_info_lbl)
        
        layout.addWidget(upload_card)
        
        # 2. Template Mapping Card
        template_card = QFrame()
        template_card.setObjectName("formGroup")
        template_card.setStyleSheet("QFrame#formGroup { background-color: white; border: 1px solid #e0e0e0; border-radius: 12px; }")
        template_layout = QVBoxLayout(template_card)
        template_layout.setContentsMargins(20, 20, 20, 20)
        template_layout.setSpacing(15)
        
        template_title = QLabel("Step 2: Message Template")
        template_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50;")
        template_layout.addWidget(template_title)
        
        self.bulk_template_input = QTextEdit()
        self.bulk_template_input.setPlaceholderText("Enter template... (Placeholders: {name}, {reg_no})")
        self.bulk_template_input.setMaximumHeight(100)
        self.bulk_template_input.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.bulk_template_input.setStyleSheet("""
            QTextEdit {
                font-family: 'Jameel Noori Nastaleeq', 'Urdu Typesetting', 'Tahoma', 'Arial';
                font-size: 18px;
                line-height: 1.6;
                padding: 10px;
                border: 1px solid #ced4da;
                border-radius: 8px;
            }
        """)
        template_layout.addWidget(self.bulk_template_input)
        
        template_hint = QLabel("Available Placeholders: {name}, {reg_no}, {phone} or any {Column Name} from Excel")
        template_hint.setStyleSheet("color: #7f8c8d; font-size: 11px; font-style: italic;")
        template_layout.addWidget(template_hint)
        
        layout.addWidget(template_card)
        
        # 3. Validation & Start Card
        start_card = QFrame()
        start_card.setObjectName("formGroup")
        start_card.setStyleSheet("QFrame#formGroup { background-color: white; border: 1px solid #e0e0e0; border-radius: 12px; }")
        start_layout = QVBoxLayout(start_card)
        start_layout.setContentsMargins(20, 20, 20, 20)
        
        self.bulk_validation_lbl = QLabel("Validation summary will appear here.")
        self.bulk_validation_lbl.setStyleSheet("color: #2c3e50; font-weight: bold;")
        start_layout.addWidget(self.bulk_validation_lbl)
        
        self.bulk_start_btn = QPushButton("🚀 Create Campaign & Start Sending")
        self.bulk_start_btn.setObjectName("primaryButton")
        self.bulk_start_btn.setFixedHeight(50)
        self.bulk_start_btn.setEnabled(False)
        self.bulk_start_btn.clicked.connect(self._on_bulk_start_clicked)
        start_layout.addWidget(self.bulk_start_btn)
        
        layout.addWidget(start_card)
        layout.addStretch(1)

        # Connect sheet selector change to re-validation
        self.bulk_sheet_selector.currentTextChanged.connect(self._on_sheet_selected)
        
        return page

    def _create_sms_campaigns_subpage(self) -> QWidget:
        """UI for viewing previous and active campaigns."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 20, 30, 30)
        layout.setSpacing(20)
        
        # Campaigns Table
        self.campaigns_table_model = CampaignsTableModel()
        self.campaigns_table_view = QTableView()
        self.campaigns_table_view.setModel(self.campaigns_table_model)
        self.campaigns_table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.campaigns_table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.campaigns_table_view.verticalHeader().setVisible(False)
        self.campaigns_table_view.setAlternatingRowColors(True)
        
        layout.addWidget(self.campaigns_table_view, 1)
        
        # Actions
        btn_bar = QHBoxLayout()
        refresh_btn = QPushButton("↻ Refresh Campaigns")
        refresh_btn.clicked.connect(self._reload_sms_campaigns)
        btn_bar.addWidget(refresh_btn)

        self.delete_campaign_btn = QPushButton("🗑️ Delete Selected Campaign")
        self.delete_campaign_btn.setStyleSheet("background-color: #e74c3c; color: white; font-weight: bold;")
        self.delete_campaign_btn.clicked.connect(self._on_delete_campaign)
        btn_bar.addWidget(self.delete_campaign_btn)

        self.view_campaign_details_btn = QPushButton("View Details")
        self.view_campaign_details_btn.clicked.connect(self._on_view_campaign_details)
        btn_bar.addWidget(self.view_campaign_details_btn)

        btn_bar.addStretch(1)
        layout.addLayout(btn_bar)
        
        return page

    def _on_view_campaign_details(self):
        from app.services.bulk_sms_service import bulk_sms_service
        from .campaign_details_dialog import CampaignDetailsDialog

        selected = self.campaigns_table_view.selectionModel().selectedRows()
        if not selected:
            QMessageBox.warning(self, "Selection Required", "Please select a campaign to view details.")
            return

        row_idx = selected[0].row()
        campaign = self.campaigns_table_model._rows[row_idx]

        details = bulk_sms_service.get_campaign_details(campaign.id)
        if details:
            dialog = CampaignDetailsDialog(details, self)
            dialog.retry_requested.connect(self._on_retry_campaign)
            dialog.exec()
        else:
            QMessageBox.critical(self, "Error", "Failed to load campaign details.")

    def _on_retry_campaign(self, campaign_id: int):
        from app.services.bulk_sms_service import bulk_sms_service

        success, message = bulk_sms_service.retry_failed_messages(campaign_id)
        if success:
            QMessageBox.information(self, "Success", message)
            self._reload_sms_campaigns()
            # Optionally, restart the campaign worker
            bulk_sms_service.start_campaign(campaign_id)
        else:
            QMessageBox.critical(self, "Error", message)

    def _on_bulk_browse_clicked(self):
        from PyQt6.QtWidgets import QFileDialog
        from app.services.excel_processing_service import ExcelProcessingService

        file_path, _ = QFileDialog.getOpenFileName(self, "Select Excel File", "", "Excel Files (*.xlsx *.xls *.xlsm)")
        if file_path:
            self.bulk_file_path_input.setText(file_path)
            
            # Reset UI elements
            self.bulk_sheet_selector.clear()
            self.bulk_sheet_selector.setEnabled(False)
            self.bulk_validation_lbl.setText("Processing...")
            self.bulk_start_btn.setEnabled(False)

            try:
                service = ExcelProcessingService()
                sheet_names = service.get_sheet_names(file_path)
                
                if not sheet_names:
                    self.bulk_file_info_lbl.setText("Error: No sheets found in the Excel file.")
                    return

                self.bulk_sheet_selector.addItems(sheet_names)
                self.bulk_sheet_selector.setEnabled(True)
                
                # Automatically trigger validation for the first sheet
                self._validate_bulk_excel(file_path, sheet_names[0])

            except Exception as e:
                self.bulk_file_info_lbl.setText(f"Error reading Excel file: {e}")
                logger.error(f"Failed to read Excel sheets: {e}", exc_info=True)

    def _on_sheet_selected(self, sheet_name: str):
        """Triggered when the user selects a different sheet from the dropdown."""
        file_path = self.bulk_file_path_input.text()
        if file_path and sheet_name:
            self._validate_bulk_excel(file_path, sheet_name)

    def _validate_bulk_excel(self, file_path: str, sheet_name: str):
        from app.services.excel_processing_service import ExcelProcessingService
        service = ExcelProcessingService()
        try:
            # Now read the specific sheet
            data, headers = service.read_excel(file_path, sheet_name=sheet_name)
            validation = service.validate_data(data, headers)
            
            if not validation["success"]:
                self.bulk_validation_lbl.setText(f"❌ Error: {validation['error']}")
                self.bulk_validation_lbl.setStyleSheet("color: #e74c3c; font-weight: bold;")
                self.bulk_start_btn.setEnabled(False)
            else:
                self.bulk_file_info_lbl.setText(f"File: {file_path.split('/')[-1]} | Sheet: {sheet_name} | Rows: {len(data)}")
                self.bulk_validation_lbl.setText(f"✅ Ready: {validation['valid_count']} valid recipients found ({validation['invalid_count']} skipped)")
                self.bulk_validation_lbl.setStyleSheet("color: #27ae60; font-weight: bold;")
                self.bulk_start_btn.setEnabled(validation['valid_count'] > 0)
                self._current_bulk_data = validation["valid_data"]

        except Exception as e:
            self.bulk_validation_lbl.setText(f"❌ Failed to process sheet '{sheet_name}': {str(e)}")
            self.bulk_start_btn.setEnabled(False)
            logger.error(f"Error validating Excel sheet '{sheet_name}': {e}", exc_info=True)

    def _on_bulk_start_clicked(self):
        from app.services.bulk_sms_service import bulk_sms_service
        from PyQt6.QtWidgets import QInputDialog
        from app.db.session import SessionLocal
        from app.db.models import SMSConfiguration

        # Check if SMS module is enabled before starting
        db = SessionLocal()
        try:
            config = db.query(SMSConfiguration).first()
            if not config or not config.is_enabled:
                QMessageBox.warning(self, "SMS Module Disabled", 
                    "The SMS Module is currently disabled.\n\n"
                    "Please go to the 'CONFIGURATION' tab, check 'Enable SMS Module', and save.")
                self.sms_config_tab_btn.click()
                return
        finally:
            db.close()
        
        campaign_name, ok = QInputDialog.getText(self, "Campaign Name", "Enter a name for this campaign:")
        if not ok or not campaign_name:
            return
            
        template = self.bulk_template_input.toPlainText().strip()
        if not template:
            QMessageBox.warning(self, "Template Required", "Please enter a message template.")
            return
            
        try:
            # Create campaign in database
            campaign_id = bulk_sms_service.create_campaign(
                campaign_name,
                template,
                self._current_bulk_data
            )
            
            # Start worker
            def on_progress(sent, failed, total):
                self.campaign_progress_signal.emit(campaign_id, sent, failed, total)
                
            def on_complete(success, msg):
                self.campaign_complete_signal.emit(campaign_id, success, msg)
                
            bulk_sms_service.start_campaign(
                campaign_id,
                on_progress=on_progress,
                on_complete=on_complete
            )
            
            QMessageBox.information(self, "Campaign Started", 
                f"Campaign '{campaign_name}' has been created and started.\n"
                "You can track progress in the Campaigns tab.")
            
            # Clear fields after success
            self._clear_bulk_sms_fields()
            
            # Switch to campaigns tab
            self.sms_campaigns_tab_btn.click()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to start campaign: {e}")

    def _clear_bulk_sms_fields(self):
        """Clears all input fields in the Bulk SMS creation page."""
        self.bulk_file_path_input.clear()
        self.bulk_sheet_selector.clear()
        self.bulk_sheet_selector.setEnabled(False)
        self.bulk_template_input.clear()
        self.bulk_file_info_lbl.setText("No file selected.")
        self.bulk_validation_lbl.setText("Validation summary will appear here.")
        self.bulk_validation_lbl.setStyleSheet("color: #2c3e50; font-weight: bold;")
        self.bulk_start_btn.setEnabled(False)
        if hasattr(self, '_current_bulk_data'):
            self._current_bulk_data = []

    def _on_download_template_clicked(self):
        from PyQt6.QtWidgets import QFileDialog
        import pandas as pd

        file_path, _ = QFileDialog.getSaveFileName(self, "Save Template File", "sms_template.xlsx", "Excel Files (*.xlsx)")

        if file_path:
            try:
                # Define the structure of the template
                template_data = {
                    'phone': ['03001234567', '03219876543'],
                    'name': ['John Doe', 'Jane Smith'],
                    'reg_no': ['ABC-123', 'XYZ-789'],
                    'custom_field_1': ['Value1', 'Value2'],
                    'custom_field_2': ['ValueA', 'ValueB']
                }
                df = pd.DataFrame(template_data)

                # Write the DataFrame to an Excel file
                df.to_excel(file_path, index=False)

                self._show_success("Template Saved", f"The SMS template has been saved to:\n{file_path}")

            except Exception as e:
                self._show_error("Save Error", f"Failed to save the template file: {e}")
                logger.error(f"Error saving SMS template: {e}", exc_info=True)

    def _reload_sms_campaigns(self):
        """Reloads campaigns list from database."""
        from app.db.models import SMSCampaign
        from app.db.session import SessionLocal
        
        db = SessionLocal()
        try:
            campaigns = db.query(SMSCampaign).order_by(SMSCampaign.created_at.desc()).all()
            
            rows = [
                 CampaignRow(
                     id=c.id,
                     name=c.name,
                     status=c.status,
                     sent=c.sent_count,
                     failed=c.failed_count,
                     total=c.total_recipients,
                     created_at=c.created_at,
                     error_message=c.error_message
                 ) for c in campaigns
             ]
            
            self.campaigns_table_model.update_rows(rows)
            
        except Exception as e:
            logger.error(f"Error reloading campaigns: {e}")
        finally:
            db.close()

    def _on_delete_campaign(self):
        """Deletes the selected campaign after confirmation."""
        from app.services.bulk_sms_service import bulk_sms_service
        
        selected = self.campaign_table_view.selectionModel().selectedRows() if hasattr(self, 'campaign_table_view') else self.campaigns_table_view.selectionModel().selectedRows()
        if not selected:
            QMessageBox.warning(self, "Selection Required / انتخاب ضروری ہے", "Please select a campaign to delete.")
            return
            
        row_idx = selected[0].row()
        campaign = self.campaigns_table_model._rows[row_idx]
        
        reply = QMessageBox.question(self, "Confirm Delete / تصدیق کریں", 
                                   f"Are you sure you want to delete campaign '{campaign.name}'?\n\n"
                                   "This will also delete all message history for this campaign.",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                                   
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if bulk_sms_service.delete_campaign(campaign.id):
                    self._reload_sms_campaigns()
                    self._show_success("Deleted / حذف کر دیا گیا", f"Campaign '{campaign.name}' has been deleted.")
                else:
                    self._show_error("Error / غلطی", "Failed to delete campaign.")
            except Exception as e:
                self._show_error("Error / غلطی", str(e))

    def _on_gateway_type_changed(self, gateway_type: str) -> None:
        """Shows/hides relevant fields based on gateway type."""
        is_wifi = gateway_type == "WIFI"
        self.wifi_settings_widget.setVisible(is_wifi)
        self.cloud_settings_widget.setVisible(not is_wifi)

    def _toggle_cloud_password_visibility(self, checked: bool) -> None:
        """Toggles the visibility of the cloud password field."""
        if checked:
            self.sms_cloud_password.setEchoMode(QLineEdit.EchoMode.Normal)
            self.show_cloud_pwd_btn.setText("🔒")
        else:
            self.sms_cloud_password.setEchoMode(QLineEdit.EchoMode.Password)
            self.show_cloud_pwd_btn.setText("👁️")

    def _load_sms_config(self) -> None:
        db = SessionLocal()
        try:
            from app.db.models import SMSConfiguration
            config = db.query(SMSConfiguration).first()
            if not config:
                config = SMSConfiguration(is_enabled=False, gateway_type="WIFI")
                db.add(config)
                db.commit()
            
            self.sms_enabled_check.setChecked(config.is_enabled)
            self.sms_gateway_type.setCurrentText(getattr(config, 'gateway_type', 'WIFI'))
            self._on_gateway_type_changed(self.sms_gateway_type.currentText())
            
            self.sms_gateway_ip.setText(config.gateway_ip or "")
            self.sms_gateway_port.setText(config.gateway_port or "8080")
            self.sms_use_https.setChecked(getattr(config, 'use_https', False))
            self.sms_cloud_url.setText(getattr(config, 'api_url', '') or "")
            self.sms_cloud_username.setText(getattr(config, 'cloud_username', '') or "")
            self.sms_cloud_password.setText(getattr(config, 'cloud_password', '') or "")
            
            self.sms_gateway_username.setText(config.gateway_username or "")
            self.sms_gateway_password.setText(config.gateway_password or "")
            self.sms_api_key.setText(config.api_key or "")
            self.sms_bulk_delay.setValue(config.delay_seconds or 5)
            self.sms_invoice_template.setPlainText(config.invoice_template)
                    
        except Exception as e:
            logger.error(f"Error loading SMS config: {e}")
        finally:
            db.close()

    def _on_save_sms_config(self) -> None:
        db = SessionLocal()
        try:
            from app.db.models import SMSConfiguration
            config = db.query(SMSConfiguration).first()
            config.is_enabled = self.sms_enabled_check.isChecked()
            config.gateway_type = self.sms_gateway_type.currentText()
            config.gateway_ip = self.sms_gateway_ip.text().strip()
            config.gateway_port = self.sms_gateway_port.text().strip()
            config.use_https = self.sms_use_https.isChecked()
            config.api_url = self.sms_cloud_url.text().strip()
            config.cloud_username = self.sms_cloud_username.text().strip()
            config.cloud_password = self.sms_cloud_password.text().strip()
            
            config.gateway_username = self.sms_gateway_username.text().strip()
            config.gateway_password = self.sms_gateway_password.text().strip()
            config.api_key = self.sms_api_key.text().strip()
            config.delay_seconds = self.sms_bulk_delay.value()
            config.invoice_template = self.sms_invoice_template.toPlainText()
            db.commit()
            self._show_success("SMS Saved", "SMS Gateway configuration updated successfully.")
        except Exception as e:
            logger.error(f"Error saving SMS config: {e}")
            self._show_error("Save Error", str(e))
        finally:
            db.close()

    def _on_test_sms_connection(self) -> None:
        """Tests connectivity to the selected SMS Gateway (WiFi or Cloud) in a background thread."""
        import threading
        gateway_type = self.sms_gateway_type.currentText()
        
        # Feedback: Disable the button and show testing state
        self.test_conn_btn.setEnabled(False)
        self.test_conn_btn.setText("⌛ Testing...")
        
        def run_test():
            try:
                if gateway_type == "WIFI":
                    self._test_wifi_connection()
                else:
                    self._test_cloud_connection()
            except Exception as e:
                logger.error(f"Error in run_test thread: {e}")
                self.conn_test_result_signal.emit(False, f"Test Error: {str(e)}")
                
        threading.Thread(target=run_test, daemon=True).start()

    def _test_wifi_connection(self) -> None:
        """Tests if the PC can reach the Android Gateway app via WiFi or Public IP (runs in thread)."""
        ip = self.sms_gateway_ip.text().strip()
        port = self.sms_gateway_port.text().strip()
        user = self.sms_gateway_username.text().strip()
        pwd = self.sms_gateway_password.text().strip()
        use_https = self.sms_use_https.isChecked()

        if not ip or not port:
            self.conn_test_result_signal.emit(False, "Please enter Phone IP and Port.")
            return
            
        try:
            import base64
            import socket
            
            # 0. Context-aware Timeout and IP detection
            is_public = "." in ip and not ip.startswith(("192.", "10.", "172.16."))
            sock_timeout = 5.0 if is_public else 3.0
            protocol = "https" if use_https else "http"
            
            # Fast socket check first
            logger.info(f"Test WiFi: Fast socket check for {ip}:{port} (Timeout: {sock_timeout}s)")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(sock_timeout)
            result = sock.connect_ex((ip, int(port)))
            sock.close()
            
            if result != 0:
                if is_public:
                    msg = (f"The Public IP {ip} is unreachable on port {port}.\n\n"
                           f"1. Ensure Port Forwarding is enabled on your router for port {port}.\n"
                           "2. Ensure the SMS Gateway app is running on your phone.\n"
                           "3. Verify your Public IP has not changed.")
                else:
                    msg = (f"The Local IP {ip} is unreachable on port {port}.\n\n"
                           "1. Ensure your phone and PC are on the SAME WiFi.\n"
                           "2. Ensure the SMS Gateway app is open and running on your phone.")
                self.conn_test_result_signal.emit(False, msg)
                return

            endpoints = ["/message", "/sms", "/send", "/"]
            found = []
            
            # Prepare auth variants for testing
            auth_variants = [({}, {})] 
            if user and pwd:
                auth_str = base64.b64encode(f"{user}:{pwd}".encode()).decode()
                auth_variants.append(({"Authorization": f"Basic {auth_str}"}, {}))

            # Test both protocols if the primary fails (Adaptive Discovery)
            protocols_to_try = [protocol]
            if protocol == "https": protocols_to_try.append("http")
            else: protocols_to_try.append("https")

            for proto in protocols_to_try:
                for path in endpoints:
                    url = f"{proto}://{ip}:{port}{path}"
                    path_found = False
                    
                    for headers, params in auth_variants:
                        try:
                            # Increase timeout for public IP
                            req_timeout = 4 if is_public else 2
                            response = requests.post(url, headers=headers, params=params, timeout=req_timeout)
                            if response.status_code in [200, 201, 202, 401, 403]:
                                found.append(f"{path} ({proto.upper()}, Status {response.status_code})")
                                path_found = True
                                break
                        except: continue
                    
                    if not path_found:
                        try:
                            req_timeout = 4 if is_public else 2
                            response = requests.get(url, timeout=req_timeout)
                            if response.status_code in [200, 401, 403, 405]:
                                found.append(f"{path} ({proto.upper()}, Status {response.status_code})")
                        except: continue
                
                if found: break # Stop if we found anything on the first protocol

            if found:
                self.conn_test_result_signal.emit(True, f"Found active endpoints at {ip}:{port}:\n" + "\n".join(found))
            else:
                self.conn_test_result_signal.emit(False, f"Could not find any active SMS service at {ip}:{port} via HTTP or HTTPS.")
        except Exception as e:
            self.conn_test_result_signal.emit(False, f"Error: {e}")

    def _test_cloud_connection(self) -> None:
        """Tests if the PC can reach the Cloud SMS API URL (runs in thread)."""
        url = self.sms_cloud_url.text().strip()
        user = self.sms_cloud_username.text().strip()
        pwd = self.sms_cloud_password.text().strip()
        api_key = self.sms_api_key.text().strip()

        if not url:
            self.conn_test_result_signal.emit(False, "Please enter the Cloud API URL.")
            return
            
        try:
            import base64
            headers = {"Content-Type": "application/json", "User-Agent": "FBR-Uploader/2.0"}
            
            # 1. Prepare Authentication (Additive approach)
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
                headers["X-API-KEY"] = api_key
            
            # Use Username/Password for both Basic Auth and custom headers
            if user and pwd:
                auth_str = base64.b64encode(f"{user}:{pwd}".encode()).decode()
                if "Authorization" not in headers:
                    headers["Authorization"] = f"Basic {auth_str}"
                headers["X-USERNAME"] = user
                headers["X-PASSWORD"] = pwd

            logger.info(f"Test Cloud: Checking {url}")
            # Try to include credentials in parameters as well for maximum compatibility
            params = {}
            if user and pwd:
                params.update({"username": user, "password": pwd, "user": user, "pass": pwd})
            if api_key:
                params.update({"api_key": api_key, "apikey": api_key})

            # Try POST first to truly test authentication
            test_payload = {"to": "0000000000", "message": "Connection Test", "sender": "TEST"}
            logger.info(f"Test Cloud: Trying POST to {url} with test payload...")
            response = requests.post(url, headers=headers, json=test_payload, params=params, timeout=10.0)
            
            # If POST is not allowed, try GET
            if response.status_code == 405:
                logger.info("Test Cloud: POST not allowed, trying GET...")
                response = requests.get(url, headers=headers, params=params, timeout=10.0)

            # 200 OK can still mean an error in the response body for some SMS APIs
            response_text = response.text.lower()
            auth_errors = ["invalid", "error", "failed", "unauthorized", "wrong", "mismatch", "denied"]
            
            # 200, 201, 202 means success, but ONLY if the body doesn't contain an error
            if response.status_code in [200, 201, 202]:
                is_actually_error = any(err in response_text for err in auth_errors)
                if is_actually_error:
                    msg = (f"The cloud server responded with Status 200 OK, but the message says:\n\n"
                           f"\"{response.text[:200]}\"\n\n"
                           "Please check your Username, Password, or API Key.")
                    self.conn_test_result_signal.emit(False, msg)
                else:
                    msg = (f"Successfully connected and authenticated with the cloud server.\n"
                           f"Result: Status {response.status_code} OK")
                    self.conn_test_result_signal.emit(True, msg)
            
            # 401 or 403 means authentication failure
            elif response.status_code in [401, 403]:
                msg = (f"The cloud server rejected your credentials (Status {response.status_code}).\n\n"
                       "Please check your Username, Password, or API Key.")
                self.conn_test_result_signal.emit(False, msg)
            
            else:
                self.conn_test_result_signal.emit(False, f"Server responded with error status: {response.status_code}")
                
        except Exception as e:
            self.conn_test_result_signal.emit(False, f"Could not reach the cloud server.\nError: {str(e)}")

    def _handle_conn_test_result(self, success: bool, message: str) -> None:
        """Safely handle the connection test result in the UI thread."""
        self.test_conn_btn.setEnabled(True)
        self.test_conn_btn.setText("🔌 Test Connection")
        
        if success:
            self._show_success("Connection Success", message)
        else:
            self._show_error("Connection Failed", message)

    def _handle_sms_result(self, success: bool, result_msg: str) -> None:
        """Handle the result of an SMS send operation from a background thread."""
        if hasattr(self, '_sms_safety_timer') and self._sms_safety_timer.isActive():
            self._sms_safety_timer.stop()
        
        btn = self.send_test_btn
        # If button was already re-enabled by safety timer, don't show another message
        if btn.isEnabled() and btn.text() != "⌛ Sending...":
            return

        btn.setEnabled(True)
        btn.setText("📤 Send Test SMS") # Reset to original text
        
        if success:
            gateway = self.sms_gateway_type.currentText()
            self._show_success("SMS Sent", f"Test SMS has been sent via {gateway} Gateway.\n\nResult: {result_msg}")
        else:
            self._show_error("SMS Failed", f"Failed to send SMS.\n\nError: {result_msg}")

    def _handle_campaign_progress(self, camp_id: int, sent: int, failed: int, total: int) -> None:
        """Update the campaign row in the table when progress is reported."""
        self._reload_sms_campaigns()

    def _handle_campaign_complete(self, camp_id: int, success: bool, message: str) -> None:
        """Handle campaign completion."""
        self._reload_sms_campaigns()
        if success:
            self._show_success("Campaign Finished", message)
        else:
            self._show_error("Campaign Failed", message)

    def _on_send_test_sms(self) -> None:
        import threading
        from app.services.sms_service import sms_service
        
        phone = self.sms_test_phone.text().strip()
        gateway_type = self.sms_gateway_type.currentText()
        
        # WiFi Config
        ip = self.sms_gateway_ip.text().strip()
        port = self.sms_gateway_port.text().strip()
        wifi_user = self.sms_gateway_username.text().strip()
        wifi_pwd = self.sms_gateway_password.text().strip()
        
        # Cloud Config
        api_url = self.sms_cloud_url.text().strip()
        cloud_user = self.sms_cloud_username.text().strip()
        cloud_pwd = self.sms_cloud_password.text().strip()
        
        # Shared Config
        api_key = self.sms_api_key.text().strip()

        if not phone:
            QMessageBox.warning(self, "Input Required", "Please enter a recipient phone number.")
            return

        if gateway_type == "WIFI" and (not ip or not port):
            QMessageBox.warning(self, "Input Required", "Please ensure WiFi IP and Port are set.")
            return
            
        if gateway_type == "CLOUD" and not api_url:
            QMessageBox.warning(self, "Input Required", "Please ensure Cloud API URL is set.")
            return

        # UI feedback: Disable button and show sending state
        btn = self.send_test_btn
        btn.setEnabled(False)
        btn.setText("⌛ Sending...")
        
        # Robustness: Safety timer to re-enable button if thread hangs
        self._sms_safety_timer = QTimer(self)
        self._sms_safety_timer.setSingleShot(True)
        
        def on_safety_timeout():
            if not btn.isEnabled():
                logger.error("SMS safety timeout reached. Re-enabling button.")
                btn.setEnabled(True)
                btn.setText("📤 Send Test SMS")
                self._show_error("SMS Timeout", 
                    f"The {gateway_type} sending process exceeded 30 seconds and was aborted.")
        
        self._sms_safety_timer.timeout.connect(on_safety_timeout)
        self._sms_safety_timer.start(30000) # 30 seconds

        def run_send():
            try:
                if gateway_type == "WIFI":
                    success, result_msg = sms_service.send_sms_via_wifi(
                        ip, port, phone, "Test SMS from FBR WiFi Gateway.", 
                        api_key=api_key, username=wifi_user, password=wifi_pwd,
                        use_https=self.sms_use_https.isChecked(),
                        total_timeout=30.0
                    )
                else:
                    success, result_msg = sms_service.send_sms_via_cloud(
                        api_url, phone, "Test SMS from FBR Cloud Gateway.",
                        api_key=api_key, username=cloud_user, password=cloud_pwd
                    )
                self.sms_result_signal.emit(success, result_msg)
            except Exception as e:
                logger.error(f"Error in run_send thread: {e}")
                self.sms_result_signal.emit(False, f"Exception: {str(e)}")

        threading.Thread(target=run_send, daemon=True).start()

    def _create_inventory_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(25)

        # Style inherited from Reports page but applied locally for consistency
        page.setStyleSheet("""
            QWidget { background-color: #f8f9fa; }
            QLabel#pageHeader { font-size: 26px; font-weight: bold; color: #2c3e50; }
            QFrame#filterCard { background-color: white; border: 1px solid #e0e0e0; border-radius: 12px; }
            QLabel.filterLabel { color: #7f8c8d; font-weight: bold; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; }
            QLineEdit, QComboBox { padding: 10px 15px; border: 1px solid #dee2e6; border-radius: 8px; background-color: #ffffff; font-size: 13px; }
            QPushButton#primaryButton { background-color: #3498db; color: white; border: none; border-radius: 8px; font-weight: bold; padding: 10px 20px; }
            QPushButton#primaryButton:hover { background-color: #2980b9; }
            QTableView { 
                background-color: white; 
                border: 1px solid #e0e0e0; 
                border-radius: 12px; 
                gridline-color: #f1f1f1; 
                alternate-background-color: #fafafa;
                selection-background-color: #e3f2fd;
                selection-color: #1976d2;
                outline: none;
            }
            QTableView::item {
                padding: 12px;
                border-bottom: 1px solid #f1f1f1;
            }
            QTableView::item:hover {
                background-color: #f1f8ff;
            }
            QHeaderView::section { 
                background-color: #f8f9fa; 
                color: #5a6268; 
                padding: 12px; 
                font-weight: bold; 
                text-transform: uppercase; 
                font-size: 11px; 
                border: none; 
                border-bottom: 2px solid #e9ecef; 
            }
        """)

        # Header
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        header_v_box = QVBoxLayout()
        header = QLabel("Inventory Management")
        header.setObjectName("pageHeader")
        header_v_box.addWidget(header)
        
        header_subtitle = QLabel("View and filter motorcycle stock by chassis, engine, or model.")
        header_subtitle.setStyleSheet("color: #7f8c8d; font-size: 13px;")
        header_v_box.addWidget(header_subtitle)
        
        header_layout.addLayout(header_v_box)
        header_layout.addStretch(1)

        # Consolidated Sync & Capture Button
        sync_capture_btn = QPushButton("🔄 Sync & Capture Data")
        sync_capture_btn.setStyleSheet("background-color: #3498db; color: white; border: none; font-weight: bold; padding: 10px 20px; border-radius: 8px;")
        sync_capture_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sync_capture_btn.clicked.connect(self._on_sync_and_capture_clicked)
        header_layout.addWidget(sync_capture_btn)

        view_cap_btn = QPushButton("📁 View Captured")
        view_cap_btn.setStyleSheet("background-color: #1abc9c; color: white; border: none; font-weight: bold; padding: 10px 20px; border-radius: 8px;")
        view_cap_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        view_cap_btn.clicked.connect(self._on_view_captured_clicked)
        header_layout.addWidget(view_cap_btn)

        layout.addWidget(header_widget)

        # Filter Card
        filter_card = QFrame()
        filter_card.setObjectName("filterCard")
        filter_layout = QHBoxLayout(filter_card)
        filter_layout.setContentsMargins(25, 20, 25, 20)
        filter_layout.setSpacing(25)

        # Search Group
        search_box = QVBoxLayout()
        search_box.setSpacing(8)
        search_lbl = QLabel("Search Keywords")
        search_lbl.setProperty("class", "filterLabel")
        search_box.addWidget(search_lbl)
        self.inventory_search_input = QLineEdit()
        self.inventory_search_input.setPlaceholderText("Chassis, engine or model")
        self.inventory_search_input.setFixedWidth(300)
        self.inventory_search_input.textChanged.connect(self._reload_inventory)
        search_box.addWidget(self.inventory_search_input)
        filter_layout.addLayout(search_box)

        # Status Group
        status_box = QVBoxLayout()
        status_box.setSpacing(8)
        status_lbl = QLabel("Stock Status")
        status_lbl.setProperty("class", "filterLabel")
        status_box.addWidget(status_lbl)
        self.inventory_status_combo = QComboBox()
        self.inventory_status_combo.addItems(["All Statuses", "IN_STOCK", "SOLD"])
        self.inventory_status_combo.currentTextChanged.connect(self._reload_inventory)
        status_box.addWidget(self.inventory_status_combo)
        filter_layout.addLayout(status_box)

        filter_layout.addStretch(1)
        
        refresh_btn = QPushButton("↻ Reload")
        refresh_btn.setStyleSheet("background-color: white; color: #2c3e50; border: 1px solid #dee2e6; border-radius: 8px; font-weight: bold; padding: 10px 20px;")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self._reload_inventory)
        filter_layout.addWidget(refresh_btn, 0, Qt.AlignmentFlag.AlignBottom)
        
        layout.addWidget(filter_card)

        # Table Section
        table_container = QFrame()
        table_container.setStyleSheet("background-color: white; border: 1px solid #e0e0e0; border-radius: 12px;")
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(1, 1, 1, 1)

        self.inventory_table_model = InventoryTableModel()
        self.inventory_table_view = QTableView()
        self.inventory_table_view.setModel(self.inventory_table_model)
        self.inventory_table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.inventory_table_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.inventory_table_view.setAlternatingRowColors(True)
        self.inventory_table_view.horizontalHeader().setStretchLastSection(True)
        self.inventory_table_view.verticalHeader().setVisible(False)
        self.inventory_table_view.setShowGrid(False)
        self.inventory_table_view.doubleClicked.connect(self._on_inventory_row_double_clicked)
        
        table_layout.addWidget(self.inventory_table_view)
        layout.addWidget(table_container, 1)

        # Action Buttons (New)
        action_bar = QHBoxLayout()
        action_bar.setSpacing(15)
        
        edit_btn = QPushButton("✎ Edit Record")
        edit_btn.setObjectName("resetButton")
        edit_btn.setStyleSheet("background-color: #3498db; color: white; border: none; font-weight: bold; padding: 10px 20px; border-radius: 8px;")
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.clicked.connect(self._on_edit_inventory_clicked)
        
        delete_btn = QPushButton("🗑 Delete Record")
        delete_btn.setStyleSheet("background-color: #e74c3c; color: white; border: none; font-weight: bold; padding: 10px 20px; border-radius: 8px;")
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.clicked.connect(self._on_delete_inventory_clicked)
        
        action_bar.addStretch(1)
        action_bar.addWidget(edit_btn)
        action_bar.addWidget(delete_btn)
        layout.addLayout(action_bar)

        self._reload_inventory()

        return page

    def _on_sync_and_capture_clicked(self) -> None:
        """Sequential workflow: Import inventory then launch capture browser."""
        # Step 1: Open the Import Dialog
        dialog = WebImportDialog(self)
        dialog.exec()
        
        # Step 2: Automatically trigger capture browser launch after import
        self._on_launch_capture_clicked()

    def _on_launch_capture_clicked(self) -> None:
        """Launches the background capture browser."""
        try:
            # Default to Atlas Honda Portal base URL
            target_url = "https://dealers.ahlportal.com"
            form_capture_service.start_capture_session(target_url)
            QMessageBox.information(self, "Browser Launched", "Capture browser has been launched.\nNavigate to the portal to begin capturing data.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to launch browser: {e}")

    def _on_view_captured_clicked(self) -> None:
        """Switches to the captured data page."""
        self._select_page("captured_data")

    def _on_browser_data_captured(self, chassis: str) -> None:
        """Callback from background service when data is captured."""
        # Use QTimer to ensure this runs on main thread
        QTimer.singleShot(0, lambda: self._handle_background_capture(chassis))

    def _handle_background_capture(self, chassis: str) -> None:
        if not self.isVisible():
            return
            
        # If we are on invoice page, try to auto-fill
        if self.stack.currentWidget() == self._pages.get("invoice"):
            if chassis:
                self.invoice_chassis_input.setText(chassis)
                self._on_chassis_selected(chassis)
                QMessageBox.information(self, "Data Captured", f"Imported details for chassis: {chassis}")
            else:
                QMessageBox.information(self, "Data Captured", "New data was captured from the browser.")
        elif self.stack.currentWidget() == self._pages.get("captured_data"):
            self._reload_captured_data()
            
    def _create_captured_data_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(25)

        # Header
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        header_v_box = QVBoxLayout()
        header = QLabel("Captured Customer Data")
        header.setObjectName("pageHeader")
        header_v_box.addWidget(header)
        
        self.captured_last_updated_label = QLabel("Last updated: Never")
        self.captured_last_updated_label.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        header_v_box.addWidget(self.captured_last_updated_label)
        
        header_subtitle = QLabel("Review and manage data captured from the browser sessions.")
        header_subtitle.setStyleSheet("color: #7f8c8d; font-size: 13px;")
        header_v_box.addWidget(header_subtitle)
        
        header_layout.addLayout(header_v_box)
        header_layout.addStretch(1)
        
        back_btn = QPushButton("← Back to Inventory")
        back_btn.setObjectName("resetButton")
        back_btn.clicked.connect(lambda: self._select_page("inventory"))
        header_layout.addWidget(back_btn)
        
        layout.addWidget(header_widget)

        # Table
        self.captured_table_model = CapturedDataTableModel()
        self.captured_table_view = QTableView()
        self.captured_table_view.setModel(self.captured_table_model)
        self.captured_table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.captured_table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.captured_table_view.verticalHeader().setVisible(False)
        self.captured_table_view.setAlternatingRowColors(True)
        self.captured_table_view.setShowGrid(True)
        self.captured_table_view.setStyleSheet("""
            QTableView { 
                background-color: white; 
                border: 1px solid #e0e0e0; 
                border-radius: 12px; 
                gridline-color: #f1f1f1;
                color: #2c3e50;
            }
            QHeaderView::section {
                background-color: #f8f9fa;
                color: #5a6268;
                padding: 10px;
                border: none;
                border-bottom: 2px solid #e9ecef;
                font-weight: bold;
            }
        """)
        
        layout.addWidget(self.captured_table_view, 1)

        # Actions
        btn_bar = QHBoxLayout()
        btn_bar.addStretch(1)
        
        refresh_btn = QPushButton("↻ Refresh List")
        refresh_btn.clicked.connect(self._reload_captured_data)
        btn_bar.addWidget(refresh_btn)
        
        delete_btn = QPushButton("🗑 Delete Selected")
        delete_btn.setStyleSheet("background-color: #e74c3c; color: white;")
        delete_btn.clicked.connect(self._on_delete_captured_clicked)
        btn_bar.addWidget(delete_btn)
        
        layout.addLayout(btn_bar)
        
        return page

    def _reload_captured_data(self) -> None:
        db = SessionLocal()
        try:
            # Query the correct model
            rows = db.query(CapturedData).filter(CapturedData.is_deleted == False).order_by(CapturedData.created_at.desc()).all()
            
            # Diagnostic logging (using print to ensure it shows up in some contexts)
            # print(f"DEBUG: Reloading captured data. Found {len(rows)} records. Timer active: {self._captured_data_timer.isActive()}")
            
            # Update the model and notify the view
            self.captured_table_model.update_rows(rows)
            
            # Ensure the table is visible and updating
            self.captured_table_view.viewport().update()
            
            # Update last updated label
            if hasattr(self, "captured_last_updated_label"):
                now = dt.datetime.now().strftime("%H:%M:%S")
                self.captured_last_updated_label.setText(f"Auto-refreshing: {now}")
                self.captured_last_updated_label.setStyleSheet("color: #27ae60; font-weight: bold; font-size: 11px;") # Green color when active
            
        except Exception as e:
            logger.error(f"CRITICAL: Failed to reload captured data: {e}", exc_info=True)
            if hasattr(self, "captured_last_updated_label"):
                self.captured_last_updated_label.setText(f"Refresh Error: {e}")
                self.captured_last_updated_label.setStyleSheet("color: #e74c3c; font-size: 11px;")
        finally:
            db.close()

    def _on_delete_captured_clicked(self) -> None:
        selection = self.captured_table_view.selectionModel().selectedRows()
        if not selection:
            return
            
        row = selection[0].row()
        record = self.captured_table_model._rows[row]
        
        reply = QMessageBox.question(self, "Confirm Delete", f"Delete captured data for {record.chassis_number}?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            db = SessionLocal()
            try:
                db.query(CapturedData).filter(CapturedData.id == record.id).update({"is_deleted": True})
                db.commit()
                self._reload_captured_data()
            finally:
                db.close()

    def _create_prices_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(25)

        # Style inherited from Reports page but applied locally for consistency
        page.setStyleSheet("""
            QWidget { background-color: #f8f9fa; }
            QLabel#pageHeader { font-size: 26px; font-weight: bold; color: #2c3e50; }
            QFrame#filterCard { background-color: white; border: 1px solid #e0e0e0; border-radius: 12px; }
            QLabel.filterLabel { color: #7f8c8d; font-weight: bold; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; }
            QLineEdit, QComboBox { padding: 10px 15px; border: 1px solid #dee2e6; border-radius: 8px; background-color: #ffffff; font-size: 13px; }
            QPushButton#primaryButton { background-color: #3498db; color: white; border: none; border-radius: 8px; font-weight: bold; padding: 10px 20px; }
            QPushButton#primaryButton:hover { background-color: #2980b9; }
            QTableView { 
                background-color: white; 
                border: 1px solid #e0e0e0; 
                border-radius: 12px; 
                gridline-color: #f1f1f1; 
                alternate-background-color: #fafafa;
                selection-background-color: #e3f2fd;
                selection-color: #1976d2;
                outline: none;
            }
            QTableView::item {
                padding: 12px;
                border-bottom: 1px solid #f1f1f1;
            }
            QTableView::item:hover {
                background-color: #f1f8ff;
            }
            QHeaderView::section { 
                background-color: #f8f9fa; 
                color: #5a6268; 
                padding: 12px; 
                font-weight: bold; 
                text-transform: uppercase; 
                font-size: 11px; 
                border: none; 
                border-bottom: 2px solid #e9ecef; 
            }
        """)

        # Header
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        header_v_box = QVBoxLayout()
        header = QLabel("Motorcycle Price List")
        header.setObjectName("pageHeader")
        header_v_box.addWidget(header)
        
        header_subtitle = QLabel("Configure and manage base prices and tax structures for each model.")
        header_subtitle.setStyleSheet("color: #7f8c8d; font-size: 13px;")
        header_v_box.addWidget(header_subtitle)
        
        header_layout.addLayout(header_v_box)
        header_layout.addStretch(1)
        layout.addWidget(header_widget)

        # Filter Card
        filter_card = QFrame()
        filter_card.setObjectName("filterCard")
        filter_layout = QHBoxLayout(filter_card)
        filter_layout.setContentsMargins(25, 20, 25, 20)
        filter_layout.setSpacing(25)

        # Search Group
        search_box = QVBoxLayout()
        search_box.setSpacing(8)
        search_lbl = QLabel("Search Models")
        search_lbl.setProperty("class", "filterLabel")
        search_box.addWidget(search_lbl)
        self.prices_search_input = QLineEdit()
        self.prices_search_input.setPlaceholderText("Model name...")
        self.prices_search_input.setFixedWidth(300)
        self.prices_search_input.textChanged.connect(self._reload_prices)
        search_box.addWidget(self.prices_search_input)
        filter_layout.addLayout(search_box)

        filter_layout.addStretch(1)
        
        refresh_btn = QPushButton("↻ Reload")
        refresh_btn.setStyleSheet("background-color: white; color: #2c3e50; border: 1px solid #dee2e6; border-radius: 8px; font-weight: bold; padding: 10px 20px;")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self._reload_prices)
        filter_layout.addWidget(refresh_btn, 0, Qt.AlignmentFlag.AlignBottom)
        
        layout.addWidget(filter_card)

        # Table Section
        table_container = QFrame()
        table_container.setStyleSheet("background-color: white; border: 1px solid #e0e0e0; border-radius: 12px;")
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(1, 1, 1, 1)

        self.prices_table_model = PricesTableModel()
        self.prices_table_view = QTableView()
        self.prices_table_view.setModel(self.prices_table_model)
        self.prices_table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.prices_table_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.prices_table_view.setAlternatingRowColors(True)
        self.prices_table_view.setShowGrid(False)
        self.prices_table_view.doubleClicked.connect(self._on_price_row_double_clicked)
        
        # Responsive Columns
        self.prices_table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.prices_table_view.horizontalHeader().setStretchLastSection(True)
        self.prices_table_view.verticalHeader().setVisible(False)
        
        table_layout.addWidget(self.prices_table_view)
        layout.addWidget(table_container, 1)

        # Action Buttons
        action_bar = QHBoxLayout()
        action_bar.setSpacing(15)
        
        add_btn = QPushButton("+ New Price")
        add_btn.setStyleSheet("background-color: #27ae60; color: white; border: none; font-weight: bold; padding: 10px 20px; border-radius: 8px;")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._on_add_price_clicked)

        edit_btn = QPushButton("✎ Edit Price")
        edit_btn.setStyleSheet("background-color: #3498db; color: white; border: none; font-weight: bold; padding: 10px 20px; border-radius: 8px;")
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.clicked.connect(self._on_edit_price_clicked)
        
        delete_btn = QPushButton("🗑 Delete Price")
        delete_btn.setStyleSheet("background-color: #e74c3c; color: white; border: none; font-weight: bold; padding: 10px 20px; border-radius: 8px;")
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.clicked.connect(self._on_delete_price_clicked)
        
        action_bar.addStretch(1)
        action_bar.addWidget(add_btn)
        action_bar.addWidget(edit_btn)
        action_bar.addWidget(delete_btn)
        layout.addLayout(action_bar)

        self._reload_prices()

        return page

    def _reload_prices(self) -> None:
        search = self.prices_search_input.text().strip() if hasattr(self, "prices_search_input") else ""

        db = SessionLocal()
        data: List[PriceRow] = []
        try:
            from app.db.models import Price, ProductModel
            query = db.query(Price).join(ProductModel).filter(Price.expiration_date.is_(None))
            
            if search:
                value = f"%{search}%"
                query = query.filter(ProductModel.model_name.ilike(value))

            rows = query.order_by(ProductModel.model_name).all()

            for p in rows:
                data.append(
                    PriceRow(
                        id=p.id,
                        model=p.product_model.model_name,
                        base_price=p.base_price,
                        tax=p.tax_amount,
                        levy=p.levy_amount,
                        total=p.total_price,
                        effective_date=p.effective_date
                    )
                )
        except Exception as e:
            logger.error(f"Error reloading prices: {e}")
        finally:
            db.close()

        self.prices_table_model.update_rows(data)

    def _on_price_row_double_clicked(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        self._on_edit_price_clicked()

    def _on_add_price_clicked(self) -> None:
        self._open_price_dialog()

    def _on_edit_price_clicked(self) -> None:
        selection = self.prices_table_view.selectionModel().selectedRows()
        if not selection:
            QMessageBox.warning(self, "Selection Required", "Please select a price record to edit.")
            return
        
        row_index = selection[0].row()
        row_data = self.prices_table_model._rows[row_index]
        self._open_price_dialog(row_data)

    def _on_delete_price_clicked(self) -> None:
        selection = self.prices_table_view.selectionModel().selectedRows()
        if not selection:
            QMessageBox.warning(self, "Selection Required", "Please select a record to delete.")
            return
            
        row_index = selection[0].row()
        row_data = self.prices_table_model._rows[row_index]
        
        reply = QMessageBox.question(
            self, 
            "Confirm Delete", 
            f"Are you sure you want to delete the price record for {row_data.model}?\nThis will mark the current price as expired.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            db = SessionLocal()
            try:
                from app.db.models import Price
                price = db.query(Price).filter(Price.id == row_data.id).first()
                if price:
                    # Soft delete by setting expiration date
                    price.expiration_date = dt.datetime.utcnow()
                    db.commit()
                    QMessageBox.information(self, "Deleted", "Price record has been expired.")
                    self._reload_prices()
                else:
                    QMessageBox.warning(self, "Error", "Record not found.")
            except Exception as e:
                db.rollback()
                logger.error(f"Error deleting price: {e}")
                QMessageBox.critical(self, "Error", f"Failed to delete record: {e}")
            finally:
                db.close()

    def _open_price_dialog(self, row_data: PriceRow | None = None) -> None:
        db = SessionLocal()
        try:
            from app.db.models import Price, ProductModel
            
            dialog = QDialog(self)
            dialog.setWindowTitle("Edit Price" if row_data else "Add New Price")
            dialog.setMinimumSize(450, 500)
            dialog.setStyleSheet("""
                QDialog { background-color: #f8f9fa; }
                QLabel { font-weight: bold; color: #2c3e50; }
                QLineEdit, QComboBox { padding: 8px; border: 1px solid #ced4da; border-radius: 4px; }
            """)

            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(30, 30, 30, 30)
            layout.setSpacing(15)

            form_grid = QGridLayout()
            form_grid.setSpacing(12)

            # Model Name
            form_grid.addWidget(QLabel("Model Name:"), 0, 0)
            model_combo = QComboBox()
            models = db.query(ProductModel).order_by(ProductModel.model_name).all()
            for m in models:
                model_combo.addItem(m.model_name, m.id)
            
            if row_data:
                idx = model_combo.findText(row_data.model)
                if idx >= 0:
                    model_combo.setCurrentIndex(idx)
                    model_combo.setEnabled(False) # Don't change model on edit
            form_grid.addWidget(model_combo, 0, 1)

            # Base Price
            form_grid.addWidget(QLabel("Base Price:"), 1, 0)
            base_input = QLineEdit(str(row_data.base_price) if row_data else "0")
            form_grid.addWidget(base_input, 1, 1)

            # Sales Tax
            form_grid.addWidget(QLabel("Sales Tax:"), 2, 0)
            tax_input = QLineEdit(str(row_data.tax) if row_data else "0")
            form_grid.addWidget(tax_input, 2, 1)

            # Further Tax
            form_grid.addWidget(QLabel("Further Tax/Levy:"), 3, 0)
            levy_input = QLineEdit(str(row_data.levy) if row_data else "0")
            form_grid.addWidget(levy_input, 3, 1)

            # Total Price (Auto calculated)
            form_grid.addWidget(QLabel("Total Price:"), 4, 0)
            total_lbl = QLabel(f"Rs. {row_data.total:,.2f}" if row_data else "Rs. 0.00")
            total_lbl.setStyleSheet("color: #27ae60; font-size: 16px;")
            form_grid.addWidget(total_lbl, 4, 1)

            def update_total():
                try:
                    b = float(base_input.text() or 0)
                    t = float(tax_input.text() or 0)
                    l = float(levy_input.text() or 0)
                    total = b + t + l
                    total_lbl.setText(f"Rs. {total:,.2f}")
                except ValueError:
                    pass

            base_input.textChanged.connect(update_total)
            tax_input.textChanged.connect(update_total)
            levy_input.textChanged.connect(update_total)

            layout.addLayout(form_grid)
            layout.addStretch(1)

            btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
            btn_box.accepted.connect(dialog.accept)
            btn_box.rejected.connect(dialog.reject)
            layout.addWidget(btn_box)

            if dialog.exec() == QDialog.DialogCode.Accepted:
                b = float(base_input.text() or 0)
                t = float(tax_input.text() or 0)
                l = float(levy_input.text() or 0)
                model_id = model_combo.currentData()
                
                # If editing, expire old price and create new one (Audit trail)
                if row_data:
                    old_price = db.query(Price).filter(Price.id == row_data.id).first()
                    if old_price:
                        old_price.expiration_date = dt.datetime.utcnow()
                
                new_price = Price(
                    product_model_id=model_id,
                    base_price=b,
                    tax_amount=t,
                    levy_amount=l,
                    total_price=b + t + l,
                    effective_date=dt.datetime.utcnow()
                )
                db.add(new_price)
                db.commit()
                QMessageBox.information(self, "Success", "Price record updated successfully.")
                self._reload_prices()

        except Exception as e:
            db.rollback()
            logger.error(f"Error saving price: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save price: {e}")
        finally:
            db.close()

    def _load_invoice_models(self) -> None:
        prices = price_service.get_all_active_prices()
        models: List[str] = []
        for p in prices:
            if p.product_model and p.product_model.model_name and p.product_model.model_name not in models:
                models.append(p.product_model.model_name)
        self.invoice_model_combo.clear()
        self.invoice_model_combo.addItem("")
        for name in models:
            self.invoice_model_combo.addItem(name)
        self.invoice_color_combo.clear()

    def _generate_invoice_number(self) -> None:
        db = SessionLocal()
        try:
            next_inv_num = invoice_service.generate_next_invoice_number(db)
            self.invoice_number_input.setText(next_inv_num)
        except Exception as exc:
            logger.error("Error generating invoice number: %s", exc)
            self.invoice_number_input.setText("ERROR")
        finally:
            db.close()

    def eventFilter(self, obj: QWidget, event) -> bool:
        # Handle Enter key for QComboBox navigation
        if isinstance(obj, QComboBox) and event.type() == event.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.focusNextChild()
                return True
        return super().eventFilter(obj, event)

    def _on_invoice_model_changed(self, model_name: str) -> None:
        if not model_name:
            self.invoice_color_combo.clear()
            self._invoice_current_price = None
            return
        prices = price_service.get_active_prices_for_model(model_name)
        if not prices:
            self.invoice_color_combo.clear()
            self._invoice_current_price = None
            return
        colors: List[str] = []
        for price in prices:
            opt = getattr(price, "optional_features", None)
            if opt and isinstance(opt, dict):
                colors_str = opt.get("colors") or ""
                if colors_str:
                    for part in colors_str.split(","):
                        value = part.strip()
                        if value and value not in colors:
                            colors.append(value)
        self.invoice_color_combo.blockSignals(True)
        self.invoice_color_combo.clear()
        if colors:
            for c in colors:
                self.invoice_color_combo.addItem(c)
            self.invoice_color_combo.setCurrentIndex(0)
            self.invoice_color_combo.blockSignals(False)
            self._on_invoice_color_changed(self.invoice_color_combo.currentText())
        else:
            self.invoice_color_combo.blockSignals(False)
            price = prices[0]
            self._invoice_current_price = price
            self.invoice_amount_spin.setValue(float(price.base_price or 0))
            self._recalculate_invoice_totals()

    def _on_invoice_color_changed(self, color: str) -> None:
        model_name = self.invoice_model_combo.currentText()
        if not model_name or not color:
            return
        price = price_service.get_price_by_model_and_color(model_name, color)
        self._invoice_current_price = price
        if price:
            self.invoice_amount_spin.blockSignals(True)
            self.invoice_amount_spin.setValue(float(price.base_price or 0))
            self.invoice_amount_spin.blockSignals(False)
            self._recalculate_invoice_totals()

    def _recalculate_invoice_totals(self) -> None:
        try:
            qty = float(self.invoice_quantity_spin.value())
            amount_excl = float(self.invoice_amount_spin.value())
            focused = self.focusWidget()
            tax_charged = 0.0
            total_further_tax = 0.0
            if self._invoice_current_price:
                tax_per_unit = float(getattr(self._invoice_current_price, "tax_amount", 0) or 0)
                # If dealer is selected, further tax is typically 0
                further_per_unit = 0.0 if self._is_dealer_selected else float(getattr(self._invoice_current_price, "levy_amount", 0) or 0)
                tax_charged = tax_per_unit * qty
                total_further_tax = further_per_unit * qty
            else:
                settings = settings_service.get_active_settings()
                tax_rate = float(settings.get("tax_rate", 18.0))
                sale_value = amount_excl * qty
                tax_charged = (sale_value * tax_rate) / 100.0
                try:
                    # If dealer is selected, default further tax to 0
                    if self._is_dealer_selected:
                        total_further_tax = 0.0
                    else:
                        total_further_tax = float(self.invoice_further_tax_spin.value())
                except ValueError:
                    total_further_tax = 0.0
            if focused is self.invoice_tax_spin:
                try:
                    tax_charged = float(self.invoice_tax_spin.value())
                except ValueError:
                    pass
            if focused is self.invoice_further_tax_spin:
                try:
                    total_further_tax = float(self.invoice_further_tax_spin.value())
                except ValueError:
                    pass
            sale_value_total = amount_excl * qty
            total_amount = sale_value_total + tax_charged + total_further_tax
            if focused is not self.invoice_tax_spin:
                self.invoice_tax_spin.blockSignals(True)
                self.invoice_tax_spin.setValue(tax_charged)
                self.invoice_tax_spin.blockSignals(False)
            if focused is not self.invoice_further_tax_spin:
                self.invoice_further_tax_spin.blockSignals(True)
                self.invoice_further_tax_spin.setValue(total_further_tax)
                self.invoice_further_tax_spin.blockSignals(False)
            if focused is not self.invoice_total_spin:
                self.invoice_total_spin.blockSignals(True)
                self.invoice_total_spin.setValue(total_amount)
                self.invoice_total_spin.blockSignals(False)
        except Exception:
            return

    def _on_invoice_buyer_name_changed(self, text: str) -> None:
        if getattr(self.invoice_buyer_name_input, "is_navigating", False):
            return
            
        # If user manually edits name, reset dealer selection flag
        self._is_dealer_selected = False
        
        raw = text
        cleaned = "".join(c for c in raw if c.isalpha() or c.isspace())
        if cleaned != raw:
            upper = cleaned.upper()
            self.invoice_buyer_name_input.blockSignals(True)
            self.invoice_buyer_name_input.setText(upper)
            self.invoice_buyer_name_input.blockSignals(False)
            name = upper.strip()
        else:
            name = cleaned.strip()
            if name and name != name.upper():
                name_upper = name.upper()
                self.invoice_buyer_name_input.blockSignals(True)
                self.invoice_buyer_name_input.setText(name_upper)
                self.invoice_buyer_name_input.blockSignals(False)
                name = name_upper
        if not name:
            return
        self._dealer_search_query = name
        self._dealer_completer_timer.start()

    def _on_invoice_chassis_changed(self, text: str) -> None:
        if getattr(self.invoice_chassis_input, "is_navigating", False):
            return
        chassis = text.strip().upper()
        if chassis != text:
            self.invoice_chassis_input.blockSignals(True)
            self.invoice_chassis_input.setText(chassis)
            self.invoice_chassis_input.blockSignals(False)
        
        if not chassis:
            self._chassis_completer_model.setStringList([])
            return
            
        self._chassis_search_query = chassis
        self._chassis_completer_timer.start()

    def _perform_chassis_search(self) -> None:
        query_text = getattr(self, "_chassis_search_query", "").strip()
        if not query_text:
            self._chassis_completer_model.setStringList([])
            return
            
        db = SessionLocal()
        try:
            # Search in Motorcycle Inventory
            results = db.query(Motorcycle.chassis_number).filter(
                Motorcycle.status == "IN_STOCK",
                Motorcycle.chassis_number.ilike(f"%{query_text}%")
            ).limit(10).all()
            
            suggestions = [r[0] for r in results]
            
            # Also search in Captured Data
            captured_results = db.query(CapturedData.chassis_number).filter(
                CapturedData.is_deleted == False,
                CapturedData.chassis_number.ilike(f"%{query_text}%")
            ).limit(10).all()
            
            for r in captured_results:
                if r[0] not in suggestions:
                    suggestions.append(r[0])
            
            self._chassis_completer_model.setStringList(suggestions)
            if suggestions:
                popup = self.invoice_chassis_completer.popup()
                if popup is not None:
                    popup.setMinimumWidth(self.invoice_chassis_input.width())
                self.invoice_chassis_completer.complete()
        except Exception as e:
            logger.error(f"Chassis search error: {e}")
        finally:
            db.close()

    def _on_chassis_selected(self, chassis: str) -> None:
        chassis = chassis.strip().upper()
        if not chassis:
            return
            
        db = SessionLocal()
        try:
            # 1. Search in Captured Data (Priority for Buyer Info)
            cap = db.query(CapturedData).filter(CapturedData.chassis_number == chassis, CapturedData.is_deleted == False).first()
            if cap:
                # Populate Buyer Details
                if cap.cnic: self.invoice_buyer_cnic_input.setText(cap.cnic)
                if cap.name: self.invoice_buyer_name_input.setText(cap.name.upper())
                if cap.father: self.invoice_buyer_father_input.setText(cap.father.upper())
                if cap.cell: self.invoice_buyer_phone_input.setText(cap.cell)
                if cap.address: self.invoice_buyer_address_input.setText(cap.address.upper())
                
                # Populate Vehicle Details from Capture
                if cap.engine_number: self.invoice_engine_input.setText(cap.engine_number.upper())
                
                if cap.model:
                    model_idx = self.invoice_model_combo.findText(cap.model, Qt.MatchFlag.MatchContains)
                    if model_idx >= 0:
                        self.invoice_model_combo.setCurrentIndex(model_idx)
                
                if cap.color:
                    color_idx = self.invoice_color_combo.findText(cap.color, Qt.MatchFlag.MatchContains)
                    if color_idx >= 0:
                        self.invoice_color_combo.setCurrentIndex(color_idx)

            # 2. Search in Motorcycle Inventory (Priority for Pricing)
            bike = db.query(Motorcycle).filter(Motorcycle.chassis_number == chassis).first()
            if bike:
                self.invoice_chassis_input.blockSignals(True)
                self.invoice_chassis_input.setText(bike.chassis_number)
                self.invoice_chassis_input.blockSignals(False)
                
                if bike.engine_number:
                    self.invoice_engine_input.setText(bike.engine_number)
                
                if bike.product_model:
                    model_idx = self.invoice_model_combo.findText(bike.product_model.model_name)
                    if model_idx >= 0:
                        self.invoice_model_combo.setCurrentIndex(model_idx)
                
                if bike.color:
                    color_idx = self.invoice_color_combo.findText(bike.color)
                    if color_idx >= 0:
                        self.invoice_color_combo.setCurrentIndex(color_idx)
                
                if bike.sale_price:
                    self.invoice_amount_spin.setValue(float(bike.sale_price))
            
            self._check_invoice_form_completeness()
                    
        except Exception as e:
            logger.error(f"Chassis selection error: {e}")
        finally:
            db.close()

    def _on_invoice_father_name_changed(self, text: str) -> None:
        raw = text
        cleaned = "".join(c for c in raw if c.isalpha() or c.isspace())
        if cleaned != raw or cleaned != cleaned.upper():
            upper = cleaned.upper()
            self.invoice_buyer_father_input.blockSignals(True)
            self.invoice_buyer_father_input.setText(upper)
            self.invoice_buyer_father_input.blockSignals(False)

    def _on_invoice_cell_changed(self, text: str) -> None:
        digits = "".join(c for c in text if c.isdigit())
        if len(digits) > 11:
            digits = digits[:11]
        if digits != text:
            self.invoice_buyer_phone_input.blockSignals(True)
            self.invoice_buyer_phone_input.setText(digits)
            self.invoice_buyer_phone_input.blockSignals(False)

    def _perform_dealer_search(self) -> None:
        name = getattr(self, "_dealer_search_query", "").strip()
        if not name:
            self._dealer_completer_model.setStringList([])
            self._dealer_completer_map.clear()
            return
        dealers = dealer_service.search_dealers_by_business_name(name, limit=10)
        suggestions = []
        mapping: Dict[str, int] = {}
        for d in dealers:
            business = (d.business_name or "").upper()
            contact = (d.name or "").upper()
            if business and contact:
                display = f"{business} — {contact}"
            elif business:
                display = business
            elif contact:
                display = contact
            else:
                continue
            suggestions.append(display)
            mapping[display] = d.id
        self._dealer_completer_map = mapping
        self._dealer_completer_model.setStringList(suggestions)
        if suggestions:
            popup = self.invoice_dealer_completer.popup()
            if popup is not None:
                popup.setMinimumWidth(self.invoice_buyer_name_input.width())
            self.invoice_dealer_completer.complete()

    def _on_dealer_business_selected(self, business_name: str) -> None:
        display = business_name.strip()
        if not display:
            return
        dealer_id = self._dealer_completer_map.get(display)
        dealer = None
        if dealer_id is not None:
            dealer = dealer_service.get_dealer_by_id(dealer_id)
        if dealer is None:
            parts = display.split(" — ", 1)
            key_name = parts[0].strip() if parts else ""
            if key_name:
                dealer = dealer_service.get_dealer_by_business_name(key_name)
        if not dealer:
            return
            
        self._is_dealer_selected = True
        self.invoice_buyer_name_input.blockSignals(True)
        if dealer.name:
            self.invoice_buyer_name_input.setText(dealer.name.upper())
        self.invoice_buyer_name_input.blockSignals(False)
        if dealer.cnic:
            self.invoice_buyer_cnic_input.blockSignals(True)
            self.invoice_buyer_cnic_input.setText(dealer.cnic)
            self.invoice_buyer_cnic_input.blockSignals(False)
        if dealer.father_name:
            self.invoice_buyer_father_input.blockSignals(True)
            self.invoice_buyer_father_input.setText(dealer.father_name.upper())
            self.invoice_buyer_father_input.blockSignals(False)
        if dealer.phone:
            self.invoice_buyer_phone_input.blockSignals(True)
            self.invoice_buyer_phone_input.setText(dealer.phone)
            self.invoice_buyer_phone_input.blockSignals(False)
        if dealer.address:
            self.invoice_buyer_address_input.blockSignals(True)
            self.invoice_buyer_address_input.setText(dealer.address.upper())
            self.invoice_buyer_address_input.blockSignals(False)
        if dealer.ntn:
            self.invoice_buyer_ntn_input.blockSignals(True)
            self.invoice_buyer_ntn_input.setText(dealer.ntn)
            self.invoice_buyer_ntn_input.blockSignals(False)
            
        # Dealers are registered, so reset Further Tax to 0
        self.invoice_further_tax_spin.blockSignals(True)
        self.invoice_further_tax_spin.setValue(0.0)
        self.invoice_further_tax_spin.blockSignals(False)
        self._recalculate_invoice_totals()

    def _open_dealer_search_dialog(self) -> None:
        dialog = DealerSearchDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        dealer = dialog.selected_dealer
        if dealer is None:
            return
            
        self._is_dealer_selected = True
        self.invoice_buyer_name_input.blockSignals(True)
        if dealer.name:
            self.invoice_buyer_name_input.setText(dealer.name.upper())
        self.invoice_buyer_name_input.blockSignals(False)
        if dealer.cnic:
            self.invoice_buyer_cnic_input.blockSignals(True)
            self.invoice_buyer_cnic_input.setText(dealer.cnic)
            self.invoice_buyer_cnic_input.blockSignals(False)
        if dealer.father_name:
            self.invoice_buyer_father_input.blockSignals(True)
            self.invoice_buyer_father_input.setText(dealer.father_name.upper())
            self.invoice_buyer_father_input.blockSignals(False)
        if dealer.phone:
            self.invoice_buyer_phone_input.blockSignals(True)
            self.invoice_buyer_phone_input.setText(dealer.phone)
            self.invoice_buyer_phone_input.blockSignals(False)
        if dealer.address:
            self.invoice_buyer_address_input.blockSignals(True)
            self.invoice_buyer_address_input.setText(dealer.address.upper())
            self.invoice_buyer_address_input.blockSignals(False)
        if dealer.ntn:
            self.invoice_buyer_ntn_input.blockSignals(True)
            self.invoice_buyer_ntn_input.setText(dealer.ntn)
            self.invoice_buyer_ntn_input.blockSignals(False)

        # Dealers are registered, so reset Further Tax to 0
        self.invoice_further_tax_spin.blockSignals(True)
        self.invoice_further_tax_spin.setValue(0.0)
        self.invoice_further_tax_spin.blockSignals(False)
        self._recalculate_invoice_totals()

    def _on_invoice_cnic_changed(self, text: str) -> None:
        raw = text
        digits = "".join(c for c in raw if c.isdigit())
        formatted = digits
        if len(digits) > 5:
            formatted = digits[:5] + "-" + digits[5:]
        if len(digits) > 12:
            formatted = formatted[:13] + "-" + formatted[13:]
        if len(formatted) > 15:
            formatted = formatted[:15]
        if formatted != raw:
            self.invoice_buyer_cnic_input.blockSignals(True)
            self.invoice_buyer_cnic_input.setText(formatted)
            self.invoice_buyer_cnic_input.blockSignals(False)
        cnic = formatted.strip()
        if not cnic or len(cnic) < 15:
            self.invoice_buyer_name_input.clear()
            self.invoice_buyer_father_input.clear()
            self.invoice_buyer_phone_input.clear()
            self.invoice_buyer_address_input.clear()
            return
        db = SessionLocal()
        try:
            customer = db.query(Customer).filter(Customer.cnic == cnic).first()
            if not customer:
                return
            if customer.name:
                self.invoice_buyer_name_input.setText(customer.name)
            if customer.father_name:
                self.invoice_buyer_father_input.setText(customer.father_name)
            if customer.phone:
                self.invoice_buyer_phone_input.setText(customer.phone)
            if customer.address:
                self.invoice_buyer_address_input.setText(customer.address)
        except Exception:
            return
        finally:
            db.close()

    def _check_invoice_form_completeness(self) -> None:
        """Checks if all required fields are filled to enable the submit button."""
        # Required fields (NTN is intentionally excluded)
        cnic = self.invoice_buyer_cnic_input.text().strip()
        name = self.invoice_buyer_name_input.text().strip()
        father = self.invoice_buyer_father_input.text().strip()
        phone = self.invoice_buyer_phone_input.text().strip()
        address = self.invoice_buyer_address_input.text().strip()
        chassis = self.invoice_chassis_input.text().strip()
        engine = self.invoice_engine_input.text().strip()
        model = self.invoice_model_combo.currentText().strip()
        color = self.invoice_color_combo.currentText().strip()
        
        # Simple completeness check
        is_complete = all([cnic, name, father, phone, address, chassis, engine, model, color])
        
        # Additional format checks for activation
        is_valid_cnic = bool(re.match(r"^\d{5}-\d{7}-\d$", cnic))
        is_valid_phone = bool(re.match(r"^03\d{9}$", phone))
        
        self.invoice_submit_btn.setEnabled(is_complete and is_valid_cnic and is_valid_phone)

    def _validate_invoice_form(self) -> bool:
        inv_num = self.invoice_number_input.text().strip()
        if not inv_num or inv_num == "ERROR":
            self._show_error("Validation Error", "Invoice number is not valid.")
            return False
        buyer_cnic = self.invoice_buyer_cnic_input.text().strip()
        if not buyer_cnic:
            self._show_error("Validation Error", "CNIC is required.")
            return False
        if not re.match(r"^\d{5}-\d{7}-\d$", buyer_cnic):
            self._show_error("Validation Error", "CNIC format must be 12345-1234567-1.")
            return False
        buyer_name = self.invoice_buyer_name_input.text().strip()
        if not buyer_name:
            self._show_error("Validation Error", "Buyer name is required.")
            return False
        phone = self.invoice_buyer_phone_input.text().strip()
        if not phone:
            self._show_error("Validation Error", "Cell number is required.")
            return False
        if not re.match(r"^03\d{9}$", phone):
            self._show_error("Validation Error", "Cell must be 03XXXXXXXXX.")
            return False
        model_name = self.invoice_model_combo.currentText().strip()
        if not model_name:
            self._show_error("Validation Error", "Model is required.")
            return False
        color = self.invoice_color_combo.currentText().strip()
        if not color:
            self._show_error("Validation Error", "Color is required.")
            return False
        chassis = self.invoice_chassis_input.text().strip()
        if not chassis:
            self._show_error("Validation Error", "Chassis number is required.")
            return False
        engine = self.invoice_engine_input.text().strip()
        if not engine:
            self._show_error("Validation Error", "Engine number is required.")
            return False
        if self.invoice_amount_spin.value() <= 0:
            self._show_error("Validation Error", "Amount (Excl. Tax) must be greater than zero.")
            return False
        return True

    def _show_error(self, title: str, message: str) -> None:
        """Shows a professional looking error message box."""
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle(title)
        msg.setText(f"<b>{title}</b>")
        msg.setInformativeText(message)
        msg.setStyleSheet("""
            QMessageBox {
                background-color: white;
            }
            QLabel {
                font-size: 13px;
                color: #2c3e50;
            }
            QPushButton {
                background-color: #3498db;
                color: white;
                padding: 6px 20px;
                border-radius: 4px;
                font-weight: bold;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        msg.exec()

    def _show_success(self, title: str, message: str) -> None:
        """Shows a professional looking success message box."""
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle(title)
        msg.setText(f"<b>{title}</b>")
        msg.setInformativeText(message)
        msg.setStyleSheet("""
            QMessageBox {
                background-color: white;
            }
            QLabel {
                font-size: 13px;
                color: #27ae60;
            }
            QPushButton {
                background-color: #2ecc71;
                color: white;
                padding: 6px 20px;
                border-radius: 4px;
                font-weight: bold;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #27ae60;
            }
        """)
        msg.exec()

    def _display_invoice_qr(self, data: str | None) -> None:
        if not data:
            self.invoice_qr_label.clear()
            self.invoice_fbr_label.clear()
            self._invoice_qr_pixmap = None
            return
        try:
            qr = qrcode.QRCode(version=1, box_size=10, border=2)
            qr.add_data(data)
            qr.make(fit=True)
            qr_img_pil = qr.make_image(fill_color="black", back_color="white")
            qr_img_pil = qr_img_pil.resize((100, 100))
            buf = io.BytesIO()
            qr_img_pil.save(buf, format="PNG")
            pixmap = QPixmap()
            if not pixmap.loadFromData(buf.getvalue(), "PNG"):
                self.invoice_qr_label.clear()
                self.invoice_fbr_label.clear()
                self._invoice_qr_pixmap = None
                return
            self._invoice_qr_pixmap = pixmap
            self.invoice_qr_label.setPixmap(pixmap)
            self.invoice_fbr_label.setText(data)
        except Exception:
            self.invoice_qr_label.clear()
            self.invoice_fbr_label.clear()
            self._invoice_qr_pixmap = None

    def _update_fbr_submitted_counter(self) -> None:
        """Update the FBR Submitted counter in the UI."""
        db = SessionLocal()
        try:
            count = db.query(Invoice).filter(Invoice.fbr_invoice_number != None).count()
            if hasattr(self, "invoice_fbr_stat_value"):
                self.invoice_fbr_stat_value.setText(str(count))
        except Exception as e:
            logger.error("Error updating FBR counter: %s", e)
        finally:
            db.close()

    def _submit_invoice(self) -> None:
        if not self._validate_invoice_form():
            return
        
        # Disable button during submission to prevent double-clicks
        self.invoice_submit_btn.setEnabled(False)
        self.invoice_submit_btn.setText("Submitting...")
        QApplication.processEvents() # Ensure UI updates

        inv_num = self.invoice_number_input.text().strip()
        buyer_cnic = self.invoice_buyer_cnic_input.text().strip()
        buyer_name = self.invoice_buyer_name_input.text().strip()
        buyer_father = self.invoice_buyer_father_input.text().strip()
        buyer_cell = self.invoice_buyer_phone_input.text().strip()
        buyer_address = self.invoice_buyer_address_input.text().strip()
        buyer_ntn_raw = self.invoice_buyer_ntn_input.text().strip()
        buyer_ntn = "-" if not buyer_ntn_raw or buyer_ntn_raw == "0" else buyer_ntn_raw
        payment_mode = self.invoice_payment_mode_combo.currentText().strip() or "Cash"
        qty = float(self.invoice_quantity_spin.value())
        amount_excl = float(self.invoice_amount_spin.value())
        tax = float(self.invoice_tax_spin.value())
        further_tax = float(self.invoice_further_tax_spin.value())
        chassis = self.invoice_chassis_input.text().strip().upper()
        engine = self.invoice_engine_input.text().strip().upper()
        model_name = self.invoice_model_combo.currentText().strip()
        color = self.invoice_color_combo.currentText().strip()
        settings = settings_service.get_active_settings()
        sales_tax_rate = float(settings.get("tax_rate", 18.0))
        fbr_item_name_base = settings.get("item_name", "Motorcycle") or "Motorcycle"
        fbr_item_code_base = settings.get("item_code", "MOTO") or "MOTO"
        fbr_pct_code = settings.get("pct_code", "8711.2010") or "8711.2010"
        final_item_name = f"{fbr_item_name_base} {model_name} {color}"
        final_item_code = f"{fbr_item_code_base}-{model_name}-{color}"
        item = InvoiceItemCreate(
            item_code=final_item_code,
            item_name=final_item_name,
            quantity=qty,
            tax_rate=sales_tax_rate,
            sale_value=amount_excl,
            tax_charged=tax,
            further_tax=further_tax,
            pct_code=fbr_pct_code,
            chassis_number=chassis,
            engine_number=engine,
            model_name=model_name,
            color=color,
        )
        inv = InvoiceCreate(
            invoice_number=inv_num,
            buyer_cnic=buyer_cnic,
            buyer_name=buyer_name,
            buyer_father_name=buyer_father,
            buyer_phone=buyer_cell,
            buyer_address=buyer_address,
            buyer_ntn=buyer_ntn,
            buyer_type=CustomerType.DEALER if self._is_dealer_selected else CustomerType.INDIVIDUAL,
            payment_mode=payment_mode,
            items=[item],
        )
        db = SessionLocal()
        try:
            logger.info("Submitting invoice %s for %s", inv_num, buyer_name)
            created = invoice_service.create_invoice(db, inv)
            fbr_id = created.fbr_invoice_number or "N/A"
            self._show_success(
                "Submission Success",
                f"Invoice {inv_num} has been successfully created and queued for FBR sync.\n\nFBR ID: {fbr_id}"
            )
            self._reset_invoice_form()
            self._generate_invoice_number()
            self._update_fbr_submitted_counter() # Update counter after submission
            
            # Queue SMS if enabled
            from app.services.sms_service import sms_service
            sms_service.queue_invoice_sms(db, created)
            # Start background processing of SMS queue
            QTimer.singleShot(1000, sms_service.process_queue)

            if created.fbr_invoice_number:
                self._display_invoice_qr(created.fbr_invoice_number)
        except RetryError as exc:
            try:
                last_exc = exc.last_attempt.exception()
                if isinstance(last_exc, requests.exceptions.ConnectionError):
                    msg = "Could not connect to FBR server. Check internet connection or FBR URL settings."
                elif isinstance(last_exc, requests.exceptions.Timeout):
                    msg = "Connection to FBR server timed out."
                else:
                    msg = f"FBR submission failed: {str(last_exc)}"
            except Exception:
                msg = f"FBR submission error: {str(exc)}"
            logger.error("FBR RetryError: %s", msg)
            self._show_error("FBR Connection Error", msg)
        except Exception as exc:
            logger.error("Unexpected error during invoice submission: %s", exc, exc_info=True)
            self._show_error("System Error", f"An unexpected error occurred during submission:\n\n{str(exc)}")
        finally:
            self.invoice_submit_btn.setText("Submit to FBR")
            self._check_invoice_form_completeness() # Re-evaluate state
            db.close()

    def _reset_invoice_form(self) -> None:
        self._is_dealer_selected = False
        self.invoice_buyer_cnic_input.clear()
        self.invoice_buyer_ntn_input.clear()
        self.invoice_buyer_name_input.clear()
        self.invoice_buyer_father_input.clear()
        self.invoice_buyer_phone_input.clear()
        self.invoice_buyer_address_input.clear()
        self.invoice_model_combo.setCurrentIndex(0)
        self.invoice_color_combo.clear()
        self.invoice_payment_mode_combo.setCurrentIndex(0)
        self.invoice_chassis_input.clear()
        self.invoice_engine_input.clear()
        self.invoice_quantity_spin.setValue(1)
        self.invoice_amount_spin.setValue(0.0)
        self.invoice_tax_spin.setValue(0.0)
        self.invoice_further_tax_spin.setValue(0.0)
        self.invoice_total_spin.setValue(0.0)
        self._display_invoice_qr(None)

    def _create_customers_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(25)

        # High-end Professional Style for Customer Directory
        page.setStyleSheet("""
            QWidget { background-color: #f8f9fa; }
            QLabel#pageHeader { font-size: 26px; font-weight: bold; color: #2c3e50; }
            QFrame#filterCard { background-color: white; border: 1px solid #e0e0e0; border-radius: 12px; }
            QLabel.filterLabel { color: #7f8c8d; font-weight: bold; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; }
            QLineEdit, QComboBox { padding: 10px 15px; border: 1px solid #dee2e6; border-radius: 8px; background-color: #ffffff; font-size: 13px; }
            QPushButton#primaryButton { background-color: #3498db; color: white; border: none; border-radius: 8px; font-weight: bold; padding: 10px 20px; }
            QPushButton#primaryButton:hover { background-color: #2980b9; }
            QTableView { 
                background-color: white; 
                border: 1px solid #e0e0e0; 
                border-radius: 12px; 
                gridline-color: #f1f1f1; 
                alternate-background-color: #fafafa;
                selection-background-color: #e3f2fd;
                selection-color: #1976d2;
                outline: none;
            }
            QTableView::item {
                padding: 12px;
                border-bottom: 1px solid #f8f9fa;
            }
            QTableView::item:hover {
                background-color: #f1f8ff;
            }
            QHeaderView::section { 
                background-color: #f8f9fa; 
                color: #5a6268; 
                padding: 15px; 
                font-weight: bold; 
                text-transform: uppercase; 
                font-size: 11px; 
                border: none; 
                border-bottom: 2px solid #e9ecef; 
            }
        """)

        # Header
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        header_v_box = QVBoxLayout()
        header = QLabel("Customer Directory")
        header.setObjectName("pageHeader")
        header_v_box.addWidget(header)
        
        header_subtitle = QLabel("Manage your customer information and sale history records.")
        header_subtitle.setStyleSheet("color: #7f8c8d; font-size: 13px;")
        header_v_box.addWidget(header_subtitle)
        
        header_layout.addLayout(header_v_box)
        header_layout.addStretch(1)
        layout.addWidget(header_widget)

        # Filter Card
        filter_card = QFrame()
        filter_card.setObjectName("filterCard")
        filter_layout = QHBoxLayout(filter_card)
        filter_layout.setContentsMargins(25, 20, 25, 20)
        filter_layout.setSpacing(25)

        # Search Group
        search_box = QVBoxLayout()
        search_box.setSpacing(8)
        search_lbl = QLabel("Search Customers")
        search_lbl.setProperty("class", "filterLabel")
        search_box.addWidget(search_lbl)
        self.customers_search_input = QLineEdit()
        self.customers_search_input.setPlaceholderText("Name, CNIC or phone")
        self.customers_search_input.setFixedWidth(300)
        self.customers_search_input.textChanged.connect(self._reload_customers)
        search_box.addWidget(self.customers_search_input)
        filter_layout.addLayout(search_box)

        filter_layout.addStretch(1)
        
        refresh_btn = QPushButton("↻ Reload")
        refresh_btn.setStyleSheet("background-color: white; color: #2c3e50; border: 1px solid #dee2e6; border-radius: 8px; font-weight: bold; padding: 10px 20px;")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self._reload_customers)
        filter_layout.addWidget(refresh_btn, 0, Qt.AlignmentFlag.AlignBottom)
        
        layout.addWidget(filter_card)

        # Table Section
        table_container = QFrame()
        table_container.setStyleSheet("background-color: white; border: 1px solid #e0e0e0; border-radius: 12px;")
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(1, 1, 1, 1)

        self.customers_table_model = CustomersTableModel()
        self.customers_table_view = QTableView()
        self.customers_table_view.setModel(self.customers_table_model)
        self.customers_table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.customers_table_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.customers_table_view.setAlternatingRowColors(True)
        self.customers_table_view.setShowGrid(False)
        self.customers_table_view.doubleClicked.connect(self._on_customer_row_double_clicked)
        
        # Responsive Columns
        self.customers_table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.customers_table_view.horizontalHeader().setStretchLastSection(True)
        self.customers_table_view.verticalHeader().setVisible(False)
        
        table_layout.addWidget(self.customers_table_view)
        layout.addWidget(table_container, 1)

        # Action Buttons
        action_bar = QHBoxLayout()
        action_bar.setSpacing(15)
        
        edit_btn = QPushButton("✎ Edit Customer")
        edit_btn.setObjectName("resetButton")
        edit_btn.setStyleSheet("background-color: #3498db; color: white; border: none; font-weight: bold; padding: 10px 20px; border-radius: 8px;")
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.clicked.connect(self._on_edit_customer_clicked)
        
        delete_btn = QPushButton("🗑 Delete Record")
        delete_btn.setStyleSheet("background-color: #e74c3c; color: white; border: none; font-weight: bold; padding: 10px 20px; border-radius: 8px;")
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.clicked.connect(self._on_delete_customer_clicked)
        
        action_bar.addStretch(1)
        action_bar.addWidget(edit_btn)
        action_bar.addWidget(delete_btn)
        layout.addLayout(action_bar)

        self._reload_customers()

        return page

    def _create_dealers_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(25)

        # High-end Professional Style for Dealer Network
        page.setStyleSheet("""
            QWidget { background-color: #f8f9fa; }
            QLabel#pageHeader { font-size: 26px; font-weight: bold; color: #2c3e50; }
            QFrame#filterCard { background-color: white; border: 1px solid #e0e0e0; border-radius: 12px; }
            QLabel.filterLabel { color: #7f8c8d; font-weight: bold; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; }
            QLineEdit, QComboBox { padding: 10px 15px; border: 1px solid #dee2e6; border-radius: 8px; background-color: #ffffff; font-size: 13px; }
            QPushButton#primaryButton { background-color: #3498db; color: white; border: none; border-radius: 8px; font-weight: bold; padding: 10px 20px; }
            QPushButton#primaryButton:hover { background-color: #2980b9; }
            QPushButton#actionButton { background-color: #3498db; color: white; border: none; border-radius: 8px; font-weight: bold; padding: 10px 20px; }
            QPushButton#actionButton:hover { background-color: #2980b9; }
            QPushButton#deleteButton { background-color: #e74c3c; color: white; border: none; border-radius: 8px; font-weight: bold; padding: 10px 20px; }
            QPushButton#deleteButton:hover { background-color: #c0392b; }
            QTableView { 
                background-color: white; 
                border: 1px solid #e0e0e0; 
                border-radius: 12px; 
                gridline-color: #f1f1f1; 
                alternate-background-color: #fafafa;
                selection-background-color: #e3f2fd;
                selection-color: #1976d2;
                outline: none;
            }
            QTableView::item {
                padding: 12px;
                border-bottom: 1px solid #f8f9fa;
            }
            QTableView::item:hover {
                background-color: #f1f8ff;
            }
            QHeaderView::section { 
                background-color: #f8f9fa; 
                color: #5a6268; 
                padding: 15px; 
                font-weight: bold; 
                text-transform: uppercase; 
                font-size: 11px; 
                border: none; 
                border-bottom: 2px solid #e9ecef; 
            }
        """)

        # Header
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        header_v_box = QVBoxLayout()
        header = QLabel("Dealer Network")
        header.setObjectName("pageHeader")
        header_v_box.addWidget(header)
        
        header_subtitle = QLabel("Manage your authorized dealer partnerships and contact information.")
        header_subtitle.setStyleSheet("color: #7f8c8d; font-size: 13px;")
        header_v_box.addWidget(header_subtitle)
        
        header_layout.addLayout(header_v_box)
        header_layout.addStretch(1)
        
        layout.addWidget(header_widget)

        # Filter Card
        filter_card = QFrame()
        filter_card.setObjectName("filterCard")
        filter_layout = QHBoxLayout(filter_card)
        filter_layout.setContentsMargins(25, 20, 25, 20)
        filter_layout.setSpacing(25)

        # Search Group
        search_box = QVBoxLayout()
        search_box.setSpacing(8)
        search_lbl = QLabel("Search Dealers")
        search_lbl.setProperty("class", "filterLabel")
        search_box.addWidget(search_lbl)
        self.dealers_search_input = QLineEdit()
        self.dealers_search_input.setPlaceholderText("Business name, CNIC or phone")
        self.dealers_search_input.setFixedWidth(300)
        self.dealers_search_input.textChanged.connect(self._reload_dealers)
        search_box.addWidget(self.dealers_search_input)
        filter_layout.addLayout(search_box)

        filter_layout.addStretch(1)
        
        refresh_btn = QPushButton("↻ Reload")
        refresh_btn.setStyleSheet("background-color: white; color: #2c3e50; border: 1px solid #dee2e6; border-radius: 8px; font-weight: bold; padding: 10px 20px;")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self._reload_dealers)
        filter_layout.addWidget(refresh_btn, 0, Qt.AlignmentFlag.AlignBottom)
        
        layout.addWidget(filter_card)

        # Table Section
        table_container = QFrame()
        table_container.setStyleSheet("background-color: white; border: 1px solid #e0e0e0; border-radius: 12px;")
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(1, 1, 1, 1)

        self.dealers_table_model = DealersTableModel()
        self.dealers_table_view = QTableView()
        self.dealers_table_view.setModel(self.dealers_table_model)
        self.dealers_table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.dealers_table_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.dealers_table_view.setAlternatingRowColors(True)
        self.dealers_table_view.setShowGrid(False)
        self.dealers_table_view.doubleClicked.connect(self._on_dealer_row_double_clicked)

        # Responsive Columns
        self.dealers_table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.dealers_table_view.horizontalHeader().setStretchLastSection(True)
        self.dealers_table_view.verticalHeader().setVisible(False)
        
        table_layout.addWidget(self.dealers_table_view)
        layout.addWidget(table_container, 1)

        # Action Buttons
        action_bar = QHBoxLayout()
        action_bar.setSpacing(15)
        
        add_btn = QPushButton("+ Add Dealer")
        add_btn.setObjectName("actionButton")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._on_add_dealer_clicked)

        edit_btn = QPushButton("✎ Edit Dealer")
        edit_btn.setObjectName("actionButton")
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.clicked.connect(self._on_edit_dealer_clicked)
        
        delete_btn = QPushButton("🗑 Delete Dealer")
        delete_btn.setObjectName("deleteButton")
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.clicked.connect(self._on_delete_dealer_clicked)
        
        action_bar.addStretch(1)
        action_bar.addWidget(add_btn)
        action_bar.addWidget(edit_btn)
        action_bar.addWidget(delete_btn)
        layout.addLayout(action_bar)

        self._reload_dealers()

        return page

    def _create_spare_ledger_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        # Header Section
        header_layout = QHBoxLayout()
        header = QLabel("Spare Parts Ledger")
        header.setObjectName("pageHeader")
        header_layout.addWidget(header)
        header_layout.addStretch(1)

        new_txn_btn = QPushButton("+ New Transaction")
        new_txn_btn.setObjectName("primaryButton")
        new_txn_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_txn_btn.clicked.connect(self._open_new_ledger_transaction_dialog)
        
        report_btn = QPushButton("Monthly Report")
        report_btn.setObjectName("resetButton")
        report_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        report_btn.clicked.connect(self._open_spare_ledger_report_dialog)
        
        header_layout.addWidget(report_btn)
        header_layout.addWidget(new_txn_btn)
        layout.addLayout(header_layout)

        # Summary Stats Row
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(15)

        self.ledger_total_credit_card = self._create_stat_card("TOTAL CREDITS (IN)", "0.00", "#2ecc71")
        self.ledger_total_debit_card = self._create_stat_card("TOTAL DEBITS (OUT)", "0.00", "#e74c3c")
        self.ledger_balance_card = self._create_stat_card("CURRENT BALANCE", "0.00", "#3498db")

        stats_layout.addWidget(self.ledger_total_credit_card)
        stats_layout.addWidget(self.ledger_total_debit_card)
        stats_layout.addWidget(self.ledger_balance_card)
        layout.addLayout(stats_layout)

        # Controls Section
        controls_group = QFrame()
        controls_group.setObjectName("formGroup")
        controls_group.setStyleSheet("QFrame#formGroup { background-color: #fdfdfd; }")
        controls_layout = QHBoxLayout(controls_group)
        controls_layout.setContentsMargins(15, 10, 15, 10)
        controls_layout.setSpacing(15)

        search_label = QLabel("Search:")
        self.ledger_search_input = QLineEdit()
        self.ledger_search_input.setPlaceholderText("Ref # or description...")
        self.ledger_search_input.textChanged.connect(self._reload_spare_ledger)

        type_label = QLabel("Type:")
        self.ledger_type_combo = QComboBox()
        self.ledger_type_combo.addItems(["All", "CREDIT", "DEBIT"])
        self.ledger_type_combo.currentTextChanged.connect(self._reload_spare_ledger)

        month_label = QLabel("Month:")
        self.ledger_month_combo = QComboBox()
        self.ledger_month_combo.addItem("All Months")
        self.ledger_month_combo.currentTextChanged.connect(self._reload_spare_ledger)

        filter_button = QPushButton("↻ Refresh")
        filter_button.setObjectName("resetButton")
        filter_button.clicked.connect(self._reload_spare_ledger)

        controls_layout.addWidget(search_label)
        controls_layout.addWidget(self.ledger_search_input, 1)
        controls_layout.addWidget(type_label)
        controls_layout.addWidget(self.ledger_type_combo)
        controls_layout.addWidget(month_label)
        controls_layout.addWidget(self.ledger_month_combo)
        controls_layout.addWidget(filter_button)
        layout.addWidget(controls_group)

        # Table Section
        self.ledger_table_model = SpareLedgerTableModel()
        self.ledger_table_view = QTableView(page)
        self.ledger_table_view.setModel(self.ledger_table_model)
        self.ledger_table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.ledger_table_view.setAlternatingRowColors(True)
        self.ledger_table_view.horizontalHeader().setStretchLastSection(True)
        self.ledger_table_view.verticalHeader().setVisible(False)
        self.ledger_table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ledger_table_view.customContextMenuRequested.connect(self._show_ledger_context_menu)
        
        layout.addWidget(self.ledger_table_view, 1)

        self._reload_spare_ledger()

        return page

    def _show_ledger_context_menu(self, pos) -> None:
        index = self.ledger_table_view.indexAt(pos)
        if not index.isValid():
            return

        row_data = self.ledger_table_model._rows[index.row()]
        if row_data.id == -1: # Don't allow editing virtual B/F row
            return

        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        edit_action = menu.addAction("Modify Transaction")
        delete_action = menu.addAction("Delete Transaction")
        
        action = menu.exec(self.ledger_table_view.viewport().mapToGlobal(pos))
        
        if action == edit_action:
            self._open_edit_ledger_transaction_dialog(row_data)
        elif action == delete_action:
            self._delete_ledger_transaction(row_data)

    def _delete_ledger_transaction(self, row_data: SpareLedgerRow) -> None:
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete this transaction?\n\n"
            f"Date: {row_data.timestamp.strftime('%Y-%m-%d %H:%M')}\n"
            f"Ref: {row_data.reference}\n"
            f"Amount: Rs. {max(row_data.credit, row_data.debit):,.2f}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            db = SessionLocal()
            try:
                txn = db.query(SpareLedgerTransaction).filter(SpareLedgerTransaction.id == row_data.id).first()
                if txn:
                    db.delete(txn)
                    db.commit()
                    self._show_success("Deleted", "Transaction has been deleted successfully.")
                    self._reload_spare_ledger()
                else:
                    self._show_error("Error", "Could not find the transaction in database.")
            except Exception as e:
                db.rollback()
                self._show_error("Error", f"Failed to delete: {str(e)}")
            finally:
                db.close()

    def _open_edit_ledger_transaction_dialog(self, row_data: SpareLedgerRow) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Modify Ledger Transaction")
        dialog.setFixedWidth(450)
        
        # Use same styling as New Transaction
        dialog.setStyleSheet(self.invoice_submit_btn.window().styleSheet() + """
            QDialog { background-color: white; }
            QLabel { font-size: 13px; color: #2c3e50; font-weight: 500; }
            QLineEdit, QComboBox, QDoubleSpinBox, QDateEdit {
                padding: 10px; border: 1px solid #dee2e6; border-radius: 6px;
                background-color: #f8f9fa; font-size: 13px; min-height: 20px;
            }
            QPushButton { padding: 10px 25px; border-radius: 6px; font-weight: bold; font-size: 13px; }
        """)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)

        form = QGridLayout()
        form.setSpacing(15)

        type_combo = QComboBox()
        type_combo.addItems(["CREDIT (Deposit/In)", "DEBIT (Order/Out)"])
        type_combo.setCurrentIndex(0 if row_data.credit > 0 else 1)
        form.addWidget(QLabel("Transaction Type"), 0, 0)
        form.addWidget(type_combo, 0, 1)

        cash_type_combo = QComboBox()
        cash_type_combo.addItems(["Hard Cash (Daily Ledger)", "Bank Deposited"])
        cash_type_combo.setCurrentIndex(0 if row_data.cash_type == "HARD_CASH" else 1)
        form.addWidget(QLabel("Cash Source"), 1, 0)
        form.addWidget(cash_type_combo, 1, 1)

        date_edit = QDateEdit()
        date_edit.setCalendarPopup(True)
        date_edit.setDisplayFormat("dd-MM-yyyy")
        if row_data.timestamp:
            date_edit.setDate(QDate(row_data.timestamp.year, row_data.timestamp.month, row_data.timestamp.day))
        form.addWidget(QLabel("Transaction Date"), 2, 0)
        form.addWidget(date_edit, 2, 1)

        amount_spin = QDoubleSpinBox()
        amount_spin.setRange(0, 99999999)
        amount_spin.setDecimals(2)
        amount_spin.setPrefix("Rs. ")
        amount_spin.setValue(max(row_data.credit, row_data.debit))
        form.addWidget(QLabel("Amount"), 3, 0)
        form.addWidget(amount_spin, 3, 1)

        ref_input = QLineEdit()
        ref_input.setText(row_data.reference)
        form.addWidget(QLabel("Reference"), 4, 0)
        form.addWidget(ref_input, 4, 1)

        desc_input = QLineEdit()
        desc_input.setText(row_data.description)
        form.addWidget(QLabel("Description"), 5, 0)
        form.addWidget(desc_input, 5, 1)

        layout.addLayout(form)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setText("Update Transaction")
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet("background-color: #3498db; color: white; border: none;")
        
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)
        layout.addWidget(btn_box)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            db = SessionLocal()
            try:
                txn = db.query(SpareLedgerTransaction).filter(SpareLedgerTransaction.id == row_data.id).first()
                if txn:
                    txn.trans_type = "CREDIT" if type_combo.currentIndex() == 0 else "DEBIT"
                    txn.cash_type = "HARD_CASH" if cash_type_combo.currentIndex() == 0 else "BANK"
                    txn.amount = float(amount_spin.value())
                    txn.reference_number = ref_input.text().strip()
                    txn.description = desc_input.text().strip()
                    
                    qdate = date_edit.date()
                    selected_dt = dt.datetime(qdate.year(), qdate.month(), qdate.day())
                    txn.timestamp = selected_dt
                    
                    # Update month key
                    if selected_dt.day >= 6:
                        cycle_date = selected_dt + dt.timedelta(days=30)
                        txn.month_key = cycle_date.strftime("%Y-%m")
                    else:
                        txn.month_key = selected_dt.strftime("%Y-%m")
                    
                    db.commit()
                    self._show_success("Updated", "Transaction updated successfully.")
                    self._reload_spare_ledger()
            except Exception as e:
                db.rollback()
                self._show_error("Update Error", str(e))
            finally:
                db.close()

    def _open_new_ledger_transaction_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("New Ledger Transaction")
        dialog.setFixedWidth(450)
        
        # Professional Styling for the Dialog and Calendar
        dialog.setStyleSheet("""
            QDialog {
                background-color: white;
            }
            QLabel {
                font-size: 13px;
                color: #2c3e50;
                font-weight: 500;
            }
            QLineEdit, QComboBox, QDoubleSpinBox, QDateEdit {
                padding: 10px;
                border: 1px solid #dee2e6;
                border-radius: 6px;
                background-color: #f8f9fa;
                font-size: 13px;
                min-height: 20px;
            }
            QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QDateEdit:focus {
                border: 2px solid #3498db;
                background-color: white;
            }
            QDateEdit::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 30px;
                border-left: 1px solid #dee2e6;
            }
            QCalendarWidget QWidget {
                background-color: white;
            }
            QCalendarWidget QToolButton {
                color: #2c3e50;
                font-weight: bold;
                background-color: white;
                border: none;
                margin: 5px;
            }
            QCalendarWidget QMenu {
                background-color: white;
            }
            QCalendarWidget QSpinBox {
                width: 50px;
                font-size: 14px;
                background-color: white;
                selection-background-color: #3498db;
            }
            QCalendarWidget QAbstractItemView:enabled {
                color: #2c3e50;
                selection-background-color: #3498db;
                selection-color: white;
            }
            QPushButton {
                padding: 10px 25px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
            }
        """)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)

        form = QGridLayout()
        form.setSpacing(15)

        # Event filter to handle Enter key navigation and prevent dialog submission
        class EnterKeyFilter(QObject):
            def __init__(self, next_field, parent_dialog):
                super().__init__(parent_dialog)
                self.next_field = next_field
                self.parent_dialog = parent_dialog

            def eventFilter(self, obj, event):
                if event.type() == QEvent.Type.KeyPress:
                    if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                        if self.next_field:
                            self.next_field.setFocus()
                        else:
                            self.parent_dialog.accept()
                        return True
                return super().eventFilter(obj, event)

        type_combo = QComboBox()
        type_combo.addItems(["CREDIT (Deposit/In)", "DEBIT (Order/Out)"])
        form.addWidget(QLabel("Transaction Type"), 0, 0)
        form.addWidget(type_combo, 0, 1)

        cash_type_combo = QComboBox()
        cash_type_combo.addItems(["Hard Cash (Daily Ledger)", "Bank Deposited"])
        form.addWidget(QLabel("Cash Source"), 1, 0)
        form.addWidget(cash_type_combo, 1, 1)

        date_edit = QDateEdit()
        date_edit.setCalendarPopup(True)
        date_edit.setDisplayFormat("dd-MM-yyyy")
        date_edit.setDate(QDate.currentDate())
        form.addWidget(QLabel("Transaction Date"), 2, 0)
        form.addWidget(date_edit, 2, 1)

        amount_spin = QDoubleSpinBox()
        amount_spin.setRange(0, 99999999)
        amount_spin.setDecimals(2)
        amount_spin.setPrefix("Rs. ")
        form.addWidget(QLabel("Amount"), 3, 0)
        form.addWidget(amount_spin, 3, 1)

        ref_input = QLineEdit()
        ref_input.setPlaceholderText("Enter reference number...")
        form.addWidget(QLabel("Reference"), 4, 0)
        form.addWidget(ref_input, 4, 1)

        desc_input = QLineEdit()
        desc_input.setPlaceholderText("Enter transaction description...")
        form.addWidget(QLabel("Description"), 5, 0)
        form.addWidget(desc_input, 5, 1)

        # Install event filters for sequential navigation
        type_combo.installEventFilter(EnterKeyFilter(cash_type_combo, dialog))
        cash_type_combo.installEventFilter(EnterKeyFilter(date_edit, dialog))
        date_edit.installEventFilter(EnterKeyFilter(amount_spin, dialog))
        amount_spin.installEventFilter(EnterKeyFilter(ref_input, dialog))
        ref_input.installEventFilter(EnterKeyFilter(desc_input, dialog))
        desc_input.installEventFilter(EnterKeyFilter(None, dialog))

        layout.addLayout(form)

        # Custom Button Box Styling
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        # Disable auto-default to prevent Enter key from triggering Save prematurely
        ok_btn = btn_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn:
            ok_btn.setText("Save Transaction")
            ok_btn.setAutoDefault(False)
            ok_btn.setDefault(False)
            ok_btn.setStyleSheet("""
                QPushButton { background-color: #3498db; color: white; border: none; }
                QPushButton:hover { background-color: #2980b9; }
            """)
        
        cancel_btn = btn_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_btn:
            cancel_btn.setAutoDefault(False)
            cancel_btn.setStyleSheet("""
                QPushButton { background-color: #f8f9fa; color: #6c757d; border: 1px solid #dee2e6; }
                QPushButton:hover { background-color: #e2e6ea; }
            """)
        
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)
        layout.addWidget(btn_box)

        # Initial Focus
        type_combo.setFocus()

        if dialog.exec() == QDialog.DialogCode.Accepted:
            db = SessionLocal()
            try:
                txn_type = "CREDIT" if type_combo.currentIndex() == 0 else "DEBIT"
                cash_type = "HARD_CASH" if cash_type_combo.currentIndex() == 0 else "BANK"
                amount = float(amount_spin.value())
                if amount <= 0:
                    raise ValueError("Amount must be greater than zero.")
                
                # Get selected date
                qdate = date_edit.date()
                selected_dt = dt.datetime(qdate.year(), qdate.month(), qdate.day())
                
                # Simple logic for month key (cycle 6th to 5th)
                if selected_dt.day >= 6:
                    # Current cycle belongs to next month's closing
                    cycle_date = selected_dt + dt.timedelta(days=30)
                    month_key = cycle_date.strftime("%Y-%m")
                else:
                    month_key = selected_dt.strftime("%Y-%m")

                new_txn = SpareLedgerTransaction(
                    trans_type=txn_type,
                    amount=amount,
                    cash_type=cash_type,
                    reference_number=ref_input.text().strip(),
                    description=desc_input.text().strip(),
                    month_key=month_key,
                    timestamp=selected_dt
                )
                db.add(new_txn)
                db.commit()
                self._show_success("Transaction Added", f"Successfully recorded {txn_type} of {amount:,.2f}")
                self._reload_spare_ledger()
            except Exception as e:
                db.rollback()
                self._show_error("Transaction Error", str(e))
            finally:
                db.close()

    def _open_spare_ledger_report_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Spare Ledger Monthly Report")
        dialog.setMinimumSize(900, 600)
        
        # Professional Styling for the Report Dialog
        dialog.setStyleSheet("""
            QDialog {
                background-color: #f8f9fa;
            }
            QLabel#reportTitle {
                font-size: 22px;
                font-weight: bold;
                color: #2c3e50;
                padding: 10px 0px;
            }
            QTableView {
                background-color: white;
                border: 1px solid #dee2e6;
                border-radius: 8px;
                gridline-color: #f1f1f1;
                font-size: 13px;
                outline: 0;
            }
            QHeaderView::section {
                background-color: #34495e;
                color: white;
                padding: 12px;
                font-weight: bold;
                border: none;
                border-right: 1px solid #2c3e50;
            }
            QTableView::item {
                padding: 10px;
                border-bottom: 1px solid #f1f1f1;
            }
            QTableView::item:selected {
                background-color: #e3f2fd;
                color: #2c3e50;
            }
            QPushButton {
                padding: 10px 25px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
                background-color: #f8f9fa;
                color: #6c757d;
                border: 1px solid #dee2e6;
            }
            QPushButton:hover {
                background-color: #e2e6ea;
            }
        """)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        title = QLabel("Monthly Summary Report")
        title.setObjectName("reportTitle")
        layout.addWidget(title)

        subtitle = QLabel("Double-click any row to view complete transaction details for that month.")
        subtitle.setStyleSheet("color: #7f8c8d; font-size: 12px; margin-top: -15px; margin-bottom: 10px;")
        layout.addWidget(subtitle)

        table_view = QTableView()
        model = SpareLedgerReportTableModel()
        table_view.setModel(model)
        table_view.setAlternatingRowColors(True)
        table_view.horizontalHeader().setStretchLastSection(True)
        table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table_view.verticalHeader().setVisible(False)
        table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        table_view.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        table_view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table_view.setShowGrid(False)
        table_view.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(table_view)

        def on_row_double_clicked(index: QModelIndex):
            if not index.isValid():
                return
            row_data = model._rows[index.row()]
            month_key = row_data.month_key
            
            dialog.accept() # Close dialog
            
            # Switch to Spare Ledger page
            self._select_page("spare_ledger")
            
            # Set the month filter
            if hasattr(self, "ledger_month_combo"):
                idx = self.ledger_month_combo.findText(month_key)
                if idx >= 0:
                    self.ledger_month_combo.setCurrentIndex(idx)
                else:
                    # If month not in list (shouldn't happen), reload anyway
                    self._reload_spare_ledger()

        table_view.doubleClicked.connect(on_row_double_clicked)

        # Generate Report Data
        db = SessionLocal()
        try:
            # Get all transactions chronologically
            txns = db.query(SpareLedgerTransaction).order_by(SpareLedgerTransaction.timestamp.asc()).all()
            
            # Group by month_key
            month_stats: Dict[str, Dict[str, float]] = {}
            for tx in txns:
                mk = tx.month_key or "N/A"
                if mk not in month_stats:
                    month_stats[mk] = {
                        "bank_credit": 0.0, 
                        "hard_cash_credit": 0.0,
                        "bank_debit": 0.0,
                        "hard_cash_debit": 0.0
                    }
                
                amt = float(tx.amount or 0)
                is_bank = (tx.cash_type == "BANK")
                
                if tx.trans_type == "CREDIT":
                    if is_bank:
                        month_stats[mk]["bank_credit"] += amt
                    else:
                        month_stats[mk]["hard_cash_credit"] += amt
                else:
                    if is_bank:
                        month_stats[mk]["bank_debit"] += amt
                    else:
                        month_stats[mk]["hard_cash_debit"] += amt
            
            # Calculate BF and Balances
            report_data: List[SpareLedgerReportRow] = []
            running_bf = 0.0
            
            # Sort months chronologically
            sorted_months = sorted(month_stats.keys())
            
            for mk in sorted_months:
                stats = month_stats[mk]
                
                m_bank_c = stats["bank_credit"]
                m_hard_c = stats["hard_cash_credit"]
                m_bank_d = stats["bank_debit"]
                m_hard_d = stats["hard_cash_debit"]
                
                total_in = m_bank_c + m_hard_c
                total_out = m_bank_d + m_hard_d
                
                month_balance = running_bf + (total_in - total_out)
                
                report_data.append(
                    SpareLedgerReportRow(
                        month_key=mk,
                        bf=running_bf,
                        bank_credit=m_bank_c,
                        hard_cash_credit=m_hard_c,
                        bank_debit=m_bank_d,
                        hard_cash_debit=m_hard_d,
                        balance=month_balance
                    )
                )
                # Next month's BF is this month's closing balance
                running_bf = month_balance
            
            # Display months in ascending order (oldest first)
            model.update_rows(report_data)

        except Exception as e:
            self._show_error("Report Error", str(e))
        finally:
            db.close()

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(dialog.reject)
        layout.addWidget(btn_box)

        dialog.exec()

    def _on_nav_clicked(self, checked: bool) -> None:
        button = self.sender()
        if not isinstance(button, NavigationButton):
            return
        self._select_page(button.page_key)

    def _on_group_header_clicked(self, checked: bool = False) -> None:
        """Handles group header clicks to implement accordion behavior."""
        header = self.sender()
        
        # If called manually (not via signal), header might be None or incorrect
        if not isinstance(header, GroupHeaderButton):
            # Check if we can find which header should be active from the current state
            # but usually manual calls pass the header or we can find it.
            # Let's adjust the logic to be more flexible.
            return
        
        self._expand_group(header)

    def _expand_group(self, clicked_header: GroupHeaderButton) -> None:
        """Expands a group and collapses others (Accordion logic)."""
        is_expanding = clicked_header.isChecked()
        target_group = clicked_header.group_name

        # Handle the clicked group
        clicked_header.setText(f"{'▼' if is_expanding else '▶'} {target_group}")
        for btn in self._group_buttons.get(target_group, []):
            btn.setVisible(is_expanding)

        # Collapse other groups if this one is expanding
        if is_expanding:
            for group_name, header in self._group_headers.items():
                if group_name != target_group and header.isChecked():
                    header.setChecked(False)
                    header.setText(f"▶ {group_name}")
                    for btn in self._group_buttons.get(group_name, []):
                        btn.setVisible(False)

    def _select_page(self, key: str) -> None:
        widget = self._pages.get(key)
        if widget is None:
            return
        index = self.stack.indexOf(widget)
        if index != -1:
            self.stack.setCurrentIndex(index)
        for page_key, btn in self._nav_buttons.items():
            btn.setChecked(page_key == key)
        
        # Trigger refresh if page has a refresh method
        if key == "dashboard":
            self._refresh_dashboard()
        elif key == "reports":
            self._reload_sales()
        elif key == "inventory":
            self._reload_inventory()
        elif key == "customers":
            self._reload_customers()
        elif key == "dealers":
            self._reload_dealers()
        elif key == "prices":
            self._reload_prices()
        elif key == "spare_ledger":
            self._reload_spare_ledger()
        elif key == "invoice":
            self._update_fbr_submitted_counter()
            self._generate_invoice_number()

    def _reload_sales(self) -> None:
        search = self.sales_search_input.text().strip() if hasattr(self, "sales_search_input") else ""
        status = self.sales_status_combo.currentText() if hasattr(self, "sales_status_combo") else "All"
        if status == "All Statuses":
            status = "All"
        period = self.sales_period_combo.currentText() if hasattr(self, "sales_period_combo") else "All Time"

        flt = SalesFilter(
            search_text=search,
            status=status,
            period=period,
            payment_mode="All",
            limit=500,
        )

        db = SessionLocal()
        data: List[SalesRow] = []
        try:
            rows = report_service.get_sales(db, flt)
            
            # Update the total count label
            if hasattr(self, "report_total_count_label"):
                self.report_total_count_label.setText(f"Total Records: {len(rows)}")

            for inv in rows:
                if inv.is_fiscalized:
                    status = "Synced"
                elif inv.sync_status == "FAILED":
                    status = "Failed"
                else:
                    status = "Pending"

                buyer = inv.customer.name if getattr(inv, "customer", None) else "N/A"

                chassis_list: List[str] = []
                engine_list: List[str] = []
                for item in getattr(inv, "items", []) or []:
                    mc = getattr(item, "motorcycle", None)
                    if mc:
                        if mc.chassis_number:
                            chassis_list.append(mc.chassis_number)
                        if mc.engine_number:
                            engine_list.append(mc.engine_number)

                chassis_str = ", ".join(chassis_list)
                engine_str = ", ".join(engine_list)

                data.append(
                    SalesRow(
                        date_value=inv.datetime,
                        invoice_number=inv.invoice_number or "",
                        buyer=buyer,
                        chassis=chassis_str,
                        engine=engine_str,
                        total=float(inv.total_amount or 0),
                        status=status,
                    )
                )
        finally:
            db.close()

        self.sales_table_model.update_rows(data)

    def _reload_invoice_list(self) -> None:
        search = self.invoice_search_input.text().strip() if hasattr(self, "invoice_search_input") else ""

        db = SessionLocal()
        data: List[InvoiceRow] = []
        try:
            query = db.query(Invoice).join(Customer, isouter=True).order_by(Invoice.datetime.desc())
            if search:
                value = f"%{search}%"
                query = query.filter(
                    Invoice.invoice_number.ilike(value)
                    | Customer.name.ilike(value)
                    | Customer.cnic.ilike(value)
                )

            rows = query.limit(500).all()

            for inv in rows:
                if inv.is_fiscalized:
                    status_text = "Synced"
                elif inv.sync_status == "FAILED":
                    status_text = "Failed"
                else:
                    status_text = "Pending"

                buyer = inv.customer.name if getattr(inv, "customer", None) else "N/A"

                data.append(
                    InvoiceRow(
                        date_value=inv.datetime,
                        invoice_number=inv.invoice_number or "",
                        buyer=buyer,
                        total=float(inv.total_amount or 0),
                        payment_mode=inv.payment_mode or "",
                        status=status_text,
                    )
                )
        finally:
            db.close()

        self.invoice_table_model.update_rows(data)

    def _reload_inventory(self) -> None:
        search = self.inventory_search_input.text().strip() if hasattr(self, "inventory_search_input") else ""
        status = self.inventory_status_combo.currentText() if hasattr(self, "inventory_status_combo") else "All"
        if status == "All Statuses":
            status = "All"

        db = SessionLocal()
        data: List[InventoryRow] = []
        try:
            query = db.query(Motorcycle).outerjoin(ProductModel)

            if search:
                value = f"%{search}%"
                query = query.filter(
                    Motorcycle.chassis_number.ilike(value)
                    | Motorcycle.engine_number.ilike(value)
                    | ProductModel.model_name.ilike(value)
                )

            if status != "All":
                query = query.filter(Motorcycle.status == status)

            rows = query.limit(500).all()

            for bike in rows:
                model_name = bike.product_model.model_name if getattr(bike, "product_model", None) else ""
                data.append(
                    InventoryRow(
                        chassis=bike.chassis_number or "",
                        engine=bike.engine_number or "",
                        model=model_name,
                        color=bike.color or "",
                        status=bike.status or "",
                    )
                )
        except Exception as e:
            logger.error(f"Error reloading inventory: {e}")
        finally:
            db.close()

        self.inventory_table_model.update_rows(data)

    def _on_inventory_row_double_clicked(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        self._on_edit_inventory_clicked()

    def _check_motorcycle_fbr_status(self, chassis_number: str) -> bool:
        """Returns True if the motorcycle has been uploaded to FBR."""
        db = SessionLocal()
        try:
            from app.db.models import InvoiceItem, Invoice
            # A motorcycle is considered "uploaded" if it's linked to an invoice that has an FBR Invoice Number
            uploaded = db.query(Invoice).join(InvoiceItem).join(Motorcycle).filter(
                Motorcycle.chassis_number == chassis_number,
                Invoice.fbr_invoice_number != None
            ).first()
            return uploaded is not None
        except Exception as e:
            logger.error(f"Error checking FBR status for chassis {chassis_number}: {e}")
            return False
        finally:
            db.close()

    def _on_edit_inventory_clicked(self) -> None:
        selection = self.inventory_table_view.selectionModel().selectedRows()
        if not selection:
            QMessageBox.warning(self, "Selection Required", "Please select a record to edit.")
            return
        
        row_index = selection[0].row()
        row_data = self.inventory_table_model._rows[row_index]

        # FBR Upload Check
        if self._check_motorcycle_fbr_status(row_data.chassis):
            QMessageBox.critical(
                self, 
                "Modification Prohibited", 
                f"Motorcycle with chassis {row_data.chassis} has already been uploaded to FBR.\n"
                "Records synced with FBR cannot be modified or updated for compliance reasons."
            )
            return

        self._open_edit_inventory_dialog(row_data)

    def _on_delete_inventory_clicked(self) -> None:
        selection = self.inventory_table_view.selectionModel().selectedRows()
        if not selection:
            QMessageBox.warning(self, "Selection Required", "Please select a record to delete.")
            return
            
        row_index = selection[0].row()
        row_data = self.inventory_table_model._rows[row_index]

        # FBR Upload Check
        if self._check_motorcycle_fbr_status(row_data.chassis):
            QMessageBox.critical(
                self, 
                "Deletion Prohibited", 
                f"Motorcycle with chassis {row_data.chassis} has already been uploaded to FBR.\n"
                "Records synced with FBR cannot be deleted for compliance and audit trail reasons."
            )
            return
        
        reply = QMessageBox.question(
            self, 
            "Confirm Delete", 
            f"Are you sure you want to delete motorcycle with chassis: {row_data.chassis}?\nThis action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            db = SessionLocal()
            try:
                bike = db.query(Motorcycle).filter(Motorcycle.chassis_number == row_data.chassis).first()
                if bike:
                    db.delete(bike)
                    db.commit()
                    QMessageBox.information(self, "Deleted", "Record has been deleted successfully.")
                    self._reload_inventory()
                else:
                    QMessageBox.warning(self, "Error", "Record not found in database.")
            except Exception as e:
                db.rollback()
                logger.error(f"Error deleting inventory: {e}")
                QMessageBox.critical(self, "System Error", f"Failed to delete record: {e}")
            finally:
                db.close()

    def _open_edit_inventory_dialog(self, row_data: InventoryRow) -> None:
        db = SessionLocal()
        try:
            bike = db.query(Motorcycle).filter(Motorcycle.chassis_number == row_data.chassis).first()
            if not bike:
                QMessageBox.warning(self, "Error", "Could not find record in database.")
                return

            dialog = QDialog(self)
            dialog.setWindowTitle(f"Edit Inventory - {bike.chassis_number}")
            dialog.setMinimumSize(450, 500)
            dialog.setStyleSheet("""
                QDialog { background-color: #f8f9fa; }
                QLabel { font-weight: bold; color: #2c3e50; }
                QLineEdit, QComboBox { padding: 8px; border: 1px solid #ced4da; border-radius: 4px; }
            """)

            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(30, 30, 30, 30)
            layout.setSpacing(15)

            form_grid = QGridLayout()
            form_grid.setSpacing(10)

            # Chassis (Read-only as it's the primary key/unique identifier here)
            form_grid.addWidget(QLabel("Chassis Number:"), 0, 0)
            chassis_input = QLineEdit(bike.chassis_number)
            chassis_input.setReadOnly(True)
            chassis_input.setStyleSheet("background-color: #e9ecef;")
            form_grid.addWidget(chassis_input, 0, 1)

            # Engine
            form_grid.addWidget(QLabel("Engine Number:"), 1, 0)
            engine_input = QLineEdit(bike.engine_number)
            form_grid.addWidget(engine_input, 1, 1)

            # Color
            form_grid.addWidget(QLabel("Color:"), 2, 0)
            color_input = QLineEdit(bike.color)
            form_grid.addWidget(color_input, 2, 1)

            # Status
            form_grid.addWidget(QLabel("Status:"), 3, 0)
            status_combo = QComboBox()
            status_combo.addItems(["IN_STOCK", "SOLD"])
            status_combo.setCurrentText(bike.status)
            form_grid.addWidget(status_combo, 3, 1)

            layout.addLayout(form_grid)
            layout.addStretch(1)

            # Buttons
            btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
            btn_box.accepted.connect(dialog.accept)
            btn_box.rejected.connect(dialog.reject)
            layout.addWidget(btn_box)

            if dialog.exec() == QDialog.DialogCode.Accepted:
                bike.engine_number = engine_input.text().strip()
                bike.color = color_input.text().strip()
                bike.status = status_combo.currentText()
                
                db.commit()
                QMessageBox.information(self, "Updated", "Record has been updated successfully.")
                self._reload_inventory()
                
        except Exception as e:
            db.rollback()
            logger.error(f"Error updating inventory: {e}")
            QMessageBox.critical(self, "Error", f"Failed to update record: {e}")
        finally:
            db.close()

    def _check_customer_fbr_status(self, cnic: str) -> bool:
        """Returns True if the customer has an invoice synced with FBR."""
        if not cnic:
            return False
        db = SessionLocal()
        try:
            # Check if customer has any invoice with an FBR Invoice Number
            uploaded = db.query(Invoice).join(Customer).filter(
                Customer.cnic == cnic,
                Invoice.fbr_invoice_number != None
            ).first()
            return uploaded is not None
        except Exception as e:
            logger.error(f"Error checking customer FBR status for CNIC {cnic}: {e}")
            return False
        finally:
            db.close()

    def _on_customer_row_double_clicked(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        self._on_edit_customer_clicked()

    def _on_edit_customer_clicked(self) -> None:
        selection = self.customers_table_view.selectionModel().selectedRows()
        if not selection:
            QMessageBox.warning(self, "Selection Required", "Please select a customer to edit.")
            return
            
        row_index = selection[0].row()
        row_data = self.customers_table_model._rows[row_index]
        self._open_edit_customer_dialog(row_data)

    def _on_delete_customer_clicked(self) -> None:
        selection = self.customers_table_view.selectionModel().selectedRows()
        if not selection:
            QMessageBox.warning(self, "Selection Required", "Please select a customer to delete.")
            return
            
        row_index = selection[0].row()
        row_data = self.customers_table_model._rows[row_index]
        
        # Check FBR Status for Deletion
        if self._check_customer_fbr_status(row_data.cnic):
            QMessageBox.critical(
                self, 
                "Deletion Prohibited", 
                f"Customer {row_data.name} (CNIC: {row_data.cnic}) has records already uploaded to FBR.\n"
                "This record cannot be deleted for compliance reasons."
            )
            return
            
        reply = QMessageBox.question(
            self, 
            "Confirm Delete", 
            f"Are you sure you want to delete customer: {row_data.name}?\nThis action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            db = SessionLocal()
            try:
                cust = db.query(Customer).filter(Customer.cnic == row_data.cnic).first()
                if cust:
                    db.delete(cust)
                    db.commit()
                    QMessageBox.information(self, "Deleted", "Customer record has been deleted.")
                    self._reload_customers()
                else:
                    QMessageBox.warning(self, "Error", "Customer record not found.")
            except Exception as e:
                db.rollback()
                logger.error(f"Error deleting customer: {e}")
                QMessageBox.critical(self, "Error", f"Failed to delete customer: {e}")
            finally:
                db.close()

    def _open_edit_customer_dialog(self, row_data: CustomerRow) -> None:
        db = SessionLocal()
        try:
            cust = db.query(Customer).filter(Customer.cnic == row_data.cnic).first()
            if not cust:
                QMessageBox.warning(self, "Error", "Could not find customer in database.")
                return

            is_synced = self._check_customer_fbr_status(row_data.cnic)

            dialog = QDialog(self)
            dialog.setWindowTitle(f"Edit Customer - {cust.name}")
            dialog.setMinimumSize(500, 600)
            dialog.setStyleSheet("""
                QDialog { background-color: #f8f9fa; }
                QLabel { font-weight: bold; color: #2c3e50; }
                QLineEdit { padding: 8px; border: 1px solid #ced4da; border-radius: 4px; }
            """)

            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(30, 30, 30, 30)
            layout.setSpacing(15)

            if is_synced:
                banner = QLabel("⚠️ This customer is linked to FBR-synced invoices.\nKey identity fields (Name, Father Name, CNIC) are locked.")
                banner.setStyleSheet("background-color: #fff3cd; color: #856404; padding: 10px; border-radius: 4px; border: 1px solid #ffeeba;")
                banner.setWordWrap(True)
                layout.addWidget(banner)

            form_grid = QGridLayout()
            form_grid.setSpacing(12)

            # Event filter to handle Enter key navigation and prevent dialog submission
            class EnterKeyFilter(QObject):
                def __init__(self, next_field, parent_dialog):
                    super().__init__(parent_dialog)
                    self.next_field = next_field
                    self.parent_dialog = parent_dialog

                def eventFilter(self, obj, event):
                    if event.type() == QEvent.Type.KeyPress:
                        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                            if self.next_field:
                                self.next_field.setFocus()
                            else:
                                self.parent_dialog.accept()
                            return True
                    return super().eventFilter(obj, event)

            # Name
            form_grid.addWidget(QLabel("Full Name:"), 0, 0)
            name_input = QLineEdit(cust.name)
            if is_synced:
                name_input.setReadOnly(True)
                name_input.setStyleSheet("background-color: #e9ecef; color: #6c757d;")
            form_grid.addWidget(name_input, 0, 1)

            # Allow only alphabetics and spaces for name
            def format_name_input_edit():
                text = name_input.text()
                filtered = "".join(c for c in text if c.isalpha() or c.isspace())
                if filtered != text:
                    name_input.setText(filtered)
            name_input.textChanged.connect(format_name_input_edit)

            # Father Name
            form_grid.addWidget(QLabel("Father Name:"), 1, 0)
            father_input = QLineEdit(cust.father_name or "")
            if is_synced:
                father_input.setReadOnly(True)
                father_input.setStyleSheet("background-color: #e9ecef; color: #6c757d;")
            form_grid.addWidget(father_input, 1, 1)

            # Allow only alphabetics and spaces for father name
            def format_father_input_edit():
                text = father_input.text()
                filtered = "".join(c for c in text if c.isalpha() or c.isspace())
                if filtered != text:
                    father_input.setText(filtered)
            father_input.textChanged.connect(format_father_input_edit)

            # CNIC
            form_grid.addWidget(QLabel("CNIC / ID Card:"), 2, 0)
            cnic_input = QLineEdit(cust.cnic)
            if is_synced:
                cnic_input.setReadOnly(True)
                cnic_input.setStyleSheet("background-color: #e9ecef; color: #6c757d;")
            form_grid.addWidget(cnic_input, 2, 1)

            # Auto-format and check existence
            def format_cnic_edit():
                text = cnic_input.text()
                digits = "".join(c for c in text if c.isdigit())
                formatted = digits
                if len(digits) > 5:
                    formatted = digits[:5] + "-" + digits[5:]
                if len(digits) > 12:
                    formatted = formatted[:13] + "-" + formatted[13:]
                if len(formatted) > 15:
                    formatted = formatted[:15]
                if formatted != text:
                    cnic_input.setText(formatted)
                
                # Check for other customers with the same CNIC
                if len(formatted) == 15 and formatted != cust.cnic:
                    db_check = SessionLocal()
                    try:
                        existing = db_check.query(Customer).filter(Customer.cnic == formatted).first()
                        if existing:
                            from app.updater.toast_notification import ToastNotification
                            msg = f"Another {existing.type.lower()} named '{existing.name}' with this CNIC already exists."
                            toast = ToastNotification(
                                title="CNIC Conflict",
                                message=msg,
                                parent=self,
                                duration_ms=5000,
                                show_action=False,
                                bg_color="#e67e22",
                                position="top-right"
                            )
                            toast.show_notification()
                    finally:
                        db_check.close()
            
            cnic_input.textChanged.connect(format_cnic_edit)

            # Phone
            form_grid.addWidget(QLabel("Phone Number:"), 3, 0)
            phone_input = QLineEdit(cust.phone or "")
            phone_input.setPlaceholderText("03021234567")
            form_grid.addWidget(phone_input, 3, 1)

            # Auto-format Phone Number as user types
            def format_phone_input_edit():
                text = phone_input.text()
                # Allow only digits and limit to 11
                digits = "".join(c for c in text if c.isdigit())
                if len(digits) > 11:
                    digits = digits[:11]
                if digits != text:
                    phone_input.setText(digits)

            phone_input.textChanged.connect(format_phone_input_edit)

            # Address
            form_grid.addWidget(QLabel("Address:"), 4, 0)
            address_input = QLineEdit(cust.address or "")
            form_grid.addWidget(address_input, 4, 1)

            # NTN
            form_grid.addWidget(QLabel("NTN:"), 5, 0)
            ntn_input = QLineEdit(cust.ntn or "")
            form_grid.addWidget(ntn_input, 5, 1)

            # Install event filters for sequential navigation
            name_input.installEventFilter(EnterKeyFilter(father_input, dialog))
            father_input.installEventFilter(EnterKeyFilter(cnic_input, dialog))
            cnic_input.installEventFilter(EnterKeyFilter(phone_input, dialog))
            phone_input.installEventFilter(EnterKeyFilter(address_input, dialog))
            address_input.installEventFilter(EnterKeyFilter(ntn_input, dialog))
            ntn_input.installEventFilter(EnterKeyFilter(None, dialog))

            layout.addLayout(form_grid)
            layout.addStretch(1)

            btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
            # Disable auto-default to prevent Enter key from triggering Save prematurely
            save_btn = btn_box.button(QDialogButtonBox.StandardButton.Save)
            if save_btn:
                save_btn.setAutoDefault(False)
                save_btn.setDefault(False)
            
            cancel_btn = btn_box.button(QDialogButtonBox.StandardButton.Cancel)
            if cancel_btn:
                cancel_btn.setAutoDefault(False)

            btn_box.accepted.connect(dialog.accept)
            btn_box.rejected.connect(dialog.reject)
            layout.addWidget(btn_box)

            if dialog.exec() == QDialog.DialogCode.Accepted:
                if not is_synced:
                    cust.name = name_input.text().strip()
                    cust.father_name = father_input.text().strip()
                    cust.cnic = cnic_input.text().strip()
                
                cust.phone = phone_input.text().strip()
                cust.address = address_input.text().strip()
                cust.ntn = ntn_input.text().strip()
                
                db.commit()
                QMessageBox.information(self, "Updated", "Customer record has been updated.")
                self._reload_customers()

        except Exception as e:
            db.rollback()
            logger.error(f"Error updating customer: {e}")
            QMessageBox.critical(self, "Error", f"Failed to update customer: {e}")
        finally:
            db.close()

    def _reload_customers(self) -> None:
        search = self.customers_search_input.text().strip() if hasattr(self, "customers_search_input") else ""

        db = SessionLocal()
        data: List[CustomerRow] = []
        try:
            query = db.query(Customer)
            if search:
                value = f"%{search}%"
                query = query.filter(
                    Customer.name.ilike(value)
                    | Customer.cnic.ilike(value)
                    | Customer.phone.ilike(value)
                )

            rows = query.limit(500).all()

            for c in rows:
                data.append(
                    CustomerRow(
                        name=c.name or "",
                        father_name=c.father_name or "",
                        cnic=c.cnic or "",
                        phone=c.phone or "",
                        address=c.address or "",
                        ntn=c.ntn or "",
                    )
                )
        finally:
            db.close()

        self.customers_table_model.update_rows(data)

    def _reload_dealers(self) -> None:
        search = self.dealers_search_input.text().strip() if hasattr(self, "dealers_search_input") else ""

        db = SessionLocal()
        data: List[DealerRow] = []
        try:
            query = db.query(Customer).filter(Customer.type == CustomerType.DEALER.value)
            if search:
                value = f"%{search}%"
                query = query.filter(
                    Customer.business_name.ilike(value)
                    | Customer.name.ilike(value)
                    | Customer.cnic.ilike(value)
                    | Customer.phone.ilike(value)
                )

            rows = query.limit(500).all()

            for c in rows:
                data.append(
                    DealerRow(
                        business_name=c.business_name or "",
                        contact_name=c.name or "",
                        cnic=c.cnic or "",
                        phone=c.phone or "",
                        address=c.address or "",
                        ntn=c.ntn or "",
                    )
                )
        finally:
            db.close()

        self.dealers_table_model.update_rows(data)

    def _on_dealer_row_double_clicked(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        self._on_edit_dealer_clicked()

    def _on_add_dealer_clicked(self) -> None:
        self._open_add_dealer_dialog()
        self._reload_dealers()

    def _open_add_dealer_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Add New Dealer")
        dialog.setMinimumSize(500, 600)
        dialog.setStyleSheet("""
            QDialog { background-color: #f8f9fa; }
            QLabel { font-weight: bold; color: #2c3e50; }
            QLineEdit { 
                padding: 8px; 
                border: 1px solid #ced4da; 
                border-radius: 4px; 
                background-color: white;
            }
            QLineEdit:focus {
                border: 2px solid #3498db;
                background-color: #f7fbfe;
            }
        """)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)

        form_grid = QGridLayout()
        form_grid.setSpacing(12)

        # Event filter to handle Enter key navigation and prevent dialog submission
        class EnterKeyFilter(QObject):
            def __init__(self, current, next_field, parent_dialog):
                super().__init__(parent_dialog)
                self.current = current
                self.next_field = next_field
                self.parent_dialog = parent_dialog

            def eventFilter(self, obj, event):
                if event.type() == QEvent.Type.KeyPress:
                    if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                        if self.next_field:
                            self.next_field.setFocus()
                        else:
                            self.parent_dialog.accept()
                        return True
                return super().eventFilter(obj, event)

        # Business Name
        form_grid.addWidget(QLabel("Business Name:"), 0, 0)
        business_input = QLineEdit()
        business_input.setPlaceholderText("Enter registered business name")
        form_grid.addWidget(business_input, 0, 1)

        # Contact Name
        form_grid.addWidget(QLabel("Contact Name:"), 1, 0)
        name_input = QLineEdit()
        name_input.setPlaceholderText("Enter person's full name")
        form_grid.addWidget(name_input, 1, 1)

        # Allow only alphabetics and spaces for name
        def format_name_input():
            text = name_input.text()
            filtered = "".join(c for c in text if c.isalpha() or c.isspace())
            if filtered != text:
                name_input.setText(filtered)
        name_input.textChanged.connect(format_name_input)

        # Father Name
        form_grid.addWidget(QLabel("Father Name:"), 2, 0)
        father_input = QLineEdit()
        father_input.setPlaceholderText("Enter father's name")
        form_grid.addWidget(father_input, 2, 1)

        # Allow only alphabetics and spaces for father name
        def format_father_input():
            text = father_input.text()
            filtered = "".join(c for c in text if c.isalpha() or c.isspace())
            if filtered != text:
                father_input.setText(filtered)
        father_input.textChanged.connect(format_father_input)

        # CNIC
        form_grid.addWidget(QLabel("CNIC / ID Card:"), 3, 0)
        cnic_input = QLineEdit()
        cnic_input.setPlaceholderText("XXXXX-XXXXXXX-X")
        form_grid.addWidget(cnic_input, 3, 1)
        
        # Auto-format CNIC as user types
        def format_cnic_input():
            text = cnic_input.text()
            digits = "".join(c for c in text if c.isdigit())
            formatted = digits
            if len(digits) > 5:
                formatted = digits[:5] + "-" + digits[5:]
            if len(digits) > 12:
                formatted = formatted[:13] + "-" + formatted[13:]
            if len(formatted) > 15:
                formatted = formatted[:15]
            if formatted != text:
                cnic_input.setText(formatted)
            
            # Real-time CNIC validation
            if len(formatted) == 15:
                check_cnic_exists(formatted)

        def check_cnic_exists(cnic: str):
            db = SessionLocal()
            try:
                existing = db.query(Customer).filter(Customer.cnic == cnic).first()
                if existing:
                    from app.updater.toast_notification import ToastNotification
                    msg = f"A {existing.type.lower()} named '{existing.name}' with this CNIC already exists."
                    toast = ToastNotification(
                        title="CNIC Already Exists",
                        message=msg,
                        parent=self,
                        duration_ms=5000,
                        show_action=False,
                        bg_color="#e67e22", # Warning Orange
                        position="top-right"
                    )
                    toast.show_notification()
            finally:
                db.close()

        cnic_input.textChanged.connect(format_cnic_input)

        # Phone
        form_grid.addWidget(QLabel("Phone Number:"), 4, 0)
        phone_input = QLineEdit()
        phone_input.setPlaceholderText("03021234567")
        form_grid.addWidget(phone_input, 4, 1)

        # Auto-format Phone Number as user types
        def format_phone_input():
            text = phone_input.text()
            # Allow only digits and limit to 11
            digits = "".join(c for c in text if c.isdigit())
            if len(digits) > 11:
                digits = digits[:11]
            if digits != text:
                phone_input.setText(digits)

        phone_input.textChanged.connect(format_phone_input)

        # Address
        form_grid.addWidget(QLabel("Address:"), 5, 0)
        address_input = QLineEdit()
        address_input.setPlaceholderText("Enter full business address")
        form_grid.addWidget(address_input, 5, 1)

        # NTN
        form_grid.addWidget(QLabel("NTN:"), 6, 0)
        ntn_input = QLineEdit()
        ntn_input.setPlaceholderText("Enter 7-digit NTN (e.g. 1234567-8)")
        form_grid.addWidget(ntn_input, 6, 1)

        # Install event filters for sequential navigation
        business_input.installEventFilter(EnterKeyFilter(business_input, name_input, dialog))
        name_input.installEventFilter(EnterKeyFilter(name_input, father_input, dialog))
        father_input.installEventFilter(EnterKeyFilter(father_input, cnic_input, dialog))
        cnic_input.installEventFilter(EnterKeyFilter(cnic_input, phone_input, dialog))
        phone_input.installEventFilter(EnterKeyFilter(phone_input, address_input, dialog))
        address_input.installEventFilter(EnterKeyFilter(address_input, ntn_input, dialog))
        ntn_input.installEventFilter(EnterKeyFilter(ntn_input, None, dialog))

        layout.addLayout(form_grid)
        layout.addStretch(1)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        # Disable auto-default to prevent Enter key from triggering Save prematurely
        save_btn = btn_box.button(QDialogButtonBox.StandardButton.Save)
        if save_btn:
            save_btn.setAutoDefault(False)
            save_btn.setDefault(False)
        
        cancel_btn = btn_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_btn:
            cancel_btn.setAutoDefault(False)
            
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)
        layout.addWidget(btn_box)
        
        # Initial Focus
        business_input.setFocus()

        if dialog.exec() == QDialog.DialogCode.Accepted:
            biz_name = business_input.text().strip()
            name = name_input.text().strip()
            father = father_input.text().strip()
            cnic = cnic_input.text().strip()
            phone = phone_input.text().strip()
            address = address_input.text().strip()
            ntn = ntn_input.text().strip()

            if not biz_name or not name or not cnic:
                QMessageBox.warning(self, "Validation Error", "Business Name, Contact Name, and CNIC are required.")
                return

            db = SessionLocal()
            try:
                # Check for existing CNIC
                existing = db.query(Customer).filter(Customer.cnic == cnic).first()
                if existing:
                    QMessageBox.critical(self, "Duplicate Error", f"A dealer or customer with CNIC {cnic} already exists.")
                    return

                new_dealer = Customer(
                    business_name=biz_name.upper(),
                    name=name.upper(),
                    father_name=father.upper(),
                    cnic=cnic,
                    phone=phone,
                    address=address.upper(),
                    ntn=ntn.upper(),
                    type=CustomerType.DEALER.value
                )
                db.add(new_dealer)
                db.commit()
                QMessageBox.information(self, "Success", "New dealer has been added successfully.")
            except Exception as e:
                db.rollback()
                logger.error(f"Error adding dealer: {e}")
                QMessageBox.critical(self, "Error", f"Failed to add dealer: {e}")
            finally:
                db.close()

    def _on_edit_dealer_clicked(self) -> None:
        selection = self.dealers_table_view.selectionModel().selectedRows()
        if not selection:
            QMessageBox.warning(self, "Selection Required", "Please select a dealer to edit.")
            return
            
        row_index = selection[0].row()
        row_data = self.dealers_table_model._rows[row_index]
        
        # We reuse the customer edit dialog since dealers are customers
        # but we need to pass a CustomerRow compatible object
        temp_row = CustomerRow(
            name=row_data.contact_name,
            father_name="", # We don't have it in DealerRow but dialog will fetch from DB
            cnic=row_data.cnic,
            phone=row_data.phone,
            address=row_data.address,
            ntn=row_data.ntn
        )
        self._open_edit_customer_dialog(temp_row)
        self._reload_dealers() # Refresh after edit

    def _on_delete_dealer_clicked(self) -> None:
        selection = self.dealers_table_view.selectionModel().selectedRows()
        if not selection:
            QMessageBox.warning(self, "Selection Required", "Please select a dealer to delete.")
            return
            
        row_index = selection[0].row()
        row_data = self.dealers_table_model._rows[row_index]
        
        # Use same logic as customer deletion
        if self._check_customer_fbr_status(row_data.cnic):
            QMessageBox.critical(
                self, 
                "Deletion Prohibited", 
                f"Dealer {row_data.business_name} has records already uploaded to FBR.\n"
                "This record cannot be deleted for compliance reasons."
            )
            return
            
        reply = QMessageBox.question(
            self, 
            "Confirm Delete", 
            f"Are you sure you want to delete dealer: {row_data.business_name}?\nThis action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            db = SessionLocal()
            try:
                cust = db.query(Customer).filter(Customer.cnic == row_data.cnic).first()
                if cust:
                    db.delete(cust)
                    db.commit()
                    QMessageBox.information(self, "Deleted", "Dealer record has been deleted.")
                    self._reload_dealers()
                else:
                    QMessageBox.warning(self, "Error", "Dealer record not found.")
            except Exception as e:
                db.rollback()
                logger.error(f"Error deleting dealer: {e}")
                QMessageBox.critical(self, "Error", f"Failed to delete dealer: {e}")
            finally:
                db.close()

    def _reload_spare_ledger(self) -> None:
        search = self.ledger_search_input.text().strip() if hasattr(self, "ledger_search_input") else ""
        txn_type_filter = self.ledger_type_combo.currentText() if hasattr(self, "ledger_type_combo") else "All"
        month_filter = self.ledger_month_combo.currentText() if hasattr(self, "ledger_month_combo") else "All Months"

        db = SessionLocal()
        data: List[SpareLedgerRow] = []
        try:
            # We fetch all rows chronologically to maintain correct running balance
            query = db.query(SpareLedgerTransaction).order_by(SpareLedgerTransaction.timestamp.asc())
            all_rows = query.all()
            
            # Extract unique month keys for the dropdown (sorted descending)
            months = sorted(list(set(tx.month_key for tx in all_rows if tx.month_key)), reverse=True)
            if hasattr(self, "ledger_month_combo"):
                current_month = self.ledger_month_combo.currentText()
                # Block signals while updating items to avoid recursive reloads
                self.ledger_month_combo.blockSignals(True)
                # Only repopulate if the month list has changed (excluding "All Months")
                existing_months = [self.ledger_month_combo.itemText(i) for i in range(1, self.ledger_month_combo.count())]
                if months != existing_months:
                    self.ledger_month_combo.clear()
                    self.ledger_month_combo.addItem("All Months")
                    self.ledger_month_combo.addItems(months)
                    # Try to restore the previously selected month
                    idx = self.ledger_month_combo.findText(current_month)
                    if idx >= 0:
                        self.ledger_month_combo.setCurrentIndex(idx)
                    else:
                        self.ledger_month_combo.setCurrentIndex(0)
                self.ledger_month_combo.blockSignals(False)

            running_balance = 0.0
            total_credit = 0.0
            total_debit = 0.0
            
            # Brought Forward (B/F) tracking
            bf_balance = 0.0
            
            temp_data: List[SpareLedgerRow] = []
            for tx in all_rows:
                amt = float(tx.amount or 0)
                credit = amt if tx.trans_type == "CREDIT" else 0.0
                debit = amt if tx.trans_type == "DEBIT" else 0.0
                
                # If we are filtering by month, anything BEFORE that month contributes to B/F
                if month_filter != "All Months" and tx.month_key < month_filter:
                    bf_balance += (credit - debit)
                
                total_credit += credit
                total_debit += debit
                running_balance += (credit - debit)
                
                # Check if this row matches all filters
                matches_search = not search or (
                    (tx.reference_number and search.lower() in tx.reference_number.lower()) or
                    (tx.description and search.lower() in tx.description.lower())
                )
                matches_type = txn_type_filter == "All" or tx.trans_type == txn_type_filter
                matches_month = month_filter == "All Months" or tx.month_key == month_filter
                
                if matches_search and matches_type and matches_month:
                    temp_data.append(
                        SpareLedgerRow(
                            id=tx.id,
                            timestamp=tx.timestamp,
                            credit=credit,
                            debit=debit,
                            balance=running_balance,
                            reference=tx.reference_number or "",
                            description=tx.description or "",
                            month_key=tx.month_key or "",
                            cash_type=tx.cash_type or "HARD_CASH",
                        )
                    )
            
            # Add a "Brought Forward" row if a month is selected
            if month_filter != "All Months" and not search and txn_type_filter == "All":
                # Create a virtual row for B/F
                bf_row = SpareLedgerRow(
                    id=-1, # Virtual ID
                    timestamp=None, # Will show as OPENING
                    credit=bf_balance if bf_balance > 0 else 0.0,
                    debit=abs(bf_balance) if bf_balance < 0 else 0.0,
                    balance=bf_balance,
                    reference="B/F",
                    description=f"Balance Brought Forward from previous months",
                    month_key=month_filter
                )
                # For Ascending order (oldest first), B/F must be the first row (index 0)
                temp_data.insert(0, bf_row)

            # Use Ascending order (oldest first) as requested
            data = temp_data
            
            # Update Stat Cards based on ALL data or just the filtered view?
            if month_filter != "All Months":
                filtered_credit = sum(row.credit for row in data if row.reference != "B/F")
                filtered_debit = sum(row.debit for row in data if row.reference != "B/F")
                if hasattr(self, "ledger_total_credit_card"):
                    # We can show B/F in the credit/debit or just focus on current month's activity
                    self.ledger_total_credit_card.value_label.setText(f"{filtered_credit:,.2f}")
                    self.ledger_total_debit_card.value_label.setText(f"{filtered_debit:,.2f}")
            else:
                if hasattr(self, "ledger_total_credit_card"):
                    self.ledger_total_credit_card.value_label.setText(f"{total_credit:,.2f}")
                    self.ledger_total_debit_card.value_label.setText(f"{total_debit:,.2f}")
            
            if hasattr(self, "ledger_balance_card"):
                self.ledger_balance_card.value_label.setText(f"{running_balance:,.2f}")

        finally:
            db.close()

        self.ledger_table_model.update_rows(data)

    def closeEvent(self, event) -> None:
        """Ensure background services are stopped when the application closes."""
        try:
            logger.info("Application shutting down. Stopping background services...")
            form_capture_service.stop_capture_session()
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
        event.accept()


class SalesRow:
    def __init__(
        self,
        date_value,
        invoice_number: str,
        buyer: str,
        chassis: str,
        engine: str,
        total: float,
        status: str,
    ) -> None:
        self.date_value = date_value
        self.invoice_number = invoice_number
        self.buyer = buyer
        self.chassis = chassis
        self.engine = engine
        self.total = total
        self.status = status


class InventoryRow:
    def __init__(
        self,
        chassis: str,
        engine: str,
        model: str,
        color: str,
        status: str,
    ) -> None:
        self.chassis = chassis
        self.engine = engine
        self.model = model
        self.color = color
        self.status = status


class CustomerRow:
    def __init__(
        self,
        name: str,
        father_name: str,
        cnic: str,
        phone: str,
        address: str,
        ntn: str,
    ) -> None:
        self.name = name
        self.father_name = father_name
        self.cnic = cnic
        self.phone = phone
        self.address = address
        self.ntn = ntn


class DealerRow:
    def __init__(
        self,
        business_name: str,
        contact_name: str,
        cnic: str,
        phone: str,
        address: str,
        ntn: str,
    ) -> None:
        self.business_name = business_name
        self.contact_name = contact_name
        self.cnic = cnic
        self.phone = phone
        self.address = address
        self.ntn = ntn


class SpareLedgerRow:
    def __init__(
        self,
        id: int,
        timestamp,
        credit: float,
        debit: float,
        balance: float,
        reference: str,
        description: str,
        month_key: str,
        cash_type: str = "HARD_CASH",
    ) -> None:
        self.id = id
        self.timestamp = timestamp
        self.credit = credit
        self.debit = debit
        self.balance = balance
        self.reference = reference
        self.description = description
        self.month_key = month_key
        self.cash_type = cash_type


class SpareLedgerReportRow:
    def __init__(
        self,
        month_key: str,
        bf: float,
        bank_credit: float,
        hard_cash_credit: float,
        bank_debit: float,
        hard_cash_debit: float,
        balance: float,
    ) -> None:
        self.month_key = month_key
        self.bf = bf
        self.bank_credit = bank_credit
        self.hard_cash_credit = hard_cash_credit
        self.bank_debit = bank_debit
        self.hard_cash_debit = hard_cash_debit
        self.balance = balance


class InvoiceRow:
    def __init__(
        self,
        date_value,
        invoice_number: str,
        buyer: str,
        total: float,
        payment_mode: str,
        status: str,
    ) -> None:
        self.date_value = date_value
        self.invoice_number = invoice_number
        self.buyer = buyer
        self.total = total
        self.payment_mode = payment_mode
        self.status = status


class SalesTableModel(QAbstractTableModel):
    headers = ["Date", "Invoice #", "Buyer", "Chassis", "Engine", "Total", "FBR Status"]

    def __init__(self) -> None:
        super().__init__()
        self._rows: List[SalesRow] = []

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        return len(self._rows)

    def columnCount(self, parent: QModelIndex | None = None) -> int:
        return len(self.headers)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return row.date_value.strftime("%Y-%m-%d %H:%M") if row.date_value else ""
            if col == 1:
                return row.invoice_number
            if col == 2:
                return row.buyer
            if col == 3:
                return row.chassis
            if col == 4:
                return row.engine
            if col == 5:
                return f"{row.total:,.2f}"
            if col == 6:
                return row.status
        
        if role == Qt.ItemDataRole.ForegroundRole:
            if col == 6:
                if row.status == "Synced":
                    return Qt.GlobalColor.darkGreen
                if row.status == "Failed":
                    return Qt.GlobalColor.red
                if row.status == "Pending":
                    return Qt.GlobalColor.darkYellow
                    
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col == 5: # Total column
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            if col in (0, 1, 6): # Center alignment for some columns
                return Qt.AlignmentFlag.AlignCenter
                
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self.headers):
                return self.headers[section]
        return super().headerData(section, orientation, role)

    def update_rows(self, rows: List[SalesRow]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()


class InventoryTableModel(QAbstractTableModel):
    headers = ["Chassis", "Engine", "Model", "Color", "Status"]

    def __init__(self) -> None:
        super().__init__()
        self._rows: List[InventoryRow] = []

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        return len(self._rows)

    def columnCount(self, parent: QModelIndex | None = None) -> int:
        return len(self.headers)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return row.chassis
            if col == 1:
                return row.engine
            if col == 2:
                return row.model
            if col == 3:
                return row.color
            if col == 4:
                return row.status
        
        if role == Qt.ItemDataRole.ForegroundRole:
            if col == 4: # Status column
                if row.status == "IN_STOCK":
                    return Qt.GlobalColor.darkGreen
                if row.status == "SOLD":
                    return Qt.GlobalColor.red
                    
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignCenter
                
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self.headers):
                return self.headers[section]
        return super().headerData(section, orientation, role)

    def update_rows(self, rows: List[InventoryRow]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()


class CustomersTableModel(QAbstractTableModel):
    headers = ["Name", "Father Name", "CNIC", "Phone", "Address", "NTN"]

    def __init__(self) -> None:
        super().__init__()
        self._rows: List[CustomerRow] = []

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        return len(self._rows)

    def columnCount(self, parent: QModelIndex | None = None) -> int:
        return len(self.headers)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return row.name
            if col == 1:
                return row.father_name
            if col == 2:
                return row.cnic
            if col == 3:
                return row.phone
            if col == 4:
                return row.address
            if col == 5:
                return row.ntn
        
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignCenter
            
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self.headers):
                return self.headers[section]
        return super().headerData(section, orientation, role)

    def update_rows(self, rows: List[CustomerRow]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()


class DealersTableModel(QAbstractTableModel):
    headers = ["Business", "Contact", "CNIC", "Phone", "Address", "NTN"]

    def __init__(self) -> None:
        super().__init__()
        self._rows: List[DealerRow] = []

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        return len(self._rows)

    def columnCount(self, parent: QModelIndex | None = None) -> int:
        return len(self.headers)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return row.business_name
            if col == 1:
                return row.contact_name
            if col == 2:
                return row.cnic
            if col == 3:
                return row.phone
            if col == 4:
                return row.address
            if col == 5:
                return row.ntn
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self.headers):
                return self.headers[section]
        return super().headerData(section, orientation, role)

    def update_rows(self, rows: List[DealerRow]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()


class PriceRow:
    def __init__(
        self,
        id: int,
        model: str,
        base_price: float,
        tax: float,
        levy: float,
        total: float,
        effective_date: dt.datetime,
    ) -> None:
        self.id = id
        self.model = model
        self.base_price = base_price
        self.tax = tax
        self.levy = levy
        self.total = total
        self.effective_date = effective_date


class PricesTableModel(QAbstractTableModel):
    headers = ["Model Name", "Base Price", "Sales Tax", "Further Tax", "Total Price", "Effective Date"]

    def __init__(self) -> None:
        super().__init__()
        self._rows: List[PriceRow] = []

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        return len(self._rows)

    def columnCount(self, parent: QModelIndex | None = None) -> int:
        return len(self.headers)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return row.model
            if col == 1:
                return f"{row.base_price:,.2f}"
            if col == 2:
                return f"{row.tax:,.2f}"
            if col == 3:
                return f"{row.levy:,.2f}"
            if col == 4:
                return f"{row.total:,.2f}"
            if col == 5:
                return row.effective_date.strftime("%Y-%m-%d") if row.effective_date else "N/A"
        
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col > 0:
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self.headers):
                return self.headers[section]
        return super().headerData(section, orientation, role)

    def update_rows(self, rows: List[PriceRow]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()


class SpareLedgerTableModel(QAbstractTableModel):
    headers = ["Date/Time", "Source", "Reference", "Description", "Credit (In)", "Debit (Out)", "Balance", "Month"]

    def __init__(self) -> None:
        super().__init__()
        self._rows: List[SpareLedgerRow] = []

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        return len(self._rows)

    def columnCount(self, parent: QModelIndex | None = None) -> int:
        return len(self.headers)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return row.timestamp.strftime("%Y-%m-%d %H:%M") if row.timestamp else "OPENING"
            if col == 1:
                return "Hard Cash" if row.cash_type == "HARD_CASH" else "Bank"
            if col == 2:
                return row.reference
            if col == 3:
                return row.description
            if col == 4:
                return f"{row.credit:,.2f}" if row.credit > 0 else ""
            if col == 5:
                return f"{row.debit:,.2f}" if row.debit > 0 else ""
            if col == 6:
                return f"{row.balance:,.2f}"
            if col == 7:
                return row.month_key
        
        if role == Qt.ItemDataRole.ForegroundRole:
            if col == 4 and row.credit > 0:
                return Qt.GlobalColor.darkGreen
            if col == 5 and row.debit > 0:
                return Qt.GlobalColor.red
                
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self.headers):
                return self.headers[section]
        return super().headerData(section, orientation, role)

    def update_rows(self, rows: List[SpareLedgerRow]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()


class SpareLedgerReportTableModel(QAbstractTableModel):
    headers = [
        "Date", "Previous Month Balance", 
        "Bank Credit", "Cash Credit", 
        "Bank Debit", "Cash Debit", 
        "Monthly Balance"
    ]

    def __init__(self) -> None:
        super().__init__()
        self._rows: List[SpareLedgerReportRow] = []

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        return len(self._rows)

    def columnCount(self, parent: QModelIndex | None = None) -> int:
        return len(self.headers)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                # Format month_key (YYYY-MM) to Date (05-MM-YY)
                try:
                    year, month = row.month_key.split("-")
                    return f"05-{month}-{year[2:]}"
                except:
                    return row.month_key
            if col == 1:
                return f"{row.bf:,.2f}"
            if col == 2:
                return f"{row.bank_credit:,.2f}"
            if col == 3:
                return f"{row.hard_cash_credit:,.2f}"
            if col == 4:
                return f"{row.bank_debit:,.2f}"
            if col == 5:
                return f"{row.hard_cash_debit:,.2f}"
            if col == 6:
                return f"{row.balance:,.2f}"
        
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col > 0:
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        
        if role == Qt.ItemDataRole.ForegroundRole:
            if col == 6: # Monthly Balance
                if row.balance < 0:
                    return Qt.GlobalColor.red
                elif row.balance > 0:
                    return Qt.GlobalColor.darkGreen
                
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self.headers):
                return self.headers[section]
        return super().headerData(section, orientation, role)

    def update_rows(self, rows: List[SpareLedgerReportRow]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()


class InvoiceTableModel(QAbstractTableModel):
    headers = ["Date", "Invoice #", "Buyer", "Total", "Payment", "Status"]

    def __init__(self) -> None:
        super().__init__()
        self._rows: List[InvoiceRow] = []

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        return len(self._rows)

    def columnCount(self, parent: QModelIndex | None = None) -> int:
        return len(self.headers)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0 and row.date_value is not None:
                return row.date_value.strftime("%Y-%m-%d %H:%M")
            if col == 1:
                return row.invoice_number
            if col == 2:
                return row.buyer
            if col == 3:
                return f"{row.total:,.2f}"
            if col == 4:
                return row.payment_mode
            if col == 5:
                return row.status
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self.headers):
                return self.headers[section]
        return super().headerData(section, orientation, role)

    def update_rows(self, rows: List[InvoiceRow]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()


class CampaignsTableModel(QAbstractTableModel):
    headers = ["Date", "Campaign Name", "Status", "Sent", "Failed", "Total", "Error Message"]

    def __init__(self) -> None:
        super().__init__()
        self._rows: List[CampaignRow] = []

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        return len(self._rows)

    def columnCount(self, parent: QModelIndex | None = None) -> int:
        return len(self.headers)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return row.created_at.strftime("%Y-%m-%d %H:%M") if row.created_at else ""
            if col == 1:
                return row.name
            if col == 2:
                return row.status
            if col == 3:
                return str(row.sent)
            if col == 4:
                return str(row.failed)
            if col == 5:
                return str(row.total)
            if col == 6:
                return row.error_message or ""
        
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col == 6:
                return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            return Qt.AlignmentFlag.AlignCenter
            
        if role == Qt.ItemDataRole.ForegroundRole:
            if col == 2: # Status column
                if row.status == "COMPLETED":
                    return Qt.GlobalColor.darkGreen
                if row.status == "RUNNING":
                    return Qt.GlobalColor.blue
                if row.status == "FAILED":
                    return Qt.GlobalColor.red
            if col == 6: # Error Message column
                return Qt.GlobalColor.red
                    
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self.headers):
                return self.headers[section]
        return super().headerData(section, orientation, role)

    def update_rows(self, rows: List[CampaignRow]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()
