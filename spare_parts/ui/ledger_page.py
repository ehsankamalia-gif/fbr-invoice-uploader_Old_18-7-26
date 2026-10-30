"""Ledger: a read-only statement of account for one customer or
supplier, built from spare_parts/services/ledger_service.py."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from spare_parts.db.base import get_spare_session
from spare_parts.services import customers_service, ledger_service, suppliers_service
from spare_parts.ui.widgets import NoScrollComboBox


class LedgerPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        header = QLabel("Ledgers")
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(header)

        toolbar = QHBoxLayout()
        self.party_type_combo = NoScrollComboBox()
        self.party_type_combo.addItems(["Customer", "Supplier"])
        self.party_type_combo.currentIndexChanged.connect(self._on_party_type_changed)
        toolbar.addWidget(self.party_type_combo)

        self.party_combo = NoScrollComboBox()
        self.party_combo.setEditable(True)
        self.party_combo.setInsertPolicy(NoScrollComboBox.InsertPolicy.NoInsert)
        self.party_combo.currentIndexChanged.connect(self._reload)
        toolbar.addWidget(self.party_combo, 1)
        toolbar.addStretch(1)

        self.balance_label = QLabel("")
        self.balance_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #2c3e50;")
        toolbar.addWidget(self.balance_label)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Date", "Type", "Ref No.", "Debit", "Credit", "Balance"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)

        self._reload_parties()

    def _on_party_type_changed(self) -> None:
        self._reload_parties()

    def _reload_parties(self) -> None:
        db = get_spare_session()
        try:
            self.party_combo.blockSignals(True)
            self.party_combo.clear()
            self.party_combo.addItem("", None)
            if self.party_type_combo.currentText() == "Customer":
                for customer in customers_service.list_customers(db, active_only=False):
                    self.party_combo.addItem(customer.name, customer.id)
            else:
                for supplier in suppliers_service.list_suppliers(db, active_only=False):
                    self.party_combo.addItem(supplier.name, supplier.id)
            self.party_combo.blockSignals(False)
        finally:
            db.close()
        self._reload()

    def refresh_party_lists(self) -> None:
        """Called by the host widget (e.g. after a new customer/supplier
        or payment is recorded elsewhere) so this page's combo and totals
        don't go stale while the tab sits in the background."""
        self._reload_parties()

    def _reload(self) -> None:
        party_id = self.party_combo.currentData()
        self.table.setRowCount(0)
        if not party_id:
            self.balance_label.setText("")
            return

        db = get_spare_session()
        try:
            if self.party_type_combo.currentText() == "Customer":
                rows = ledger_service.get_customer_ledger(db, party_id)
                balance = customers_service.get_customer_outstanding(db, party_id)
                self.balance_label.setText(f"Current Balance (owed to us): Rs. {balance:,.2f}")
            else:
                rows = ledger_service.get_supplier_ledger(db, party_id)
                balance = suppliers_service.get_supplier_outstanding(db, party_id)
                self.balance_label.setText(f"Current Balance (we owe): Rs. {balance:,.2f}")
        finally:
            db.close()

        self.table.setRowCount(len(rows))
        for row, entry in enumerate(rows):
            self.table.setItem(row, 0, QTableWidgetItem(entry["date"].strftime("%Y-%m-%d")))
            self.table.setItem(row, 1, QTableWidgetItem(entry["type"]))
            self.table.setItem(row, 2, QTableWidgetItem(entry["ref_no"]))
            debit_item = QTableWidgetItem(f"{entry['debit']:,.2f}" if entry["debit"] else "")
            self.table.setItem(row, 3, debit_item)
            credit_item = QTableWidgetItem(f"{entry['credit']:,.2f}" if entry["credit"] else "")
            self.table.setItem(row, 4, credit_item)
            balance_item = QTableWidgetItem(f"{entry['balance']:,.2f}")
            balance_item.setForeground(Qt.GlobalColor.darkBlue if entry["balance"] >= 0 else Qt.GlobalColor.red)
            self.table.setItem(row, 5, balance_item)
            if entry["type"] == "Opening Balance":
                for col in range(6):
                    item = self.table.item(row, col)
                    if item:
                        item.setForeground(Qt.GlobalColor.gray)
