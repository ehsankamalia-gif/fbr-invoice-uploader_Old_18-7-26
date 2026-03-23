import base64
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QLineEdit, QTextEdit, QFrame, 
                             QApplication, QMessageBox, QScrollArea)
from PyQt6.QtCore import Qt, pyqtSlot, QSize
from PyQt6.QtGui import QPixmap, QImage, QColor, QFont

from app.services.whatsapp_service import whatsapp_service
from app.core.logger import logger

class WhatsAppWidget(QWidget):
    """
    Production-ready PyQt6 widget for WhatsApp integration.
    Handles QR display, status monitoring, and message testing.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.connect_service()

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setSpacing(15)

        # 1. Status Banner
        self.status_frame = QFrame()
        self.status_frame.setFixedHeight(50)
        self.status_frame.setStyleSheet("background-color: #f8f9fa; border-radius: 8px; border: 1px solid #dee2e6;")
        status_layout = QHBoxLayout(self.status_frame)
        
        self.status_dot = QLabel()
        self.status_dot.setFixedSize(12, 12)
        self.set_status_color("gray")
        
        self.status_text = QLabel("Status: Initializing...")
        self.status_text.setStyleSheet("font-weight: bold; color: #495057;")
        
        status_layout.addWidget(self.status_dot)
        status_layout.addWidget(self.status_text)
        status_layout.addStretch()
        
        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.clicked.connect(self.refresh_status)
        status_layout.addWidget(self.refresh_btn)
        
        self.reset_btn = QPushButton("🗑️ Reset Instance")
        self.reset_btn.setToolTip("Force logout and delete instance to fix 'Stuck' state.")
        self.reset_btn.setStyleSheet("color: #e74c3c; font-weight: bold;")
        self.reset_btn.clicked.connect(self.on_reset_clicked)
        status_layout.addWidget(self.reset_btn)
        
        self.main_layout.addWidget(self.status_frame)

        # 2. QR Code Area
        self.qr_frame = QFrame()
        self.qr_frame.setMinimumHeight(300)
        self.qr_frame.setStyleSheet("background-color: white; border: 2px dashed #ced4da; border-radius: 8px;")
        qr_layout = QVBoxLayout(self.qr_frame)
        
        self.qr_label = QLabel("Scan QR Code to Connect")
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setWordWrap(True)
        self.qr_label.setStyleSheet("color: #6c757d; font-size: 14px;")
        qr_layout.addWidget(self.qr_label)
        
        self.main_layout.addWidget(self.qr_frame)

        # 3. Test Message Section
        msg_group = QFrame()
        msg_group.setStyleSheet("background-color: #e9ecef; border-radius: 8px; padding: 10px;")
        msg_layout = QVBoxLayout(msg_group)
        
        msg_layout.addWidget(QLabel("<b>Quick Test Message</b>"))
        
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("Phone Number (e.g. 923001234567)")
        msg_layout.addWidget(self.phone_input)
        
        self.msg_input = QTextEdit()
        self.msg_input.setPlaceholderText("Enter message content...")
        self.msg_input.setMaximumHeight(80)
        msg_layout.addWidget(self.msg_input)
        
        self.send_btn = QPushButton("Send WhatsApp")
        self.send_btn.setStyleSheet("""
            QPushButton { background-color: #25d366; color: white; font-weight: bold; padding: 8px; border: none; border-radius: 4px; }
            QPushButton:hover { background-color: #128c7e; }
            QPushButton:disabled { background-color: #adb5bd; }
        """)
        self.send_btn.clicked.connect(self.on_send_clicked)
        msg_layout.addWidget(self.send_btn)
        
        self.main_layout.addWidget(msg_group)
        self.main_layout.addStretch()

    def set_status_color(self, color):
        self.status_dot.setStyleSheet(f"background-color: {color}; border-radius: 6px;")

    def connect_service(self):
        whatsapp_service.start_monitoring(
            status_callback=self.update_status,
            qr_callback=self.display_qr
        )
        if whatsapp_service.worker:
            whatsapp_service.worker.message_result.connect(self.on_message_result)
            whatsapp_service.worker.error_occurred.connect(self.on_error)

    @pyqtSlot(str)
    def update_status(self, status):
        status = status.lower()
        logger.info(f"UI received status update: {status}")
        
        if status == "open":
            self.status_text.setText("Status: CONNECTED ✅")
            self.set_status_color("#2ecc71")
            self.qr_label.setText("WhatsApp is Ready")
            self.send_btn.setEnabled(True)
        elif status == "connecting":
            self.status_text.setText("Status: CONNECTING... ⏳")
            self.set_status_color("#f1c40f")
            if not self.qr_label.pixmap():
                self.qr_label.setText("Instance is connecting. Please scan the QR code if it appears below.")
        elif status == "creating":
            self.status_text.setText("Status: CREATING INSTANCE...")
            self.set_status_color("#3498db")
            self.qr_label.setText("Setting up instance on server...")
        elif "not_found" in status:
            self.status_text.setText("Status: NOT FOUND")
            self.set_status_color("#e67e22")
            self.qr_label.setText("Instance not found. Auto-creating...")
        elif "error" in status or "offline" in status:
            err_msg = status.split(":", 1)[1] if ":" in status else status
            self.status_text.setText(f"Status: ERROR ❌")
            self.set_status_color("#e74c3c")
            self.qr_label.setText(f"<b>Connection Error:</b><br>{err_msg}<br><br>Check Evolution API URL & Key in .env")
            self.send_btn.setEnabled(False)
        else:
            self.status_text.setText(f"Status: {status.upper()}")
            self.set_status_color("#e74c3c")
            self.send_btn.setEnabled(False)
            if status == "close" or status == "disconnected":
                self.qr_label.setText("Waiting for QR Code...")

    @pyqtSlot(str)
    def display_qr(self, base64_data):
        try:
            # Evolution returns format "data:image/png;base64,iVBOR..." or raw base64
            if "," in base64_data:
                base64_data = base64_data.split(",")[1]
            
            img_data = base64.b64decode(base64_data)
            image = QImage.fromData(img_data)
            pixmap = QPixmap.fromImage(image)
            
            scaled = pixmap.scaled(280, 280, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.qr_label.setPixmap(scaled)
        except Exception as e:
            self.qr_label.setText(f"Error loading QR: {e}")

    def refresh_status(self):
        if whatsapp_service.worker:
            whatsapp_service.worker.set_action("status")

    def on_reset_clicked(self):
        reply = QMessageBox.question(
            self, "Reset WhatsApp Instance",
            "This will logout and delete your current WhatsApp instance from the server. "
            "You will need to scan the QR code again. Proceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.status_text.setText("Status: RESETTING...")
            self.set_status_color("#e67e22")
            whatsapp_service.worker.set_action("reset")

    def on_send_clicked(self):
        num = self.phone_input.text().strip()
        txt = self.msg_input.toPlainText().strip()
        if not num or not txt:
            QMessageBox.warning(self, "Validation", "Please enter number and message.")
            return
        
        self.send_btn.setEnabled(False)
        self.send_btn.setText("Sending...")
        whatsapp_service.send_quick_message(num, txt)

    def on_message_result(self, success, msg):
        self.send_btn.setEnabled(True)
        self.send_btn.setText("Send WhatsApp")
        if success:
            QMessageBox.information(self, "Success", "Message Sent Successfully!")
            self.msg_input.clear()
        else:
            QMessageBox.critical(self, "Error", f"Failed to send: {msg}")

    def on_error(self, err):
        QMessageBox.warning(self, "WhatsApp Error", f"Service reported error: {err}")
