"""
Portal Account Management Page

Allows staff members to:
- Look up a customer's portal account by customer ID or phone number
- Change/reset the portal account password
- View portal account status (active/inactive)
"""
from __future__ import annotations

from typing import Optional, Dict, Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
    QGroupBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QApplication,
)

from app.services.customer_portal_service import customer_portal_service
from app.services.customer_service import CustomerService
from app.db.models import Customer
from app.db.session import SessionLocal
from app.core.logger import logger


class PortalAccountPage(QWidget):
    """Desktop UI page for managing customer portal accounts and changing passwords."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Portal Account Management")
        self._customer_service = CustomerService()
        self._current_customer: Optional[Dict[str, Any]] = None
        self._setup_ui()

    # ── UI Setup ──────────────────────────────────────────────────────────

    def _setup_ui(self):
        self.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #dfe6e9;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 20px;
                background: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 8px;
                color: #2d3436;
            }
            QLineEdit {
                padding: 8px 12px;
                border: 1px solid #dfe6e9;
                border-radius: 6px;
                background: white;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #3498db;
            }
            QPushButton {
                padding: 8px 20px;
                border: 1px solid #dfe6e9;
                border-radius: 6px;
                background: white;
                font-weight: 500;
                font-size: 13px;
            }
            QPushButton:hover {
                background: #f1f2f6;
                border-color: #b2bec3;
            }
            QPushButton#btnChangePwd {
                background: #0984e3;
                color: white;
                border: none;
                padding: 10px 30px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 8px;
            }
            QPushButton#btnChangePwd:hover {
                background: #0773c5;
            }
            QPushButton#btnChangePwd:disabled {
                background: #b2bec3;
            }
            QPushButton#btnSearch {
                background: #00b894;
                color: white;
                border: none;
                padding: 8px 20px;
                font-weight: bold;
                border-radius: 6px;
            }
            QPushButton#btnSearch:hover {
                background: #00a381;
            }
            QLabel#infoLabel {
                font-size: 13px;
                color: #636e72;
            }
            QLabel#valueLabel {
                font-size: 13px;
                color: #2d3436;
                font-weight: 500;
            }
            QLabel#statusActive {
                color: #00b894;
                font-weight: bold;
                font-size: 13px;
            }
            QLabel#statusInactive {
                color: #d63031;
                font-weight: bold;
                font-size: 13px;
            }
            QFrame#card {
                background: #f8f9fa;
                border: 1px solid #dfe6e9;
                border-radius: 8px;
                padding: 15px;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(15)

        # ── Header ────────────────────────────────────────────────────────
        header = QLabel("Portal Account Management")
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #2d3436;")
        root.addWidget(header)

        desc = QLabel(
            "Search for a customer and change their portal account password. "
            "The customer uses their phone number as the login username."
        )
        desc.setStyleSheet("color: #636e72; font-size: 13px;")
        desc.setWordWrap(True)
        root.addWidget(desc)

        # ── Search Section ────────────────────────────────────────────────
        search_group = QGroupBox("Search Customer")
        search_layout = QGridLayout(search_group)
        search_layout.setSpacing(10)

        search_layout.addWidget(QLabel("Customer ID:"), 0, 0)
        self._input_customer_id = QLineEdit()
        self._input_customer_id.setPlaceholderText("Enter customer ID")
        self._input_customer_id.textChanged.connect(self._on_search_input_changed)
        search_layout.addWidget(self._input_customer_id, 0, 1)

        search_layout.addWidget(QLabel("Phone Number:"), 1, 0)
        self._input_phone = QLineEdit()
        self._input_phone.setPlaceholderText("Enter phone number")
        self._input_phone.textChanged.connect(self._on_search_input_changed)
        search_layout.addWidget(self._input_phone, 1, 1)

        self._btn_search = QPushButton("Search")
        self._btn_search.setObjectName("btnSearch")
        self._btn_search.clicked.connect(self._on_search)
        search_layout.addWidget(self._btn_search, 0, 2, 2, 1, Qt.AlignmentFlag.AlignBottom)

        root.addWidget(search_group)

        # ── Customer Info Section ─────────────────────────────────────────
        self._info_group = QGroupBox("Customer & Portal Account Info")
        info_layout = QFormLayout(self._info_group)
        info_layout.setSpacing(8)
        info_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self._lbl_customer_name = QLabel("--")
        self._lbl_customer_name.setObjectName("valueLabel")
        info_layout.addRow("Customer Name:", self._lbl_customer_name)

        self._lbl_customer_phone = QLabel("--")
        self._lbl_customer_phone.setObjectName("valueLabel")
        info_layout.addRow("Phone:", self._lbl_customer_phone)

        self._lbl_customer_cnic = QLabel("--")
        self._lbl_customer_cnic.setObjectName("valueLabel")
        info_layout.addRow("CNIC:", self._lbl_customer_cnic)

        info_layout.addRow("", QLabel(""))  # spacer

        self._lbl_portal_phone = QLabel("--")
        self._lbl_portal_phone.setObjectName("valueLabel")
        info_layout.addRow("Portal Login (Phone):", self._lbl_portal_phone)

        self._lbl_portal_status = QLabel("--")
        info_layout.addRow("Portal Account:", self._lbl_portal_status)

        self._lbl_portal_created = QLabel("--")
        self._lbl_portal_created.setObjectName("valueLabel")
        info_layout.addRow("Account Created:", self._lbl_portal_created)

        self._lbl_no_portal = QLabel("No portal account exists for this customer.")
        self._lbl_no_portal.setStyleSheet("color: #d63031; font-size: 12px;")
        self._lbl_no_portal.setVisible(False)
        info_layout.addRow("", self._lbl_no_portal)

        root.addWidget(self._info_group)

        # ── Change Password Section ───────────────────────────────────────
        self._pwd_group = QGroupBox("Change Password")
        pwd_layout = QGridLayout(self._pwd_group)
        pwd_layout.setSpacing(10)

        pwd_layout.addWidget(QLabel("New Password:"), 0, 0)
        self._input_new_password = QLineEdit()
        self._input_new_password.setPlaceholderText("Enter new password (min 4 characters)")
        pwd_layout.addWidget(self._input_new_password, 0, 1)

        pwd_layout.addWidget(QLabel("Confirm Password:"), 1, 0)
        self._input_confirm_password = QLineEdit()
        self._input_confirm_password.setPlaceholderText("Re-enter new password")
        pwd_layout.addWidget(self._input_confirm_password, 1, 1)

        btn_layout = QHBoxLayout()
        self._btn_generate = QPushButton("Generate Strong Password")
        self._btn_generate.clicked.connect(self._on_generate_password)
        btn_layout.addWidget(self._btn_generate)

        self._btn_change_pwd = QPushButton("Update Password")
        self._btn_change_pwd.setObjectName("btnChangePwd")
        self._btn_change_pwd.setEnabled(False)
        self._btn_change_pwd.clicked.connect(self._on_change_password)
        btn_layout.addWidget(self._btn_change_pwd)

        pwd_layout.addLayout(btn_layout, 2, 0, 1, 2)

        root.addWidget(self._pwd_group)

        # ── Initial state ─────────────────────────────────────────────────
        self._info_group.setVisible(False)
        self._pwd_group.setVisible(False)

        # ── Stretch ───────────────────────────────────────────────────────
        root.addStretch()

    # ── Search Logic ─────────────────────────────────────────────────────

    def _on_search_input_changed(self):
        """Clear results when input changes."""
        self._current_customer = None
        self._info_group.setVisible(False)
        self._pwd_group.setVisible(False)

    def _on_search(self):
        """Search for customer by ID or phone number."""
        customer_id_text = self._input_customer_id.text().strip()
        phone_text = self._input_phone.text().strip()

        if not customer_id_text and not phone_text:
            QMessageBox.warning(
                self,
                "Search Error",
                "Please enter a Customer ID or Phone Number to search."
            )
            return

        db = SessionLocal()
        try:
            customer = None
            if customer_id_text:
                try:
                    cid = int(customer_id_text)
                    customer = db.query(Customer).filter(Customer.id == cid).first()
                except ValueError:
                    QMessageBox.warning(self, "Invalid Input", "Customer ID must be a number.")
                    db.close()
                    return

            if not customer and phone_text:
                customer = db.query(Customer).filter(Customer.phone == phone_text).first()

            if not customer:
                QMessageBox.information(
                    self,
                    "Not Found",
                    "No customer found matching the search criteria."
                )
                self._info_group.setVisible(False)
                self._pwd_group.setVisible(False)
                db.close()
                return

            # Store current customer info
            self._current_customer = {
                "id": customer.id,
                "name": customer.name,
                "phone": customer.phone,
                "cnic": customer.cnic,
            }

            # Fill customer info
            self._lbl_customer_name.setText(customer.name or "--")
            self._lbl_customer_phone.setText(customer.phone or "--")
            self._lbl_customer_cnic.setText(customer.cnic or "--")

            # Look up portal account
            portal_info = customer_portal_service.get_portal_account_info(customer.id)

            if portal_info:
                self._lbl_portal_phone.setText(portal_info["phone_number"] or "--")
                is_active = portal_info["is_active"]
                if is_active:
                    self._lbl_portal_status.setText("ACTIVE")
                    self._lbl_portal_status.setStyleSheet(
                        "color: #00b894; font-weight: bold; font-size: 13px;"
                    )
                else:
                    self._lbl_portal_status.setText("INACTIVE (Blocked)")
                    self._lbl_portal_status.setStyleSheet(
                        "color: #d63031; font-weight: bold; font-size: 13px;"
                    )
                created = portal_info.get("created_at")
                self._lbl_portal_created.setText(
                    str(created)[:19] if created else "--"
                )
                self._lbl_no_portal.setVisible(False)
                self._pwd_group.setVisible(True)
                self._btn_change_pwd.setEnabled(True)
            else:
                self._lbl_portal_phone.setText("--")
                self._lbl_portal_status.setText("NO ACCOUNT")
                self._lbl_portal_status.setStyleSheet(
                    "color: #d63031; font-weight: bold; font-size: 13px;"
                )
                self._lbl_portal_created.setText("--")
                self._lbl_no_portal.setVisible(True)
                self._pwd_group.setVisible(False)

            self._info_group.setVisible(True)

        except Exception as e:
            logger.error(f"Error searching customer: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Error",
                f"An error occurred while searching:\n{e}"
            )
        finally:
            db.close()

    # ── Password Change Logic ────────────────────────────────────────────

    def _on_generate_password(self):
        """Generate a strong random password and fill the fields."""
        password = customer_portal_service._generate_password(10)
        self._input_new_password.setText(password)
        self._input_confirm_password.setText(password)

    def _on_change_password(self):
        """Change the portal account password."""
        if not self._current_customer:
            return

        new_password = self._input_new_password.text().strip()
        confirm_password = self._input_confirm_password.text().strip()

        # Validation
        if not new_password:
            QMessageBox.warning(self, "Validation Error", "Please enter a new password.")
            self._input_new_password.setFocus()
            return

        if len(new_password) < 4:
            QMessageBox.warning(
                self,
                "Validation Error",
                "Password must be at least 4 characters long."
            )
            self._input_new_password.setFocus()
            return

        if new_password != confirm_password:
            QMessageBox.warning(
                self,
                "Validation Error",
                "Passwords do not match. Please re-enter."
            )
            self._input_confirm_password.clear()
            self._input_confirm_password.setFocus()
            return

        # Confirm with the user
        reply = QMessageBox.question(
            self,
            "Confirm Password Change",
            f"Are you sure you want to change the portal password for:\n\n"
            f"Customer: {self._current_customer['name']}\n"
            f"Phone: {self._current_customer['phone']}\n\n"
            f"New Password: {new_password}\n\n"
            f"The customer will need to use this new password to log in.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Perform the password change
        result = customer_portal_service.change_password(
            customer_id=self._current_customer["id"],
            new_password=new_password
        )

        if result:
            QMessageBox.information(
                self,
                "Password Changed Successfully",
                f"Portal password has been updated.\n\n"
                f"Customer: {result['customer_name']}\n"
                f"Login (Phone): {result['phone_number']}\n"
                f"New Password: {result['password']}\n\n"
                f"Please share the new password with the customer."
            )
            # Clear password fields for security
            self._input_new_password.clear()
            self._input_confirm_password.clear()
        else:
            QMessageBox.critical(
                self,
                "Error",
                "Failed to change password. The customer may not have a portal account.\n"
                "A portal account is created automatically when a credit sale is issued."
            )

    # ── Keyboard shortcuts ──────────────────────────────────────────────

    def keyPressEvent(self, event):
        """Handle Enter key to trigger search."""
        from PyQt6.QtGui import QKeyEvent
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            if self._input_customer_id.hasFocus() or self._input_phone.hasFocus():
                self._on_search()
            elif self._input_new_password.hasFocus() or self._input_confirm_password.hasFocus():
                if self._btn_change_pwd.isEnabled():
                    self._on_change_password()
        super().keyPressEvent(event)
