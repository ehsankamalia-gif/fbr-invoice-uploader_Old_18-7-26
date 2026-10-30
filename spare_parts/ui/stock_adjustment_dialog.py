"""Stock Adjustment: the direct answer to "how do I add/remove quantity
for a part" - a manual stock-ledger entry for things a purchase or sale
doesn't cover, like setting a brand-new part's starting quantity or
correcting a count after a physical stocktake (damage, shrinkage,
miscount). Always goes through stock_service.create_adjustment, which
posts a normal ADJUSTMENT ledger entry - stock is never edited directly
anywhere in this module (see spare_parts/__init__.py).
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from spare_parts.db.base import get_spare_session
from spare_parts.errors import SparePartsValidationError
from spare_parts.services import parts_service, stock_service
from spare_parts.ui.widgets import NoScrollComboBox, NoScrollSpinBox
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


class StockAdjustmentDialog(QDialog):
    def __init__(self, part_id: int | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Adjust Stock")
        self.setMinimumWidth(420)
        self._saving = False

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        self.part_combo = NoScrollComboBox()
        self.part_combo.setEditable(True)
        self.part_combo.setInsertPolicy(NoScrollComboBox.InsertPolicy.NoInsert)
        self.part_combo.currentIndexChanged.connect(self._update_current_stock_label)
        form.addRow("Part *", self.part_combo)

        self.current_stock_label = QLabel("")
        self.current_stock_label.setStyleSheet("color: #7f8c8d;")
        form.addRow("", self.current_stock_label)

        self.direction_combo = NoScrollComboBox()
        self.direction_combo.addItem("Add Stock (+)", "IN")
        self.direction_combo.addItem("Remove Stock (-)", "OUT")
        form.addRow("Action *", self.direction_combo)

        self.qty_spin = NoScrollSpinBox()
        self.qty_spin.setRange(1, 1_000_000)
        self.qty_spin.setValue(1)
        form.addRow("Quantity *", self.qty_spin)

        self.reason_input = QLineEdit()
        self.reason_input.setPlaceholderText(
            "e.g. Opening stock, physical stocktake correction, damaged goods..."
        )
        form.addRow("Reason *", self.reason_input)

        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(_RESET_BTN)
        cancel_btn.setAutoDefault(False)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        self.save_btn = QPushButton("Save (Ctrl+S)")
        self.save_btn.setStyleSheet(_PRIMARY_BTN)
        self.save_btn.setAutoDefault(False)
        self.save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self.save_btn)
        layout.addLayout(btn_row)

        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._on_save)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.reject)

        self._reload_parts()
        if part_id is not None:
            idx = self.part_combo.findData(part_id)
            if idx >= 0:
                self.part_combo.setCurrentIndex(idx)
            self._update_current_stock_label()
        self.reason_input.setFocus()

    def _reload_parts(self) -> None:
        db = get_spare_session()
        try:
            self.part_combo.clear()
            self.part_combo.addItem("", None)
            for part in parts_service.search_parts(db, active_only=True):
                self.part_combo.addItem(f"{part.part_no} - {part.name}", part.id)
        finally:
            db.close()

    def _update_current_stock_label(self) -> None:
        part_id = self.part_combo.currentData()
        if not part_id:
            self.current_stock_label.setText("")
            return
        db = get_spare_session()
        try:
            current_stock = stock_service.get_current_stock(db, part_id)
            part = parts_service.get_part(db, part_id)
            unit = part.unit if part else ""
            self.current_stock_label.setText(f"Current stock: {current_stock} {unit}".strip())
        finally:
            db.close()

    def _on_save(self) -> None:
        if self._saving:
            return
        self._saving = True
        self.save_btn.setEnabled(False)
        self.error_label.hide()
        try:
            part_id = self.part_combo.currentData()
            if not part_id:
                raise SparePartsValidationError("Select a part.")

            db = get_spare_session()
            try:
                stock_service.create_adjustment(
                    db,
                    part_id=part_id,
                    direction=self.direction_combo.currentData(),
                    qty=self.qty_spin.value(),
                    reason=self.reason_input.text(),
                )
            finally:
                db.close()
            logger.info("Stock adjustment saved via dialog.")
            self.accept()
        except SparePartsValidationError as e:
            self.error_label.setText(str(e))
            self.error_label.show()
        except Exception as e:
            logger.error(f"Unexpected error saving stock adjustment: {e}", exc_info=True)
            self.error_label.setText(f"Unexpected error: {e}")
            self.error_label.show()
        finally:
            self._saving = False
            self.save_btn.setEnabled(True)
