"""Stock Ledger: read-only movement history for one part - the "check the
stock" audit trail. Current stock is never just a number here; every
purchase/sale/return/opening entry/adjustment behind that number is
listed, oldest first, with the running balance after each one (mirrors
the statement-of-account convention already used by
spare_parts/ui/ledger_page.py for customers/suppliers).

Launched from the Parts page and from Reports > Stock.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from spare_parts.db.base import get_spare_session
from spare_parts.services import parts_service, stock_service
from spare_parts.ui.stock_adjustment_dialog import StockAdjustmentDialog

_RESET_BTN = """
    QPushButton {
        background-color: #f8f9fa; color: #6c757d; border: 1px solid #dee2e6;
        border-radius: 4px; padding: 8px 16px;
    }
    QPushButton:hover { background-color: #e2e6ea; }
"""

_PRIMARY_BTN = """
    QPushButton {
        background-color: #3498db; color: white; border: none;
        border-radius: 4px; padding: 8px 16px; font-weight: bold;
    }
    QPushButton:hover { background-color: #2980b9; }
"""

_REFERENCE_LABELS = {
    "OPENING": "Opening Stock",
    "PURCHASE": "Purchase",
    "PURCHASE_CANCEL": "Purchase Cancelled",
    "PURCHASE_RETURN": "Purchase Return",
    "SALE": "Sale",
    "SALE_CANCEL": "Sale Cancelled",
    "SALE_RETURN": "Sale Return",
    "SALE_EDIT": "Sale Edited",
    "ADJUSTMENT": "Adjustment",
}


class StockLedgerDialog(QDialog):
    def __init__(self, part_id: int, parent=None):
        super().__init__(parent)
        self.part_id = part_id
        self.setWindowTitle("Stock Ledger")
        self.setMinimumSize(640, 480)

        layout = QVBoxLayout(self)

        self.header_label = QLabel("")
        self.header_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(self.header_label)

        self.current_stock_label = QLabel("")
        self.current_stock_label.setStyleSheet("font-size: 13px; color: #27ae60; font-weight: bold;")
        layout.addWidget(self.current_stock_label)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Date", "Type", "Qty In", "Qty Out", "Balance", "Note"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)

        btn_row = QHBoxLayout()
        adjust_stock_btn = QPushButton("Adjust Stock")
        adjust_stock_btn.setStyleSheet(_PRIMARY_BTN)
        adjust_stock_btn.setAutoDefault(False)
        adjust_stock_btn.clicked.connect(self._on_adjust_stock_clicked)
        btn_row.addWidget(adjust_stock_btn)
        btn_row.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(_RESET_BTN)
        close_btn.setAutoDefault(False)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._load()

    def _on_adjust_stock_clicked(self) -> None:
        dlg = StockAdjustmentDialog(part_id=self.part_id, parent=self)
        if dlg.exec():
            self._load()  # refresh the history + current stock in place

    def _load(self) -> None:
        db = get_spare_session()
        try:
            part = parts_service.get_part(db, self.part_id)
            if not part:
                self.header_label.setText("Part not found.")
                return
            self.header_label.setText(f"{part.part_no} - {part.name}")

            current_stock = stock_service.get_current_stock(db, self.part_id)
            unit = part.unit or ""
            self.current_stock_label.setText(f"Current Stock: {current_stock} {unit}".strip())

            entries = stock_service.get_ledger_entries(db, self.part_id)
            self.table.setRowCount(len(entries))
            for row, entry in enumerate(entries):
                self.table.setItem(row, 0, QTableWidgetItem(entry.entry_date.strftime("%Y-%m-%d %H:%M")))
                label = _REFERENCE_LABELS.get(entry.reference_type, entry.reference_type)
                self.table.setItem(row, 1, QTableWidgetItem(label))

                in_item = QTableWidgetItem(str(entry.qty_in) if entry.qty_in else "")
                if entry.qty_in:
                    in_item.setForeground(Qt.GlobalColor.darkGreen)
                self.table.setItem(row, 2, in_item)

                out_item = QTableWidgetItem(str(entry.qty_out) if entry.qty_out else "")
                if entry.qty_out:
                    out_item.setForeground(Qt.GlobalColor.darkRed)
                self.table.setItem(row, 3, out_item)

                self.table.setItem(row, 4, QTableWidgetItem(str(entry.balance)))
                self.table.setItem(row, 5, QTableWidgetItem(entry.note or ""))

            if entries:
                self.table.scrollToBottom()  # most recent movement visible first
        finally:
            db.close()
