from __future__ import annotations

from typing import Dict, List, Callable
from dataclasses import dataclass

import io
import re
import requests
import qrcode
import base64
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
    QItemSelectionModel,
    QStringListModel, 
    QTimer, 
    QDate, 
    pyqtSignal, 
    QObject, 
    QEvent,
    QThread,
    QPoint
)
from PyQt6.QtGui import QPixmap, QKeySequence, QShortcut, QCursor
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

from sqlalchemy.orm import joinedload, Session

from app.core import config
from app.core.config import settings
from app.db.session import SessionLocal, close_all_db_connections
from app.utils.string_utils import to_uppercase_preserving
from app.db.models import (
    Motorcycle,
    ProductModel,
    Price,
    Customer,
    Invoice,
    InvoiceItem,
    SpareLedgerTransaction,
    CustomerType,
    CapturedData,
    AdvanceBooking,
)
from app.api.schemas import InvoiceCreate, InvoiceItemCreate
from app.services.invoice_service import invoice_service
from app.services.price_service import price_service
from app.services.settings_service import settings_service
from app.services.dealer_service import dealer_service
from app.services.customer_service import customer_service
from app.services.advance_booking_service import advance_booking_service
from app.services.form_capture_service import form_capture_service
from app.services.backup_service import backup_service
from app.services.print_service_v2 import print_service_v2
from app.qt_ui.dealer_search_dialog import DealerSearchDialog
from app.qt_ui.web_import_dialog import WebImportDialog
from app.qt_ui.settings_modals import (
    FBRSecurityDialog, 
    BusinessPreferencesDialog, 
    DatabaseSettingsDialog, 
    BackupSettingsDialog,
    AppUpdatesDialog,
    SMSConfigDialog,
    AddressShortcodeDialog,
    UrduFontDialog,
    FontCustomizationDialog,
    DMSSettingsDialog
)
from app.qt_ui.auto_scroll_manager import AutoScrollManager
from app.core.signals import booking_signals
from app.core.logger import logger
from app.core.version_manager import VersionManager
from app.updater.updater_manager import UpdaterManager
from app.qt_ui.whatsapp_campaign_widget import WhatsAppCampaignWidget
from app.qt_ui.dms_automation_page import DMSAutomationPage


@dataclass
class CampaignRow:
    id: int
    name: str
    status: str
    sent: int
    failed: int
    total: int
    created_at: dt.datetime
    channel: str = "SMS"
    error_message: str = ""


class BackupWorker(QObject):
    """Professional worker for background backup operations."""
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, output_format: str | None = None):
        super().__init__()
        self.output_format = output_format

    def run(self):
        try:
            logger.info("BackupWorker started manual backup process.")
            result = backup_service.create_backup(is_manual=True, output_format=self.output_format)
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


class PanScrollArea(QScrollArea):
    """
    Custom QScrollArea with professional Auto Scroll feature (like web browsers)
    Features:
    - Middle mouse button activates auto-scroll
    - Cursor changes to auto-scroll indicator
    - Scrolling speed depends on distance from activation point
    - Vertical and horizontal scrolling
    - Second click or key press deactivates
    """
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Initialize auto scroll manager
        self.auto_scroll = AutoScrollManager(self)
        # Install on self (since it's a QAbstractScrollArea, AutoScrollManager will handle the viewport)
        self.auto_scroll.install_on_widget(self)
        
    def __del__(self):
        """Cleanup auto scroll manager when scroll area is destroyed"""
        self.auto_scroll.uninstall_from_widget()


class ClearableDateEdit(QDateEdit):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._empty_date = QDate(1900, 1, 1)
        self._digit_buffer = ""
        self.setCalendarPopup(True)
        self.setDisplayFormat("dd-MM-yyyy")
        self.setDateRange(self._empty_date, QDate(2100, 12, 31))
        self.setSpecialValueText(" ")
        self.setDate(QDate.currentDate())
        le = self.lineEdit()
        if le:
            le.setClearButtonEnabled(True)
            le.setPlaceholderText("DD-MM-YYYY")
            le.textChanged.connect(self._on_text_changed)
        self.editingFinished.connect(self._normalize_date_text)

    def clear_date(self) -> None:
        self.setDate(self._empty_date)
        le = self.lineEdit()
        if le:
            le.setText("")
        self.setStyleSheet("")

    def is_empty(self) -> bool:
        return self.date() == self._empty_date

    def focusInEvent(self, event) -> None:
        self._reset_digit_buffer()
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self._reset_digit_buffer()
        super().focusOutEvent(event)

    def textFromDateTime(self, dt_value) -> str:
        try:
            if dt_value and dt_value.date() == self._empty_date:
                return ""
        except Exception:
            pass
        return super().textFromDateTime(dt_value)

    def _reset_digit_buffer(self) -> None:
        self._digit_buffer = ""

    def _render_digit_buffer(self) -> str:
        d = self._digit_buffer[0:2]
        m = self._digit_buffer[2:4]
        y = self._digit_buffer[4:8]
        if len(self._digit_buffer) <= 2:
            return d
        if len(self._digit_buffer) <= 4:
            return f"{d}-{m}"
        return f"{d}-{m}-{y}"

    def keyPressEvent(self, event) -> None:
        key = event.key()
        mods = event.modifiers()
        txt = event.text() or ""

        if txt.isdigit():
            if not self._digit_buffer:
                le = self.lineEdit()
                if le:
                    if le.hasSelectedText() or self.is_empty():
                        self.clear_date()
            if len(self._digit_buffer) < 8:
                self._digit_buffer += txt
            le = self.lineEdit()
            if le:
                le.blockSignals(True)
                le.setText(self._render_digit_buffer())
                le.setCursorPosition(len(le.text()))
                le.blockSignals(False)

            if len(self._digit_buffer) == 8:
                d = int(self._digit_buffer[0:2])
                m = int(self._digit_buffer[2:4])
                y = int(self._digit_buffer[4:8])
                parsed = QDate(y, m, d)
                if parsed.isValid():
                    self.setDate(parsed)
                    self.setStyleSheet("")
                else:
                    self.setStyleSheet("QDateEdit { border: 2px solid #e74c3c; background-color: #fff; }")
                self._reset_digit_buffer()
            return

        if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            if self._digit_buffer:
                self._digit_buffer = self._digit_buffer[:-1]
                le = self.lineEdit()
                if le:
                    le.blockSignals(True)
                    le.setText(self._render_digit_buffer())
                    le.setCursorPosition(len(le.text()))
                    le.blockSignals(False)
                if not self._digit_buffer:
                    self.setStyleSheet("")
                return
            le = self.lineEdit()
            if mods == Qt.KeyboardModifier.ControlModifier or (le and le.hasSelectedText()) or (le and not (le.text() or "").strip()):
                self.clear_date()
                return
        if mods == Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_T:
            self.setDate(QDate.currentDate())
            return
        if mods == Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_Y:
            self.setDate(QDate.currentDate().addDays(-1))
            return
        if key == Qt.Key.Key_F4:
            self.showPopup()
            return
        if mods == Qt.KeyboardModifier.AltModifier and key == Qt.Key.Key_Down:
            self.showPopup()
            return
        super().keyPressEvent(event)

    def _parse_user_date(self, raw: str) -> QDate | None:
        s = (raw or "").strip()
        if not s:
            return None

        for fmt in ("dd-MM-yyyy", "dd/MM/yyyy", "dd.MM.yyyy", "yyyy-MM-dd", "yyyy/MM/dd", "yyyy.MM.dd"):
            dt_parsed = QDate.fromString(s, fmt)
            if dt_parsed.isValid():
                return dt_parsed

        digits = "".join(ch for ch in s if ch.isdigit())
        if len(digits) == 8:
            y_first = int(digits[0:4])
            if 1900 <= y_first <= 2100:
                y = y_first
                m = int(digits[4:6])
                d = int(digits[6:8])
                dt_parsed = QDate(y, m, d)
                if dt_parsed.isValid():
                    return dt_parsed
            d = int(digits[0:2])
            m = int(digits[2:4])
            y = int(digits[4:8])
            dt_parsed = QDate(y, m, d)
            if dt_parsed.isValid():
                return dt_parsed

        parts = re.split(r"[^0-9]", s)
        parts = [p for p in parts if p]
        if len(parts) == 3 and all(p.isdigit() for p in parts):
            a = int(parts[0])
            b = int(parts[1])
            c = int(parts[2])

            if len(parts[0]) == 4:
                y, m, d = a, b, c
                dt_parsed = QDate(y, m, d)
                if dt_parsed.isValid():
                    return dt_parsed

            d, m, y = a, b, c
            if a <= 12 and b <= 12:
                d, m = a, b
            elif a <= 12 and b > 12:
                m, d = a, b
            else:
                d, m = a, b

            if y < 100:
                y = 2000 + y
            dt_parsed = QDate(y, m, d)
            if dt_parsed.isValid():
                return dt_parsed

        return None

    def _on_text_changed(self, text: str) -> None:
        raw = (text or "").strip()
        if not raw:
            self.setStyleSheet("")
            return

        digits = "".join(ch for ch in raw if ch.isdigit())
        if digits and len(digits) < 8:
            self.setStyleSheet("")
            return

        parsed = self._parse_user_date(raw)
        if parsed and parsed.isValid():
            self.setStyleSheet("")
            return
        self.setStyleSheet("QDateEdit { border: 2px solid #e74c3c; background-color: #fff; }")

    def _normalize_date_text(self) -> None:
        le = self.lineEdit()
        if not le:
            return
        raw = (le.text() or "").strip()
        if not raw:
            self.clear_date()
            return

        parsed = self._parse_user_date(raw)
        if parsed and parsed.isValid():
            self.setDate(parsed)
            self.setStyleSheet("")
        else:
            self.clear_date()


class InvoiceSubmissionWorker(QThread):
    """Background worker for invoice creation and sync to prevent UI freezing."""
    finished = pyqtSignal(int) # Returns invoice ID
    error = pyqtSignal(str)
    
    def __init__(self, invoice_in: InvoiceCreate):
        super().__init__()
        self.invoice_in = invoice_in
        
    def run(self):
        db = SessionLocal()
        try:
            logger.info(f"Background SubmissionWorker started for invoice {self.invoice_in.invoice_number}")
            created = invoice_service.create_invoice(db, self.invoice_in)
            self.finished.emit(created.id)
        except Exception as e:
            logger.error(f"Background SubmissionWorker failed: {e}", exc_info=True)
            self.error.emit(str(e))
        finally:
            db.close()

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

class BookingCard(QFrame):
    """Dynamic card displaying real-time booking quantity for a specific model."""
    def __init__(self, model_name: str, count: int = 0, color: str = "#3498db", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model_name = model_name
        self.count = max(0, int(count)) # Prevent negative quantities
        self.color = color
        
        self.setObjectName("bookingCard")
        self.setMinimumHeight(110)
        self.setMinimumWidth(180)
        self.setStyleSheet(f"""
            QFrame#bookingCard {{
                border-top: 4px solid {color};
                background-color: white;
                border-radius: 8px;
            }}
            QLabel#modelTitle {{
                color: #7f8c8d;
                font-size: 11px;
                font-weight: bold;
                letter-spacing: 0.5px;
            }}
            QLabel#countValue {{
                color: {color};
                font-size: 28px;
                font-weight: bold;
            }}
            QLabel#countLabel {{
                color: #95a5a6;
                font-size: 12px;
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(2)

        self.title_lbl = QLabel(model_name.upper())
        self.title_lbl.setObjectName("modelTitle")
        self.title_lbl.setWordWrap(True)
        
        self.val_lbl = QLabel(str(self.count))
        self.val_lbl.setObjectName("countValue")
        
        self.footer_lbl = QLabel("UNITS BOOKED")
        self.footer_lbl.setObjectName("countLabel")
        
        layout.addWidget(self.title_lbl)
        layout.addWidget(self.val_lbl)
        layout.addWidget(self.footer_lbl)
        layout.addStretch(1)
        
        # Connect to booking signals for real-time updates
        booking_signals.booking_updated.connect(self._on_booking_updated)

    def update_quantity(self, count: int) -> None:
        """Manually update the displayed quantity."""
        self.count = max(0, int(count))
        self.val_lbl.setText(str(self.count))
        
        # Highlight update with a quick flash effect (optional, but good for UX)
        self.val_lbl.setStyleSheet(f"color: {self.color}; font-size: 32px; font-weight: bold;")
        QTimer.singleShot(500, lambda: self.val_lbl.setStyleSheet(f"color: {self.color}; font-size: 28px; font-weight: bold;"))

    def _on_booking_updated(self, model_name: str, count: int) -> None:
        """Handle real-time update if this card belongs to the updated model."""
        if model_name.upper() == self.model_name.upper():
            self.update_quantity(count)

class NavigationButton(QPushButton):
    def __init__(
        self,
        icon_text: str,
        title: str,
        page_key: str,
        parent: QWidget | None = None,
        expanded_font_size: int = 15,
        collapsed_font_size: int = 18,
    ) -> None:
        super().__init__(parent)
        self.icon_text = icon_text
        self.title = title
        self.page_key = page_key
        self.expanded_font_size = int(expanded_font_size)
        self.collapsed_font_size = int(collapsed_font_size)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setText(f"{icon_text}  {title}")

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed:
            self.setText(self.icon_text)
            self.setToolTip(self.title)
            self.setStyleSheet(f"""
                NavigationButton {{
                    background-color: transparent;
                    color: #bdc3c7;
                    border: none;
                    border-left: 4px solid transparent;
                    text-align: center;
                    padding: 10px 0px;
                    font-size: {self.collapsed_font_size}px;
                    border-radius: 0;
                }}
                NavigationButton:hover {{
                    background-color: #3e4f5f;
                    color: white;
                }}
                NavigationButton:checked {{
                    background-color: #3498db;
                    color: white;
                    border-left: 4px solid #2980b9;
                }}
            """)
        else:
            self.setText(f"{self.icon_text}  {self.title}")
            self.setToolTip("")
            self.setStyleSheet(f"""
                NavigationButton {{
                    background-color: transparent;
                    color: #bdc3c7;
                    border: none;
                    border-left: 4px solid transparent;
                    text-align: left;
                    padding: 10px 15px;
                    font-size: {self.expanded_font_size}px;
                    border-radius: 0;
                }}
                NavigationButton:hover {{
                    background-color: #3e4f5f;
                    color: white;
                }}
                NavigationButton:checked {{
                    background-color: #3498db;
                    color: white;
                    border-left: 4px solid #2980b9;
                }}
            """)

    def set_font_sizes(self, expanded_font_size: int, collapsed_font_size: int) -> None:
        self.expanded_font_size = int(expanded_font_size)
        self.collapsed_font_size = int(collapsed_font_size)


class GroupHeaderButton(QPushButton):
    def __init__(self, arrow: str, group_name: str, parent: QWidget | None = None, font_size: int = 12) -> None:
        super().__init__(parent)
        self.arrow = arrow
        self.group_name = group_name
        self.font_size = int(font_size)
        self.setCheckable(True)
        self.setChecked(True) # Expanded by default
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setText(f"{arrow} {group_name}")
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: #7f8c8d;
                border: none;
                text-align: left;
                padding: 15px 20px 5px 20px;
                font-size: {self.font_size}px;
                font-weight: bold;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{
                color: white;
            }}
        """)

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed:
            self.setText("") # Hide group headers in collapsed mode
            self.setMaximumHeight(0)
        else:
            self.setText(f"{self.arrow} {self.group_name}")
            self.setMaximumHeight(16777215)

    def set_font_size(self, font_size: int) -> None:
        self.font_size = int(font_size)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: #7f8c8d;
                border: none;
                text-align: left;
                padding: 15px 20px 5px 20px;
                font-size: {self.font_size}px;
                font-weight: bold;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{
                color: white;
            }}
        """)


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


class AddressShortcodeLineEdit(QLineEdit):
    """
    A PyQt6 QLineEdit for address fields that supports auto-expansion of shortcodes.
    Example: Typing 'KT' and pressing Space expands to 'Tehsil Kamalia District Toba Tek Singh'.
    """
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

    def keyReleaseEvent(self, event) -> None:
        # Trigger expansion on space, comma, or return
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Comma):
            self._check_expansion(event.key())
        
        # Also force uppercase if it's not already (common pattern in this app)
        val = self.text()
        if val != val.upper():
            pos = self.cursorPosition()
            self.setText(val.upper())
            self.setCursorPosition(pos)
        
        super().keyReleaseEvent(event)

    def _check_expansion(self, key):
        content = self.text()
        if not content:
            return
            
        # Get latest shortcodes
        try:
            shortcodes = settings_service.get_address_shortcodes()
        except Exception as e:
            logger.error(f"Failed to fetch shortcodes: {e}")
            return
            
        if not shortcodes:
            return
            
        # text_to_check is the content before the last key press was processed
        # For Return, it's the whole text. For Space/Comma, it's the text minus the last char.
        text_to_check = content.strip()
        if not text_to_check:
            return
            
        words = text_to_check.split()
        if not words:
            return
            
        # Strip trailing comma if present on the last word for matching
        last_word_raw = words[-1].upper()
        last_word = last_word_raw.rstrip(',')
        
        if last_word in shortcodes:
            expansion = shortcodes[last_word].upper()
            
            # Reconstruct the text
            prefix = " ".join(words[:-1])
            
            if prefix:
                new_content = prefix + " " + expansion
            else:
                new_content = expansion
                
            # Add back comma if it was stripped from last_word_raw
            if last_word_raw.endswith(','):
                new_content += ","
                
            # Add back the delimiter if it wasn't Return
            if key == Qt.Key.Key_Space:
                new_content += " "
            elif key == Qt.Key.Key_Comma:
                if not new_content.endswith(','):
                    new_content += ","
                new_content += " "
                
            self.setText(new_content)
            self.setCursorPosition(len(new_content))
            logger.info(f"Expanded shortcode '{last_word}' to '{expansion}'")


class MainWindow(QMainWindow):
    sms_result_signal = pyqtSignal(bool, str)
    conn_test_result_signal = pyqtSignal(bool, str) # Added for connection tests
    campaign_progress_signal = pyqtSignal(int, int, int, int) # camp_id, sent, failed, total
    campaign_complete_signal = pyqtSignal(int, bool, str) # camp_id, success, message

    def __init__(self, parent: QWidget | None = None, db_status: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("Ehsan Trader FBR System")
        self.resize(1100, 700)
        self.db_status = db_status # Store DB status to show warning if missing

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
        
        self._settings_subscription_token = settings_service.subscribe(self._on_settings_event)
        self._active_fbr_settings_snapshot = settings_service.get_active_settings()
        self._last_settings_revision = settings_service.get_revision()

        self._update_app_branding(self._active_fbr_settings_snapshot.get("business_name", "Ehsan Trader"))
        try:
            from app.services.sync_service import sync_service
            self._sync_service = sync_service
            self._sync_service.start()
        except Exception as e:
            logger.error(f"Failed to start background sync service: {e}", exc_info=True)

    def _on_settings_event(self, event: dict) -> None:
        QTimer.singleShot(0, lambda e=event: self._apply_settings_event(e))

    def _apply_settings_event(self, event: dict) -> None:
        try:
            event_type = event.get("type")
            if event_type not in ("fbr_settings_saved", "fbr_active_environment_changed"):
                return

            revision = int(event.get("revision") or 0)
            last_rev = int(getattr(self, "_last_settings_revision", 0) or 0)
            if revision and revision <= last_rev:
                logger.info(f"Ignoring stale FBR settings event: type={event_type} revision={revision} last={last_rev}")
                return
            if revision:
                self._last_settings_revision = revision

            new_active_settings = settings_service.get_active_settings()
            old_active_settings = getattr(self, "_active_fbr_settings_snapshot", {}) or {}
            changed_keys = [
                k for k in new_active_settings.keys()
                if old_active_settings.get(k) != new_active_settings.get(k)
            ]
            self._active_fbr_settings_snapshot = dict(new_active_settings)

            if "business_name" in changed_keys:
                self._update_app_branding(new_active_settings.get("business_name", "Ehsan Trader"))

            self._sync_invoice_page_with_fbr_settings(old_active_settings, new_active_settings, changed_keys)
            logger.info(f"FBR settings event applied: type={event_type} revision={revision} changed={changed_keys}")
        except Exception as e:
            logger.error(f"Failed to apply settings event: {e}", exc_info=True)

    def _sync_invoice_page_with_fbr_settings(self, before: dict, after: dict, changed_keys: list[str]) -> None:
        try:
            if hasattr(self, "invoice_env_value_label") and hasattr(self, "invoice_env_badge"):
                active_env = settings_service.get_active_environment()
                self.invoice_env_value_label.setText(active_env.upper())
                color = "#e67e22" if active_env.upper() == "SANDBOX" else "#27ae60"
                self.invoice_env_badge.setStyleSheet(f"QFrame {{ border: 2px solid {color}; border-radius: 8px; background-color: white; }}")

            if hasattr(self, "invoice_number_input"):
                from app.services.settings_service import should_regenerate_invoice_number
                current_inv = self.invoice_number_input.text()
                if should_regenerate_invoice_number(current_inv, before.get("usin") or "", changed_keys):
                    self._generate_invoice_number()

            if "tax_rate" in changed_keys and getattr(self, "_invoice_current_price", None) is None:
                if hasattr(self, "_recalculate_invoice_totals"):
                    self._recalculate_invoice_totals()
        except Exception as e:
            logger.error(f"Invoice page sync failed: {e}", exc_info=True)

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
        
        # Get Update URL from settings
        version_url = config.settings.APP_UPDATE_URL
        
        # If URL is empty or explicitly set to placeholder, skip background update check
        if not version_url or "your-server.com" in version_url:
            logger.info("Update check skipped: No valid APP_UPDATE_URL configured.")
            return

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

        self._ui_cfg = settings_service.get_app_config() or {}

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
        self.nav_header_label.setStyleSheet("color: white; font-weight: bold; border: none;")
        
        self.nav_header_layout.addWidget(self.nav_header_label, 1)
        nav_layout.addWidget(nav_header_container)

        self.stack = QStackedWidget(central)

        root_layout.addWidget(self.nav_widget)
        root_layout.addWidget(self.stack, 1)

        self._add_page("dashboard", self._create_dashboard_page(), "Dashboard")
        self._add_page("reports", self._create_reports_page(), "Reports")
        self._add_page("invoice", self._create_invoice_page(), "Invoice")
        self._add_page("print_document", self._create_print_document_page(), "Print Document")
        self._add_page("inventory", self._create_inventory_page(), "Inventory")
        self._add_page("captured_data", self._create_captured_data_page(), "Captured Data")
        self._add_page("prices", self._create_prices_page(), "Prices")
        self._add_page("customers", self._create_customers_page(), "Customers")
        self._add_page("dealers", self._create_dealers_page(), "Dealers")
        self._add_page("advance_booking", self._create_advance_booking_page(), "Advance Booking")
        self._add_page("credit_ledger", self._create_credit_ledger_page(), "Credit Ledger System")
        self._add_page("spare_ledger", self._create_spare_ledger_page(), "Spare Ledger")
        self._add_page("sms", self._create_sms_page(), "SMS Module")
        self._add_page("whatsapp", self._create_whatsapp_page(), "Whatsapp Module")
        self._add_page("settings", self._create_settings_page(), "Settings")
        self._add_page("welcome", self._create_welcome_page(), "Welcome")
        self._add_page("dms_automation", self._create_dms_automation_page(), "DMS Automation")

        nav_layout.addSpacing(10)
        
        self.nav_icons = {
            "dashboard": "📊",
            "reports": "📈",
            "invoice": "📝",
            "inventory": "📦",
            "prices": "💰",
            "customers": "👥",
            "dealers": "🏢",
            "advance_booking": "📅",
            "credit_ledger": "🧾",
            "spare_ledger": "📒",
            "sms": "💬",
            "whatsapp": "📱",
            "settings": "⚙️",
            "welcome": "👋",
            "captured_data": "📁",
            "print_document": "🖨️",
            "dms_automation": "🤖",
        }

        self.menu_groups = {
            "GENERAL": ["dashboard", "welcome"],
            "SALES": ["invoice", "reports", "advance_booking", "credit_ledger", "print_document"],
            "INVENTORY": ["inventory", "prices", "spare_ledger", "captured_data"],
            "DIRECTORY": ["customers", "dealers"],
            "AUTOMATION": ["dms_automation"],
            "SYSTEM": ["sms", "whatsapp", "settings"]
        }

        self._group_headers: Dict[str, GroupHeaderButton] = {}
        self._group_buttons: Dict[str, List[NavigationButton]] = {}
        self._group_header_manager = QButtonGroup(self)
        self._group_header_manager.setExclusive(False) # We'll handle exclusivity manually for more control

        for i, (group_name, keys) in enumerate(self.menu_groups.items()):
            # Group Header
            is_first = (i == 0)
            arrow = "▼" if is_first else "▶"
            header = GroupHeaderButton(
                arrow,
                group_name,
                self.nav_widget,
                font_size=int(self._ui_cfg.get("sidebar_group_font_size", 12) or 12),
            )
            header.setChecked(is_first)
            header.clicked.connect(self._on_group_header_clicked)
            self._group_header_manager.addButton(header)
            nav_layout.addWidget(header)
            self._group_headers[group_name] = header
            self._group_buttons[group_name] = []

            for key in keys:
                title = self._pages[key].windowTitle()
                icon = self.nav_icons.get(key, "🔹")
                button = NavigationButton(
                    icon,
                    title,
                    key,
                    self.nav_widget,
                    expanded_font_size=int(self._ui_cfg.get("sidebar_font_size", 15) or 15),
                    collapsed_font_size=int(self._ui_cfg.get("sidebar_collapsed_font_size", 18) or 18),
                )
                button.set_collapsed(self._is_sidebar_collapsed)
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
        self.footer_update_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: #bdc3c7;
                border: none;
                border-left: 4px solid transparent;
                text-align: left;
                padding: 15px 20px;
                font-size: {int(self._ui_cfg.get("sidebar_footer_font_size", 15) or 15)}px;
                border-radius: 0;
            }}
            QPushButton:hover {{
                background-color: #34495e;
                color: white;
                border-left: 4px solid #3498db;
            }}
        """)
        self.footer_update_btn.clicked.connect(self._on_manual_update_check)
        nav_layout.addWidget(self.footer_update_btn)

        # Exit Button
        self.exit_btn = QPushButton("🚪 Exit Application")
        self.exit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: #e74c3c;
                border: none;
                border-left: 4px solid transparent;
                text-align: left;
                padding: 15px 20px;
                font-size: {int(self._ui_cfg.get("sidebar_exit_font_size", 16) or 16)}px;
                font-weight: bold;
                border-radius: 0;
            }}
            QPushButton:hover {{
                background-color: #c0392b;
                color: white;
            }}
        """)
        self.exit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.exit_btn.clicked.connect(self.close)
        nav_layout.addWidget(self.exit_btn)

        self.apply_sidebar_font_settings(self._ui_cfg)

        self._select_page("dashboard")
        self._update_fbr_submitted_counter() # Initial load of counter state

        # Connect global focus signal to automatic scrolling logic
        QApplication.instance().focusChanged.connect(self._on_focus_changed)

        # Ensure the dashboard and welcome stats refresh their data once the application is fully ready
        QTimer.singleShot(100, self._refresh_dashboard)
        QTimer.singleShot(100, self._refresh_welcome_stats)
        
        # --- Handle Missing Database Notification ---
        if self.db_status == "DATABASE_MISSING":
            QTimer.singleShot(500, self._show_db_missing_warning)

    def _show_db_missing_warning(self):
        """Professionally warns the user that the selected database does not exist."""
        QMessageBox.warning(
            self,
            "Database Not Found",
            "The database specified in your settings does not exist on the server.\n\n"
            "Please go to Settings > Database Connection and select an existing database or check your connection details.",
        )
        self._select_page("settings")

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
        self.apply_sidebar_font_settings(self._ui_cfg)

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

    def apply_sidebar_font_settings(self, cfg: dict) -> None:
        self._ui_cfg = {**(getattr(self, "_ui_cfg", {}) or {}), **(cfg or {})}
        sidebar_font_size = max(8, min(24, int(self._ui_cfg.get("sidebar_font_size", 15) or 15)))
        sidebar_group_font_size = max(8, min(24, int(self._ui_cfg.get("sidebar_group_font_size", 12) or 12)))
        sidebar_header_font_size = max(8, min(24, int(self._ui_cfg.get("sidebar_header_font_size", 18) or 18)))
        sidebar_footer_font_size = max(8, min(24, int(self._ui_cfg.get("sidebar_footer_font_size", 15) or 15)))
        sidebar_exit_font_size = max(8, min(24, int(self._ui_cfg.get("sidebar_exit_font_size", 16) or 16)))
        sidebar_collapsed_font_size = max(8, min(24, int(self._ui_cfg.get("sidebar_collapsed_font_size", 18) or 18)))

        if hasattr(self, "nav_header_label"):
            self.nav_header_label.setStyleSheet(
                f"color: white; font-size: {sidebar_header_font_size}px; font-weight: bold; border: none;"
            )

        for header in getattr(self, "_group_headers", {}).values():
            if hasattr(header, "set_font_size"):
                header.set_font_size(sidebar_group_font_size)

        for btn in getattr(self, "_nav_buttons", {}).values():
            if hasattr(btn, "set_font_sizes"):
                btn.set_font_sizes(sidebar_font_size, sidebar_collapsed_font_size)
            if hasattr(btn, "set_collapsed"):
                btn.set_collapsed(self._is_sidebar_collapsed)

        if hasattr(self, "footer_update_btn"):
            if self._is_sidebar_collapsed:
                self.footer_update_btn.setText("🔄")
                self.footer_update_btn.setToolTip("Check for Updates")
                self.footer_update_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: transparent;
                        color: #bdc3c7;
                        border: none;
                        border-left: 4px solid transparent;
                        text-align: center;
                        padding: 15px 0px;
                        font-size: {sidebar_collapsed_font_size}px;
                        border-radius: 0;
                    }}
                    QPushButton:hover {{
                        background-color: #34495e;
                        color: white;
                        border-left: 4px solid #3498db;
                    }}
                """)
            else:
                self.footer_update_btn.setText("🔄 Check for Updates")
                self.footer_update_btn.setToolTip("")
                self.footer_update_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: transparent;
                        color: #bdc3c7;
                        border: none;
                        border-left: 4px solid transparent;
                        text-align: left;
                        padding: 15px 20px;
                        font-size: {sidebar_footer_font_size}px;
                        border-radius: 0;
                    }}
                    QPushButton:hover {{
                        background-color: #34495e;
                        color: white;
                        border-left: 4px solid #3498db;
                    }}
                """)

        if hasattr(self, "exit_btn"):
            if self._is_sidebar_collapsed:
                self.exit_btn.setText("🚪")
                self.exit_btn.setToolTip("Exit Application")
                self.exit_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: transparent;
                        color: #e74c3c;
                        border: none;
                        border-left: 4px solid transparent;
                        text-align: center;
                        padding: 15px 0px;
                        font-size: {sidebar_collapsed_font_size}px;
                        font-weight: bold;
                        border-radius: 0;
                    }}
                    QPushButton:hover {{
                        background-color: #c0392b;
                        color: white;
                    }}
                """)
            else:
                self.exit_btn.setText("🚪 Exit Application")
                self.exit_btn.setToolTip("")
                self.exit_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: transparent;
                        color: #e74c3c;
                        border: none;
                        border-left: 4px solid transparent;
                        text-align: left;
                        padding: 15px 20px;
                        font-size: {sidebar_exit_font_size}px;
                        font-weight: bold;
                        border-radius: 0;
                    }}
                    QPushButton:hover {{
                        background-color: #c0392b;
                        color: white;
                    }}
                """)

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

        # Real-time Bike Booking Cards
        booking_label = QLabel("BIKE BOOKING STATUS (BY MODEL)")
        booking_label.setObjectName("groupTitle")
        layout.addWidget(booking_label)
        
        self.dash_booking_host = QWidget()
        self.dash_booking_grid = QGridLayout(self.dash_booking_host)
        self.dash_booking_grid.setContentsMargins(0, 0, 0, 0)
        self.dash_booking_grid.setHorizontalSpacing(20)
        self.dash_booking_grid.setVerticalSpacing(20)
        self._dash_booking_card_widgets: Dict[str, BookingCard] = {}
        layout.addWidget(self.dash_booking_host)

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
        self.dash_table_view.doubleClicked.connect(self._on_dash_row_double_clicked)
        # Install Auto Scroll Manager
        self.dash_table_auto_scroll = AutoScrollManager(self)
        self.dash_table_auto_scroll.install_on_widget(self.dash_table_view)
        
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
            rows = (
                db.query(Invoice)
                .options(
                    joinedload(Invoice.customer),
                    joinedload(Invoice.items).joinedload(InvoiceItem.motorcycle),
                )
                .order_by(Invoice.datetime.desc())
                .limit(10)
                .all()
            )
            
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

            # Update Dynamic Booking Cards on Dashboard
            if hasattr(self, "dash_booking_grid"):
                booking_counts = advance_booking_service.get_active_counts_by_model(db, limit=8)
                
                # Check for model changes to rebuild layout if needed
                current_dash_models = set(self._dash_booking_card_widgets.keys())
                new_dash_models = set(m for m, c in booking_counts)
                
                if current_dash_models != new_dash_models:
                    while self.dash_booking_grid.count():
                        item = self.dash_booking_grid.takeAt(0)
                        w = item.widget()
                        if w: w.setParent(None)
                    self._dash_booking_card_widgets.clear()
                    
                    cols = 4
                    for i, (model_name, count) in enumerate(booking_counts):
                        card = BookingCard(model_name or "-", count, "#3498db")
                        self.dash_booking_grid.addWidget(card, i // cols, i % cols)
                        self._dash_booking_card_widgets[model_name] = card
                else:
                    for model_name, count in booking_counts:
                        if model_name in self._dash_booking_card_widgets:
                            self._dash_booking_card_widgets[model_name].update_quantity(count)

        except Exception as e:
            logger.error(f"Dashboard refresh error: {e}", exc_info=True)
        finally:
            db.close()

    def _on_dash_row_double_clicked(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        row_data = self.dash_table_model._rows[index.row()]
        self._open_invoice_detail_dialog(row_data)

    def _create_print_document_page(self) -> QWidget:
        """Creates a standalone page for printing existing FBR-submitted invoices by Chassis Number."""
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(25)

        # Header
        header = QLabel("Print Documents")
        header.setObjectName("pageHeader")
        layout.addWidget(header)

        # Search Card
        search_card = QFrame()
        search_card.setObjectName("formGroup")
        search_card.setStyleSheet("QFrame#formGroup { background-color: white; border-radius: 12px; }")
        search_layout = QVBoxLayout(search_card)
        search_layout.setContentsMargins(30, 25, 30, 25)
        search_layout.setSpacing(15)

        title = QLabel("SEARCH BY CHASSIS NUMBER")
        title.setObjectName("groupTitle")
        search_layout.addWidget(title)

        input_layout = QHBoxLayout()
        self.print_search_input = QLineEdit()
        self.print_search_input.setPlaceholderText("Enter Chassis Number...")
        self.print_search_input.setMinimumHeight(45)
        self.print_search_input.setStyleSheet("font-size: 16px; padding: 0 15px;")
        self.print_search_input.returnPressed.connect(self._on_print_search_clicked)
        
        search_btn = QPushButton("🔍 Search Invoice")
        search_btn.setObjectName("primaryButton")
        search_btn.setMinimumHeight(45)
        search_btn.setFixedWidth(200)
        search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        search_btn.clicked.connect(self._on_print_search_clicked)
        
        input_layout.addWidget(self.print_search_input, 1)
        input_layout.addWidget(search_btn)
        search_layout.addLayout(input_layout)
        
        layout.addWidget(search_card)

        # Results Area (Initially Hidden)
        self.print_results_card = QFrame()
        self.print_results_card.setObjectName("formGroup")
        self.print_results_card.setStyleSheet("QFrame#formGroup { background-color: white; border-radius: 12px; }")
        self.print_results_card.setVisible(False)
        results_layout = QVBoxLayout(self.print_results_card)
        results_layout.setContentsMargins(30, 25, 30, 25)
        results_layout.setSpacing(20)

        # "Editable" Form Fields
        form_grid = QGridLayout()
        form_grid.setSpacing(15)

        def add_field(row, col, label_text, widget_factory=QLineEdit):
            lbl = QLabel(label_text)
            lbl.setStyleSheet("font-weight: bold; color: #7f8c8d;")
            edit = widget_factory()
            edit.setMinimumHeight(35)
            edit.setStyleSheet("background-color: #f9f9f9; border: 1px solid #ddd; padding: 0 10px;")
            form_grid.addWidget(lbl, row, col)
            form_grid.addWidget(edit, row + 1, col)
            return edit

        self.print_field_invoice = add_field(0, 0, "Invoice Number")
        self.print_field_fbr = add_field(0, 1, "FBR Generated ID")
        self.print_field_date = add_field(2, 0, "Date")
        self.print_field_customer = add_field(2, 1, "Customer Name")
        self.print_field_cnic = add_field(4, 0, "Customer CNIC")
        father_lbl = QLabel("Father / Husband Name")
        father_lbl.setStyleSheet("font-weight: bold; color: #7f8c8d;")
        form_grid.addWidget(father_lbl, 4, 1)
        father_row = QWidget()
        father_row_layout = QHBoxLayout(father_row)
        father_row_layout.setContentsMargins(0, 0, 0, 0)
        father_row_layout.setSpacing(10)
        self.print_field_relation = QComboBox()
        self.print_field_relation.addItems(["S/O", "D/O", "W/O"])
        self.print_field_relation.setMinimumHeight(35)
        self.print_field_relation.setFixedWidth(80)
        self.print_field_relation.setStyleSheet("background-color: #f9f9f9; border: 1px solid #ddd; padding: 0 6px;")
        self.print_field_father = QLineEdit()
        self.print_field_father.setMinimumHeight(35)
        self.print_field_father.setStyleSheet("background-color: #f9f9f9; border: 1px solid #ddd; padding: 0 10px;")
        father_row_layout.addWidget(self.print_field_relation)
        father_row_layout.addWidget(self.print_field_father, 1)
        form_grid.addWidget(father_row, 5, 1)
        self.print_field_address = add_field(6, 0, "Address", AddressShortcodeLineEdit)
        self.print_field_model = add_field(6, 1, "Model")
        self.print_field_color = add_field(8, 0, "Color")

        qr_lbl = QLabel("FBR Generated ID QR Code")
        qr_lbl.setStyleSheet("font-weight: bold; color: #7f8c8d;")
        self.print_field_qr = QLabel("")
        self.print_field_qr.setMinimumHeight(120)
        self.print_field_qr.setMinimumWidth(120)
        self.print_field_qr.setFixedSize(140, 140)
        self.print_field_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.print_field_qr.setStyleSheet("background-color: #ffffff; border: 1px solid #ddd;")
        form_grid.addWidget(qr_lbl, 8, 1)
        form_grid.addWidget(self.print_field_qr, 9, 1)
        
        results_layout.addLayout(form_grid)

        # Action Buttons for Printing
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)
        
        self.print_page_inv_btn = QPushButton("🖨️ Print Invoice")
        self.print_page_inv_btn.setObjectName("primaryButton")
        self.print_page_inv_btn.setMinimumHeight(50)
        
        self.print_page_al_btn = QPushButton("📄 Authority Letter")
        self.print_page_al_btn.setObjectName("primaryButton")
        self.print_page_al_btn.setMinimumHeight(50)
        
        btn_layout.addWidget(self.print_page_inv_btn)
        btn_layout.addWidget(self.print_page_al_btn)
        btn_layout.addStretch(1)
        results_layout.addLayout(btn_layout)

        layout.addWidget(self.print_results_card)
        layout.addStretch(1)

        return page

    def _on_print_search_clicked(self) -> None:
        """Handles searching for an invoice by chassis number for printing."""
        chassis = self.print_search_input.text().strip().upper()
        
        if not chassis:
            self._show_error("Validation Error", "Please enter a Chassis Number.")
            return

        db = SessionLocal()
        try:
            # Search for invoice item with matching chassis that belongs to an FBR submitted invoice
            # We use joinedload to eagerly load related customer, items, and motorcycles
            # This prevents "DetachedInstanceError" when the session is closed.
            query = db.query(Invoice).join(InvoiceItem).join(Motorcycle).options(
                joinedload(Invoice.customer),
                joinedload(Invoice.items).joinedload(InvoiceItem.motorcycle).joinedload(Motorcycle.product_model)
            ).filter(
                Motorcycle.chassis_number == chassis,
                Invoice.fbr_invoice_number.isnot(None)
            ).order_by(Invoice.datetime.desc())
            
            invoice = query.first()
            
            if not invoice:
                self.print_results_card.setVisible(False)
                self._show_error("Not Found", f"No FBR-submitted invoice found for chassis: {chassis}")
                return

            # Display Results in "Editable" fields
            self.current_print_invoice = invoice # Store for button actions
            cust = invoice.customer
            first_item = invoice.items[0] if invoice.items else None
            bike = first_item.motorcycle if first_item else None
            
            self.print_field_invoice.setText(invoice.invoice_number or "")
            self.print_field_fbr.setText(invoice.fbr_invoice_number or "")
            self.print_field_date.setText(invoice.datetime.strftime('%Y-%m-%d %H:%M') if invoice.datetime else "")
            self.print_field_customer.setText(cust.name if cust else "")
            self.print_field_cnic.setText(cust.cnic if cust else "")
            self.print_field_father.setText((cust.father_name if cust else "") or "")
            if hasattr(self, "print_field_relation"):
                idx = self.print_field_relation.findText("S/O")
                if idx >= 0:
                    self.print_field_relation.setCurrentIndex(idx)
            self.print_field_address.setText((cust.address if cust else "") or "")
            self.print_field_model.setText((bike.model if bike else (first_item.item_name if first_item else "")) or "")
            self.print_field_color.setText((bike.color if bike else "") or "")

            self._print_doc_qr_base64 = ""
            self.print_field_qr.setPixmap(QPixmap())
            fbr_id = (invoice.fbr_invoice_number or "").strip()
            if fbr_id:
                try:
                    qr = qrcode.QRCode(version=1, box_size=8, border=2)
                    qr.add_data(fbr_id)
                    qr.make(fit=True)
                    img = qr.make_image(fill_color="black", back_color="white")
                    buffered = io.BytesIO()
                    img.save(buffered, format="PNG")
                    png_bytes = buffered.getvalue()
                    self._print_doc_qr_base64 = base64.b64encode(png_bytes).decode()
                    pixmap = QPixmap()
                    pixmap.loadFromData(png_bytes, "PNG")
                    self.print_field_qr.setPixmap(
                        pixmap.scaled(
                            self.print_field_qr.size(),
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                    )
                except Exception:
                    self._print_doc_qr_base64 = ""
            
            # Connect actions (disconnect first to avoid multiple triggers)
            try: self.print_page_inv_btn.clicked.disconnect()
            except: pass
            try: self.print_page_al_btn.clicked.disconnect()
            except: pass
            
            self.print_page_inv_btn.clicked.connect(self._on_print_page_print_invoice)
            self.print_page_al_btn.clicked.connect(self._on_print_page_print_authority_letter)
            
            self.print_results_card.setVisible(True)

        except Exception as e:
            logger.error(f"Search error: {e}", exc_info=True)
            self._show_error("Search Error", f"An error occurred while searching: {e}")
        finally:
            db.close()

    def _get_print_page_overrides(self) -> Dict[str, str]:
        fbr_invoice_number = self.print_field_fbr.text().strip() if hasattr(self, "print_field_fbr") else ""
        relation_prefix = ""
        if hasattr(self, "print_field_relation"):
            relation_prefix = self.print_field_relation.currentText().strip()
        return {
            "invoice_number": self.print_field_invoice.text().strip() if hasattr(self, "print_field_invoice") else "",
            "date": self.print_field_date.text().strip() if hasattr(self, "print_field_date") else "",
            "customer_name": self.print_field_customer.text().strip() if hasattr(self, "print_field_customer") else "",
            "customer_cnic": self.print_field_cnic.text().strip() if hasattr(self, "print_field_cnic") else "",
            "father_name": self.print_field_father.text().strip() if hasattr(self, "print_field_father") else "",
            "relation_prefix": relation_prefix,
            "customer_address": self.print_field_address.text().strip() if hasattr(self, "print_field_address") else "",
            "model": self.print_field_model.text().strip() if hasattr(self, "print_field_model") else "",
            "color": self.print_field_color.text().strip() if hasattr(self, "print_field_color") else "",
            "fbr_invoice_number": fbr_invoice_number,
            "qr_code_base64": getattr(self, "_print_doc_qr_base64", "") or "",
        }

    def _on_print_page_print_invoice(self) -> None:
        invoice = getattr(self, "current_print_invoice", None)
        if not invoice:
            self._show_error("Error", "No invoice selected for printing.")
            return
        self._print_invoice_standalone(invoice, overrides=self._get_print_page_overrides())

    def _on_print_page_print_authority_letter(self) -> None:
        invoice = getattr(self, "current_print_invoice", None)
        if not invoice:
            self._show_error("Error", "No invoice selected for printing.")
            return
        self._print_authority_letter_standalone(invoice, overrides=self._get_print_page_overrides())

    def _create_reports_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)

        header = QLabel("Reporting Portal")
        header.setStyleSheet("font-size: 22px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(header)

        subtitle = QLabel("Open interactive dashboards in your browser (recommended for best performance and compatibility).")
        subtitle.setStyleSheet("color: #7f8c8d;")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        btn_row = QHBoxLayout()
        open_dash = QPushButton("Open Dashboard")
        open_builder = QPushButton("Template Builder")
        open_sched = QPushButton("Schedules")

        open_dash.setObjectName("primaryButton")
        open_builder.setObjectName("resetButton")
        open_sched.setObjectName("resetButton")

        def open_url(url: str) -> None:
            try:
                from PyQt6.QtGui import QDesktopServices
                from PyQt6.QtCore import QUrl

                QDesktopServices.openUrl(QUrl(url))
            except Exception as e:
                self._show_error("Browser Error", str(e))

        open_dash.clicked.connect(lambda: open_url("http://localhost:9000/dashboard"))
        open_builder.clicked.connect(lambda: open_url("http://localhost:9000/builder"))
        open_sched.clicked.connect(lambda: open_url("http://localhost:9000/schedules"))

        btn_row.addWidget(open_dash)
        btn_row.addWidget(open_builder)
        btn_row.addWidget(open_sched)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        note = QLabel("If the portal does not open, ensure the Reporting Server is running on http://localhost:9000.")
        note.setStyleSheet("color: #95a5a6; font-size: 11px;")
        note.setWordWrap(True)
        layout.addWidget(note)

        layout.addStretch(1)
        return page

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
        # Install Auto Scroll Manager
        self.sales_table_auto_scroll = AutoScrollManager(self)
        self.sales_table_auto_scroll.install_on_widget(self.sales_table_view)
        
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
            scroll = PanScrollArea()
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

            # --- Action Buttons Card ---
            action_card = QFrame()
            action_card.setProperty("class", "detailCard")
            action_card.setObjectName("actionCard")
            action_card.setStyleSheet("QFrame#actionCard { background-color: white; border: 1px solid #e0e0e0; border-radius: 12px; }")
            action_layout = QHBoxLayout(action_card)
            action_layout.setContentsMargins(20, 15, 20, 15)
            action_layout.setSpacing(15)
            
            print_inv_btn = QPushButton("🖨️ Print Invoice")
            print_inv_btn.setObjectName("primaryButton")
            print_inv_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            print_inv_btn.clicked.connect(lambda: self._print_invoice_standalone(invoice))
            
            print_al_btn = QPushButton("📄 Authority Letter")
            print_al_btn.setObjectName("primaryButton")
            print_al_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            print_al_btn.clicked.connect(lambda: self._print_authority_letter_standalone(invoice))
            
            action_layout.addWidget(print_inv_btn)
            action_layout.addWidget(print_al_btn)
            action_layout.addStretch(1)
            
            content_layout.addWidget(action_card)

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

        self.invoice_scroll_area = PanScrollArea(page)
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

        self.invoice_preserve_info_checkbox = QCheckBox("Preserve invoice and customer information")
        self.invoice_preserve_info_checkbox.setStyleSheet("font-weight: bold; color: #2c3e50;")
        group1_layout.addWidget(self.invoice_preserve_info_checkbox, 1, 0, 1, 4)

        # Invoice Number
        group1_layout.addWidget(QLabel("Invoice Number"), 2, 0)
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
        group1_layout.addLayout(inv_num_layout, 2, 1)

        # QR Code & FBR Invoice Number Layout
        qr_fbr_layout = QHBoxLayout()
        qr_fbr_layout.setSpacing(15)
        qr_fbr_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        # QR Code Placeholder
        self.invoice_qr_label = QLabel()
        self.invoice_qr_label.setFixedSize(100, 100)
        self.invoice_qr_label.setStyleSheet("border: 1px dashed #ced4da; border-radius: 4px; background: #fdfdfd;")
        self.invoice_qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.invoice_qr_label.setText("QR CODE")
        qr_fbr_layout.addWidget(self.invoice_qr_label)

        # FBR Invoice Number Display (Red Rectangle Area)
        self.invoice_fbr_number_display = QLabel("")
        self.invoice_fbr_number_display.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 14px;
                color: #c0392b;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 10px;
                background-color: #fcfcfc;
            }
        """)
        self.invoice_fbr_number_display.setMinimumWidth(250)
        self.invoice_fbr_number_display.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        qr_fbr_layout.addWidget(self.invoice_fbr_number_display)
        
        group1_layout.addLayout(qr_fbr_layout, 2, 3)

        # CNIC
        group1_layout.addWidget(QLabel("ID Card (CNIC)"), 3, 0)
        self.invoice_buyer_cnic_input = QLineEdit()
        self.invoice_buyer_cnic_input.setPlaceholderText("12345-1234567-1")
        group1_layout.addWidget(self.invoice_buyer_cnic_input, 3, 1)

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
        group1_layout.addWidget(QLabel("NTN (Optional)"), 3, 2)
        self.invoice_buyer_ntn_input = QLineEdit()
        self.invoice_buyer_ntn_input.textChanged.connect(self._on_invoice_ntn_changed)
        group1_layout.addWidget(self.invoice_buyer_ntn_input, 3, 3)

        # Buyer Name & Father Name (Side by Side)
        group1_layout.addWidget(QLabel("Buyer Name"), 4, 0)
        
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
        
        group1_layout.addLayout(buyer_name_layout, 4, 1)

        group1_layout.addWidget(QLabel("Father Name"), 4, 2)
        self.invoice_buyer_father_input = QLineEdit()
        group1_layout.addWidget(self.invoice_buyer_father_input, 4, 3)

        # Allow only alphabetics and spaces for father name
        def format_invoice_father_input():
            text = self.invoice_buyer_father_input.text()
            filtered = "".join(c for c in text if c.isalpha() or c.isspace())
            if filtered != text:
                self.invoice_buyer_father_input.setText(filtered)
        self.invoice_buyer_father_input.textChanged.connect(format_invoice_father_input)

        # Phone & Address
        group1_layout.addWidget(QLabel("Cell (Phone)"), 5, 0)
        self.invoice_buyer_phone_input = QLineEdit()
        self.invoice_buyer_phone_input.setPlaceholderText("03021234567")
        group1_layout.addWidget(self.invoice_buyer_phone_input, 5, 1)
        
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

        group1_layout.addWidget(QLabel("Address"), 5, 2)
        self.invoice_buyer_address_input = AddressShortcodeLineEdit()
        group1_layout.addWidget(self.invoice_buyer_address_input, 5, 3)

        def uppercase_invoice_address():
            text = self.invoice_buyer_address_input.text()
            normalized = to_uppercase_preserving(text)
            if normalized != text:
                pos = self.invoice_buyer_address_input.cursorPosition()
                self.invoice_buyer_address_input.blockSignals(True)
                self.invoice_buyer_address_input.setText(normalized)
                self.invoice_buyer_address_input.setCursorPosition(min(pos, len(normalized)))
                self.invoice_buyer_address_input.blockSignals(False)
                self._check_invoice_form_completeness()

        self.invoice_buyer_address_input.textChanged.connect(uppercase_invoice_address)
        self.invoice_buyer_address_input.editingFinished.connect(uppercase_invoice_address)

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
        self.invoice_quantity_spin.valueChanged.connect(self._recalculate_invoice_totals)
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
        self.invoice_amount_spin.valueChanged.connect(self._recalculate_invoice_totals)
        group3_layout.addWidget(self.invoice_amount_spin, 1, 1)

        group3_layout.addWidget(QLabel("Sale Tax"), 1, 2)
        self.invoice_tax_spin = QDoubleSpinBox()
        self.invoice_tax_spin.setRange(0, 99999999)
        self.invoice_tax_spin.valueChanged.connect(self._recalculate_invoice_totals)
        group3_layout.addWidget(self.invoice_tax_spin, 1, 3)

        # Further Tax & Total
        group3_layout.addWidget(QLabel("Further Tax"), 2, 0)
        self.invoice_further_tax_spin = QDoubleSpinBox()
        self.invoice_further_tax_spin.setRange(0, 99999999)
        self.invoice_further_tax_spin.valueChanged.connect(self._recalculate_invoice_totals)
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
        reset_btn.clicked.connect(self._on_invoice_reset_clicked)  # type: ignore[arg-type]
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
        """Dashboard-style settings page with category launchers."""
        page = QWidget(self)
        root_layout = QVBoxLayout(page)
        root_layout.setContentsMargins(40, 40, 40, 40)
        root_layout.setSpacing(30)

        header_layout = QHBoxLayout()
        header = QLabel("Settings Dashboard")
        header.setObjectName("pageHeader")
        header.setStyleSheet("font-size: 28px; color: #2c3e50; font-weight: bold;")
        header_layout.addWidget(header)
        header_layout.addStretch(1)
        root_layout.addLayout(header_layout)

        # Grid for settings categories
        grid_container = QWidget()
        grid_layout = QGridLayout(grid_container)
        grid_layout.setSpacing(25)
        
        categories = [
            ("Security & FBR API", "🔒", "Configure FBR credentials, tokens, and environments.", self._open_fbr_security),
            ("Business Preferences", "🏢", "Set tax rules, PCT codes, and business identity.", self._open_business_prefs),
            ("Database Connection", "🗄️", "Manage MySQL server, credentials, and connectivity.", self._open_db_settings),
            ("Backup & Maintenance", "💾", "Schedule backups, restore data, and manage storage.", self._open_backup_settings),
            ("System Updates", "🔄", "Check for software updates and view version info.", self._open_app_updates),
            ("SMS & Whatsapp Features", "💬", "Configure SMS gateways, WhatsApp, and bulk campaigns.", self._open_sms_settings),
            ("Address Shortcodes", "⌨️", "Manage address shortcuts for faster data entry.", self._open_address_shortcodes),
            ("Urdu Font", "ا", "Enable Urdu Noori Nastaleeq font for Urdu text entry.", self._open_urdu_font_settings),
            ("Font Customization", "🔤", "Customize fonts and sizes for UI and sidebar (accessibility).", self._open_font_customization),
            ("DMS Portal Automation", "🤖", "Configure DMS portal credentials and site URL for automation.", self._open_dms_settings),
        ]

        for i, (title, icon, desc, callback) in enumerate(categories):
            card = QFrame()
            card.setObjectName("formGroup")
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.setStyleSheet("""
                QFrame#formGroup {
                    background-color: white;
                    border: 1px solid #e0e0e0;
                    border-radius: 12px;
                    padding: 20px;
                }
                QFrame#formGroup:hover {
                    border: 1px solid #3498db;
                    background-color: #f8fbff;
                }
            """)
            
            card_layout = QVBoxLayout(card)
            
            icon_lbl = QLabel(icon)
            icon_lbl.setStyleSheet("font-size: 36px; margin-bottom: 5px;")
            card_layout.addWidget(icon_lbl)
            
            title_lbl = QLabel(title)
            title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50;")
            card_layout.addWidget(title_lbl)
            
            desc_lbl = QLabel(desc)
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet("color: #7f8c8d; font-size: 13px; margin-top: 5px;")
            card_layout.addWidget(desc_lbl)
            
            card_layout.addStretch(1)
            
            # Make card clickable
            card.mousePressEvent = lambda e, cb=callback: cb()
            
            grid_layout.addWidget(card, i // 3, i % 3)

        root_layout.addWidget(grid_container)
        root_layout.addStretch(1)

        return page

    def _create_dms_automation_page(self) -> QWidget:
        return DMSAutomationPage(self)

    def _open_fbr_security(self):
        dialog = FBRSecurityDialog(self)
        dialog.exec()

    def _open_business_prefs(self):
        dialog = BusinessPreferencesDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Refresh branding if business name changed
            active_settings = settings_service.get_active_settings()
            self._update_app_branding(active_settings.get("business_name", "Ehsan Trader"))

    def _open_db_settings(self):
        dialog = DatabaseSettingsDialog(self)
        dialog.exec()

    def _open_backup_settings(self):
        dialog = BackupSettingsDialog(self)
        dialog.exec()

    def _open_app_updates(self):
        dialog = AppUpdatesDialog(self)
        dialog.exec()

    def _open_sms_settings(self):
        dialog = SMSConfigDialog(self)
        dialog.exec()

    def _open_address_shortcodes(self):
        dialog = AddressShortcodeDialog(self)
        dialog.exec()

    def _open_urdu_font_settings(self):
        dialog = UrduFontDialog(self)
        dialog.exec()

    def _open_font_customization(self):
        dialog = FontCustomizationDialog(self)
        dialog.exec()

    def _open_dms_settings(self):
        dialog = DMSSettingsDialog(self)
        dialog.exec()

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

        scroll = PanScrollArea()
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
        scroll = PanScrollArea()
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

        # Booking SMS Template
        template_layout.addSpacing(10)
        template_layout.addWidget(QLabel("Booking SMS Template:"))
        self.sms_booking_template = QTextEdit()
        self.sms_booking_template.setMaximumHeight(80)
        self.sms_booking_template.setPlaceholderText("Enter message template... (Placeholders: {customer}, {model}, {color}, {booking_no})")
        self.sms_booking_template.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.sms_booking_template.setStyleSheet("""
            QTextEdit {
                font-family: 'Jameel Noori Nastaleeq', 'Urdu Typesetting', 'Tahoma', 'Arial';
                font-size: 18px;
                line-height: 1.6;
                padding: 10px;
                border: 1px solid #ced4da;
                border-radius: 4px;
            }
        """)
        template_layout.addWidget(self.sms_booking_template)
        
        booking_template_hint = QLabel("Placeholders: {customer}, {model}, {color}, {booking_no}, {paid}, {balance}")
        booking_template_hint.setStyleSheet("color: #7f8c8d; font-size: 11px; font-style: italic;")
        template_layout.addWidget(booking_template_hint)

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
        
        # Channel Selection
        channel_layout = QHBoxLayout()
        channel_layout.addWidget(QLabel("Select Channel:"))
        self.bulk_channel_selector = QComboBox()
        self.bulk_channel_selector.addItems(["SMS"])
        self.bulk_channel_selector.setFixedHeight(35)
        self.bulk_channel_selector.setStyleSheet("""
            QComboBox { font-weight: bold; padding-left: 10px; }
            QComboBox:item:selected { background-color: #3498db; color: white; }
        """)
        channel_layout.addWidget(self.bulk_channel_selector)
        channel_layout.addStretch(1)
        start_layout.addLayout(channel_layout)
        
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

    def _create_whatsapp_page(self) -> QWidget:
        """Creates the WhatsApp management page using the WhatsAppCampaignWidget."""
        return WhatsAppCampaignWidget()

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
        channel = self.bulk_channel_selector.currentText()
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
        
        campaign_name, ok = QInputDialog.getText(self, "Campaign Name", f"Enter a name for this {channel} campaign:")
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
                self._current_bulk_data,
                channel=channel
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
        from openpyxl import Workbook

        file_path, _ = QFileDialog.getSaveFileName(self, "Save Template File", "sms_template.xlsx", "Excel Files (*.xlsx)")

        if file_path:
            try:
                headers = ["phone", "name", "reg_no", "custom_field_1", "custom_field_2"]
                sample_rows = [
                    ["03001234567", "John Doe", "ABC-123", "Value1", "ValueA"],
                    ["03219876543", "Jane Smith", "XYZ-789", "Value2", "ValueB"],
                ]

                wb = Workbook()
                ws = wb.active
                ws.title = "Sheet1"
                ws.append(headers)
                for row in sample_rows:
                    ws.append(row)
                wb.save(file_path)

                self._show_success("Template Saved", f"The SMS template has been saved to:\n{file_path}")

            except Exception as e:
                self._show_error("Save Error", f"Failed to save the template file: {e}")
                logger.error(f"Error saving SMS template: {e}", exc_info=True)

    def _reload_sms_campaigns(self):
        """Reloads campaigns list from database."""
        # Preserve current selection before reload
        selected_ids = set()
        try:
            selection_model = self.campaigns_table_view.selectionModel()
            selected_rows = selection_model.selectedRows()
            for index in selected_rows:
                row_idx = index.row()
                if 0 <= row_idx < len(self.campaigns_table_model._rows):
                    selected_ids.add(self.campaigns_table_model._rows[row_idx].id)
        except Exception as e:
            logger.debug(f"Could not preserve campaign selection: {e}")

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
                     channel=getattr(c, 'channel', 'SMS'),
                     error_message=c.error_message
                 ) for c in campaigns
             ]
            
            self.campaigns_table_model.update_rows(rows)

            # Restore selection after reload
            if selected_ids:
                def restore_selection():
                    selection_model = self.campaigns_table_view.selectionModel()
                    for i, row in enumerate(self.campaigns_table_model._rows):
                        if row.id in selected_ids:
                            index = self.campaigns_table_model.index(i, 0)
                            selection_model.select(index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
                
                # Use QTimer to ensure selection happens after view updates
                QTimer.singleShot(0, restore_selection)
            
        except Exception as e:
            logger.error(f"Error reloading campaigns: {e}")
        finally:
            db.close()

    def _on_delete_campaign(self):
        """Deletes the selected campaign(s) after confirmation."""
        from app.services.bulk_sms_service import bulk_sms_service
        
        selected = self.campaigns_table_view.selectionModel().selectedRows()
        if not selected:
            QMessageBox.warning(self, "Selection Required / انتخاب ضروری ہے", "Please select one or more campaigns to delete.")
            return
            
        campaigns_to_delete = []
        for index in selected:
            row_idx = index.row()
            if 0 <= row_idx < len(self.campaigns_table_model._rows):
                campaigns_to_delete.append(self.campaigns_table_model._rows[row_idx])

        if len(campaigns_to_delete) == 1:
            msg = f"Are you sure you want to delete campaign '{campaigns_to_delete[0].name}'?"
        else:
            msg = f"Are you sure you want to delete {len(campaigns_to_delete)} selected campaigns?"

        reply = QMessageBox.question(self, "Confirm Delete / تصدیق کریں", 
                                   f"{msg}\n\n"
                                   "This will also delete all message history for the selected campaign(s).",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                                   
        if reply == QMessageBox.StandardButton.Yes:
            success_count = 0
            for campaign in campaigns_to_delete:
                try:
                    if bulk_sms_service.delete_campaign(campaign.id):
                        success_count += 1
                except Exception as e:
                    logger.error(f"Error deleting campaign {campaign.id}: {e}")

            if success_count > 0:
                self._reload_sms_campaigns()
                self._show_success("Deleted / حذف کر دیا گیا", f"{success_count} campaign(s) have been deleted.")
            
            if success_count < len(campaigns_to_delete):
                self._show_error("Error / غلطی", f"Failed to delete {len(campaigns_to_delete) - success_count} campaign(s).")

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
            self.sms_booking_template.setPlainText(getattr(config, 'booking_template', '') or "")
                    
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
            config.invoice_template = self.sms_invoice_template.toPlainText().strip()
            config.booking_template = self.sms_booking_template.toPlainText().strip()
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
                border-right: 1px solid #f1f1f1;
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
                border-right: 1px solid #e9ecef;
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
        # Install Auto Scroll Manager
        self.inventory_table_auto_scroll = AutoScrollManager(self)
        self.inventory_table_auto_scroll.install_on_widget(self.inventory_table_view)
        
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
        # Install Auto Scroll Manager
        self.captured_table_auto_scroll = AutoScrollManager(self)
        self.captured_table_auto_scroll.install_on_widget(self.captured_table_view)
        
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
                gridline-color: #e0e0e0; 
                alternate-background-color: #fafafa;
                selection-background-color: #e3f2fd;
                selection-color: #1976d2;
                outline: none;
            }
            QTableView::item {
                padding: 12px;
                border-bottom: 1px solid #e9ecef;
                border-right: 1px solid #e9ecef;
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
                border-right: 1px solid #e9ecef;
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
        self.prices_table_view.setShowGrid(True)
        self.prices_table_view.setGridStyle(Qt.PenStyle.SolidLine)
        self.prices_table_view.doubleClicked.connect(self._on_price_row_double_clicked)
        
        # Resizable Columns
        self.prices_table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.prices_table_view.horizontalHeader().setStretchLastSection(True)
        self.prices_table_view.horizontalHeader().setMinimumSectionSize(80)
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

            rows = query.order_by(ProductModel.model_name, Price.id).all()

            for p in rows:
                color = ""
                opt = getattr(p, "optional_features", None)
                if opt and isinstance(opt, dict):
                    raw = opt.get("colors") or opt.get("color") or ""
                    raw_str = str(raw or "")
                    parts: List[str] = []
                    for part in raw_str.split(","):
                        value = re.sub(r"[^A-Za-z]", "", (part or "")).upper()
                        if value and value not in parts:
                            parts.append(value)
                    color = ", ".join(parts) if parts else ""
                data.append(
                    PriceRow(
                        id=p.id,
                        model=p.product_model.model_name,
                        color=color,
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

            # Color
            form_grid.addWidget(QLabel("Color:"), 1, 0)
            color_input = QLineEdit(row_data.color if row_data else "")
            form_grid.addWidget(color_input, 1, 1)

            color_error = QLabel("")
            color_error.setStyleSheet("color: #e74c3c; font-weight: normal;")
            form_grid.addWidget(color_error, 2, 1)

            def set_color_error(message: str) -> None:
                color_error.setText(message or "")
                if message:
                    color_input.setStyleSheet("border: 1px solid #e74c3c; border-radius: 4px; padding: 8px;")
                else:
                    color_input.setStyleSheet("")

            def _sanitize_color_text(raw: str) -> tuple[str, bool, bool]:
                raw_str = str(raw or "")
                ends_with_comma = raw_str.rstrip().endswith(",")
                filtered = re.sub(r"[^A-Za-z,\\s]", "", raw_str)
                had_invalid = filtered != raw_str
                uppered = "".join((ch.upper() if ch.isalpha() else ch) for ch in filtered)
                collapsed = re.sub(r"\\s+", "", uppered)
                collapsed = re.sub(r",+", ",", collapsed)
                collapsed = collapsed.lstrip(",")
                if ends_with_comma and collapsed and not collapsed.endswith(","):
                    collapsed = f"{collapsed},"
                is_typing_partial = collapsed.endswith(",")
                return collapsed, had_invalid, is_typing_partial

            def parse_colors(raw: str) -> tuple[List[str], bool]:
                normalized, had_invalid, _ = _sanitize_color_text(raw)
                colors: List[str] = []
                for part in normalized.split(","):
                    value = (part or "").strip()
                    if not value:
                        continue
                    if not re.fullmatch(r"[A-Z]+", value):
                        had_invalid = True
                        continue
                    if value not in colors:
                        colors.append(value)
                return colors, had_invalid

            def normalize_color_entry() -> None:
                raw = color_input.text() or ""
                normalized, had_invalid, is_typing_partial = _sanitize_color_text(raw)
                if normalized != raw:
                    color_input.blockSignals(True)
                    color_input.setText(normalized)
                    color_input.blockSignals(False)
                if had_invalid:
                    set_color_error("Use comma-separated colors with letters A-Z only (e.g., RED,BLACK,BLUE). Invalid characters were removed.")
                else:
                    set_color_error("")

            color_input.textChanged.connect(normalize_color_entry)
            normalize_color_entry()

            # Base Price
            form_grid.addWidget(QLabel("Base Price:"), 3, 0)
            base_input = QLineEdit(str(row_data.base_price) if row_data else "0")
            form_grid.addWidget(base_input, 3, 1)

            # Sales Tax
            form_grid.addWidget(QLabel("Sales Tax:"), 4, 0)
            tax_input = QLineEdit(str(row_data.tax) if row_data else "0")
            form_grid.addWidget(tax_input, 4, 1)

            # Further Tax
            form_grid.addWidget(QLabel("Further Tax/Levy:"), 5, 0)
            levy_input = QLineEdit(str(row_data.levy) if row_data else "0")
            form_grid.addWidget(levy_input, 5, 1)

            # Total Price (Auto calculated)
            form_grid.addWidget(QLabel("Total Price:"), 6, 0)
            total_lbl = QLabel(f"Rs. {row_data.total:,.2f}" if row_data else "Rs. 0.00")
            total_lbl.setStyleSheet("color: #27ae60; font-size: 16px;")
            form_grid.addWidget(total_lbl, 6, 1)

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
                colors, _ = parse_colors(color_input.text() or "")
                if not colors:
                    QMessageBox.warning(dialog, "Validation Error", "Color is required. Enter one or more colors separated by commas (e.g., RED,BLACK,BLUE).")
                    return
                colors_str = ",".join(colors)

                b = float(base_input.text() or 0)
                t = float(tax_input.text() or 0)
                l = float(levy_input.text() or 0)
                model_id = model_combo.currentData()
                
                # If editing, expire old price and create new one (Audit trail)
                now = dt.datetime.utcnow()
                if row_data:
                    old_price = db.query(Price).filter(Price.id == row_data.id).first()
                    if old_price:
                        old_price.expiration_date = now

                active_prices = db.query(Price).filter(
                    Price.product_model_id == model_id,
                    Price.expiration_date.is_(None),
                ).all()
                for ap in active_prices:
                    opt = getattr(ap, "optional_features", None)
                    ap_colors: List[str] = []
                    if opt and isinstance(opt, dict):
                        raw = opt.get("colors") or opt.get("color") or ""
                        raw_str = str(raw or "")
                        for part in raw_str.split(","):
                            value = re.sub(r"[^A-Za-z]", "", (part or "")).upper()
                            if value and value not in ap_colors:
                                ap_colors.append(value)
                    if any(c in colors for c in ap_colors):
                        ap.expiration_date = now
                
                new_price = Price(
                    product_model_id=model_id,
                    base_price=b,
                    tax_amount=t,
                    levy_amount=l,
                    total_price=b + t + l,
                    optional_features={"color": colors_str, "colors": colors_str},
                    effective_date=now
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
            
            # Use current price if available, but respect manual overrides if focused
            if self._invoice_current_price:
                tax_per_unit = float(getattr(self._invoice_current_price, "tax_amount", 0) or 0)
                further_per_unit = float(getattr(self._invoice_current_price, "levy_amount", 0) or 0)
                
                # Fallback: If levy is 0 in DB, calculate 3% further tax
                if further_per_unit == 0 and amount_excl > 0:
                    further_per_unit = (amount_excl * 3.0) / 100.0
                    logger.debug(f"Applied 3% fallback further tax: {further_per_unit}")

                tax_charged = tax_per_unit * qty
                total_further_tax = further_per_unit * qty
            else:
                settings = settings_service.get_active_settings()
                tax_rate = float(settings.get("tax_rate", 18.0))
                sale_value = amount_excl * qty
                tax_charged = (sale_value * tax_rate) / 100.0
                
                # Default further tax logic for manual entry or missing price records
                # If no price record exists, default to 3% further tax if the field is currently 0.
                # Otherwise, preserve the user's manual entry.
                current_val = float(self.invoice_further_tax_spin.value())
                if current_val == 0 and sale_value > 0:
                    total_further_tax = round((sale_value * 3.0) / 100.0, 2)
                else:
                    total_further_tax = current_val

            # Manual override prioritization:
            # If a spin box is focused AND the signal sender is NOT the spin box itself
            # (to avoid overwriting what user is currently typing)
            sender = self.sender()
            
            if focused is self.invoice_tax_spin or sender is self.invoice_tax_spin:
                tax_charged = float(self.invoice_tax_spin.value())
            
            if focused is self.invoice_further_tax_spin or sender is self.invoice_further_tax_spin:
                total_further_tax = float(self.invoice_further_tax_spin.value())

            sale_value_total = amount_excl * qty
            total_amount = sale_value_total + tax_charged + total_further_tax
            
            # Update UI components safely - only update if the value changed and it's not the sender
            if sender is not self.invoice_tax_spin:
                self.invoice_tax_spin.blockSignals(True)
                self.invoice_tax_spin.setValue(tax_charged)
                self.invoice_tax_spin.blockSignals(False)
                
            if sender is not self.invoice_further_tax_spin:
                self.invoice_further_tax_spin.blockSignals(True)
                self.invoice_further_tax_spin.setValue(total_further_tax)
                self.invoice_further_tax_spin.blockSignals(False)
                
            if sender is not self.invoice_total_spin:
                self.invoice_total_spin.blockSignals(True)
                self.invoice_total_spin.setValue(total_amount)
                self.invoice_total_spin.blockSignals(False)
                
        except Exception as e:
            logger.error(f"Error recalculating totals: {e}")
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
            # Subquery to find already uploaded motorcycles
            uploaded_motorcycle_ids = db.query(InvoiceItem.motorcycle_id).join(Invoice).filter(
                Invoice.is_fiscalized == True,
                InvoiceItem.motorcycle_id.isnot(None)
            ).subquery()

            # Search in Motorcycle Inventory - EXCLUDE already uploaded
            results = db.query(Motorcycle.chassis_number).filter(
                Motorcycle.status == "IN_STOCK",
                Motorcycle.chassis_number.ilike(f"%{query_text}%"),
                ~Motorcycle.id.in_(uploaded_motorcycle_ids)
            ).limit(10).all()
            
            suggestions = [r[0] for r in results]
            
            # Also search in Captured Data - EXCLUDE already uploaded
            # To exclude from captured data, we need to check if the captured chassis 
            # matches any chassis already in fiscalized invoices
            uploaded_chassis = db.query(Motorcycle.chassis_number).join(InvoiceItem).join(Invoice).filter(
                Invoice.is_fiscalized == True
            ).subquery()

            captured_results = db.query(CapturedData.chassis_number).filter(
                CapturedData.is_deleted == False,
                CapturedData.chassis_number.ilike(f"%{query_text}%"),
                ~CapturedData.chassis_number.in_(uploaded_chassis)
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
            # Backend Check: Is this chassis already uploaded to FBR?
            # We check InvoiceItem joined with Invoice to see if it's fiscalized
            from app.db.models import Invoice, InvoiceItem
            already_uploaded = db.query(InvoiceItem).join(Invoice).filter(
                InvoiceItem.motorcycle_id.in_(
                    db.query(Motorcycle.id).filter(Motorcycle.chassis_number == chassis)
                ),
                Invoice.is_fiscalized == True
            ).first()

            if already_uploaded:
                QMessageBox.critical(self, "Duplicate Upload / ڈپلیکیٹ اپ لوڈ", 
                                   f"This Chassis number {chassis} is already uploaded to FBR.\n"
                                   f"FBR Invoice: {already_uploaded.invoice.fbr_invoice_number}")
                self.invoice_chassis_input.clear()
                return

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
                
                # Update current price for tax calculations
                if bike.product_model and bike.color:
                    from app.services.price_service import price_service
                    self._invoice_current_price = price_service.get_price_by_model_and_color(
                        bike.product_model.model_name, bike.color
                    )

                if bike.sale_price:
                    self.invoice_amount_spin.setValue(float(bike.sale_price))
                
                self._recalculate_invoice_totals()
            
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
            
        self._recalculate_invoice_totals()
        self._check_invoice_form_completeness()

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

        self._recalculate_invoice_totals()
        self._check_invoice_form_completeness()

    def _on_invoice_ntn_changed(self, text: str) -> None:
        ntn = text.strip()
        if not ntn:
            return
        db = SessionLocal()
        try:
            customer = db.query(Customer).filter(Customer.ntn == ntn).first()
            if customer:
                # Update dealer status based on customer type
                from app.db.models import CustomerType
                self._is_dealer_selected = (customer.type == CustomerType.DEALER)
                self._recalculate_invoice_totals()
                self._check_invoice_form_completeness()
        except Exception:
            pass
        finally:
            db.close()

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
            
            # Update dealer status based on customer type
            from app.db.models import CustomerType
            self._is_dealer_selected = (customer.type == CustomerType.DEALER)
            self._recalculate_invoice_totals()
            self._check_invoice_form_completeness()
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
        chassis_upper = chassis.strip().upper()
        db_check = SessionLocal()
        try:
            if invoice_service.is_chassis_uploaded_to_fbr(db_check, chassis_upper):
                from app.db.models import Invoice, InvoiceItem, Motorcycle
                inv = (
                    db_check.query(Invoice)
                    .join(InvoiceItem)
                    .join(Motorcycle, InvoiceItem.motorcycle_id == Motorcycle.id)
                    .filter(Motorcycle.chassis_number == chassis_upper, Invoice.is_fiscalized == True)
                    .order_by(Invoice.datetime.desc())
                    .first()
                )
                fbr_id = inv.fbr_invoice_number if inv else None
                detail = f"\n\nFBR Invoice: {fbr_id}" if fbr_id else ""
                self._show_error(
                    "Duplicate Chassis Detected",
                    f"Chassis number {chassis_upper} has already been uploaded to FBR and cannot be submitted again.{detail}",
                )
                return False
            from app.db.models import Motorcycle
            bike = db_check.query(Motorcycle).filter(Motorcycle.chassis_number == chassis_upper).first()
            if not bike or (bike.status or "").upper() != "IN_STOCK":
                self.invoice_fbr_label.setText("Out-of-stock chassis detected: will still submit to FBR and auto-create SOLD inventory on success.")
        finally:
            db_check.close()
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
        if not self.invoice_submit_btn.isEnabled():
            logger.warning("Duplicate _submit_invoice call prevented (button already disabled).")
            return

        if not self._validate_invoice_form():
            return
        
        # Disable button during submission to prevent double-clicks
        self.invoice_submit_btn.setEnabled(False)
        self.invoice_submit_btn.setText("⏳ Submitting...")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
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
        
        inv_data = InvoiceCreate(
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

        # Start background worker
        self._submission_worker = InvoiceSubmissionWorker(inv_data)
        self._submission_worker.finished.connect(self._handle_submission_success)
        self._submission_worker.error.connect(self._handle_submission_error)
        self._submission_worker.start()

    def _handle_submission_success(self, invoice_id: int) -> None:
        """Called when background invoice submission succeeds."""
        QApplication.restoreOverrideCursor()
        self.invoice_submit_btn.setEnabled(True)
        self.invoice_submit_btn.setText("Submit to FBR")
        
        # Fetch the invoice in the main thread's session to avoid threading issues
        db = SessionLocal()
        try:
            # We eager load customer and items to avoid lazy load issues during UI/Print
            created = db.query(Invoice).options(
                joinedload(Invoice.customer),
                joinedload(Invoice.items).joinedload(InvoiceItem.motorcycle)
            ).filter(Invoice.id == invoice_id).first()
            
            if not created:
                self._show_error("System Error", "Invoice was created but could not be retrieved from database.")
                return

            inv_num = created.invoice_number
            fbr_id = created.fbr_invoice_number
            
            if fbr_id:
                title = "Submission Success"
                msg = f"Invoice {inv_num} has been successfully created and uploaded to FBR.\n\nFBR ID: {fbr_id}"
            else:
                title = "Local Save Success"
                msg = f"Invoice {inv_num} has been created locally but FBR sync failed.\n\n{created.fbr_response_message}\n\nYou can retry the sync later from the reports section."

            self._show_success(title, msg)
            
            self._clear_invoice_form_after_submission()
            self._update_fbr_submitted_counter()
            
            # Queue SMS if enabled
            try:
                from app.services.sms_service import sms_service
                sms_service.queue_invoice_sms(db, created)
                db.commit()
                threading.Thread(target=sms_service.process_queue, daemon=True).start()
            except Exception as e:
                logger.error(f"Error queuing SMS: {e}")

            if created.fbr_invoice_number:
                self.invoice_fbr_number_display.setText(f"FBR INV: {created.fbr_invoice_number}")
                self._display_invoice_qr(created.fbr_invoice_number)
            else:
                self.invoice_fbr_number_display.setText("FBR SYNC PENDING")
        except Exception as e:
            logger.error(f"Error in _handle_submission_success: {e}", exc_info=True)
            self._show_error("UI Error", f"Error updating UI after submission: {e}")
        finally:
            db.close()
            self._check_invoice_form_completeness()

    def _handle_submission_error(self, error_msg: str) -> None:
        """Called when background invoice submission fails."""
        QApplication.restoreOverrideCursor()
        self.invoice_submit_btn.setEnabled(True)
        self.invoice_submit_btn.setText("Submit to FBR")
        
        logger.error(f"FBR submission error caught in UI: {error_msg}")
        
        # Check if it's a known FBR connection error to show friendly message
        if "ConnectionError" in error_msg or "Timeout" in error_msg:
            msg = "Could not connect to FBR server. Check internet connection or FBR URL settings."
        else:
            msg = f"Submission failed: {error_msg}"
            
        self._show_error("Submission Error", msg)
        self._check_invoice_form_completeness()

    def _reset_invoice_form(self) -> None:
        self._is_dealer_selected = False
        self._invoice_current_price = None
        if hasattr(self, "invoice_preserve_info_checkbox"):
            self.invoice_preserve_info_checkbox.setChecked(False)
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
        self.invoice_fbr_number_display.setText("")
        self._display_invoice_qr(None)
        self._check_invoice_form_completeness()

    def _clear_invoice_form_after_submission(self) -> None:
        preserve = False
        if hasattr(self, "invoice_preserve_info_checkbox"):
            preserve = self.invoice_preserve_info_checkbox.isChecked()
        if not preserve:
            self._reset_invoice_form()
            self._generate_invoice_number()
            return

        self._invoice_current_price = None
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
        self.invoice_fbr_number_display.setText("")
        self._display_invoice_qr(None)
        self._generate_invoice_number()
        self._check_invoice_form_completeness()

    def _on_invoice_reset_clicked(self) -> None:
        self._reset_invoice_form()
        self._generate_invoice_number()

    def _handle_post_submission_print(self, invoice: Invoice) -> None:
        """Independent print handler that offers printing options without blocking UI."""
        msg = QMessageBox(self)
        msg.setWindowTitle("Print Options")
        msg.setText("Invoice created successfully! Would you like to print now?")
        msg.setIcon(QMessageBox.Icon.Question)
        
        print_invoice_btn = msg.addButton("Print Invoice", QMessageBox.ButtonRole.ActionRole)
        print_letter_btn = msg.addButton("Print Authority Letter", QMessageBox.ButtonRole.ActionRole)
        cancel_btn = msg.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        
        msg.exec()
        
        clicked = msg.clickedButton()
        if clicked == print_invoice_btn:
            self._print_invoice_standalone(invoice)
        elif clicked == print_letter_btn:
            self._print_authority_letter_standalone(invoice)

    def _print_invoice_standalone(self, invoice: Invoice, overrides: Dict[str, str] | None = None) -> None:
        """Populates and displays the standalone invoice print template."""
        try:
            o = overrides or {}
            items = []
            total = 0.0
            model_override = o.get("model", "").strip()
            color_override = o.get("color", "").strip()
            for idx, item in enumerate(invoice.items):
                bike = item.motorcycle
                sale_value = float(getattr(item, "sale_value", 0.0) or 0.0)
                sales_tax = float(getattr(item, "tax_charged", 0.0) or 0.0)
                levy = float(getattr(item, "further_tax", 0.0) or 0.0)
                line_total = sale_value + sales_tax + levy
                model_value = bike.model if bike else item.item_name
                color_value = bike.color if bike else "-"
                if idx == 0 and model_override:
                    model_value = model_override
                if idx == 0 and color_override:
                    color_value = color_override
                items.append({
                    "description": item.item_name,
                    "model": model_value,
                    "color": color_value,
                    "chassis": bike.chassis_number if bike else "-",
                    "engine": bike.engine_number if bike else "-",
                    "sale_value": f"{sale_value:,.0f}",
                    "sales_tax": f"{sales_tax:,.0f}",
                    "levy": f"{levy:,.0f}",
                    "total_line": f"{line_total:,.0f}",
                    "price": f"{line_total:,.0f}",
                })
                total += line_total

            # Generate QR Base64
            qr_base64 = (o.get("qr_code_base64") or "").strip()
            fbr_invoice_number = (o.get("fbr_invoice_number") or invoice.fbr_invoice_number or "PENDING").strip()
            if not qr_base64 and fbr_invoice_number and fbr_invoice_number != "PENDING":
                qr = qrcode.QRCode(version=1, box_size=10, border=2)
                qr.add_data(fbr_invoice_number)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                buffered = io.BytesIO()
                img.save(buffered, format="PNG")
                qr_base64 = base64.b64encode(buffered.getvalue()).decode()

            cust = invoice.customer
            date_value: object = invoice.datetime
            if (o.get("date") or "").strip():
                date_value = o["date"].strip()
            data = {
                "invoice_number": (o.get("invoice_number") or invoice.invoice_number or "").strip(),
                "date": date_value,
                "customer_name": (o.get("customer_name") or (cust.name if cust else "-") or "-").strip(),
                "father_name": (o.get("father_name") or (cust.father_name if cust else "-") or "-").strip(),
                "relation_prefix": (o.get("relation_prefix") or "S/O").strip(),
                "customer_cnic": (o.get("customer_cnic") or (cust.cnic if cust else "-") or "-").strip(),
                "customer_phone": (cust.phone if cust else "-") or "-",
                "customer_address": (o.get("customer_address") or (cust.address if cust else "-") or "-").strip(),
                "customer_ntn": (cust.ntn if cust else "-") or "-",
                "items": items,
                "total_amount": f"{total:,.0f}",
                "registration_letter_no": str(invoice.id or ""),
                "fbr_invoice_number": fbr_invoice_number,
                "qr_code_base64": qr_base64,
            }
            
            html = print_service_v2.render_invoice(data)
            print_service_v2.print_html(html, f"Invoice {invoice.invoice_number}")
        except Exception as e:
            logger.error(f"Standalone print failed: {e}", exc_info=True)
            self._show_error("Print Error", f"Failed to generate print: {e}")

    def _print_authority_letter_standalone(self, invoice: Invoice, overrides: Dict[str, str] | None = None) -> None:
        """Populates and displays the standalone authority letter template."""
        try:
            o = overrides or {}
            # Take the first item for the letter (standard for vehicle registration)
            item = invoice.items[0] if invoice.items else None
            if not item: return

            bike = item.motorcycle
            cust = invoice.customer
            date_value: object = invoice.datetime
            if (o.get("date") or "").strip():
                date_value = o["date"].strip()
            data = {
                "serial_number": invoice.id,
                "date": date_value,
                "customer_name": (o.get("customer_name") or (cust.name if cust else "-") or "-").strip(),
                "father_name": (o.get("father_name") or (cust.father_name if cust else "-") or "-").strip(),
                "relation_prefix": (o.get("relation_prefix") or "S/O").strip(),
                "customer_cnic": (o.get("customer_cnic") or (cust.cnic if cust else "-") or "-").strip(),
                "customer_address": (o.get("customer_address") or (cust.address if cust else "-") or "-").strip(),
                "product_model": (o.get("model") or (bike.model if bike else item.item_name) or "-").strip(),
                "product_color": (o.get("color") or (bike.color if bike else "-") or "-").strip(),
                "chassis_number": bike.chassis_number if bike else "-",
                "engine_number": bike.engine_number if bike else "-",
                "invoice_number": (o.get("invoice_number") or invoice.invoice_number or "").strip(),
                "manufacturing_year": getattr(bike, "year", None) if bike else None,
            }
            
            html = print_service_v2.render_authority_letter(data)
            print_service_v2.print_html(html, f"Authority Letter - {cust.name if cust else 'Unknown'}")
        except Exception as e:
            logger.error(f"Authority letter print failed: {e}", exc_info=True)
            self._show_error("Print Error", f"Failed to generate authority letter: {e}")

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
        # Install Auto Scroll Manager
        self.customers_table_auto_scroll = AutoScrollManager(self)
        self.customers_table_auto_scroll.install_on_widget(self.customers_table_view)
        
        # Responsive Columns
        self.customers_table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.customers_table_view.horizontalHeader().setStretchLastSection(True)
        self.customers_table_view.verticalHeader().setVisible(False)
        
        table_layout.addWidget(self.customers_table_view)
        layout.addWidget(table_container, 1)

        # Action Buttons
        action_bar = QHBoxLayout()
        action_bar.setSpacing(15)

        add_btn = QPushButton("＋ Add Customer")
        add_btn.setStyleSheet("background-color: #2ecc71; color: white; border: none; font-weight: bold; padding: 10px 20px; border-radius: 8px;")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._on_add_customer_clicked)
        
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
        action_bar.addWidget(add_btn)
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
        # Install Auto Scroll Manager
        self.dealers_table_auto_scroll = AutoScrollManager(self)
        self.dealers_table_auto_scroll.install_on_widget(self.dealers_table_view)

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

    def _create_advance_booking_page(self) -> QWidget:
        page = PanScrollArea(self)
        page.setWidgetResizable(True)
        page.setFrameShape(QFrame.Shape.NoFrame)
        page.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        page.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        host = QWidget()
        host.setStyleSheet("""
            QWidget { background-color: #f8f9fa; }
            QLabel#pageHeader { font-size: 26px; font-weight: bold; color: #2c3e50; }
            QFrame#card { background-color: white; border: 1px solid #e0e0e0; border-radius: 12px; }
            QLabel.fieldLabel { color: #7f8c8d; font-weight: bold; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; }
            QLineEdit, QComboBox, QDoubleSpinBox { padding: 10px 15px; border: 1px solid #dee2e6; border-radius: 8px; background-color: #ffffff; font-size: 13px; }
            QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus { border: 2px solid #3498db; background-color: #f7fbfe; }
            QPushButton#primaryButton { background-color: #3498db; color: white; border: none; border-radius: 8px; font-weight: bold; padding: 10px 20px; }
            QPushButton#primaryButton:hover { background-color: #2980b9; }
            QPushButton#resetButton { background-color: #f8f9fa; color: #2c3e50; border: 1px solid #dee2e6; border-radius: 8px; font-weight: bold; padding: 10px 20px; }
            QPushButton#resetButton:hover { background-color: #e9ecef; }
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
        page.setWidget(host)

        host_layout = QVBoxLayout(host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.setSpacing(0)

        container = QWidget()
        container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(24, 24, 24, 24)
        container_layout.setSpacing(18)
        host_layout.addWidget(container, 0, Qt.AlignmentFlag.AlignTop)

        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)

        header_v = QVBoxLayout()
        header = QLabel("Motorcycle Advance Booking")
        header.setObjectName("pageHeader")
        header_v.addWidget(header)

        subtitle = QLabel("Create advance bookings and print duplicate receipts (Customer + Showroom copies).")
        subtitle.setStyleSheet("color: #7f8c8d; font-size: 13px;")
        header_v.addWidget(subtitle)

        header_layout.addLayout(header_v)
        header_layout.addStretch(1)
        container_layout.addWidget(header_widget)

        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(15)
        
        # Active Stats
        self.ab_active_count_card = self._create_stat_card("ACTIVE BOOKINGS", "0", "#e67e22")
        self.ab_net_advance_card = self._create_stat_card("NET ADVANCE HELD", "Rs. 0", "#2ecc71")
        self.ab_outstanding_balance_card = self._create_stat_card("PENDING BALANCE", "Rs. 0", "#e74c3c")
        
        # Delivered Stats
        self.ab_delivered_count_card = self._create_stat_card("BIKES DELIVERED", "0", "#3498db")
        self.ab_delivered_value_card = self._create_stat_card("TOTAL DELIVERED VALUE", "Rs. 0", "#2c3e50")
        self.ab_realized_advance_card = self._create_stat_card("REALIZED (ADV+BAL)", "Rs. 0", "#27ae60")
        
        stats_layout.addWidget(self.ab_active_count_card, 1)
        stats_layout.addWidget(self.ab_net_advance_card, 1)
        stats_layout.addWidget(self.ab_outstanding_balance_card, 1)
        stats_layout.addWidget(self.ab_delivered_count_card, 1)
        stats_layout.addWidget(self.ab_delivered_value_card, 1)
        stats_layout.addWidget(self.ab_realized_advance_card, 1)
        stats_widget = QWidget()
        stats_widget.setLayout(stats_layout)
        container_layout.addWidget(stats_widget)

        model_cards_frame = QFrame()
        model_cards_frame.setObjectName("card")
        model_cards_frame.setMinimumHeight(160)
        model_cards_layout = QVBoxLayout(model_cards_frame)
        model_cards_layout.setContentsMargins(15, 12, 15, 12)
        model_cards_layout.setSpacing(10)
        model_title = QLabel("Bookings Counter by Model")
        model_title.setStyleSheet("font-weight: bold; color: #2c3e50;")
        model_cards_layout.addWidget(model_title)

        self.ab_model_cards_host = QWidget()
        self.ab_model_cards_grid = QGridLayout(self.ab_model_cards_host)
        self.ab_model_cards_grid.setContentsMargins(0, 0, 0, 0)
        self.ab_model_cards_grid.setHorizontalSpacing(12)
        self.ab_model_cards_grid.setVerticalSpacing(12)
        self._ab_model_card_widgets: Dict[str, BookingCard] = {} # Store cards by model name
        model_cards_layout.addWidget(self.ab_model_cards_host)
        container_layout.addWidget(model_cards_frame)

        form_card = QFrame()
        form_card.setObjectName("card")
        form_layout = QGridLayout(form_card)
        form_layout.setContentsMargins(25, 20, 25, 20)
        form_layout.setHorizontalSpacing(20)
        form_layout.setVerticalSpacing(14)

        def make_label(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setProperty("class", "fieldLabel")
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return lbl

        form_layout.setColumnStretch(0, 0)
        form_layout.setColumnStretch(1, 1)
        form_layout.setColumnStretch(2, 0)
        form_layout.setColumnStretch(3, 1)

        self.ab_customer_name = QLineEdit()
        self.ab_customer_name.setPlaceholderText("Customer Name")
        self.ab_model_combo = QComboBox()
        self.ab_model_combo.setEditable(False)
        self.ab_model_combo.setPlaceholderText("Select model")
        self.ab_color_combo = QComboBox()
        self.ab_color_combo.setEditable(False)
        self.ab_color_combo.setPlaceholderText("Select color")

        def force_upper(le: QLineEdit) -> None:
            t = le.text()
            up = to_uppercase_preserving(t)
            if up != t:
                pos = le.cursorPosition()
                le.blockSignals(True)
                le.setText(up)
                le.setCursorPosition(pos)
                le.blockSignals(False)

        self.ab_customer_name.textChanged.connect(lambda: force_upper(self.ab_customer_name))
        self.ab_model_combo.currentTextChanged.connect(self._on_ab_model_changed)  # type: ignore[arg-type]
        self.ab_color_combo.currentTextChanged.connect(self._on_ab_color_changed)  # type: ignore[arg-type]

        self.ab_total_price = QDoubleSpinBox()
        self.ab_total_price.setMaximum(1000000000)
        self.ab_total_price.setDecimals(0)
        self.ab_total_price.setPrefix("Rs. ")
        self.ab_total_price.setValue(0)
        self.ab_total_price.setEnabled(False)

        self.ab_advance_paid = QDoubleSpinBox()
        self.ab_advance_paid.setMaximum(1000000000)
        self.ab_advance_paid.setDecimals(0)
        self.ab_advance_paid.setPrefix("Rs. ")
        self.ab_advance_paid.setValue(0)

        self.ab_balance = QLineEdit()
        self.ab_balance.setReadOnly(True)
        self.ab_balance.setPlaceholderText("Balance Amount")

        def update_balance() -> None:
            total = float(self.ab_total_price.value())
            adv = float(self.ab_advance_paid.value())
            bal = total - adv
            self.ab_balance.setText(f"Rs. {bal:,.0f}")

        self.ab_total_price.valueChanged.connect(update_balance)
        self.ab_advance_paid.valueChanged.connect(update_balance)
        update_balance()

        form_layout.addWidget(make_label("Customer Name"), 0, 0)
        form_layout.addWidget(self.ab_customer_name, 0, 1)
        form_layout.addWidget(make_label("Customer Phone"), 0, 2)
        self.ab_customer_phone = QLineEdit()
        self.ab_customer_phone.setPlaceholderText("03xxxxxxxxx")
        form_layout.addWidget(self.ab_customer_phone, 0, 3)

        form_layout.addWidget(make_label("Motorcycle Model"), 1, 0)
        form_layout.addWidget(self.ab_model_combo, 1, 1)
        form_layout.addWidget(make_label("Color"), 1, 2)
        form_layout.addWidget(self.ab_color_combo, 1, 3)

        form_layout.addWidget(make_label("Total Price"), 2, 0)
        form_layout.addWidget(self.ab_total_price, 2, 1)
        form_layout.addWidget(make_label("Advance Paid"), 2, 2)
        form_layout.addWidget(self.ab_advance_paid, 2, 3)

        form_layout.addWidget(make_label("Balance Amount"), 3, 0)
        form_layout.addWidget(self.ab_balance, 3, 1)

        btn_bar = QHBoxLayout()
        btn_bar.addStretch(1)

        save_btn = QPushButton("💾 Save Booking & Print")
        save_btn.setObjectName("primaryButton")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self._save_advance_booking)

        delivered_btn = QPushButton("✅ Mark Delivered")
        delivered_btn.setObjectName("resetButton")
        delivered_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delivered_btn.clicked.connect(self._mark_selected_booking_delivered)

        active_btn = QPushButton("↩ Mark Active")
        active_btn.setObjectName("resetButton")
        active_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        active_btn.clicked.connect(self._mark_selected_booking_active)

        refresh_btn = QPushButton("↻ Refresh")
        refresh_btn.setObjectName("resetButton")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self._refresh_advance_booking_page)

        cancel_btn = QPushButton("❌ Cancel Booking")
        cancel_btn.setObjectName("resetButton")
        cancel_btn.setStyleSheet("""QPushButton#resetButton { background-color: #e74c3c; color: white; } 
                                   QPushButton#resetButton:hover { background-color: #c0392b; }""")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self._cancel_selected_booking)

        print_btn = QPushButton("🖨️ Print Selected")
        print_btn.setObjectName("resetButton")
        print_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        print_btn.clicked.connect(self._print_selected_advance_booking)

        btn_bar.addWidget(print_btn)
        btn_bar.addWidget(delivered_btn)
        btn_bar.addWidget(active_btn)
        btn_bar.addWidget(cancel_btn)
        btn_bar.addWidget(refresh_btn)
        btn_bar.addWidget(save_btn)

        form_layout.addLayout(btn_bar, 4, 0, 1, 4)
        container_layout.addWidget(form_card)

        filter_card = QFrame()
        filter_card.setObjectName("card")
        filter_layout = QHBoxLayout(filter_card)
        filter_layout.setContentsMargins(15, 12, 15, 12)
        filter_layout.setSpacing(12)

        self.ab_search_input = QLineEdit()
        self.ab_search_input.setPlaceholderText("Search booking # / customer / model / color")
        self.ab_search_input.textChanged.connect(self._reload_advance_bookings)

        self.ab_status_filter = QComboBox()
        self.ab_status_filter.addItems(["ALL", "ACTIVE", "DELIVERED", "CANCELLED"])
        self.ab_status_filter.currentTextChanged.connect(self._reload_advance_bookings)  # type: ignore[arg-type]

        filter_layout.addWidget(QLabel("Filter:"))
        filter_layout.addWidget(self.ab_search_input, 1)
        filter_layout.addWidget(QLabel("Status:"))
        filter_layout.addWidget(self.ab_status_filter)
        container_layout.addWidget(filter_card)

        class EnterToNextFilter(QObject):
            def __init__(self, next_widget, on_last, parent_widget):
                super().__init__(parent_widget)
                self.next_widget = next_widget
                self.on_last = on_last
                self.parent_widget = parent_widget

            def eventFilter(self, obj, event):
                if event.type() == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    if self.next_widget:
                        self.next_widget.setFocus()
                    else:
                        self.on_last()
                    return True
                return super().eventFilter(obj, event)

        self.ab_customer_name.installEventFilter(EnterToNextFilter(self.ab_customer_phone, self._save_advance_booking, page))
        self.ab_customer_phone.installEventFilter(EnterToNextFilter(self.ab_model_combo, self._save_advance_booking, page))
        self.ab_model_combo.installEventFilter(EnterToNextFilter(self.ab_color_combo, self._save_advance_booking, page))
        self.ab_color_combo.installEventFilter(EnterToNextFilter(self.ab_advance_paid, self._save_advance_booking, page))
        self.ab_advance_paid.installEventFilter(EnterToNextFilter(None, self._save_advance_booking, page))

        QWidget.setTabOrder(self.ab_customer_name, self.ab_customer_phone)
        QWidget.setTabOrder(self.ab_customer_phone, self.ab_model_combo)
        QWidget.setTabOrder(self.ab_model_combo, self.ab_color_combo)
        QWidget.setTabOrder(self.ab_color_combo, self.ab_advance_paid)

        table_container = QFrame()
        table_container.setObjectName("card")
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(1, 1, 1, 1)

        self.ab_table_model = AdvanceBookingsTableModel()
        self.ab_table_view = QTableView()
        self.ab_table_view.setModel(self.ab_table_model)
        self.ab_table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.ab_table_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.ab_table_view.setAlternatingRowColors(True)
        self.ab_table_view.setShowGrid(False)
        self.ab_table_view.doubleClicked.connect(self._on_advance_booking_double_clicked)
        # Install Auto Scroll Manager
        self.ab_table_auto_scroll = AutoScrollManager(self)
        self.ab_table_auto_scroll.install_on_widget(self.ab_table_view)
        self.ab_table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.ab_table_view.horizontalHeader().setStretchLastSection(True)
        self.ab_table_view.verticalHeader().setVisible(False)
        self.ab_table_view.setMinimumHeight(320)

        table_layout.addWidget(self.ab_table_view)
        container_layout.addWidget(table_container)

        self._load_ab_models()
        self._reload_advance_bookings()
        self.ab_customer_name.setFocus()

        return page

    def _reload_advance_bookings(self) -> None:
        if not hasattr(self, "ab_table_model"):
            return
        db = SessionLocal()
        try:
            status = None
            if hasattr(self, "ab_status_filter"):
                selected = (self.ab_status_filter.currentText() or "").strip().upper()
                if selected and selected != "ALL":
                    status = selected
            search = (self.ab_search_input.text() or "").strip() if hasattr(self, "ab_search_input") else ""

            bookings = advance_booking_service.list_bookings(db, limit=300, status=status, search=search)
            rows: List[AdvanceBookingRow] = []
            for b in bookings:
                rows.append(
                    AdvanceBookingRow(
                        booking_number=b.booking_number,
                        created_at=b.created_at,
                        delivered_at=b.delivered_at,
                        customer_name=b.customer_name,
                        motorcycle_model=b.motorcycle_model,
                        color=b.color,
                        total_price=float(b.total_price or 0.0),
                        advance_paid=float(b.advance_paid or 0.0),
                        balance_amount=float(b.balance_amount or 0.0),
                        delivery_paid=float(b.delivery_paid or 0.0),
                        status=b.status or "",
                    )
                )
            self.ab_table_model.update_rows(rows)
            self._update_advance_booking_stats(db)
        except Exception as e:
            logger.error(f"Advance booking reload failed: {e}", exc_info=True)
            self._show_error("Error", f"Failed to load bookings: {e}")
        finally:
            db.close()

    def _update_advance_booking_stats(self, db: Session) -> None:
        try:
            summary = advance_booking_service.get_summary(db)
            # Active
            if hasattr(self, "ab_active_count_card"):
                self.ab_active_count_card.value_label.setText(str(summary["active_count"]))
            if hasattr(self, "ab_net_advance_card"):
                self.ab_net_advance_card.value_label.setText(f"Rs. {summary['outstanding_advance']:,.0f}")
            if hasattr(self, "ab_outstanding_balance_card"):
                self.ab_outstanding_balance_card.value_label.setText(f"Rs. {summary['outstanding_balance']:,.0f}")
            
            # Delivered
            if hasattr(self, "ab_delivered_count_card"):
                self.ab_delivered_count_card.value_label.setText(str(summary["delivered_count"]))
            if hasattr(self, "ab_delivered_value_card"):
                self.ab_delivered_value_card.value_label.setText(f"Rs. {summary['delivered_total_value']:,.0f}")
            if hasattr(self, "ab_realized_advance_card"):
                # Sum of advance + balance collected for delivered bikes
                total_realized = summary["delivered_advance"] + summary["delivered_balance"]
                self.ab_realized_advance_card.value_label.setText(f"Rs. {total_realized:,.0f}")

            if hasattr(self, "ab_model_cards_grid"):
                counts = advance_booking_service.get_active_counts_by_model(db, limit=12)
                
                # Check if we need to completely rebuild or just update
                current_models = set(self._ab_model_card_widgets.keys())
                new_models = set(m for m, c in counts)
                
                if current_models != new_models:
                    # Clear and rebuild if models changed
                    while self.ab_model_cards_grid.count():
                        item = self.ab_model_cards_grid.takeAt(0)
                        w = item.widget()
                        if w:
                            w.setParent(None)
                    self._ab_model_card_widgets.clear()
                    
                    cols = 4
                    for i, (model_name, count) in enumerate(counts):
                        card = BookingCard(model_name or "-", count, "#3498db")
                        self.ab_model_cards_grid.addWidget(card, i // cols, i % cols)
                        self._ab_model_card_widgets[model_name] = card
                else:
                    # Just update existing cards
                    for model_name, count in counts:
                        if model_name in self._ab_model_card_widgets:
                            self._ab_model_card_widgets[model_name].update_quantity(count)
        except Exception as e:
            logger.error(f"Advance booking stats update failed: {e}", exc_info=True)

    def _refresh_advance_booking_page(self) -> None:
        self._load_ab_models()
        self._reload_advance_bookings()

    def _load_ab_models(self) -> None:
        if not hasattr(self, "ab_model_combo"):
            return

        prices = price_service.get_all_active_prices()
        models: List[str] = []
        for p in prices:
            if p.product_model and p.product_model.model_name and p.product_model.model_name not in models:
                models.append(p.product_model.model_name)

        self.ab_model_combo.blockSignals(True)
        self.ab_model_combo.clear()
        self.ab_model_combo.addItem("")
        for m in models:
            self.ab_model_combo.addItem(m)
        self.ab_model_combo.blockSignals(False)

        self.ab_color_combo.blockSignals(True)
        self.ab_color_combo.clear()
        self.ab_color_combo.addItem("")
        self.ab_color_combo.blockSignals(False)
        self._load_ab_colors_for_model("")

        self._ab_current_price = None
        self.ab_total_price.blockSignals(True)
        self.ab_total_price.setValue(0)
        self.ab_total_price.blockSignals(False)

    def _on_ab_model_changed(self, model_name: str) -> None:
        if not hasattr(self, "ab_color_combo"):
            return
        self._load_ab_colors_for_model(model_name)
        self._update_ab_price()

    def _on_ab_color_changed(self, color: str) -> None:
        self._update_ab_price()

    def _load_ab_colors_for_model(self, model_name: str) -> None:
        if not hasattr(self, "ab_color_combo"):
            return

        self.ab_color_combo.blockSignals(True)
        self.ab_color_combo.clear()
        self.ab_color_combo.addItem("")

        if model_name:
            prices = price_service.get_active_prices_for_model(model_name)
            colors: List[str] = []
            for price in prices:
                opt = getattr(price, "optional_features", None)
                if opt and isinstance(opt, dict):
                    colors_str = opt.get("colors") or opt.get("color") or ""
                    if colors_str:
                        for part in str(colors_str).split(","):
                            value = part.strip()
                            if value and value not in colors:
                                colors.append(value)
            for c in colors:
                self.ab_color_combo.addItem(c)

        self.ab_color_combo.blockSignals(False)

    def _update_ab_price(self) -> None:
        model_name = self.ab_model_combo.currentText() if hasattr(self, "ab_model_combo") else ""
        color = self.ab_color_combo.currentText() if hasattr(self, "ab_color_combo") else ""

        if not model_name or not color:
            self._ab_current_price = None
            self.ab_total_price.blockSignals(True)
            self.ab_total_price.setValue(0)
            self.ab_total_price.blockSignals(False)
            return

        price = price_service.get_price_by_model_and_color(model_name, color)
        self._ab_current_price = price
        self.ab_total_price.blockSignals(True)
        self.ab_total_price.setValue(float(getattr(price, "total_price", 0) or 0) if price else 0)
        self.ab_total_price.blockSignals(False)

    def _save_advance_booking(self) -> None:
        name = (self.ab_customer_name.text() or "").strip()
        phone = (self.ab_customer_phone.text() or "").strip()
        model = (self.ab_model_combo.currentText() or "").strip()
        color = (self.ab_color_combo.currentText() or "").strip()
        total = float(self.ab_total_price.value())
        advance = float(self.ab_advance_paid.value())

        if not name:
            self._show_error("Validation Error", "Customer Name is required.")
            self.ab_customer_name.setFocus()
            return
        
        # Phone validation (optional but recommended for SMS)
        if phone and not (phone.isdigit() and len(phone) >= 10):
            self._show_error("Validation Error", "Please enter a valid phone number (e.g., 03001234567).")
            self.ab_customer_phone.setFocus()
            return

        if not model:
            self._show_error("Validation Error", "Motorcycle Model is required.")
            self.ab_model_combo.setFocus()
            return
        if not color:
            self._show_error("Validation Error", "Color is required.")
            self.ab_color_combo.setFocus()
            return
        if total <= 0:
            self._show_error("Validation Error", "Price is not available for the selected Model/Color. Please update Price List first.")
            self.ab_color_combo.setFocus()
            return
        if advance < 0 or advance > total:
            self._show_error("Validation Error", "Advance Paid must be between 0 and Total Price.")
            self.ab_advance_paid.setFocus()
            return

        db = SessionLocal()
        try:
            booking = advance_booking_service.create_booking(
                db=db,
                customer_name=name,
                customer_phone=phone,
                motorcycle_model=model,
                color=color,
                total_price=total,
                advance_paid=advance,
            )
            html = print_service_v2.render_advance_booking_receipt(
                {
                    "booking_number": booking.booking_number,
                    "created_at": booking.created_at,
                    "customer_name": booking.customer_name,
                    "customer_phone": getattr(booking, "customer_phone", "") or "",
                    "motorcycle_model": booking.motorcycle_model,
                    "color": booking.color,
                    "total_price": booking.total_price,
                    "advance_paid": booking.advance_paid,
                    "balance_amount": booking.balance_amount,
                }
            )
            print_service_v2.print_html_direct(html)
            
            # Real-time state management: Notify all listeners about the booking update
            # We fetch the new active count for this specific model to ensure accuracy
            active_count = db.query(AdvanceBooking).filter(
                AdvanceBooking.motorcycle_model == model,
                AdvanceBooking.status == "ACTIVE"
            ).count()
            booking_signals.booking_updated.emit(model, active_count)
            
            self._reload_advance_bookings()
            self.ab_customer_name.clear()
            self.ab_customer_phone.clear()
            self.ab_model_combo.setCurrentIndex(0)
            self.ab_color_combo.setCurrentIndex(0)
            self.ab_total_price.blockSignals(True)
            self.ab_total_price.setValue(0)
            self.ab_total_price.blockSignals(False)
            self.ab_advance_paid.setValue(0)
            self.ab_customer_name.setFocus()
        except Exception as e:
            logger.error(f"Advance booking save failed: {e}", exc_info=True)
            self._show_error("Error", f"Failed to save booking: {e}")
        finally:
            db.close()

    def _print_selected_advance_booking(self) -> None:
        if not hasattr(self, "ab_table_view"):
            return
        selection_model = self.ab_table_view.selectionModel()
        selection = selection_model.selectedRows()
        if selection:
            row = selection[0].row()
        else:
            current = self.ab_table_view.currentIndex()
            if not current.isValid():
                self._show_error("Selection Required", "Please select a booking to print.")
                return
            row = current.row()
        row_data = self.ab_table_model._rows[row]

        db = SessionLocal()
        try:
            booking = advance_booking_service.get_by_booking_number(db, row_data.booking_number)
            if not booking:
                self._show_error("Error", "Booking not found.")
                return
            html = print_service_v2.render_advance_booking_receipt(
                {
                    "booking_number": booking.booking_number,
                    "created_at": booking.created_at,
                    "customer_name": booking.customer_name,
                    "customer_phone": getattr(booking, "customer_phone", "") or "",
                    "motorcycle_model": booking.motorcycle_model,
                    "color": booking.color,
                    "total_price": booking.total_price,
                    "advance_paid": booking.advance_paid,
                    "balance_amount": booking.balance_amount,
                }
            )
            print_service_v2.print_html(html, title="Advance Booking Receipt")
            self.statusBar().showMessage("Receipt preview opened.", 4000)
        except Exception as e:
            logger.error(f"Advance booking print failed: {e}", exc_info=True)
            self._show_error("Print Error", f"Failed to print receipt: {e}")
        finally:
            db.close()

    def _get_selected_advance_booking_number(self) -> str | None:
        if not hasattr(self, "ab_table_view"):
            return None
        selection_model = self.ab_table_view.selectionModel()
        selection = selection_model.selectedRows()
        if selection:
            row = selection[0].row()
        else:
            current = self.ab_table_view.currentIndex()
            if not current.isValid():
                return None
            row = current.row()
        row_data = self.ab_table_model._rows[row]
        return row_data.booking_number

    def _on_advance_booking_double_clicked(self, index: QModelIndex) -> None:
        """Opens a modal dialog to modify or reprint the selected booking."""
        if not index.isValid():
            return
            
        row_data = self.ab_table_model._rows[index.row()]
        db = SessionLocal()
        try:
            booking = advance_booking_service.get_by_booking_number(db, row_data.booking_number)
            if not booking:
                self._show_error("Error", "Booking not found in database.")
                return

            # Check if current user is showroom staff (for simplicity, we allow modification if status is ACTIVE)
            # You can add more strict role checks here if needed.
            
            dialog = QDialog(self)
            dialog.setWindowTitle(f"Modify Booking - {booking.booking_number}")
            dialog.setFixedWidth(500)
            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(25, 25, 25, 25)
            layout.setSpacing(15)

            # Header
            header = QLabel(f"Modify Booking: {booking.booking_number}")
            header.setStyleSheet("font-size: 18px; font-weight: bold; color: #2c3e50;")
            layout.addWidget(header)

            form_grid = QGridLayout()
            form_grid.setSpacing(10)

            def add_field(row, label_text, widget):
                lbl = QLabel(label_text)
                lbl.setStyleSheet("font-weight: bold; color: #7f8c8d; font-size: 11px;")
                form_grid.addWidget(lbl, row, 0)
                form_grid.addWidget(widget, row, 1)
                return widget

            edit_name = QLineEdit(booking.customer_name)
            edit_phone = QLineEdit(booking.customer_phone or "")
            edit_phone.setPlaceholderText("03xxxxxxxxx")
            
            # Use current models from the system
            edit_model = QComboBox()
            prices = price_service.get_all_active_prices()
            models = sorted(list(set(p.product_model.model_name for p in prices if p.product_model)))
            edit_model.addItems(models)
            edit_model.setCurrentText(booking.motorcycle_model)

            edit_color = QComboBox()
            # Initial colors for selected model
            current_prices = price_service.get_active_prices_for_model(booking.motorcycle_model)
            colors = []
            for p in current_prices:
                opt = p.optional_features or {}
                c_str = opt.get("colors") or opt.get("color") or ""
                for c in str(c_str).split(","):
                    val = c.strip()
                    if val and val not in colors: colors.append(val)
            edit_color.addItems(colors)
            edit_color.setCurrentText(booking.color)

            edit_total = QDoubleSpinBox()
            edit_total.setRange(0, 10000000)
            edit_total.setValue(booking.total_price)
            edit_total.setPrefix("Rs. ")
            edit_total.setDecimals(0)
            edit_total.setEnabled(False) # Price linked to model/color

            edit_advance = QDoubleSpinBox()
            edit_advance.setRange(0, 10000000)
            edit_advance.setValue(booking.advance_paid)
            edit_advance.setPrefix("Rs. ")
            edit_advance.setDecimals(0)

            add_field(0, "Customer Name:", edit_name)
            add_field(1, "Phone Number:", edit_phone)
            add_field(2, "Motorcycle Model:", edit_model)
            add_field(3, "Color:", edit_color)
            add_field(4, "Total Price:", edit_total)
            add_field(5, "Advance Paid:", edit_advance)

            layout.addLayout(form_grid)

            # Logic for updating price when model/color changes
            def update_price():
                p = price_service.get_price_by_model_and_color(edit_model.currentText(), edit_color.currentText())
                if p:
                    edit_total.setValue(float(p.total_price or 0))
                else:
                    edit_total.setValue(0)

            def update_colors(model_name):
                edit_color.blockSignals(True)
                edit_color.clear()
                prices = price_service.get_active_prices_for_model(model_name)
                colors = []
                for p in prices:
                    opt = p.optional_features or {}
                    c_str = opt.get("colors") or opt.get("color") or ""
                    for c in str(c_str).split(","):
                        val = c.strip()
                        if val and val not in colors: colors.append(val)
                edit_color.addItems(colors)
                edit_color.blockSignals(False)
                update_price()

            edit_model.currentTextChanged.connect(update_colors)
            edit_color.currentTextChanged.connect(update_price)

            # Footer buttons
            btn_layout = QHBoxLayout()
            
            reprint_btn = QPushButton("🖨️ Reprint Receipt")
            reprint_btn.setStyleSheet("background-color: #95a5a6; color: white; padding: 10px; border-radius: 5px;")
            
            save_btn = QPushButton("💾 Save Changes")
            save_btn.setStyleSheet("background-color: #3498db; color: white; padding: 10px; border-radius: 5px;")
            
            cancel_btn = QPushButton("Cancel")
            cancel_btn.setStyleSheet("background-color: #e74c3c; color: white; padding: 10px; border-radius: 5px;")
            
            btn_layout.addWidget(reprint_btn)
            btn_layout.addStretch(1)
            btn_layout.addWidget(cancel_btn)
            btn_layout.addWidget(save_btn)
            layout.addLayout(btn_layout)

            # Disable modification if not ACTIVE
            is_active = (booking.status == "ACTIVE")
            if not is_active:
                edit_name.setEnabled(False)
                edit_phone.setEnabled(False)
                edit_model.setEnabled(False)
                edit_color.setEnabled(False)
                edit_advance.setEnabled(False)
                save_btn.setEnabled(False)
                save_btn.setText("Locked (Delivered)")
                save_btn.setStyleSheet("background-color: #bdc3c7; color: white; padding: 10px; border-radius: 5px;")

            def on_reprint():
                html = print_service_v2.render_advance_booking_receipt({
                    "booking_number": booking.booking_number,
                    "created_at": booking.created_at,
                    "customer_name": booking.customer_name,
                    "customer_phone": getattr(booking, "customer_phone", "") or "",
                    "motorcycle_model": booking.motorcycle_model,
                    "color": booking.color,
                    "total_price": booking.total_price,
                    "advance_paid": booking.advance_paid,
                    "balance_amount": booking.balance_amount,
                })
                print_service_v2.print_html_direct(html)
                dialog.accept()

            def on_save():
                try:
                    advance_booking_service.update_booking(
                        db=db,
                        booking_number=booking.booking_number,
                        customer_name=edit_name.text(),
                        customer_phone=edit_phone.text(),
                        motorcycle_model=edit_model.currentText(),
                        color=edit_color.currentText(),
                        total_price=edit_total.value(),
                        advance_paid=edit_advance.value(),
                    )
                    self._reload_advance_bookings()
                    QMessageBox.information(self, "Success", "Booking updated successfully.")
                    dialog.accept()
                except Exception as e:
                    self._show_error("Update Failed", str(e))

            reprint_btn.clicked.connect(on_reprint)
            save_btn.clicked.connect(on_save)
            cancel_btn.clicked.connect(dialog.reject)

            dialog.exec()

        except Exception as e:
            logger.error(f"Error opening booking edit dialog: {e}", exc_info=True)
            self._show_error("Error", f"Could not load booking details: {e}")
        finally:
            db.close()

    def _mark_selected_booking_delivered(self) -> None:
        booking_number = self._get_selected_advance_booking_number()
        if not booking_number:
            self._show_error("Selection Required", "Please select a booking to mark as delivered.")
            return

        db = SessionLocal()
        try:
            booking = advance_booking_service.get_by_booking_number(db, booking_number)
            if not booking:
                self._show_error("Error", "Booking not found.")
                return
            required = float(getattr(booking, "balance_amount", 0.0) or 0.0)

            dialog = QDialog(self)
            dialog.setWindowTitle("Confirm Delivery Payment")
            dialog.setFixedWidth(420)
            dlg_layout = QVBoxLayout(dialog)
            dlg_layout.setContentsMargins(20, 20, 20, 20)
            dlg_layout.setSpacing(12)

            info = QLabel(
                f"<b>Booking:</b> {booking_number}<br/>"
                f"<b>Customer:</b> {booking.customer_name}<br/>"
                f"<b>Model:</b> {booking.motorcycle_model} ({booking.color})<br/>"
                f"<b>Remaining Balance:</b> Rs. {required:,.0f}"
            )
            info.setStyleSheet("color:#2c3e50;")
            dlg_layout.addWidget(info)

            pay_spin = QDoubleSpinBox()
            pay_spin.setDecimals(0)
            pay_spin.setMaximum(1000000000)
            pay_spin.setPrefix("Rs. ")
            pay_spin.setValue(required)
            dlg_layout.addWidget(pay_spin)

            btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            dlg_layout.addWidget(btns)
            btns.accepted.connect(dialog.accept)
            btns.rejected.connect(dialog.reject)

            if dialog.exec() != QDialog.DialogCode.Accepted:
                return

            paid = float(pay_spin.value())
            reply = QMessageBox.question(
                self,
                "Confirm",
                f"Confirm delivery for {booking_number} and record payment Rs. {paid:,.0f}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

            advance_booking_service.mark_delivered(db, booking_number, delivery_paid=paid)
            
            # Real-time state management: Notify all listeners about the delivery update
            # We decrement the count for this specific model
            model = booking.motorcycle_model
            active_count = db.query(AdvanceBooking).filter(
                AdvanceBooking.motorcycle_model == model,
                AdvanceBooking.status == "ACTIVE"
            ).count()
            booking_signals.booking_updated.emit(model, active_count)
            
            self._reload_advance_bookings()
        except Exception as e:
            logger.error(f"Advance booking mark delivered failed: {e}", exc_info=True)
            self._show_error("Error", f"Failed to mark delivered: {e}")
        finally:
            db.close()

    def _mark_selected_booking_active(self) -> None:
        booking_number = self._get_selected_advance_booking_number()
        if not booking_number:
            self._show_error("Selection Required", "Please select a booking to mark as active.")
            return
        reply = QMessageBox.question(
            self,
            "Confirm",
            f"Mark booking {booking_number} as ACTIVE?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        db = SessionLocal()
        try:
            booking = advance_booking_service.get_by_booking_number(db, booking_number)
            if not booking:
                self._show_error("Error", "Booking not found.")
                return
            model = booking.motorcycle_model
            
            advance_booking_service.mark_active(db, booking_number)
            
            # Real-time state management: Notify all listeners about the restoration update
            # Increment the count for this specific model
            active_count = db.query(AdvanceBooking).filter(
                AdvanceBooking.motorcycle_model == model,
                AdvanceBooking.status == "ACTIVE"
            ).count()
            booking_signals.booking_updated.emit(model, active_count)
            
            self._reload_advance_bookings()
        except Exception as e:
            logger.error(f"Advance booking mark active failed: {e}", exc_info=True)
            self._show_error("Error", f"Failed to mark active: {e}")
        finally:
            db.close()

    def _cancel_selected_booking(self) -> None:
        booking_number = self._get_selected_advance_booking_number()
        if not booking_number:
            self._show_error("Selection Required", "Please select a booking to cancel.")
            return
        
        db = SessionLocal()
        try:
            booking = advance_booking_service.get_by_booking_number(db, booking_number)
            if not booking:
                self._show_error("Error", "Booking not found.")
                return
            
            # Create a dialog to get refund amount and note
            dialog = QDialog(self)
            dialog.setWindowTitle("Cancel Booking")
            dialog.setMinimumWidth(400)
            layout = QVBoxLayout(dialog)
            
            # Info label
            info_label = QLabel(f"Customer: {booking.customer_name}\n"
                               f"Total Price: Rs. {booking.total_price:,.0f}\n"
                               f"Advance Remaining: Rs. {booking.advance_remaining:,.0f}")
            info_label.setStyleSheet("padding: 10px; background-color: #f8f9fa; border-radius: 8px;")
            layout.addWidget(info_label)
            
            # Refund amount input
            refund_layout = QHBoxLayout()
            refund_layout.addWidget(QLabel("Refund Amount:"))
            refund_spin = QDoubleSpinBox()
            refund_spin.setMaximum(1000000000)
            refund_spin.setDecimals(0)
            refund_spin.setPrefix("Rs. ")
            refund_spin.setValue(booking.advance_remaining)
            refund_layout.addWidget(refund_spin)
            layout.addLayout(refund_layout)
            
            # Note input
            note_layout = QHBoxLayout()
            note_layout.addWidget(QLabel("Note (optional):"))
            note_input = QLineEdit()
            note_layout.addWidget(note_input)
            layout.addLayout(note_layout)
            
            # Buttons
            btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            btn_box.accepted.connect(dialog.accept)
            btn_box.rejected.connect(dialog.reject)
            layout.addWidget(btn_box)
            
            if dialog.exec() == QDialog.DialogCode.Accepted:
                model = booking.motorcycle_model
                advance_booking_service.cancel_booking(
                    db, 
                    booking_number, 
                    refund_amount=refund_spin.value(), 
                    note=note_input.text()
                )
                
                # Update real-time model count
                active_count = db.query(AdvanceBooking).filter(
                    AdvanceBooking.motorcycle_model == model,
                    AdvanceBooking.status == "ACTIVE"
                ).count()
                booking_signals.booking_updated.emit(model, active_count)
                
                self._reload_advance_bookings()
                
        except Exception as e:
            logger.error(f"Advance booking cancel failed: {e}", exc_info=True)
            self._show_error("Error", f"Failed to cancel booking: {e}")
        finally:
            db.close()

    def _create_credit_ledger_page(self) -> QWidget:
        from app.qt_ui.credit_ledger_system_page import CreditLedgerSystemPage

        page = CreditLedgerSystemPage(self)
        self.credit_ledger_page = page
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
        # Install Auto Scroll Manager
        self.ledger_table_auto_scroll = AutoScrollManager(self)
        self.ledger_table_auto_scroll.install_on_widget(self.ledger_table_view)
        
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

        date_edit = ClearableDateEdit()
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
                    
                    if isinstance(date_edit, ClearableDateEdit) and date_edit.is_empty():
                        raise ValueError("Transaction Date is required.")

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

        date_edit = ClearableDateEdit()
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
                if isinstance(date_edit, ClearableDateEdit) and date_edit.is_empty():
                    raise ValueError("Transaction Date is required.")

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
            txns = (
                db.query(SpareLedgerTransaction)
                .filter(
                    (SpareLedgerTransaction.description.is_(None))
                    | (~SpareLedgerTransaction.description.like("Advance Booking -%"))
                )
                .order_by(SpareLedgerTransaction.timestamp.asc())
                .all()
            )
            
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
            if hasattr(self, "sales_table_model"):
                self._reload_sales()
        elif key == "inventory":
            self._reload_inventory()
        elif key == "customers":
            self._reload_customers()
        elif key == "dealers":
            self._reload_dealers()
        elif key == "advance_booking":
            self._load_ab_models()
            self._reload_advance_bookings()
        elif key == "credit_ledger":
            if hasattr(self, "credit_ledger_page") and self.credit_ledger_page:
                try:
                    self.credit_ledger_page.refresh()
                except Exception:
                    pass
        elif key == "prices":
            self._reload_prices()
        elif key == "spare_ledger":
            self._reload_spare_ledger()
        elif key == "invoice":
            self._update_fbr_submitted_counter()
            self._generate_invoice_number()

    def _reload_sales(self) -> None:
        """Handles reloading for the dashboard/legacy sales list."""
        if hasattr(self, "report_page"):
            self.report_page.refresh_data()
            return
        if not hasattr(self, "sales_table_model"):
            return

        search = self.sales_search_input.text().strip() if hasattr(self, "sales_search_input") else ""
        status = self.sales_status_combo.currentText() if hasattr(self, "sales_status_combo") else "All"
        if status == "All Statuses":
            status = "All"
        period = self.sales_period_combo.currentText() if hasattr(self, "sales_period_combo") else "All Time"

        db = SessionLocal()
        data: List[SalesRow] = []
        try:
            query = (
                db.query(Invoice)
                .join(Customer, isouter=True)
                .options(
                    joinedload(Invoice.customer),
                    joinedload(Invoice.items).joinedload(InvoiceItem.motorcycle),
                )
                .order_by(Invoice.datetime.desc())
            )

            if search:
                value = f"%{search}%"
                query = query.filter(
                    (Invoice.invoice_number.ilike(value))
                    | (Customer.name.ilike(value))
                    | (Customer.cnic.ilike(value))
                )

            if status == "Synced":
                query = query.filter(Invoice.is_fiscalized.is_(True))
            elif status == "Pending":
                query = query.filter(Invoice.is_fiscalized.is_(False), Invoice.sync_status != "FAILED")
            elif status == "Failed":
                query = query.filter(Invoice.sync_status == "FAILED")

            now = dt.datetime.now()
            if period == "Today":
                start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
                end_dt = now.replace(hour=23, minute=59, second=59, microsecond=999999)
                query = query.filter(Invoice.datetime >= start_dt, Invoice.datetime <= end_dt)
            elif period in ("This Month", "Current Month"):
                start_dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                query = query.filter(Invoice.datetime >= start_dt)

            rows = query.limit(500).all()
            
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

    def _on_add_customer_clicked(self) -> None:
        self._open_add_customer_dialog()
        self._reload_customers()

    def _open_add_customer_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Add New Customer")
        dialog.setMinimumSize(520, 560)
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
                border: 2px solid #2ecc71;
                background-color: #f7fbfe;
            }
        """)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)

        form_grid = QGridLayout()
        form_grid.setSpacing(12)

        name_input = QLineEdit()
        father_input = QLineEdit()
        cnic_input = QLineEdit()
        phone_input = QLineEdit()
        address_input = AddressShortcodeLineEdit()
        ntn_input = QLineEdit()

        form_grid.addWidget(QLabel("Full Name:"), 0, 0)
        name_input.setPlaceholderText("Customer full name")
        form_grid.addWidget(name_input, 0, 1)

        form_grid.addWidget(QLabel("Father Name:"), 1, 0)
        father_input.setPlaceholderText("Father's name")
        form_grid.addWidget(father_input, 1, 1)

        form_grid.addWidget(QLabel("CNIC / ID Card:"), 2, 0)
        cnic_input.setPlaceholderText("XXXXX-XXXXXXX-X")
        form_grid.addWidget(cnic_input, 2, 1)

        form_grid.addWidget(QLabel("Phone:"), 3, 0)
        phone_input.setPlaceholderText("03XXXXXXXXX")
        form_grid.addWidget(phone_input, 3, 1)

        form_grid.addWidget(QLabel("Address:"), 4, 0)
        address_input.setPlaceholderText("Customer address")
        form_grid.addWidget(address_input, 4, 1)

        form_grid.addWidget(QLabel("NTN (Optional):"), 5, 0)
        ntn_input.setPlaceholderText("1234567-8")
        form_grid.addWidget(ntn_input, 5, 1)

        def apply_uppercase_lineedit(le: QLineEdit) -> None:
            text = le.text()
            upper = to_uppercase_preserving(text)
            if upper != text:
                pos = le.cursorPosition()
                le.blockSignals(True)
                le.setText(upper)
                le.setCursorPosition(pos)
                le.blockSignals(False)

        def filter_alpha_and_uppercase(le: QLineEdit) -> None:
            text = le.text()
            filtered = "".join(c for c in text if c.isalpha() or c.isspace())
            upper = to_uppercase_preserving(filtered)
            if upper != text:
                pos = le.cursorPosition()
                le.blockSignals(True)
                le.setText(upper)
                le.setCursorPosition(min(pos, len(upper)))
                le.blockSignals(False)

        def format_cnic_input() -> None:
            text = cnic_input.text()
            pos = cnic_input.cursorPosition()
            digits_before = len([c for c in text[:pos] if c.isdigit()])
            digits = "".join(c for c in text if c.isdigit())[:13]

            if len(digits) <= 5:
                formatted = digits
            elif len(digits) <= 12:
                formatted = f"{digits[:5]}-{digits[5:]}"
            else:
                formatted = f"{digits[:5]}-{digits[5:12]}-{digits[12:]}"

            def cursor_from_digits_count(value: str, count: int) -> int:
                seen = 0
                for i, ch in enumerate(value):
                    if ch.isdigit():
                        seen += 1
                        if seen >= count:
                            return i + 1
                return len(value)

            if formatted != text:
                cnic_input.blockSignals(True)
                cnic_input.setText(formatted)
                cnic_input.setCursorPosition(cursor_from_digits_count(formatted, digits_before))
                cnic_input.blockSignals(False)

            if len(formatted) == 15:
                check_cnic_exists(formatted)

        def check_cnic_exists(cnic: str) -> None:
            if not cnic or len(cnic) != 15:
                return
            db = SessionLocal()
            try:
                existing = db.query(Customer).filter(Customer.cnic == cnic).first()
                if existing:
                    from app.updater.toast_notification import ToastNotification

                    kind = existing.type.lower() if hasattr(existing.type, "lower") else str(existing.type).lower()
                    msg = f"A {kind} named '{existing.name}' with this CNIC already exists."
                    toast = ToastNotification(
                        title="CNIC Already Exists",
                        message=msg,
                        parent=self,
                        duration_ms=5000,
                        show_action=False,
                        bg_color="#e67e22",
                        position="top-right",
                    )
                    toast.show_notification()
            finally:
                db.close()

        def format_phone_input() -> None:
            text = phone_input.text()
            pos = phone_input.cursorPosition()
            digits_before = len([c for c in text[:pos] if c.isdigit()])
            digits = "".join(c for c in text if c.isdigit())[:11]

            def cursor_from_digits_count(value: str, count: int) -> int:
                seen = 0
                for i, ch in enumerate(value):
                    if ch.isdigit():
                        seen += 1
                        if seen >= count:
                            return i + 1
                return len(value)

            if digits != text:
                phone_input.blockSignals(True)
                phone_input.setText(digits)
                phone_input.setCursorPosition(cursor_from_digits_count(digits, digits_before))
                phone_input.blockSignals(False)

        name_input.textChanged.connect(lambda: filter_alpha_and_uppercase(name_input))
        father_input.textChanged.connect(lambda: filter_alpha_and_uppercase(father_input))
        address_input.textChanged.connect(lambda: apply_uppercase_lineedit(address_input))
        cnic_input.textChanged.connect(format_cnic_input)
        phone_input.textChanged.connect(format_phone_input)
        ntn_input.textChanged.connect(lambda: None)

        layout.addLayout(form_grid)
        layout.addStretch(1)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        save_btn = btn_box.button(QDialogButtonBox.StandardButton.Save)
        if save_btn:
            save_btn.setAutoDefault(False)
            save_btn.setDefault(False)
        cancel_btn = btn_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_btn:
            cancel_btn.setAutoDefault(False)

        class EnterKeyFilter(QObject):
            def __init__(self, next_field, on_last, parent_dialog):
                super().__init__(parent_dialog)
                self.next_field = next_field
                self.on_last = on_last
                self.parent_dialog = parent_dialog

            def eventFilter(self, obj, event):
                if event.type() == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    if self.next_field:
                        self.next_field.setFocus()
                    else:
                        self.on_last()
                    return True
                return super().eventFilter(obj, event)

        def validate_inputs() -> tuple[bool, str, QLineEdit | None]:
            name = name_input.text().strip()
            father = father_input.text().strip()
            cnic_raw = cnic_input.text().strip()
            phone_raw = phone_input.text().strip()
            address = address_input.text().strip()
            ntn = ntn_input.text().strip()

            if not name:
                return False, "Full Name is required.", name_input
            if not father:
                return False, "Father Name is required.", father_input
            if not cnic_raw:
                return False, "CNIC is required.", cnic_input
            cnic_digits = "".join(c for c in cnic_raw if c.isdigit())
            if len(cnic_digits) != 13:
                return False, "Invalid CNIC format (33302-1234567-1).", cnic_input
            cnic = f"{cnic_digits[:5]}-{cnic_digits[5:12]}-{cnic_digits[12]}"
            if cnic != cnic_raw:
                cnic_input.blockSignals(True)
                cnic_input.setText(cnic)
                cnic_input.setCursorPosition(len(cnic))
                cnic_input.blockSignals(False)
            if not phone_raw:
                return False, "Phone is required.", phone_input
            phone_digits = "".join(c for c in phone_raw if c.isdigit())
            if phone_digits != phone_raw:
                phone_input.blockSignals(True)
                phone_input.setText(phone_digits)
                phone_input.setCursorPosition(len(phone_digits))
                phone_input.blockSignals(False)
            if not re.match(r"^03\d{9}$", phone_digits):
                return False, "Invalid phone format (03XXXXXXXXX).", phone_input
            if not address:
                return False, "Address is required.", address_input
            if ntn and not re.match(r"^\d{7}(-\d)?$", ntn):
                return False, "Invalid NTN format (1234567-8).", ntn_input
            if customer_service.get_customer_by_cnic(cnic):
                return False, "Customer with this CNIC already exists.", cnic_input
            return True, "", None

        def on_save() -> None:
            ok, msg, focus = validate_inputs()
            if not ok:
                QMessageBox.warning(self, "Validation Error", msg)
                if focus:
                    focus.setFocus()
                return

            try:
                customer_service.create_customer(
                    cnic=cnic_input.text().strip(),
                    name=name_input.text().strip(),
                    father_name=father_input.text().strip(),
                    phone=phone_input.text().strip(),
                    address=address_input.text().strip(),
                    ntn=ntn_input.text().strip(),
                    customer_type=CustomerType.INDIVIDUAL,
                )
                QMessageBox.information(self, "Success", "Customer created successfully.")
                dialog.accept()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to create customer: {e}")

        btn_box.accepted.connect(on_save)
        btn_box.rejected.connect(dialog.reject)
        layout.addWidget(btn_box)

        name_input.installEventFilter(EnterKeyFilter(father_input, on_save, dialog))
        father_input.installEventFilter(EnterKeyFilter(cnic_input, on_save, dialog))
        cnic_input.installEventFilter(EnterKeyFilter(phone_input, on_save, dialog))
        phone_input.installEventFilter(EnterKeyFilter(address_input, on_save, dialog))
        address_input.installEventFilter(EnterKeyFilter(ntn_input, on_save, dialog))
        ntn_input.installEventFilter(EnterKeyFilter(None, on_save, dialog))

        QWidget.setTabOrder(name_input, father_input)
        QWidget.setTabOrder(father_input, cnic_input)
        QWidget.setTabOrder(cnic_input, phone_input)
        QWidget.setTabOrder(phone_input, address_input)
        QWidget.setTabOrder(address_input, ntn_input)

        name_input.setFocus()
        dialog.exec()

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
            address_input = AddressShortcodeLineEdit()
            address_input.setText(cust.address or "")
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
            pos = cnic_input.cursorPosition()
            digits_before = len([c for c in text[:pos] if c.isdigit()])
            digits = "".join(c for c in text if c.isdigit())[:13]

            if len(digits) <= 5:
                formatted = digits
            elif len(digits) <= 12:
                formatted = f"{digits[:5]}-{digits[5:]}"
            else:
                formatted = f"{digits[:5]}-{digits[5:12]}-{digits[12:]}"

            def cursor_from_digits_count(value: str, count: int) -> int:
                seen = 0
                for i, ch in enumerate(value):
                    if ch.isdigit():
                        seen += 1
                        if seen >= count:
                            return i + 1
                return len(value)

            if formatted != text:
                cnic_input.blockSignals(True)
                cnic_input.setText(formatted)
                cnic_input.setCursorPosition(cursor_from_digits_count(formatted, digits_before))
                cnic_input.blockSignals(False)
            
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
        address_input = AddressShortcodeLineEdit()
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
            query = (
                db.query(SpareLedgerTransaction)
                .filter(
                    (SpareLedgerTransaction.description.is_(None))
                    | (~SpareLedgerTransaction.description.like("Advance Booking -%"))
                )
                .order_by(SpareLedgerTransaction.timestamp.asc())
            )
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
            try:
                if getattr(self, "_settings_subscription_token", None):
                    settings_service.unsubscribe(self._settings_subscription_token)
            except Exception:
                pass
            form_capture_service.stop_capture_session()
            
            # Cleanup DB connections
            close_all_db_connections()
            
            # Stop SMS scheduler
            from app.services.sms_service import sms_service
            sms_service.stop_scheduler()
            try:
                if getattr(self, "_sync_service", None):
                    self._sync_service.stop()
            except Exception as e:
                logger.error(f"Failed to stop background sync service: {e}", exc_info=True)
                
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


class AdvanceBookingRow:
    def __init__(
        self,
        booking_number: str,
        created_at: dt.datetime | None,
        customer_name: str,
        motorcycle_model: str,
        color: str,
        total_price: float,
        advance_paid: float,
        balance_amount: float,
        delivery_paid: float,
        status: str,
        delivered_at: dt.datetime | None = None,
    ) -> None:
        self.booking_number = booking_number
        self.created_at = created_at
        self.delivered_at = delivered_at
        self.customer_name = customer_name
        self.motorcycle_model = motorcycle_model
        self.color = color
        self.total_price = total_price
        self.advance_paid = advance_paid
        self.balance_amount = balance_amount
        self.delivery_paid = delivery_paid
        self.status = status


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


class AdvanceBookingsTableModel(QAbstractTableModel):
    headers = ["Booking #", "Booked At", "Delivered At", "Customer", "Model", "Color", "Total", "Advance", "Delivery Paid", "Balance", "Status"]

    def __init__(self) -> None:
        super().__init__()
        self._rows: List[AdvanceBookingRow] = []

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
                return row.booking_number
            if col == 1:
                return row.created_at.strftime("%Y-%m-%d %H:%M") if row.created_at else ""
            if col == 2:
                return row.delivered_at.strftime("%Y-%m-%d %H:%M") if row.delivered_at else ""
            if col == 3:
                return row.customer_name
            if col == 4:
                return row.motorcycle_model
            if col == 5:
                return row.color
            if col == 6:
                return f"{row.total_price:,.0f}"
            if col == 7:
                return f"{row.advance_paid:,.0f}"
            if col == 8:
                return f"{row.delivery_paid:,.0f}"
            if col == 9:
                return f"{row.balance_amount:,.0f}"
            if col == 10:
                return row.status

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (6, 7, 8, 9):
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            return Qt.AlignmentFlag.AlignCenter

        if role == Qt.ItemDataRole.ForegroundRole and col == 10:
            if (row.status or "").upper() == "ACTIVE":
                return Qt.GlobalColor.darkGreen
            return Qt.GlobalColor.darkYellow

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self.headers):
                return self.headers[section]
        return super().headerData(section, orientation, role)

    def update_rows(self, rows: List[AdvanceBookingRow]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()


class PriceRow:
    def __init__(
        self,
        id: int,
        model: str,
        color: str,
        base_price: float,
        tax: float,
        levy: float,
        total: float,
        effective_date: dt.datetime,
    ) -> None:
        self.id = id
        self.model = model
        self.color = color
        self.base_price = base_price
        self.tax = tax
        self.levy = levy
        self.total = total
        self.effective_date = effective_date


class PricesTableModel(QAbstractTableModel):
    headers = ["Model Name", "Color", "Base Price", "Sales Tax", "Further Tax", "Total Price", "Effective Date"]

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
                return row.color
            if col == 2:
                return f"{row.base_price:,.2f}"
            if col == 3:
                return f"{row.tax:,.2f}"
            if col == 4:
                return f"{row.levy:,.2f}"
            if col == 5:
                return f"{row.total:,.2f}"
            if col == 6:
                return row.effective_date.strftime("%Y-%m-%d") if row.effective_date else "N/A"
        
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col > 1:
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
    headers = ["Date", "Campaign Name", "Channel", "Status", "Sent", "Failed", "Total", "Error Message"]

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
                return getattr(row, 'channel', 'SMS')
            if col == 3:
                return row.status
            if col == 4:
                return str(row.sent)
            if col == 5:
                return str(row.failed)
            if col == 6:
                return str(row.total)
            if col == 7:
                return row.error_message or ""
        
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col == 7:
                return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            return Qt.AlignmentFlag.AlignCenter
            
        if role == Qt.ItemDataRole.ForegroundRole:
            if col == 3: # Status column
                if row.status == "COMPLETED":
                    return Qt.GlobalColor.darkGreen
                if row.status == "RUNNING":
                    return Qt.GlobalColor.blue
                if row.status == "FAILED":
                    return Qt.GlobalColor.red
            if col == 7: # Error Message column
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
