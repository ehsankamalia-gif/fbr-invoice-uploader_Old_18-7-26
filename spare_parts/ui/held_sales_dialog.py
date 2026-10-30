"""Held Sales: lists every draft POS card saved via "Hold Sale", so a
cashier can find and resume one once the customer comes back - see
spare_parts/services/held_sales_service.py and
spare_parts/ui/sale_card_widget.py.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from spare_parts.db.base import get_spare_session
from spare_parts.services import held_sales_service

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

_DANGER_BTN = """
    QPushButton {
        background-color: #e74c3c; color: white; border: none;
        border-radius: 4px; padding: 8px 16px; font-weight: bold;
    }
    QPushButton:hover { background-color: #c0392b; }
"""


class HeldSalesDialog(QDialog):
    """Returns (via exec()'s result + self.resumed_held_sale_id) which
    draft, if any, the cashier chose to resume - PosPage reads that after
    the dialog closes and does the actual card-opening itself, since this
    dialog doesn't know about PosPage's tabs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Held Sales")
        self.setMinimumSize(700, 420)
        self.resumed_held_sale_id: int | None = None

        layout = QVBoxLayout(self)
        header = QLabel("Held Sales")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(header)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["", "Hold No.", "Reference", "Type", "Items", "Total", "Held At"]
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._on_resume_clicked)
        layout.addWidget(self.table, 1)

        btn_row = QHBoxLayout()
        delete_btn = QPushButton("Delete Checked")
        delete_btn.setStyleSheet(_DANGER_BTN)
        delete_btn.setAutoDefault(False)
        delete_btn.setToolTip("Tick the checkbox on each row you want to delete")
        delete_btn.clicked.connect(self._on_delete_clicked)
        btn_row.addWidget(delete_btn)
        btn_row.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(_RESET_BTN)
        close_btn.setAutoDefault(False)
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)
        self.resume_btn = QPushButton("Resume Selected")
        self.resume_btn.setStyleSheet(_PRIMARY_BTN)
        self.resume_btn.setAutoDefault(False)
        self.resume_btn.clicked.connect(self._on_resume_clicked)
        btn_row.addWidget(self.resume_btn)
        layout.addLayout(btn_row)

        self._reload()

    def _reload(self) -> None:
        db = get_spare_session()
        try:
            held_sales = held_sales_service.list_held_sales(db)
            self.table.setRowCount(len(held_sales))
            for row, held in enumerate(held_sales):
                self.table.setCellWidget(row, 0, self._make_row_checkbox())
                self.table.setItem(row, 1, QTableWidgetItem(held.hold_no))
                reference = held.reference or (held.customer.name if held.customer else "Walk-in")
                self.table.setItem(row, 2, QTableWidgetItem(reference))
                overall_type, is_mixed = held_sales_service.held_sale_overall_type(held)
                type_text = f"{overall_type} (Mixed)" if is_mixed else overall_type
                self.table.setItem(row, 3, QTableWidgetItem(type_text))
                self.table.setItem(row, 4, QTableWidgetItem(str(len(held.items))))
                total = held_sales_service.held_sale_total(held)
                self.table.setItem(row, 5, QTableWidgetItem(f"{total:,.2f}"))
                self.table.setItem(row, 6, QTableWidgetItem(held.held_at.strftime("%Y-%m-%d %H:%M")))
                self.table.item(row, 1).setData(Qt.ItemDataRole.UserRole, held.id)
        finally:
            db.close()

    @staticmethod
    def _make_row_checkbox() -> QWidget:
        """A checkbox centered in its cell - QTableWidget cell widgets
        aren't centered by default, so this wraps it in a small container
        with stretch on both sides. This is the per-row "pick this one
        for deletion" control - an actual multi-select mechanism, unlike
        a QRadioButton (mutually exclusive by design) which could only
        ever mark one row at a time."""
        container = QWidget()
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addStretch(1)
        container_layout.addWidget(QCheckBox())
        container_layout.addStretch(1)
        return container

    def _selected_held_sale_id(self) -> int | None:
        """The current row (click/double-click) - used by Resume, which
        only ever acts on one held sale. Independent of the per-row
        checkboxes, which are for the separate bulk-delete flow below."""
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 1)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _selected_held_sale_ids(self) -> list[int]:
        """Every held_sale id whose row checkbox is ticked, in table
        order - the bulk-delete selection mechanism."""
        ids = []
        for row in range(self.table.rowCount()):
            container = self.table.cellWidget(row, 0)
            checkbox = container.findChild(QCheckBox) if container else None
            if checkbox and checkbox.isChecked():
                item = self.table.item(row, 1)
                if item:
                    ids.append(item.data(Qt.ItemDataRole.UserRole))
        return ids

    def _on_resume_clicked(self) -> None:
        held_sale_id = self._selected_held_sale_id()
        if not held_sale_id:
            QMessageBox.information(self, "No Selection", "Select a held sale first.")
            return
        self.resumed_held_sale_id = held_sale_id
        self.accept()

    def _on_delete_clicked(self) -> None:
        held_sale_ids = self._selected_held_sale_ids()
        if not held_sale_ids:
            QMessageBox.information(self, "No Selection", "Tick the checkbox on one or more held sales first.")
            return
        count = len(held_sale_ids)
        message = (
            "Permanently delete this held sale? This cannot be undone."
            if count == 1 else
            f"Permanently delete these {count} held sales? This cannot be undone."
        )
        confirm = QMessageBox.question(self, "Delete Held Sale" if count == 1 else "Delete Held Sales", message)
        if confirm != QMessageBox.StandardButton.Yes:
            return
        db = get_spare_session()
        try:
            for held_sale_id in held_sale_ids:
                held_sales_service.delete_held_sale(db, held_sale_id)
        finally:
            db.close()
        self._reload()
