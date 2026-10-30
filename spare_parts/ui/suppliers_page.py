"""Suppliers master screen: searchable list + Add/Edit dialog. Mirrors
parts_page.py's pattern (see that file for the established conventions
this one follows)."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from spare_parts.db.base import get_spare_session
from spare_parts.errors import SparePartsValidationError
from spare_parts.services import suppliers_service
from spare_parts.ui.widgets import NoScrollDoubleSpinBox
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


class SupplierDialog(QDialog):
    def __init__(self, supplier_id: int | None = None, parent=None):
        super().__init__(parent)
        self.supplier_id = supplier_id
        self.setWindowTitle("Edit Supplier" if supplier_id else "Add Supplier")
        self.setMinimumWidth(420)
        self._saving = False

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        self.name_input = QLineEdit()
        form.addRow("Name *", self.name_input)

        self.phone_input = QLineEdit()
        form.addRow("Phone", self.phone_input)

        self.address_input = QLineEdit()
        form.addRow("Address", self.address_input)

        self.opening_balance_spin = NoScrollDoubleSpinBox()
        self.opening_balance_spin.setRange(-99_999_999, 99_999_999)
        self.opening_balance_spin.setDecimals(2)
        self.opening_balance_spin.setToolTip(
            "Positive = you owe the supplier this much as of today. "
            "Negative = the supplier owes you (advance/credit)."
        )
        form.addRow("Opening Balance", self.opening_balance_spin)

        self.active_checkbox = QCheckBox("Active")
        self.active_checkbox.setChecked(True)
        if supplier_id:
            form.addRow("", self.active_checkbox)

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
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        self.save_btn = QPushButton("Save (Ctrl+S)")
        self.save_btn.setStyleSheet(_PRIMARY_BTN)
        self.save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self.save_btn)
        layout.addLayout(btn_row)

        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._on_save)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.reject)

        self.setTabOrder(self.name_input, self.phone_input)
        self.setTabOrder(self.phone_input, self.address_input)
        self.setTabOrder(self.address_input, self.opening_balance_spin)
        for line_edit in (self.name_input, self.phone_input, self.address_input):
            line_edit.returnPressed.connect(self.focusNextChild)

        if supplier_id:
            self._load_supplier(supplier_id)

    def _load_supplier(self, supplier_id: int) -> None:
        db = get_spare_session()
        try:
            supplier = suppliers_service.get_supplier(db, supplier_id)
            if not supplier:
                QMessageBox.critical(self, "Error", f"Supplier id={supplier_id} not found.")
                self.reject()
                return
            self.name_input.setText(supplier.name)
            self.phone_input.setText(supplier.phone or "")
            self.address_input.setText(supplier.address or "")
            self.opening_balance_spin.setValue(float(supplier.opening_balance or 0))
            self.active_checkbox.setChecked(bool(supplier.is_active))
        finally:
            db.close()

    def _on_save(self) -> None:
        if self._saving:
            return
        self._saving = True
        self.save_btn.setEnabled(False)
        self.error_label.hide()
        try:
            fields = dict(
                name=self.name_input.text(),
                phone=self.phone_input.text(),
                address=self.address_input.text(),
                opening_balance=self.opening_balance_spin.value(),
            )
            db = get_spare_session()
            try:
                if self.supplier_id:
                    supplier = suppliers_service.update_supplier(db, self.supplier_id, **fields)
                    suppliers_service.set_supplier_active(
                        db, self.supplier_id, self.active_checkbox.isChecked()
                    )
                else:
                    suppliers_service.create_supplier(db, **fields)
            finally:
                db.close()
            self.accept()
        except SparePartsValidationError as e:
            self.error_label.setText(str(e))
            self.error_label.show()
        except Exception as e:
            logger.error(f"Unexpected error saving supplier: {e}", exc_info=True)
            self.error_label.setText(f"Unexpected error: {e}")
            self.error_label.show()
        finally:
            self._saving = False
            self.save_btn.setEnabled(True)


class SuppliersPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        header = QLabel("Suppliers")
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(header)

        toolbar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search name or phone...")
        self.search_input.textChanged.connect(self._on_search_text_changed)
        toolbar.addWidget(self.search_input, 2)

        self.show_inactive_checkbox = QCheckBox("Show inactive")
        self.show_inactive_checkbox.stateChanged.connect(self._reload)
        toolbar.addWidget(self.show_inactive_checkbox)
        toolbar.addStretch(1)

        add_btn = QPushButton("+ Add Supplier (Ctrl+N)")
        add_btn.setStyleSheet(_PRIMARY_BTN)
        add_btn.clicked.connect(self._on_add_clicked)
        toolbar.addWidget(add_btn)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Name", "Phone", "Opening Balance", "Status"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._on_edit_clicked)
        layout.addWidget(self.table, 1)

        action_row = QHBoxLayout()
        edit_btn = QPushButton("Edit Selected")
        edit_btn.setStyleSheet(_RESET_BTN)
        edit_btn.clicked.connect(self._on_edit_clicked)
        action_row.addWidget(edit_btn)

        toggle_btn = QPushButton("Deactivate Selected")
        toggle_btn.setStyleSheet(_RESET_BTN)
        toggle_btn.clicked.connect(self._on_toggle_active_clicked)
        action_row.addWidget(toggle_btn)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_timer.timeout.connect(self._reload)

        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._on_add_clicked)

        self._reload()

    def _on_search_text_changed(self, _text: str) -> None:
        self._search_timer.start()

    def _reload(self) -> None:
        db = get_spare_session()
        try:
            suppliers = suppliers_service.search_suppliers(
                db,
                query=self.search_input.text(),
                active_only=not self.show_inactive_checkbox.isChecked(),
            )
            self.table.setRowCount(len(suppliers))
            for row, supplier in enumerate(suppliers):
                self.table.setItem(row, 0, QTableWidgetItem(supplier.name))
                self.table.setItem(row, 1, QTableWidgetItem(supplier.phone or ""))
                self.table.setItem(row, 2, QTableWidgetItem(f"{float(supplier.opening_balance or 0):,.2f}"))
                status_item = QTableWidgetItem("Active" if supplier.is_active else "Inactive")
                if not supplier.is_active:
                    status_item.setForeground(Qt.GlobalColor.gray)
                self.table.setItem(row, 3, status_item)
                self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, supplier.id)
        finally:
            db.close()

    def _selected_supplier_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_add_clicked(self) -> None:
        dlg = SupplierDialog(parent=self)
        if dlg.exec():
            self._reload()

    def _on_edit_clicked(self) -> None:
        supplier_id = self._selected_supplier_id()
        if not supplier_id:
            QMessageBox.information(self, "No Selection", "Select a supplier first.")
            return
        dlg = SupplierDialog(supplier_id=supplier_id, parent=self)
        if dlg.exec():
            self._reload()

    def _on_toggle_active_clicked(self) -> None:
        supplier_id = self._selected_supplier_id()
        if not supplier_id:
            QMessageBox.information(self, "No Selection", "Select a supplier first.")
            return
        db = get_spare_session()
        try:
            supplier = suppliers_service.get_supplier(db, supplier_id)
            if not supplier:
                return
            new_state = not supplier.is_active
            action = "activate" if new_state else "deactivate"
            confirm = QMessageBox.question(
                self, f"{action.title()} Supplier",
                f"{action.title()} supplier '{supplier.name}'?",
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
            suppliers_service.set_supplier_active(db, supplier_id, new_state)
        finally:
            db.close()
        self._reload()
