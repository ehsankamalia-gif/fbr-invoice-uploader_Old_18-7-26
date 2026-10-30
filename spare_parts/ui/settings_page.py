"""Spare Parts module settings: general module behavior plus this
module's OWN FBR API/security settings.

The FBR fields here mirror both the FIELD SET and the per-environment
BEHAVIOR of the main app's "FBR API & Security Configuration" dialog
(Environment, API Base URL, POS ID, USIN, Auth Token, Secret Key) -
switching Environment swaps in that environment's own saved values,
same as the main app. The storage is entirely separate (this module's
own sp_settings/sp_fbr_environments tables, not
app.db.models.FBRConfiguration / Company.ntn), and nothing here is read
by, linked to, or used by the invoice-upload/FBR-submission code in any
way. See spare_parts/__init__.py for this module's independence rules.
"""
from __future__ import annotations

from PyQt6.QtCore import QSignalBlocker
from PyQt6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from spare_parts.db.base import get_spare_session
from spare_parts.services import settings_service
from spare_parts.ui.widgets import NoScrollComboBox, NoScrollDoubleSpinBox
from spare_parts.logging_config import get_logger

logger = get_logger(__name__)

_PRIMARY_BTN = """
    QPushButton {
        background-color: #3498db; color: white; border: none;
        border-radius: 4px; padding: 8px 16px; font-weight: bold;
    }
    QPushButton:hover { background-color: #2980b9; }
    QPushButton:disabled { background-color: #bdc3c7; }
"""

_RESET_BTN = """
    QPushButton {
        background-color: #f8f9fa; color: #6c757d; border: 1px solid #dee2e6;
        border-radius: 4px; padding: 8px 16px;
    }
    QPushButton:hover { background-color: #e2e6ea; }
"""

_EYE_BTN_QSS = """
    QPushButton {
        background-color: #f8f9fa; color: #6c757d; border: 1px solid #dee2e6;
        border-radius: 4px; padding: 4px 8px;
    }
    QPushButton:hover { background-color: #e2e6ea; }
"""

_GROUP_STYLE = """
    QFrame#spSettingsGroup {
        background-color: white;
        border: 1px solid #e9ecef;
        border-radius: 8px;
    }
"""


def _make_group(title: str) -> tuple[QFrame, QFormLayout]:
    frame = QFrame()
    frame.setObjectName("spSettingsGroup")
    frame.setStyleSheet(_GROUP_STYLE)
    outer = QVBoxLayout(frame)
    outer.setContentsMargins(16, 14, 16, 14)
    outer.setSpacing(10)

    header = QLabel(title)
    header.setStyleSheet("font-size: 14px; font-weight: bold; color: #2c3e50;")
    outer.addWidget(header)

    form = QFormLayout()
    form.setSpacing(10)
    outer.addLayout(form)
    return frame, form


def _make_password_row(line_edit: QLineEdit) -> QWidget:
    """A password-style QLineEdit (masked by default) with a small
    show/hide toggle button next to it - an in-module equivalent of the
    eye-icon toggle on the main app's Auth Token/Secret Key fields, built
    from a plain QPushButton (no external icon file) to keep this
    module's own visual-asset independence (see spare_parts/ui/widgets.py's
    runtime-painted trash_icon() for the same principle)."""
    line_edit.setEchoMode(QLineEdit.EchoMode.Password)
    toggle_btn = QPushButton("Show")
    toggle_btn.setStyleSheet(_EYE_BTN_QSS)
    toggle_btn.setFixedWidth(52)
    toggle_btn.setAutoDefault(False)

    def _toggle() -> None:
        masked = line_edit.echoMode() == QLineEdit.EchoMode.Password
        line_edit.setEchoMode(QLineEdit.EchoMode.Normal if masked else QLineEdit.EchoMode.Password)
        toggle_btn.setText("Hide" if masked else "Show")

    toggle_btn.clicked.connect(_toggle)

    container = QWidget()
    row = QHBoxLayout(container)
    row.setContentsMargins(0, 0, 0, 0)
    row.addWidget(line_edit, 1)
    row.addWidget(toggle_btn)
    return container


class SettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        header = QLabel("Settings")
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(header)

        scroll_content = QWidget()
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setSpacing(16)

        general_group, general_form = _make_group("General")
        company_note = QLabel(
            "Company Name on the receipt header is read directly from the main "
            "application's own Company setting - there is nothing to configure here."
        )
        company_note.setWordWrap(True)
        company_note.setStyleSheet("color: #6c757d; font-size: 11px;")
        general_form.addRow(company_note)

        self.allow_negative_stock_checkbox = QCheckBox(
            "Allow negative stock (sales/adjustments can take a part below zero)"
        )
        general_form.addRow("", self.allow_negative_stock_checkbox)

        self.default_tax_percent_spin = NoScrollDoubleSpinBox()
        self.default_tax_percent_spin.setRange(0, 100)
        self.default_tax_percent_spin.setDecimals(2)
        self.default_tax_percent_spin.setToolTip(
            "Default tax % pre-filled on a new sale - can still be changed per sale."
        )
        general_form.addRow("Default Tax %", self.default_tax_percent_spin)

        self.purchase_no_prefix_input = QLineEdit()
        self.purchase_no_prefix_input.setMaxLength(10)
        self.purchase_no_prefix_input.setToolTip("Prefix for generated purchase numbers, e.g. 'PO-'.")
        general_form.addRow("Purchase No. Prefix", self.purchase_no_prefix_input)

        self.wholesale_no_prefix_input = QLineEdit()
        self.wholesale_no_prefix_input.setMaxLength(10)
        self.wholesale_no_prefix_input.setToolTip("Prefix for generated wholesale sale numbers, e.g. 'WS-'.")
        general_form.addRow("Wholesale No. Prefix", self.wholesale_no_prefix_input)

        self.retail_no_prefix_input = QLineEdit()
        self.retail_no_prefix_input.setMaxLength(10)
        self.retail_no_prefix_input.setToolTip("Prefix for generated retail sale numbers, e.g. 'RT-'.")
        general_form.addRow("Retail No. Prefix", self.retail_no_prefix_input)

        self.stock_take_no_prefix_input = QLineEdit()
        self.stock_take_no_prefix_input.setMaxLength(10)
        self.stock_take_no_prefix_input.setToolTip("Prefix for generated stock take numbers, e.g. 'ST-'.")
        general_form.addRow("Stock Take No. Prefix", self.stock_take_no_prefix_input)

        self.quotation_no_prefix_input = QLineEdit()
        self.quotation_no_prefix_input.setMaxLength(10)
        self.quotation_no_prefix_input.setToolTip("Prefix for generated quotation numbers, e.g. 'QT-'.")
        general_form.addRow("Quotation No. Prefix", self.quotation_no_prefix_input)
        content_layout.addWidget(general_group)

        printing_group, printing_form = _make_group("Printing")
        self.receipt_paper_format_combo = NoScrollComboBox()
        self.receipt_paper_format_combo.addItem("A4 (Standard)", "A4")
        self.receipt_paper_format_combo.addItem("Thermal - 80mm", "THERMAL_80MM")
        self.receipt_paper_format_combo.addItem("Thermal - 58mm", "THERMAL_58MM")
        self.receipt_paper_format_combo.setToolTip(
            "A4 keeps the full-page receipt layout. Thermal prints a narrow, "
            "receipt-style layout sized for that paper width - works with any "
            "thermal printer already installed as a Windows printer (prints "
            "through the normal Print dialog, same as A4)."
        )
        printing_form.addRow("Receipt Paper Format", self.receipt_paper_format_combo)
        content_layout.addWidget(printing_group)

        fbr_group, fbr_form = _make_group("FBR API & Security Configuration")
        fbr_note = QLabel(
            "This module's own FBR settings - separate from, and not linked to, the "
            "main application's FBR invoice settings. Nothing here is used to submit "
            "invoices."
        )
        fbr_note.setWordWrap(True)
        fbr_note.setStyleSheet("color: #6c757d; font-size: 11px;")
        fbr_form.addRow(fbr_note)

        self.fbr_environment_combo = NoScrollComboBox()
        self.fbr_environment_combo.addItems(["SANDBOX", "PRODUCTION"])
        self.fbr_environment_combo.currentTextChanged.connect(self._on_fbr_environment_changed)
        fbr_form.addRow("Environment", self.fbr_environment_combo)

        self.fbr_api_base_url_input = QLineEdit()
        fbr_form.addRow("API Base URL", self.fbr_api_base_url_input)

        self.fbr_pos_id_input = QLineEdit()
        fbr_form.addRow("POS ID", self.fbr_pos_id_input)

        self.fbr_usin_input = QLineEdit()
        fbr_form.addRow("USIN", self.fbr_usin_input)

        self.fbr_auth_token_input = QLineEdit()
        fbr_form.addRow("Auth Token", _make_password_row(self.fbr_auth_token_input))

        self.fbr_secret_key_input = QLineEdit()
        fbr_form.addRow("Secret Key", _make_password_row(self.fbr_secret_key_input))
        content_layout.addWidget(fbr_group)

        content_layout.addStretch(1)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setWidget(scroll_content)
        layout.addWidget(scroll_area, 1)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        self.success_label = QLabel("")
        self.success_label.setStyleSheet("color: #27ae60; font-weight: bold;")
        self.success_label.hide()
        layout.addWidget(self.success_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        reload_btn = QPushButton("Discard Changes")
        reload_btn.setStyleSheet(_RESET_BTN)
        reload_btn.clicked.connect(self.reload)
        btn_row.addWidget(reload_btn)
        self.save_btn = QPushButton("Save Settings")
        self.save_btn.setStyleSheet(_PRIMARY_BTN)
        self.save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self.save_btn)
        layout.addLayout(btn_row)

        self.reload()

    def reload(self) -> None:
        self.error_label.hide()
        self.success_label.hide()
        db = get_spare_session()
        try:
            settings = settings_service.get_settings(db)
            self.allow_negative_stock_checkbox.setChecked(bool(settings.allow_negative_stock))
            self.default_tax_percent_spin.setValue(float(settings.default_tax_percent or 0))
            self.purchase_no_prefix_input.setText(settings.purchase_no_prefix or "")
            self.wholesale_no_prefix_input.setText(settings.wholesale_no_prefix or "")
            paper_format_idx = self.receipt_paper_format_combo.findData(settings.receipt_paper_format or "A4")
            self.receipt_paper_format_combo.setCurrentIndex(paper_format_idx if paper_format_idx >= 0 else 0)
            self.retail_no_prefix_input.setText(settings.retail_no_prefix or "")
            self.stock_take_no_prefix_input.setText(settings.stock_take_no_prefix or "")
            self.quotation_no_prefix_input.setText(settings.quotation_no_prefix or "")

            selected_env = settings.fbr_environment or "SANDBOX"
            idx = self.fbr_environment_combo.findText(selected_env)
            with QSignalBlocker(self.fbr_environment_combo):
                self.fbr_environment_combo.setCurrentIndex(idx if idx >= 0 else 0)
            # Set explicitly (not left to the blocked signal above) so the
            # FBR fields are always populated for whichever environment
            # ends up selected, even when the index doesn't actually
            # change (Qt wouldn't fire currentTextChanged in that case).
            self._load_fbr_environment_fields(db, self.fbr_environment_combo.currentText())
        finally:
            db.close()

    def _load_fbr_environment_fields(self, db, environment: str) -> None:
        """Populates API Base URL/POS ID/USIN/Auth Token/Secret Key from
        THAT environment's own row - this is what makes switching
        Environment actually swap values, instead of showing one shared
        set regardless of which is selected."""
        env_settings = settings_service.get_fbr_environment(db, environment)
        self.fbr_api_base_url_input.setText(env_settings.api_base_url or "")
        self.fbr_pos_id_input.setText(env_settings.pos_id or "")
        self.fbr_usin_input.setText(env_settings.usin or "")
        self.fbr_auth_token_input.setText(env_settings.auth_token or "")
        self.fbr_secret_key_input.setText(env_settings.secret_key or "")

    def _on_fbr_environment_changed(self, environment: str) -> None:
        """Fires when the user picks a different Environment - swaps the
        API/security fields to that environment's own saved values.
        Unsaved edits to the PREVIOUS environment's fields are not
        auto-saved first (same as the main app's own FBR dialog) - click
        Save Settings before switching if they should be kept."""
        db = get_spare_session()
        try:
            self._load_fbr_environment_fields(db, environment)
        finally:
            db.close()

    def _on_save(self) -> None:
        self.error_label.hide()
        self.success_label.hide()

        purchase_prefix = self.purchase_no_prefix_input.text().strip()
        wholesale_prefix = self.wholesale_no_prefix_input.text().strip()
        retail_prefix = self.retail_no_prefix_input.text().strip()
        stock_take_prefix = self.stock_take_no_prefix_input.text().strip()
        quotation_prefix = self.quotation_no_prefix_input.text().strip()
        if not purchase_prefix:
            self.error_label.setText("Purchase No. Prefix is required.")
            self.error_label.show()
            return
        if not wholesale_prefix:
            self.error_label.setText("Wholesale No. Prefix is required.")
            self.error_label.show()
            return
        if not retail_prefix:
            self.error_label.setText("Retail No. Prefix is required.")
            self.error_label.show()
            return
        if not stock_take_prefix:
            self.error_label.setText("Stock Take No. Prefix is required.")
            self.error_label.show()
            return
        if not quotation_prefix:
            self.error_label.setText("Quotation No. Prefix is required.")
            self.error_label.show()
            return

        selected_env = self.fbr_environment_combo.currentText()
        db = get_spare_session()
        try:
            settings_service.update_settings(
                db,
                allow_negative_stock=self.allow_negative_stock_checkbox.isChecked(),
                default_tax_percent=self.default_tax_percent_spin.value(),
                purchase_no_prefix=purchase_prefix,
                wholesale_no_prefix=wholesale_prefix,
                retail_no_prefix=retail_prefix,
                stock_take_no_prefix=stock_take_prefix,
                quotation_no_prefix=quotation_prefix,
                receipt_paper_format=self.receipt_paper_format_combo.currentData(),
                fbr_environment=selected_env,
            )
            # Saves to the CURRENTLY SELECTED environment's own row only -
            # the other environment's values are untouched, which is what
            # lets the dropdown show different values per environment.
            settings_service.save_fbr_environment(
                db,
                selected_env,
                api_base_url=self.fbr_api_base_url_input.text(),
                pos_id=self.fbr_pos_id_input.text(),
                usin=self.fbr_usin_input.text(),
                auth_token=self.fbr_auth_token_input.text(),
                secret_key=self.fbr_secret_key_input.text(),
            )
        except Exception as e:
            logger.error(f"Unexpected error saving settings: {e}", exc_info=True)
            self.error_label.setText(f"Unexpected error: {e}")
            self.error_label.show()
            return
        finally:
            db.close()

        self.success_label.setText("Settings saved.")
        self.success_label.show()
