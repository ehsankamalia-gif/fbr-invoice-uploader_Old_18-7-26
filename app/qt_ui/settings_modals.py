from __future__ import annotations
from typing import Dict, Any, Optional
import os
import sys
import subprocess
import base64
import asyncio
from pathlib import Path
from PyQt6.QtCore import Qt, pyqtSignal, QDate, QTime, QThread, QTimer
from PyQt6.QtGui import QPixmap, QImage, QAction, QIcon
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QComboBox, QDoubleSpinBox, QSpinBox, 
    QFrame, QGridLayout, QCheckBox, QScrollArea, 
    QMessageBox, QApplication, QTableWidget, QTableWidgetItem, QHeaderView, QInputDialog,
    QProgressDialog, QWidget, QTextEdit, QTabWidget
)
import logging
import datetime as dt

from app.services.settings_service import settings_service
from app.services.backup_service import backup_service
from app.core.config import settings
from app.core.logger import logger
from app.qt_ui.whatsapp_widget import WhatsAppWidget
from app.qt_ui.whatsapp_campaign_widget import WhatsAppCampaignWidget

class BackupWorker(QThread):
    finished = pyqtSignal(dict)
    def __init__(self, output_format: str | None = None):
        super().__init__()
        self.output_format = output_format
    def run(self):
        try:
            result = backup_service.create_backup(is_manual=True, output_format=self.output_format)
            self.finished.emit(result)
        except Exception as e:
            self.finished.emit({"success": False, "error": str(e)})

class MySQLRestoreWorker(QThread):
    finished = pyqtSignal(dict)
    def __init__(self, path: str):
        super().__init__()
        self.path = path
    def run(self):
        try:
            result = backup_service.restore_backup(self.path)
            self.finished.emit(result)
        except Exception as e:
            self.finished.emit({"success": False, "error": str(e)})

class BaseSettingsDialog(QDialog):
    """Base class for settings modals with consistent styling and behavior."""
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(500)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setStyleSheet("""
            QDialog {
                background-color: #f8f9fa;
            }
            QLabel {
                font-size: 13px;
                color: #2c3e50;
                font-weight: bold;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
                padding: 8px;
                border: 1px solid #ced4da;
                border-radius: 4px;
                background-color: white;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #3498db;
            }
            QPushButton#primaryButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 10px 20px;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton#primaryButton:hover {
                background-color: #2980b9;
            }
            QPushButton#secondaryButton {
                background-color: #ecf0f1;
                color: #2c3e50;
                border: 1px solid #bdc3c7;
                padding: 10px 20px;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton#secondaryButton:hover {
                background-color: #bdc3c7;
            }
            QFrame#formGroup {
                background-color: white;
                border: 1px solid #e9ecef;
                border-radius: 8px;
            }
        """)
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(15)
        
        # Content area
        self.content_frame = QFrame()
        self.content_frame.setObjectName("formGroup")
        self.content_layout = QVBoxLayout(self.content_frame)
        self.content_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.addWidget(self.content_frame)
        
        # Action buttons
        self.button_layout = QHBoxLayout()
        self.button_layout.addStretch(1)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("secondaryButton")
        self.cancel_btn.clicked.connect(self.reject)
        self.button_layout.addWidget(self.cancel_btn)
        
        self.save_btn = QPushButton("Save Changes")
        self.save_btn.setObjectName("primaryButton")
        self.save_btn.clicked.connect(self.save_settings)
        self.button_layout.addWidget(self.save_btn)
        
        self.main_layout.addLayout(self.button_layout)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)

    def save_settings(self):
        """To be implemented by subclasses."""
        pass

    def _show_success(self, title: str, message: str):
        QMessageBox.information(self, title, message)

    def _show_error(self, title: str, message: str):
        QMessageBox.critical(self, title, message)

    def _add_password_toggle(self, line_edit: QLineEdit):
        """Adds a visibility toggle (eye icon) to a QLineEdit."""
        icons_dir = Path(__file__).parent.parent / "assets" / "icons"
        icon_path = str(icons_dir / "eye.svg")
        
        action = QAction(QIcon(icon_path), "Show Password", line_edit)
        line_edit.addAction(action, QLineEdit.ActionPosition.TrailingPosition)
        action.triggered.connect(lambda: self._toggle_password_visibility(line_edit, action))
        # Store initial state
        action.setData(True) # True means currently masked

    def _toggle_password_visibility(self, line_edit: QLineEdit, action: QAction):
        """Toggles between password and normal echo modes."""
        is_masked = action.data()
        icons_dir = Path(__file__).parent.parent / "assets" / "icons"
        
        if is_masked:
            line_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            icon_name = "eye-off.svg"
            action.setToolTip("Hide Password")
            action.setData(False)
        else:
            line_edit.setEchoMode(QLineEdit.EchoMode.Password)
            icon_name = "eye.svg"
            action.setToolTip("Show Password")
            action.setData(True)
            
        icon_path = str(icons_dir / icon_name)
        action.setIcon(QIcon(icon_path))

class FBRSecurityDialog(BaseSettingsDialog):
    """Modal for FBR API and Security settings."""
    def __init__(self, parent=None):
        super().__init__("FBR API & Security Configuration", parent)
        self._init_ui()
        self._load_data()

    def _init_ui(self):
        layout = QGridLayout()
        layout.setSpacing(15)
        
        layout.addWidget(QLabel("Environment:"), 0, 0)
        self.env_combo = QComboBox()
        self.env_combo.addItems(["SANDBOX", "PRODUCTION"])
        self.env_combo.currentTextChanged.connect(self._on_env_changed)
        layout.addWidget(self.env_combo, 0, 1)
        
        layout.addWidget(QLabel("API Base URL:"), 1, 0)
        self.api_url = QLineEdit()
        layout.addWidget(self.api_url, 1, 1)
        
        layout.addWidget(QLabel("POS ID:"), 2, 0)
        self.pos_id = QLineEdit()
        layout.addWidget(self.pos_id, 2, 1)
        
        layout.addWidget(QLabel("USIN:"), 3, 0)
        self.usin = QLineEdit()
        layout.addWidget(self.usin, 3, 1)
        
        layout.addWidget(QLabel("Auth Token:"), 4, 0)
        self.auth_token = QLineEdit()
        self.auth_token.setEchoMode(QLineEdit.EchoMode.Password)
        self._add_password_toggle(self.auth_token)
        layout.addWidget(self.auth_token, 4, 1)
        
        layout.addWidget(QLabel("Secret Key:"), 5, 0)
        self.secret_key = QLineEdit()
        self.secret_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._add_password_toggle(self.secret_key)
        layout.addWidget(self.secret_key, 5, 1)
        
        self.content_layout.addLayout(layout)

    def _load_data(self):
        """Initial load of data into the dialog."""
        current_env = settings_service.get_active_environment()
        self.env_combo.setCurrentText(current_env)
        self._load_env_settings(current_env)

    def _on_env_changed(self, env: str):
        self._load_env_settings(env)

    def _load_env_settings(self, env: str):
        data = settings_service.get_environment(env)
        if data:
            self.api_url.setText(data.get("base_url", ""))
            self.pos_id.setText(data.get("pos_id", ""))
            self.usin.setText(data.get("usin", ""))
            self.auth_token.setText(data.get("token", ""))
            self.secret_key.setText(data.get("secret_key", ""))

    def save_settings(self):
        env = self.env_combo.currentText()
        try:
            # We need to preserve other fields from this environment
            existing = settings_service.get_environment(env) or {}
            
            settings_service.save_environment(
                env=env,
                base_url=self.api_url.text().strip(),
                pos_id=self.pos_id.text().strip(),
                usin=self.usin.text().strip(),
                token=self.auth_token.text().strip(),
                secret_key=self.secret_key.text().strip(),
                tax_rate=existing.get("tax_rate", "18.0"),
                pct_code=existing.get("pct_code", "8711.2010"),
                invoice_type=existing.get("invoice_type", "Standard"),
                discount=existing.get("discount", "0.0"),
                item_code=existing.get("item_code", "MOTO"),
                item_name=existing.get("item_name", "Motorcycle"),
                business_name=existing.get("business_name", "Ehsan Trader")
            )
            settings_service.set_active_environment(env)
            self._show_success("Security Settings Saved", "FBR API configuration updated successfully.")
            self.accept()
        except Exception as e:
            logger.error(f"Failed to save FBR settings: {e}")
            self._show_error("Error", f"Failed to save settings: {str(e)}")

class BusinessPreferencesDialog(BaseSettingsDialog):
    """Modal for Business Rules and Tax preferences."""
    def __init__(self, parent=None):
        super().__init__("Business Rules & Preferences", parent)
        self._init_ui()
        self._load_data()

    def _init_ui(self):
        layout = QGridLayout()
        layout.setSpacing(15)
        
        layout.addWidget(QLabel("Business Name:"), 0, 0)
        self.business_name = QLineEdit()
        layout.addWidget(self.business_name, 0, 1)
        
        layout.addWidget(QLabel("Default Sales Tax (%):"), 1, 0)
        self.tax_rate = QDoubleSpinBox()
        self.tax_rate.setRange(0, 100)
        layout.addWidget(self.tax_rate, 1, 1)
        
        layout.addWidget(QLabel("PCT Code:"), 2, 0)
        self.pct_code = QLineEdit()
        layout.addWidget(self.pct_code, 2, 1)
        
        layout.addWidget(QLabel("Item Code Prefix:"), 3, 0)
        self.item_code = QLineEdit()
        layout.addWidget(self.item_code, 3, 1)
        
        layout.addWidget(QLabel("Default Item Name:"), 4, 0)
        self.item_name = QLineEdit()
        layout.addWidget(self.item_name, 4, 1)
        
        layout.addWidget(QLabel("Default Invoice Type:"), 5, 0)
        self.invoice_type = QComboBox()
        self.invoice_type.addItems(["Standard", "Debit Note", "Credit Note"])
        layout.addWidget(self.invoice_type, 5, 1)
        
        layout.addWidget(QLabel("Default Discount (%):"), 6, 0)
        self.discount = QDoubleSpinBox()
        self.discount.setRange(0, 100)
        layout.addWidget(self.discount, 6, 1)
        
        self.content_layout.addLayout(layout)

    def _load_data(self):
        env = settings_service.get_active_environment()
        data = settings_service.get_environment(env)
        if data:
            self.business_name.setText(data.get("business_name", "Ehsan Trader Kamalia Pakistan"))
            self.tax_rate.setValue(float(data.get("tax_rate", 18.0)))
            self.pct_code.setText(data.get("pct_code", "8711.2010"))
            self.item_code.setText(data.get("item_code", "ITEMCODE"))
            self.item_name.setText(data.get("item_name", "Honda"))
            self.invoice_type.setCurrentText(data.get("invoice_type", "Standard"))
            self.discount.setValue(float(data.get("discount", 0.0)))

    def save_settings(self):
        env = settings_service.get_active_environment()
        try:
            existing = settings_service.get_environment(env) or {}
            settings_service.save_environment(
                env=env,
                base_url=existing.get("base_url", ""),
                pos_id=existing.get("pos_id", ""),
                usin=existing.get("usin", ""),
                token=existing.get("token", ""),
                tax_rate=str(self.tax_rate.value()),
                pct_code=self.pct_code.text().strip(),
                invoice_type=self.invoice_type.currentText(),
                discount=str(self.discount.value()),
                item_code=self.item_code.text().strip(),
                item_name=self.item_name.text().strip(),
                business_name=self.business_name.text().strip()
            )
            self._show_success("Preferences Saved", "Business rules and preferences updated.")
            self.accept()
        except Exception as e:
            logger.error(f"Failed to save preferences: {e}")
            self._show_error("Error", str(e))

class DatabaseSettingsDialog(BaseSettingsDialog):
    """Modal for Database Connection settings."""
    def __init__(self, parent=None):
        super().__init__("Database Connection Settings", parent)
        self._init_ui()
        self._load_data()

    def _init_ui(self):
        layout = QGridLayout()
        layout.setSpacing(15)
        
        layout.addWidget(QLabel("Server (Host):"), 0, 0)
        self.db_server = QLineEdit()
        layout.addWidget(self.db_server, 0, 1)
        
        layout.addWidget(QLabel("Port:"), 1, 0)
        self.db_port = QLineEdit()
        self.db_port.setPlaceholderText("3306")
        layout.addWidget(self.db_port, 1, 1)
        
        layout.addWidget(QLabel("Database Name:"), 2, 0)
        self.db_name = QLineEdit()
        layout.addWidget(self.db_name, 2, 1)
        
        layout.addWidget(QLabel("Username:"), 3, 0)
        self.db_user = QLineEdit()
        layout.addWidget(self.db_user, 3, 1)
        
        layout.addWidget(QLabel("Password:"), 4, 0)
        self.db_password = QLineEdit()
        self.db_password.setEchoMode(QLineEdit.EchoMode.Password)
        self._add_password_toggle(self.db_password)
        layout.addWidget(self.db_password, 4, 1)
        
        self.test_btn = QPushButton("🔌 Test Connection")
        self.test_btn.clicked.connect(self._on_test_connection)
        layout.addWidget(self.test_btn, 5, 0, 1, 2)
        
        self.content_layout.addLayout(layout)

    def _load_data(self):
        db_settings = settings_service.get_db_settings()
        self.db_server.setText(db_settings.get("server", "localhost"))
        self.db_port.setText(db_settings.get("port", "3306"))
        self.db_name.setText(db_settings.get("name", "honda_fbr"))
        self.db_user.setText(db_settings.get("user", "root"))
        self.db_password.setText(db_settings.get("password", ""))

    def _on_test_connection(self):
        server = self.db_server.text().strip()
        port = self.db_port.text().strip() or "3306"
        name = self.db_name.text().strip()
        user = self.db_user.text().strip()
        pwd = self.db_password.text().strip()

        if not all([server, name, user]):
            self._show_error("Validation Error", "Required fields missing.")
            return

        self.test_btn.setEnabled(False)
        self.test_btn.setText("Testing...")
        QApplication.processEvents()

        try:
            from sqlalchemy import create_engine, text
            db_url = f"mysql+pymysql://{user}:{pwd}@{server}:{port}/{name}"
            test_engine = create_engine(db_url, connect_args={"connect_timeout": 5})
            with test_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            self._show_success("Success", "Database connection successful.")
        except Exception as e:
            self._show_error("Failed", f"Connection failed: {str(e)}")
        finally:
            self.test_btn.setEnabled(True)
            self.test_btn.setText("🔌 Test Connection")

    def save_settings(self):
        try:
            settings_service.save_db_settings(
                server=self.db_server.text().strip(),
                port=self.db_port.text().strip(),
                name=self.db_name.text().strip(),
                user=self.db_user.text().strip(),
                password=self.db_password.text().strip()
            )
            # Trigger reload in main window
            from app.core.config import reload_settings
            from app.db.session import init_db
            reload_settings()
            init_db()
            self._show_success("Saved", "Database settings updated and re-initialized.")
            self.accept()
        except Exception as e:
            self._show_error("Error", str(e))

class SMSConfigDialog(BaseSettingsDialog):
    """Modal for SMS & WhatsApp notification settings."""
    def __init__(self, parent=None):
        super().__init__("SMS & WhatsApp Configuration", parent)
        self.setMinimumWidth(600)
        self._init_ui()
        self._load_data()

    def _init_ui(self):
        # Using a scroll area for better layout
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        
        # 1. SMS Section
        sms_group = QFrame()
        sms_group.setStyleSheet("background-color: #fcfcfc; border: 1px solid #dee2e6; border-radius: 4px;")
        sms_layout = QGridLayout(sms_group)
        
        sms_title = QLabel("SMS GATEWAY (ANDROID)")
        sms_title.setStyleSheet("color: #2980b9; font-size: 14px; border: none; font-weight: bold;")
        sms_layout.addWidget(sms_title, 0, 0, 1, 2)
        
        self.sms_enabled = QCheckBox("Enable SMS Notifications")
        sms_layout.addWidget(self.sms_enabled, 1, 0, 1, 2)
        
        sms_layout.addWidget(QLabel("Gateway IP:"), 2, 0)
        self.sms_ip = QLineEdit()
        self.sms_ip.setPlaceholderText("e.g. 192.168.1.100")
        sms_layout.addWidget(self.sms_ip, 2, 1)
        
        sms_layout.addWidget(QLabel("Gateway Port:"), 3, 0)
        self.sms_port = QLineEdit()
        self.sms_port.setPlaceholderText("8080")
        sms_layout.addWidget(self.sms_port, 3, 1)
        
        sms_layout.addWidget(QLabel("Gateway Username:"), 4, 0)
        self.sms_username = QLineEdit()
        sms_layout.addWidget(self.sms_username, 4, 1)
        
        sms_layout.addWidget(QLabel("Gateway Password:"), 5, 0)
        self.sms_password = QLineEdit()
        self.sms_password.setEchoMode(QLineEdit.EchoMode.Password)
        self._add_password_toggle(self.sms_password)
        sms_layout.addWidget(self.sms_password, 5, 1)
        
        self.sms_https = QCheckBox("Use HTTPS Protocol")
        sms_layout.addWidget(self.sms_https, 6, 0, 1, 2)
        
        sms_layout.addWidget(QLabel("API Key (Optional):"), 7, 0)
        self.sms_api_key = QLineEdit()
        self.sms_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._add_password_toggle(self.sms_api_key)
        sms_layout.addWidget(self.sms_api_key, 7, 1)
        
        self.sms_test_btn = QPushButton("🧪 Test SMS Connection")
        self.sms_test_btn.setStyleSheet("background-color: #3498db; color: white; padding: 8px; font-weight: bold;")
        self.sms_test_btn.clicked.connect(self._on_test_sms)
        sms_layout.addWidget(self.sms_test_btn, 8, 0, 1, 2)
        
        layout.addWidget(sms_group)

        # 2. WhatsApp Section (Evolution API)
        wa_tabs = QTabWidget()
        wa_tabs.addTab(WhatsAppWidget(), "Status & Test")
        wa_tabs.addTab(WhatsAppCampaignWidget(), "Bulk Campaigns (Excel)")
        layout.addWidget(wa_tabs)
        
        # 3. Message Template
        tmpl_group = QFrame()
        tmpl_group.setStyleSheet("background-color: #fcfcfc; border: 1px solid #dee2e6; border-radius: 4px;")
        tmpl_layout = QVBoxLayout(tmpl_group)
        
        tmpl_title = QLabel("INVOICE MESSAGE TEMPLATE")
        tmpl_title.setStyleSheet("color: #e67e22; font-size: 14px; border: none; font-weight: bold;")
        tmpl_layout.addWidget(tmpl_title)
        
        self.template_text = QTextEdit()
        self.template_text.setFixedHeight(80)
        tmpl_layout.addWidget(self.template_text)
        
        help_text = QLabel("Variables: {customer}, {invoice_no}, {amount}, {fbr_id}")
        help_text.setStyleSheet("font-size: 11px; color: #7f8c8d; border: none;")
        tmpl_layout.addWidget(help_text)

        # Booking Template
        tmpl_layout.addSpacing(10)
        booking_tmpl_title = QLabel("BOOKING MESSAGE TEMPLATE")
        booking_tmpl_title.setStyleSheet("color: #27ae60; font-size: 14px; border: none; font-weight: bold;")
        tmpl_layout.addWidget(booking_tmpl_title)
        
        self.booking_template_text = QTextEdit()
        self.booking_template_text.setFixedHeight(80)
        tmpl_layout.addWidget(self.booking_template_text)
        
        booking_help_text = QLabel("Variables: {customer}, {model}, {color}, {booking_no}, {paid}, {balance}")
        booking_help_text.setStyleSheet("font-size: 11px; color: #7f8c8d; border: none;")
        tmpl_layout.addWidget(booking_help_text)
        
        layout.addWidget(tmpl_group)
        
        scroll.setWidget(scroll_content)
        self.content_layout.addWidget(scroll)

    def _load_data(self):
        config = settings_service.get_sms_config()
        self.sms_enabled.setChecked(config.get("is_enabled", False))
        self.sms_ip.setText(config.get("gateway_ip", ""))
        self.sms_port.setText(config.get("gateway_port", "8080"))
        self.sms_username.setText(config.get("gateway_username", ""))
        self.sms_password.setText(config.get("gateway_password", ""))
        self.sms_https.setChecked(config.get("use_https", False))
        self.sms_api_key.setText(config.get("api_key", ""))
        
        self.template_text.setPlainText(config.get("invoice_template", ""))
        self.booking_template_text.setPlainText(config.get("booking_template", ""))

    def _on_test_sms(self):
        ip = self.sms_ip.text().strip()
        port = self.sms_port.text().strip()
        
        # UI Level Sanitization: If user entered http://192.168.1.10, clean it up
        if "://" in ip:
            ip = ip.split("://")[-1]
        if ":" in ip:
            parts = ip.split(":")
            ip = parts[0]
            if not port or port == "8080":
                port = parts[1]
        ip = ip.replace("/", "").strip()
        
        username = self.sms_username.text().strip()
        password = self.sms_password.text().strip()
        api_key = self.sms_api_key.text().strip()
        use_https = self.sms_https.isChecked()

        if not ip or not port:
            self._show_error("Validation Error", "Gateway IP and Port are required for testing.")
            return

        self.sms_test_btn.setEnabled(False)
        self.sms_test_btn.setText("⏳ Testing SMS...")
        QApplication.processEvents()

        try:
            from app.services.sms_service import sms_service
            # Send a generic test message to a dummy number or ask user? 
            # We'll try to send to a placeholder or just check connectivity
            success, msg = sms_service.send_sms_via_wifi(
                ip, port, "0000000000", "FBR SMS Gateway Test", 
                api_key=api_key, 
                username=username if username else None,
                password=password if password else None,
                use_https=use_https, total_timeout=15.0
            )
            if success:
                self._show_success("SMS Test Successful", f"Gateway responded: {msg}")
            else:
                self._show_error("SMS Test Failed", msg)
        except Exception as e:
            err_msg = str(e)
            if "11001" in err_msg or "getaddrinfo failed" in err_msg:
                self._show_error("Connection Failed", "Invalid Gateway IP address. Please enter a simple IP like '192.168.1.100' without any 'http://' or slashes.")
            else:
                self._show_error("Error", err_msg)
        finally:
            self.sms_test_btn.setEnabled(True)
            self.sms_test_btn.setText("🧪 Test SMS Connection")

    def save_settings(self):
        try:
            settings_service.save_sms_config(
                is_enabled=self.sms_enabled.isChecked(),
                gateway_ip=self.sms_ip.text().strip(),
                gateway_port=self.sms_port.text().strip(),
                gateway_username=self.sms_username.text().strip(),
                gateway_password=self.sms_password.text().strip(),
                use_https=self.sms_https.isChecked(),
                api_key=self.sms_api_key.text().strip(),
                invoice_template=self.template_text.toPlainText().strip(),
                booking_template=self.booking_template_text.toPlainText().strip()
            )
            self._show_success("Saved", "Configuration updated.")
            self.accept()
        except Exception as e:
            self._show_error("Error", str(e))

class BackupSettingsDialog(BaseSettingsDialog):
    """Modal for Backup & Maintenance settings."""
    def __init__(self, parent=None):
        logger.info("Initializing BackupSettingsDialog...")
        try:
            super().__init__("Backup & Maintenance Settings", parent)
            self.setMinimumWidth(800)
            self._init_ui()
            self._load_data()
            logger.info("BackupSettingsDialog initialized successfully.")
        except Exception as e:
            logger.error(f"CRITICAL: Failed to initialize BackupSettingsDialog: {e}", exc_info=True)
            raise

    def _init_ui(self):
        layout = QVBoxLayout()
        
        # Header with Immediate Actions
        header_actions = QHBoxLayout()
        header_actions.addWidget(QLabel("Configuration & Scheduled Backups"))
        header_actions.addStretch(1)
        
        self.manual_backup_btn = QPushButton("💾 Create Backup Now")
        self.manual_backup_btn.setObjectName("primaryButton")
        self.manual_backup_btn.setStyleSheet("background-color: #27ae60;")
        self.manual_backup_btn.clicked.connect(self._on_manual_backup)
        header_actions.addWidget(self.manual_backup_btn)

        self.manual_format = QComboBox()
        self.manual_format.addItems(["Encrypted (.enc)", "Unencrypted (.zip)"])
        self.manual_format.setFixedWidth(170)
        header_actions.addWidget(self.manual_format)
        
        self.restore_btn = QPushButton("📂 Restore from File...")
        self.restore_btn.setObjectName("primaryButton")
        self.restore_btn.clicked.connect(self._on_restore_file)
        header_actions.addWidget(self.restore_btn)
        
        layout.addLayout(header_actions)
        
        # Settings Section
        settings_frame = QFrame()
        settings_frame.setStyleSheet("background-color: #fcfcfc; border: 1px solid #dee2e6; border-radius: 4px;")
        grid = QGridLayout(settings_frame)
        
        grid.addWidget(QLabel("Backup Location:"), 0, 0)
        path_layout = QHBoxLayout()
        self.backup_path = QLineEdit()
        self.backup_path.setReadOnly(True)
        path_layout.addWidget(self.backup_path)
        self.browse_btn = QPushButton("Browse")
        self.browse_btn.clicked.connect(self._on_browse)
        path_layout.addWidget(self.browse_btn)
        grid.addLayout(path_layout, 0, 1)
        
        self.auto_enabled = QCheckBox("Enable Scheduled Backups")
        grid.addWidget(self.auto_enabled, 1, 0, 1, 2)
        
        grid.addWidget(QLabel("Interval:"), 2, 0)
        self.interval = QComboBox()
        self.interval.addItems(["hourly", "daily", "weekly", "monthly"])
        grid.addWidget(self.interval, 2, 1)
        
        grid.addWidget(QLabel("Time (HH:MM):"), 3, 0)
        self.time_input = QLineEdit()
        self.time_input.setPlaceholderText("00:00")
        grid.addWidget(self.time_input, 3, 1)
        
        grid.addWidget(QLabel("Retention (Days):"), 4, 0)
        self.retention = QSpinBox()
        self.retention.setRange(1, 365)
        grid.addWidget(self.retention, 4, 1)

        grid.addWidget(QLabel("Encryption Keys:"), 5, 0)
        keys_row = QHBoxLayout()
        self.keys_status = QLabel("")
        self.keys_status.setStyleSheet("color: #7f8c8d; font-weight: normal;")
        keys_row.addWidget(self.keys_status)
        keys_row.addStretch(1)
        self.export_keys_btn = QPushButton("Export Keys")
        self.export_keys_btn.clicked.connect(self._on_export_keys)
        keys_row.addWidget(self.export_keys_btn)
        self.import_keys_btn = QPushButton("Import Keys")
        self.import_keys_btn.clicked.connect(self._on_import_keys)
        keys_row.addWidget(self.import_keys_btn)
        grid.addLayout(keys_row, 5, 1)
        
        layout.addWidget(settings_frame)
        
        # Recent Backups Table
        layout.addWidget(QLabel("RECENT BACKUPS HISTORY"))
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Date", "File Name", "Size (MB)", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setFixedHeight(250)
        self.table.setStyleSheet("""
            QTableWidget { border: 1px solid #dee2e6; border-radius: 4px; background-color: white; }
            QHeaderView::section { background-color: #f1f1f1; padding: 8px; border: none; font-weight: bold; }
        """)
        layout.addWidget(self.table)
        
        self.content_layout.addLayout(layout)

    def _load_data(self):
        try:
            config = backup_service.get_config()
            self.backup_path.setText(str(config.get("backup_path", "backups")))
            self.auto_enabled.setChecked(bool(config.get("auto_backup", False)))
            self.interval.setCurrentText(str(config.get("interval", "daily")))
            self.time_input.setText(str(config.get("backup_time", "00:00")))
            
            retention = config.get("retention_days", 30)
            try:
                self.retention.setValue(int(retention))
            except (ValueError, TypeError):
                self.retention.setValue(30)
                
            if bool(config.get("encrypt", True)) is True:
                self.manual_format.setCurrentText("Encrypted (.enc)")
            else:
                self.manual_format.setCurrentText("Unencrypted (.zip)")

            self._refresh_keys_status()
            self._refresh_table()
        except Exception as e:
            logger.error(f"Failed to load backup data: {e}")
            self._show_error("Load Error", f"Failed to load backup configuration: {str(e)}")

    def _refresh_table(self):
        try:
            backups = backup_service.list_backups()
            self.table.setRowCount(0)
            self.table.setRowCount(len(backups))
            for i, b in enumerate(backups):
                self.table.setItem(i, 0, QTableWidgetItem(str(b.get("date", "N/A"))))
                self.table.setItem(i, 1, QTableWidgetItem(str(b.get("name", "Unknown"))))
                
                size_mb = b.get("size_mb", 0)
                self.table.setItem(i, 2, QTableWidgetItem(f"{float(size_mb):.2f} MB"))
                
                # Action Buttons
                actions_widget = QWidget()
                actions_layout = QHBoxLayout(actions_widget)
                actions_layout.setContentsMargins(5, 2, 5, 2)
                actions_layout.setSpacing(5)
                
                path = b.get("path", "")
                res_btn = QPushButton("Restore")
                res_btn.setStyleSheet("background-color: #3498db; color: white; padding: 2px 8px; font-size: 11px; border-radius: 3px;")
                res_btn.clicked.connect(lambda checked, p=path: self._on_restore_path(p))
                
                del_btn = QPushButton("Delete")
                del_btn.setStyleSheet("background-color: #e74c3c; color: white; padding: 2px 8px; font-size: 11px; border-radius: 3px;")
                del_btn.clicked.connect(lambda checked, p=path: self._on_delete_path(p))
                
                actions_layout.addWidget(res_btn)
                actions_layout.addWidget(del_btn)
                self.table.setCellWidget(i, 3, actions_widget)
        except Exception as e:
            logger.error(f"Failed to refresh backup table: {e}")

    def _refresh_keys_status(self) -> None:
        try:
            st = backup_service.get_encryption_status()
            if not st.get("encrypt"):
                self.keys_status.setText("Encryption disabled")
                return
            key_id = st.get("active_key_id") or "-"
            key_count = st.get("key_count") or 0
            self.keys_status.setText(f"Active Key ID: {key_id} | Keys: {key_count}")
        except Exception:
            self.keys_status.setText("")

    def _prompt_passphrase(self, title: str, prompt: str) -> Optional[str]:
        text, ok = QInputDialog.getText(self, title, prompt, QLineEdit.EchoMode.Password)
        if not ok:
            return None
        val = (text or "").strip()
        if not val:
            return None
        return val

    def _on_export_keys(self) -> None:
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Encryption Keys",
            "fbr_backup_keys.fbrkeys",
            "Key Bundle (*.fbrkeys);;All Files (*)",
        )
        if not path:
            return

        p1 = self._prompt_passphrase("Export Keys", "Set a passphrase to encrypt this key bundle:")
        if not p1:
            return
        p2 = self._prompt_passphrase("Export Keys", "Confirm passphrase:")
        if not p2:
            return
        if p1 != p2:
            self._show_error("Failed", "Passphrases do not match.")
            return

        res = backup_service.export_encryption_keys(path, p1)
        if res.get("success"):
            self._show_success("Success", "Keys exported. Store this file securely.")
        else:
            self._show_error("Failed", res.get("message") or "Export failed.")
        self._refresh_keys_status()

    def _on_import_keys(self) -> None:
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Encryption Keys",
            "",
            "Key Bundle (*.fbrkeys);;All Files (*)",
        )
        if not path:
            return

        p1 = self._prompt_passphrase("Import Keys", "Enter the passphrase for this key bundle:")
        if not p1:
            return

        res = backup_service.import_encryption_keys(path, p1)
        if res.get("success"):
            self._show_success("Success", res.get("message") or "Keys imported.")
        else:
            self._show_error("Failed", res.get("message") or "Import failed.")
        self._refresh_keys_status()

    def _on_browse(self):
        from PyQt6.QtWidgets import QFileDialog
        path = QFileDialog.getExistingDirectory(self, "Select Backup Directory", self.backup_path.text())
        if path:
            self.backup_path.setText(path)

    def _on_manual_backup(self):
        self.manual_backup_btn.setEnabled(False)
        self.manual_backup_btn.setText("⏳ Backing up...")
        fmt_text = (self.manual_format.currentText() or "").lower()
        fmt = "enc" if ".enc" in fmt_text else "zip"
        self.worker = BackupWorker(output_format=fmt)
        self.worker.finished.connect(self._handle_backup_result)
        self.worker.start()

    def _handle_backup_result(self, result):
        self.manual_backup_btn.setEnabled(True)
        self.manual_backup_btn.setText("💾 Create Backup Now")
        if result.get("success"):
            msg = result.get('message', "Backup created successfully.")
            self._show_success("Success", msg)
            self._refresh_table()
        else:
            error_msg = result.get("message") or result.get("error") or "Unknown error"
            self._show_error("Failed", error_msg)

    def _on_restore_file(self):
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Backup File",
            "",
            "Backup Files (*.enc *.zip *.sql);;Encrypted Backup (*.enc);;ZIP Backup (*.zip);;SQL Files (*.sql);;All Files (*)",
        )
        if path:
            self._on_restore_path(path)

    def _on_restore_path(self, path):
        reply = QMessageBox.warning(
            self, "Confirm Restore",
            "This will OVERWRITE all current database data.\n\nAre you sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._perform_restore(path)

    def _perform_restore(self, path):
        progress = QProgressDialog("Restoring Database...", None, 0, 0, self)
        progress.show()
        self.res_worker = MySQLRestoreWorker(path)
        self.res_worker.finished.connect(lambda res: self._handle_restore_result(res, progress))
        self.res_worker.start()

    def _handle_restore_result(self, result, progress):
        progress.close()
        if result.get("success"):
            QMessageBox.information(self, "Success", "Database restored. Restarting application...")
            os.execl(sys.executable, sys.executable, *sys.argv)
        else:
            error_msg = result.get("message") or result.get("error") or "Unknown error"
            self._show_error("Failed", error_msg)

    def _on_delete_path(self, path):
        if QMessageBox.question(self, "Confirm", "Delete this backup?") == QMessageBox.StandardButton.Yes:
            if backup_service.delete_backup(path):
                self._refresh_table()

    def save_settings(self):
        try:
            backup_service.update_config(
                backup_path=self.backup_path.text(),
                auto_backup=self.auto_enabled.isChecked(),
                interval=self.interval.currentText(),
                backup_time=self.time_input.text(),
                retention_days=self.retention.value()
            )
            self._show_success("Saved", "Backup settings updated.")
            self.accept()
        except Exception as e:
            self._show_error("Error", str(e))

class AppUpdatesDialog(BaseSettingsDialog):
    """Modal for Application Updates and Versioning."""
    def __init__(self, parent=None):
        super().__init__("Application Updates & Version", parent)
        self._init_ui()

    def _init_ui(self):
        from app.core.version_manager import VersionManager
        layout = QVBoxLayout()
        
        layout.addWidget(QLabel(f"Current Version: {VersionManager.get_version_string()}"))
        
        self.check_btn = QPushButton("🔄 Check for Updates Now")
        self.check_btn.setObjectName("primaryButton")
        self.check_btn.clicked.connect(self._on_check)
        layout.addWidget(self.check_btn)
        
        self.content_layout.addLayout(layout)
        self.save_btn.hide()

    def _on_check(self):
        try:
            parent = self.parent()
            while parent and not hasattr(parent, "_on_manual_update_check"):
                parent = parent.parent()
            
            if parent and hasattr(parent, "_on_manual_update_check"):
                parent._on_manual_update_check()
                self.accept()
            else:
                logger.warning("Main window update check method not found.")
                self._show_error("Error", "Update system not available from this context.")
        except Exception as e:
            logger.error(f"Error triggering update check: {e}")
            self._show_error("Error", f"Failed to check for updates: {str(e)}")
