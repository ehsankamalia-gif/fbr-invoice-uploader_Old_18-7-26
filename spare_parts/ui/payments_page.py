"""Payments: recording money received from a customer ("IN") or paid to
a supplier ("OUT") against their general account balance - see
spare_parts/services/payments_service.py and ledger_service.py.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
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
from spare_parts.services import customers_service, payments_service, suppliers_service
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

_DANGER_BTN = """
    QPushButton {
        background-color: #e74c3c; color: white; border: none;
        border-radius: 4px; padding: 8px 16px; font-weight: bold;
    }
    QPushButton:hover { background-color: #c0392b; }
"""


class PaymentDialog(QDialog):
    """Records one payment. direction is fixed for the lifetime of the
    dialog: "IN" (money received from a customer) or "OUT" (money paid
    to a supplier)."""

    def __init__(self, direction: str, parent=None):
        super().__init__(parent)
        self.direction = direction
        self._saving = False
        self.setWindowTitle(
            "Record Payment Received" if direction == "IN" else "Record Payment Made"
        )
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        self.party_combo = NoScrollComboBox()
        self.party_combo.currentIndexChanged.connect(self._update_balance_label)
        form.addRow("Customer *" if direction == "IN" else "Supplier *", self.party_combo)

        self.balance_label = QLabel("")
        self.balance_label.setStyleSheet("color: #7f8c8d;")
        form.addRow("", self.balance_label)

        self.amount_spin = NoScrollDoubleSpinBox()
        self.amount_spin.setRange(0.01, 99_999_999)
        self.amount_spin.setDecimals(2)
        form.addRow("Amount *", self.amount_spin)

        self.method_combo = NoScrollComboBox()
        self.method_combo.addItems(["Cash", "Card", "Bank Transfer", "Cheque"])
        form.addRow("Method", self.method_combo)

        self.notes_input = QLineEdit()
        form.addRow("Notes", self.notes_input)

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

        self._reload_parties()

    def _reload_parties(self) -> None:
        db = get_spare_session()
        try:
            self.party_combo.clear()
            self.party_combo.addItem("", None)
            if self.direction == "IN":
                for customer in customers_service.list_customers(db, active_only=True):
                    self.party_combo.addItem(customer.name, customer.id)
            else:
                for supplier in suppliers_service.list_suppliers(db, active_only=True):
                    self.party_combo.addItem(supplier.name, supplier.id)
        finally:
            db.close()

    def _update_balance_label(self) -> None:
        party_id = self.party_combo.currentData()
        if not party_id:
            self.balance_label.setText("")
            return
        db = get_spare_session()
        try:
            if self.direction == "IN":
                balance = customers_service.get_customer_outstanding(db, party_id)
                self.balance_label.setText(f"Currently owes: Rs. {balance:,.2f}")
            else:
                balance = suppliers_service.get_supplier_outstanding(db, party_id)
                self.balance_label.setText(f"We currently owe: Rs. {balance:,.2f}")
        finally:
            db.close()

    def _on_save(self) -> None:
        if self._saving:
            return
        self._saving = True
        self.save_btn.setEnabled(False)
        self.error_label.hide()
        try:
            party_id = self.party_combo.currentData()
            if not party_id:
                raise SparePartsValidationError(
                    "Select a customer." if self.direction == "IN" else "Select a supplier."
                )
            db = get_spare_session()
            try:
                payment = payments_service.create_payment(
                    db,
                    direction=self.direction,
                    party_id=party_id,
                    amount=self.amount_spin.value(),
                    payment_method=self.method_combo.currentText(),
                    notes=self.notes_input.text(),
                )
            finally:
                db.close()
            logger.info(f"Saved payment {payment.payment_no} via dialog.")
            self.accept()
        except SparePartsValidationError as e:
            self.error_label.setText(str(e))
            self.error_label.show()
        except Exception as e:
            logger.error(f"Unexpected error saving payment: {e}", exc_info=True)
            self.error_label.setText(f"Unexpected error: {e}")
            self.error_label.show()
        finally:
            self._saving = False
            self.save_btn.setEnabled(True)


class PaymentsPage(QWidget):
    """Payment history for both directions, with Record Received / Record
    Paid actions and a Cancel action for a selected POSTED payment."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        header = QLabel("Payments")
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(header)

        toolbar = QHBoxLayout()
        self.direction_filter = NoScrollComboBox()
        self.direction_filter.addItems(["All", "Received (IN)", "Paid (OUT)"])
        self.direction_filter.currentIndexChanged.connect(self._reload)
        toolbar.addWidget(self.direction_filter)

        self.status_filter = NoScrollComboBox()
        self.status_filter.addItems(["All", "POSTED", "CANCELLED"])
        self.status_filter.currentIndexChanged.connect(self._reload)
        toolbar.addWidget(self.status_filter)
        toolbar.addStretch(1)

        received_btn = QPushButton("+ Record Payment Received")
        received_btn.setStyleSheet(_PRIMARY_BTN)
        received_btn.clicked.connect(lambda: self._on_new_clicked("IN"))
        toolbar.addWidget(received_btn)

        paid_btn = QPushButton("+ Record Payment Made")
        paid_btn.setStyleSheet(_PRIMARY_BTN)
        paid_btn.clicked.connect(lambda: self._on_new_clicked("OUT"))
        toolbar.addWidget(paid_btn)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Payment No.", "Direction", "Party", "Date", "Amount", "Status"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)

        action_row = QHBoxLayout()
        cancel_btn = QPushButton("Cancel Selected Payment")
        cancel_btn.setStyleSheet(_DANGER_BTN)
        cancel_btn.clicked.connect(self._on_cancel_clicked)
        action_row.addWidget(cancel_btn)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        self._reload()

    def _reload(self) -> None:
        db = get_spare_session()
        try:
            direction = {"All": None, "Received (IN)": "IN", "Paid (OUT)": "OUT"}[
                self.direction_filter.currentText()
            ]
            status = self.status_filter.currentText()
            payments = payments_service.list_payments(
                db, direction=direction, status=None if status == "All" else status,
            )
            self.table.setRowCount(len(payments))
            for row, payment in enumerate(payments):
                party_name = (
                    payment.customer.name if payment.customer
                    else payment.supplier.name if payment.supplier else ""
                )
                self.table.setItem(row, 0, QTableWidgetItem(payment.payment_no))
                self.table.setItem(row, 1, QTableWidgetItem(
                    "Received" if payment.direction == "IN" else "Paid"
                ))
                self.table.setItem(row, 2, QTableWidgetItem(party_name))
                self.table.setItem(row, 3, QTableWidgetItem(payment.payment_date.strftime("%Y-%m-%d")))
                self.table.setItem(row, 4, QTableWidgetItem(f"{float(payment.amount):,.2f}"))
                status_item = QTableWidgetItem(payment.status)
                if payment.status == "CANCELLED":
                    status_item.setForeground(Qt.GlobalColor.gray)
                self.table.setItem(row, 5, status_item)
                self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, payment.id)
        finally:
            db.close()

    def _selected_payment_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_new_clicked(self, direction: str) -> None:
        dlg = PaymentDialog(direction, parent=self)
        if dlg.exec():
            self._reload()

    def _on_cancel_clicked(self) -> None:
        payment_id = self._selected_payment_id()
        if not payment_id:
            QMessageBox.information(self, "No Selection", "Select a payment first.")
            return
        db = get_spare_session()
        try:
            payment = payments_service.get_payment(db, payment_id)
            if not payment:
                return
            if payment.status == "CANCELLED":
                QMessageBox.information(self, "Already Cancelled", "This payment is already cancelled.")
                return
            confirm = QMessageBox.question(
                self, "Cancel Payment",
                f"Cancel payment {payment.payment_no}? This cannot be undone.",
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
            payments_service.cancel_payment(db, payment_id)
        except SparePartsValidationError as e:
            QMessageBox.warning(self, "Cannot Cancel", str(e))
            return
        finally:
            db.close()
        self._reload()
