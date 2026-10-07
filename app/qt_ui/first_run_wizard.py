"""First-launch setup: creates the Administrator account, auto-launched by
app/qt_main.py in place of LoginDialog when the database has no Admin yet
(app/services/staff_account_service.py's has_any_admin())."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
)

from app.services import staff_account_service


_DIALOG_STYLE = """
    QDialog { background-color: #f8f9fa; }
    QLabel { color: #2c3e50; }
    QLineEdit {
        padding: 10px; border: 1px solid #ced4da; border-radius: 4px;
        background-color: white; font-size: 13px;
    }
    QLineEdit:focus { border: 1px solid #3498db; }
    QPushButton#primary {
        background-color: #3498db; color: white; border: none;
        padding: 10px 20px; font-weight: bold; border-radius: 4px;
    }
    QPushButton#primary:hover { background-color: #2980b9; }
"""


class FirstRunWizard(QDialog):
    """Auto-launched by app/qt_main.py when
    staff_account_service.has_any_admin() is False - the normal login
    screen would otherwise be a guaranteed dead end.
    created_account is set on success (result == QDialog.DialogCode.Accepted)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Welcome")
        self.setMinimumWidth(460)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setStyleSheet(_DIALOG_STYLE)
        self.created_account = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 32, 36, 28)
        layout.setSpacing(10)

        title = QLabel("Create Administrator Account")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #1a252f;")
        layout.addWidget(title)
        subtitle = QLabel("Let's set up your administrator account.")
        subtitle.setStyleSheet("color: #6c757d; font-size: 12px;")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        layout.addSpacing(6)

        layout.addWidget(QLabel("Full Name *"))
        self.admin_name_input = QLineEdit()
        layout.addWidget(self.admin_name_input)

        layout.addWidget(QLabel("Admin Mobile Number / Username *"))
        self.admin_mobile_input = QLineEdit()
        self.admin_mobile_input.setPlaceholderText("e.g. 03001234567")
        layout.addWidget(self.admin_mobile_input)

        layout.addWidget(QLabel("Password *"))
        self.admin_password_input = QLineEdit()
        self.admin_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.admin_password_input)

        layout.addWidget(QLabel("Confirm Password *"))
        self.admin_confirm_input = QLineEdit()
        self.admin_confirm_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.admin_confirm_input)

        self.admin_error_label = QLabel("")
        self.admin_error_label.setStyleSheet("color: #e74c3c; font-size: 12px;")
        self.admin_error_label.setWordWrap(True)
        layout.addWidget(self.admin_error_label)

        button_row = QHBoxLayout()
        exit_btn = QPushButton("Exit")
        exit_btn.clicked.connect(self.reject)
        button_row.addWidget(exit_btn)
        create_btn = QPushButton("Create Administrator")
        create_btn.setObjectName("primary")
        create_btn.clicked.connect(self._on_create_admin)
        button_row.addWidget(create_btn)
        layout.addLayout(button_row)

    def _on_create_admin(self):
        self.admin_error_label.setText("")

        full_name = self.admin_name_input.text().strip()
        mobile = self.admin_mobile_input.text().strip()
        password = self.admin_password_input.text()
        confirm = self.admin_confirm_input.text()

        if not full_name or not mobile or not password:
            self.admin_error_label.setText("Full name, mobile number, and password are all required.")
            return
        if password != confirm:
            self.admin_error_label.setText("Passwords do not match.")
            return
        if len(password) < 6:
            self.admin_error_label.setText("Password must be at least 6 characters.")
            return

        try:
            self.created_account = staff_account_service.create_first_admin(
                mobile_number=mobile,
                password=password,
                full_name=full_name,
            )
        except Exception as e:
            self.admin_error_label.setText(str(e))
            return

        # Explicit confirmation that the record now exists, rather than
        # just trusting the call didn't raise.
        if not staff_account_service.has_any_admin():
            self.admin_error_label.setText("Setup could not be confirmed. Please try again.")
            return

        self.accept()
