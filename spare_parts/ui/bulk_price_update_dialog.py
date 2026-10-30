"""Bulk Price Update: apply a %/fixed change to one price field across a
category, a brand, or every active part at once - instead of editing
parts one at a time or re-importing a whole file.

The preview table is computed CLIENT-SIDE from parts_service.search_parts
+ the same arithmetic parts_service.bulk_update_prices uses - there's no
existing preview/dry-run pattern in this module to extend, so Apply is
the only call that actually writes, once, atomically.
"""
from __future__ import annotations

from decimal import Decimal

from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from spare_parts.db.base import get_spare_session
from spare_parts.errors import SparePartsValidationError
from spare_parts.services import parts_service
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

_FIELD_LABELS = [
    ("Cost Price", "cost_price"),
    ("Retail Price", "retail_price"),
    ("Wholesale Price", "wholesale_price"),
]
_MODE_LABELS = [
    ("Percent (%)", "PERCENT"),
    ("Fixed Amount", "FIXED"),
]


class BulkPriceUpdateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bulk Price Update")
        self.setMinimumSize(640, 480)
        self._applying = False

        root = QVBoxLayout(self)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Category"))
        self.category_combo = NoScrollComboBox()
        self.category_combo.addItem("All Categories", None)
        filter_row.addWidget(self.category_combo, 1)

        filter_row.addWidget(QLabel("Brand"))
        self.brand_combo = NoScrollComboBox()
        self.brand_combo.addItem("All Brands", None)
        filter_row.addWidget(self.brand_combo, 1)
        root.addLayout(filter_row)

        change_row = QHBoxLayout()
        change_row.addWidget(QLabel("Field"))
        self.field_combo = NoScrollComboBox()
        for label, value in _FIELD_LABELS:
            self.field_combo.addItem(label, value)
        change_row.addWidget(self.field_combo, 1)

        change_row.addWidget(QLabel("Mode"))
        self.mode_combo = NoScrollComboBox()
        for label, value in _MODE_LABELS:
            self.mode_combo.addItem(label, value)
        change_row.addWidget(self.mode_combo, 1)

        change_row.addWidget(QLabel("Value"))
        self.value_spin = NoScrollDoubleSpinBox()
        self.value_spin.setRange(-999_999, 999_999)
        self.value_spin.setDecimals(2)
        self.value_spin.setToolTip(
            "Positive increases prices, negative decreases them. "
            "For Percent, e.g. 10 = +10%, -10 = -10%."
        )
        change_row.addWidget(self.value_spin, 1)
        root.addLayout(change_row)

        preview_btn = QPushButton("Preview")
        preview_btn.setStyleSheet(_RESET_BTN)
        preview_btn.clicked.connect(self._on_preview_clicked)
        root.addWidget(preview_btn)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Part", "Current Price", "New Price"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        root.addWidget(self.table, 1)

        self.summary_label = QLabel("Click Preview to see which parts would change.")
        self.summary_label.setStyleSheet("color: #6c757d;")
        root.addWidget(self.summary_label)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        root.addWidget(self.error_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel_btn = QPushButton("Close")
        cancel_btn.setStyleSheet(_RESET_BTN)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setStyleSheet(_PRIMARY_BTN)
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self._on_apply_clicked)
        btn_row.addWidget(self.apply_btn)
        root.addLayout(btn_row)

        self._load_filters()

    def _load_filters(self) -> None:
        db = get_spare_session()
        try:
            for cat in parts_service.list_categories(db):
                self.category_combo.addItem(cat.name, cat.id)
            for brand in parts_service.list_brands(db):
                self.brand_combo.addItem(brand.name, brand.id)
        finally:
            db.close()

    def _compute_preview(self) -> list[dict]:
        """Same arithmetic as parts_service.bulk_update_prices, computed
        here read-only so Preview never writes anything."""
        field = self.field_combo.currentData()
        mode = self.mode_combo.currentData()
        value = Decimal(str(self.value_spin.value()))
        db = get_spare_session()
        try:
            parts = parts_service.search_parts(
                db, category_id=self.category_combo.currentData(),
                brand_id=self.brand_combo.currentData(), active_only=True,
            )
            rows = []
            for part in parts:
                old_price = Decimal(str(getattr(part, field) or 0))
                if mode == "PERCENT":
                    new_price = old_price * (Decimal("1") + value / Decimal("100"))
                else:
                    new_price = old_price + value
                new_price = max(Decimal("0"), new_price).quantize(Decimal("0.01"))
                if new_price != old_price:
                    rows.append(dict(
                        part_no=part.part_no, name=part.name,
                        old_price=old_price, new_price=new_price,
                    ))
            return rows
        finally:
            db.close()

    def _on_preview_clicked(self) -> None:
        self.error_label.hide()
        try:
            rows = self._compute_preview()
        except Exception as e:
            self.error_label.setText(f"Could not compute preview: {e}")
            self.error_label.show()
            return

        self.table.setRowCount(len(rows))
        for row, entry in enumerate(rows):
            self.table.setItem(row, 0, QTableWidgetItem(f"{entry['part_no']} - {entry['name']}"))
            self.table.setItem(row, 1, QTableWidgetItem(f"{entry['old_price']:,.2f}"))
            self.table.setItem(row, 2, QTableWidgetItem(f"{entry['new_price']:,.2f}"))

        if rows:
            self.summary_label.setText(f"{len(rows)} part(s) would change.")
            self.apply_btn.setEnabled(True)
        else:
            self.summary_label.setText("No parts match this filter, or the change would not move any price.")
            self.apply_btn.setEnabled(False)

    def _on_apply_clicked(self) -> None:
        if self._applying:
            return
        self._applying = True
        self.apply_btn.setEnabled(False)
        self.error_label.hide()
        try:
            db = get_spare_session()
            try:
                results = parts_service.bulk_update_prices(
                    db,
                    category_id=self.category_combo.currentData(),
                    brand_id=self.brand_combo.currentData(),
                    field=self.field_combo.currentData(),
                    mode=self.mode_combo.currentData(),
                    value=self.value_spin.value(),
                )
            finally:
                db.close()
            QMessageBox.information(
                self, "Prices Updated", f"Updated {len(results)} part(s).",
            )
            self.accept()
        except SparePartsValidationError as e:
            self.error_label.setText(str(e))
            self.error_label.show()
            self.apply_btn.setEnabled(True)
        except Exception as e:
            logger.error(f"Unexpected error applying bulk price update: {e}", exc_info=True)
            self.error_label.setText(f"Unexpected error: {e}")
            self.error_label.show()
            self.apply_btn.setEnabled(True)
        finally:
            self._applying = False
