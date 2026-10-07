"""Desktop login gate, shown once at startup (app/qt_main.py) before
MainWindow is ever constructed. Entirely desktop-owned: no Django imports,
no shared code with the customer portal's authentication."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFrame, QStackedWidget, QWidget,
)

from app.services import staff_account_service
from app.services.auth_session import auth_session
from app.services.settings_service import settings_service


_DIALOG_STYLE = """
    QDialog { background-color: #f8f9fa; }
    QLabel { color: #2c3e50; }
    QLineEdit, QComboBox {
        padding: 10px; border: 1px solid #ced4da; border-radius: 4px;
        background-color: white; font-size: 13px;
    }
    QLineEdit:focus, QComboBox:focus { border: 1px solid #3498db; }
    QPushButton#primary {
        background-color: #3498db; color: white; border: none;
        padding: 10px 20px; font-weight: bold; border-radius: 4px;
    }
    QPushButton#primary:hover { background-color: #2980b9; }
    QPushButton#link {
        background-color: transparent; color: #3498db; border: none;
        text-decoration: underline; padding: 4px;
    }
"""


class LoginDialog(QDialog):
    """Mobile-number + password login for a desktop Staff/Admin account.
    On success, populates auth_session and accept()s; the caller
    (app/qt_main.py) proceeds to build MainWindow only after accept()."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ehsan Trader FBR System - Login")
        self.setMinimumWidth(420)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setStyleSheet(_DIALOG_STYLE)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 32, 36, 28)
        layout.setSpacing(14)

        title = QLabel("Sign in")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #1a252f;")
        layout.addWidget(title)

        subtitle = QLabel("Use your company mobile number and password.")
        subtitle.setStyleSheet("color: #6c757d; font-size: 12px;")
        layout.addWidget(subtitle)

        layout.addSpacing(10)

        layout.addWidget(QLabel("Mobile Number"))
        self.mobile_input = QLineEdit()
        self.mobile_input.setPlaceholderText("03021234567")
        self.mobile_input.setMaxLength(11)
        self.mobile_input.textChanged.connect(self._format_mobile_input)
        layout.addWidget(self.mobile_input)

        layout.addWidget(QLabel("Password"))
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Enter your password")
        self.password_input.returnPressed.connect(self._on_login)
        layout.addWidget(self.password_input)

        forgot_btn = QPushButton("Forgot Password?")
        forgot_btn.setObjectName("link")
        forgot_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        forgot_btn.clicked.connect(self._on_forgot_password)
        layout.addWidget(forgot_btn, alignment=Qt.AlignmentFlag.AlignRight)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #e74c3c; font-size: 12px;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        self.login_btn = QPushButton("Sign In")
        self.login_btn.setObjectName("primary")
        self.login_btn.clicked.connect(self._on_login)
        layout.addWidget(self.login_btn)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #e9ecef;")
        layout.addWidget(divider)

        exit_btn = QPushButton("Exit")
        exit_btn.setObjectName("link")
        exit_btn.clicked.connect(self.reject)
        layout.addWidget(exit_btn, alignment=Qt.AlignmentFlag.AlignRight)

    def _format_mobile_input(self, text: str) -> None:
        digits = "".join(c for c in text if c.isdigit())[:11]
        if digits != text:
            self.mobile_input.blockSignals(True)
            self.mobile_input.setText(digits)
            self.mobile_input.blockSignals(False)
        if len(digits) == 11:
            self.password_input.setFocus()

    def _on_login(self):
        mobile = self.mobile_input.text().strip()
        password = self.password_input.text()
        self.error_label.setText("")

        if not mobile or not password:
            self.error_label.setText("Enter both mobile number and password.")
            return

        try:
            result = staff_account_service.authenticate(mobile, password)
        except Exception as e:
            self.error_label.setText(f"Login failed: {e}")
            return

        if not result:
            self.error_label.setText("Invalid mobile number or password, or the account is inactive.")
            return

        auth_session.login(
            staff_id=result["staff_id"],
            role=result["role"],
            full_name=result["full_name"],
            mobile_number=result["mobile_number"],
            permissions=result["permissions"],
        )
        self.accept()

    def _on_forgot_password(self):
        dialog = ForgotPasswordDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.reset_mobile_number:
            self.mobile_input.setText(dialog.reset_mobile_number)
            self.password_input.clear()
            self.password_input.setFocus()
            self.error_label.setStyleSheet("color: #27ae60; font-size: 12px;")
            self.error_label.setText("Password reset. Sign in with your new password.")


class ForgotPasswordDialog(QDialog):
    """Recovery for someone who cannot log in because they forgot their
    password: mobile number -> OTP sent and verified -> set a new password.

    A thin UI shell around app/services/staff_account_service.py's
    request_password_reset_otp / verify_password_reset_otp /
    reset_password_with_verified_otp - the actual security logic (expiry,
    attempt limits) lives there, not here, so it holds even if this dialog
    is bypassed.

    On success, self.reset_mobile_number is set so LoginDialog can prefill
    the mobile field - mirrors FirstRunWizard's created_account convenience."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Forgot Password")
        self.setMinimumWidth(440)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setStyleSheet(_DIALOG_STYLE)
        self.reset_mobile_number: str | None = None
        self._mobile = ""
        self._selected_account: dict | None = None
        self._otp_seconds_remaining = 0
        self._otp_countdown_timer = QTimer(self)
        self._otp_countdown_timer.setInterval(1000)
        self._otp_countdown_timer.timeout.connect(self._tick_otp_countdown)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 32, 36, 28)
        layout.setSpacing(14)

        title = QLabel("Reset your password")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #1a252f;")
        layout.addWidget(title)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack)
        self.stack.addWidget(self._build_mobile_page())
        self.stack.addWidget(self._build_otp_page())
        self.stack.addWidget(self._build_new_password_page())

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #e74c3c; font-size: 12px;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("link")
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn, alignment=Qt.AlignmentFlag.AlignRight)

    def reject(self):
        self._stop_otp_countdown()
        super().reject()

    # --- Step 1: mobile number -> find matching company accounts --------
    def _build_mobile_page(self) -> QWidget:
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(10)

        pl.addWidget(QLabel("Enter your registered mobile number. We'll text you a verification code."))
        self.fp_mobile_input = QLineEdit()
        self.fp_mobile_input.setPlaceholderText("03021234567")
        self.fp_mobile_input.setMaxLength(11)
        self.fp_mobile_input.textChanged.connect(self._format_fp_mobile_input)
        pl.addWidget(self.fp_mobile_input)

        self.fp_continue_btn = QPushButton("Continue")
        self.fp_continue_btn.setObjectName("primary")
        self.fp_continue_btn.clicked.connect(self._on_mobile_continue)
        pl.addWidget(self.fp_continue_btn)
        pl.addStretch(1)
        return page

    def _format_fp_mobile_input(self, text: str) -> None:
        digits = "".join(c for c in text if c.isdigit())[:11]
        if digits != text:
            self.fp_mobile_input.blockSignals(True)
            self.fp_mobile_input.setText(digits)
            self.fp_mobile_input.blockSignals(False)

    def _on_mobile_continue(self):
        self.error_label.setText("")
        mobile = self.fp_mobile_input.text().strip()
        if len(mobile) != 11:
            self.error_label.setText("Enter a valid 11-digit mobile number.")
            return
        self._mobile = mobile
        self._send_otp()

    # --- Send the OTP ------------------------------------------------------
    def _send_otp(self) -> None:
        self.error_label.setText("")
        self.fp_continue_btn.setEnabled(False)
        try:
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
            staff_account_service.request_password_reset_otp(self._mobile)
            self.fp_sent_to_label.setText(f"A verification code was sent to {self._mobile}.")
            self.fp_otp_input.clear()
            self.fp_verify_btn.setEnabled(True)
            self._start_otp_countdown()
            self.fp_otp_input.setFocus()
            self.stack.setCurrentIndex(1)
        except ValueError as ve:
            self.error_label.setText(str(ve))
        except Exception as e:
            self.error_label.setText(f"Could not send code: {e}")
        finally:
            self.fp_continue_btn.setEnabled(True)

    # --- OTP expiry countdown ---------------------------------------------
    def _start_otp_countdown(self) -> None:
        self._otp_seconds_remaining = staff_account_service.OTP_EXPIRY_MINUTES * 60
        self._update_otp_countdown_label()
        self._otp_countdown_timer.start()

    def _stop_otp_countdown(self) -> None:
        self._otp_countdown_timer.stop()

    def _tick_otp_countdown(self) -> None:
        self._otp_seconds_remaining -= 1
        self._update_otp_countdown_label()
        if self._otp_seconds_remaining <= 0:
            self._stop_otp_countdown()
            self.fp_verify_btn.setEnabled(False)

    def _update_otp_countdown_label(self) -> None:
        remaining = max(0, self._otp_seconds_remaining)
        minutes, seconds = divmod(remaining, 60)
        if remaining <= 0:
            self.fp_countdown_label.setText("⏱ Code expired — request a new one")
            self.fp_countdown_label.setStyleSheet(
                "background-color: #fdecea; color: #c0392b; font-weight: 600; font-size: 12px;"
                " padding: 5px 14px; border-radius: 12px; border: 1px solid #f3c6c1;"
            )
        elif remaining <= 60:
            self.fp_countdown_label.setText(f"⏱ Code expires in {minutes:01d}:{seconds:02d}")
            self.fp_countdown_label.setStyleSheet(
                "background-color: #fff6e5; color: #92610a; font-weight: 600; font-size: 12px;"
                " font-family: Consolas, monospace; padding: 5px 14px; border-radius: 12px; border: 1px solid #f1dfb3;"
            )
        else:
            self.fp_countdown_label.setText(f"⏱ Code expires in {minutes:01d}:{seconds:02d}")
            self.fp_countdown_label.setStyleSheet(
                "background-color: #eef2f7; color: #475569; font-weight: 600; font-size: 12px;"
                " font-family: Consolas, monospace; padding: 5px 14px; border-radius: 12px; border: 1px solid #dde4ec;"
            )

    # --- Step 3: verify OTP ------------------------------------------------
    def _build_otp_page(self) -> QWidget:
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(10)

        self.fp_sent_to_label = QLabel("")
        self.fp_sent_to_label.setWordWrap(True)
        self.fp_sent_to_label.setStyleSheet("color: #6c757d; font-size: 12px;")
        pl.addWidget(self.fp_sent_to_label)

        countdown_row = QHBoxLayout()
        countdown_row.addStretch(1)
        self.fp_countdown_label = QLabel("")
        self.fp_countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        countdown_row.addWidget(self.fp_countdown_label)
        countdown_row.addStretch(1)
        pl.addLayout(countdown_row)

        pl.addWidget(QLabel("Verification Code"))
        self.fp_otp_input = QLineEdit()
        self.fp_otp_input.setPlaceholderText("6-digit code")
        self.fp_otp_input.setMaxLength(6)
        self.fp_otp_input.returnPressed.connect(self._on_verify_otp)
        pl.addWidget(self.fp_otp_input)

        self.fp_verify_btn = QPushButton("Verify Code")
        self.fp_verify_btn.setObjectName("primary")
        self.fp_verify_btn.clicked.connect(self._on_verify_otp)
        pl.addWidget(self.fp_verify_btn)

        resend_row = QHBoxLayout()
        back_btn = QPushButton("Back")
        back_btn.setObjectName("link")
        back_btn.clicked.connect(lambda: (self._stop_otp_countdown(), self.error_label.setText(""), self.stack.setCurrentIndex(0)))
        resend_row.addWidget(back_btn)
        resend_row.addStretch(1)
        resend_btn = QPushButton("Resend Code")
        resend_btn.setObjectName("link")
        resend_btn.clicked.connect(lambda: self._send_otp())
        resend_row.addWidget(resend_btn)
        pl.addLayout(resend_row)
        pl.addStretch(1)
        return page

    def _on_verify_otp(self):
        self.error_label.setText("")
        code = self.fp_otp_input.text().strip()
        if len(code) != 6:
            self.error_label.setText("Enter the 6-digit code.")
            return
        try:
            self._selected_account = staff_account_service.verify_password_reset_otp(self._mobile, code)
            self._stop_otp_countdown()
            self._enter_new_password_step()
            self.stack.setCurrentIndex(2)
        except ValueError as ve:
            self.error_label.setText(str(ve))
        except Exception as e:
            self.error_label.setText(f"Verification failed: {e}")

    # --- Step 4: set new password -----------------------------------------
    def _build_new_password_page(self) -> QWidget:
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(10)

        self.fp_account_label = QLabel("")
        self.fp_account_label.setWordWrap(True)
        self.fp_account_label.setStyleSheet("color: #2c3e50; font-weight: bold; font-size: 13px;")
        pl.addWidget(self.fp_account_label)

        pl.addWidget(QLabel("New Password"))
        self.fp_new_password_input = QLineEdit()
        self.fp_new_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.fp_new_password_input.setPlaceholderText("At least 6 characters")
        pl.addWidget(self.fp_new_password_input)

        pl.addWidget(QLabel("Confirm New Password"))
        self.fp_confirm_password_input = QLineEdit()
        self.fp_confirm_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.fp_confirm_password_input.returnPressed.connect(self._on_reset_password)
        pl.addWidget(self.fp_confirm_password_input)

        self.fp_reset_btn = QPushButton("Reset Password")
        self.fp_reset_btn.setObjectName("primary")
        self.fp_reset_btn.clicked.connect(self._on_reset_password)
        pl.addWidget(self.fp_reset_btn)
        pl.addStretch(1)
        return page

    def _enter_new_password_step(self):
        acc = self._selected_account or {}
        self.fp_account_label.setText(
            f"Resetting password for:\n{acc.get('full_name', '')} ({acc.get('role', '').capitalize()})"
        )
        self.fp_new_password_input.clear()
        self.fp_confirm_password_input.clear()
        self.fp_new_password_input.setFocus()

    def _on_reset_password(self):
        self.error_label.setText("")
        new_pw = self.fp_new_password_input.text()
        confirm_pw = self.fp_confirm_password_input.text()
        if not new_pw or not confirm_pw:
            self.error_label.setText("Enter and confirm your new password.")
            return
        if new_pw != confirm_pw:
            self.error_label.setText("Passwords do not match.")
            return

        try:
            staff_account_service.reset_password_with_verified_otp(self._mobile, new_pw)
            self.reset_mobile_number = self._mobile
            self.accept()
        except ValueError as ve:
            self.error_label.setText(str(ve))
        except Exception as e:
            self.error_label.setText(f"Could not reset password: {e}")

