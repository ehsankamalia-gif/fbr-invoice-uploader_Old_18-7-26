"""Recent Customers picker for the invoice form - lets the cashier pick
a buyer they've dealt with recently instead of retyping/re-searching,
without being limited to the Dealer Network (see dealer_search_dialog.py,
which is deliberately dealer-only).

Structurally mirrors DealerSearchDialog (same QAbstractTableModel +
QTableView + QDialogButtonBox pattern and visual style) - a separate
file rather than extending that one, since this is intentionally NOT
dealer-filtered and uses a different, read-only ordering query.
"""
from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QTableView,
    QDialogButtonBox,
    QPushButton,
    QHBoxLayout,
    QFrame,
    QHeaderView,
    QAbstractItemView,
)
from sqlalchemy import func

from app.db.session import SessionLocal
from app.db.models import Customer, Invoice


class RecentCustomerRow:
    def __init__(
        self,
        customer_id: int,
        name: str,
        cnic: str,
        phone: str,
        address: str,
        ntn: str,
        customer_type: str,
        last_activity: str,
    ) -> None:
        self.customer_id = customer_id
        self.name = name
        self.cnic = cnic
        self.phone = phone
        self.address = address
        self.ntn = ntn
        self.customer_type = customer_type
        self.last_activity = last_activity


class RecentCustomersTableModel(QAbstractTableModel):
    headers = ["Name", "CNIC", "Phone", "Address", "NTN", "Type", "Last Activity"]

    def __init__(self) -> None:
        super().__init__()
        self._rows: List[RecentCustomerRow] = []

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        return len(self._rows)

    def columnCount(self, parent: QModelIndex | None = None) -> int:
        return len(self.headers)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return row.name
            if col == 1:
                return row.cnic
            if col == 2:
                return row.phone
            if col == 3:
                return row.address
            if col == 4:
                return row.ntn
            if col == 5:
                return row.customer_type
            if col == 6:
                return row.last_activity
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self.headers):
                return self.headers[section]
        return super().headerData(section, orientation, role)

    def update_rows(self, rows: List[RecentCustomerRow]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()


class RecentCustomersDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Recent Customers")
        self.setMinimumSize(950, 650)
        self.resize(1000, 700)

        self.setStyleSheet("""
            QDialog {
                background-color: #f8f9fa;
            }
            QFrame#filterCard {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 12px;
            }
            QLabel {
                color: #2c3e50;
                font-size: 13px;
                font-weight: 500;
            }
            QLabel#pageHeader {
                font-size: 22px;
                font-weight: bold;
                color: #2c3e50;
                margin-bottom: 5px;
            }
            QLineEdit {
                padding: 10px 15px;
                border: 1px solid #dee2e6;
                border-radius: 8px;
                background-color: #ffffff;
                font-size: 13px;
                color: #495057;
            }
            QLineEdit:focus {
                border: 2px solid #3498db;
                background-color: #f7fbfe;
            }
            QPushButton#searchBtn {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 8px;
                font-weight: bold;
                padding: 10px 25px;
                font-size: 13px;
            }
            QPushButton#searchBtn:hover {
                background-color: #2980b9;
            }
            QPushButton#searchBtn:pressed {
                background-color: #2471a3;
            }
            QTableView {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 12px;
                gridline-color: #f1f1f1;
                alternate-background-color: #fafafa;
                selection-background-color: #e3f2fd;
                selection-color: #1976d2;
                outline: none;
                font-size: 13px;
            }
            QTableView::item {
                padding: 12px;
                border-bottom: 1px solid #f8f9fa;
            }
            QHeaderView::section {
                background-color: #f8f9fa;
                color: #5a6268;
                padding: 12px;
                font-weight: bold;
                text-transform: uppercase;
                font-size: 11px;
                border: none;
                border-bottom: 2px solid #e9ecef;
            }
            QDialogButtonBox QPushButton {
                padding: 8px 20px;
                border-radius: 6px;
                font-weight: bold;
            }
        """)

        self._selected_customer: Optional[Customer] = None
        self._page_size = 100

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(25, 25, 25, 25)
        main_layout.setSpacing(20)

        header_vbox = QVBoxLayout()
        header_vbox.setSpacing(2)

        header_label = QLabel("Recent Customers")
        header_label.setObjectName("pageHeader")
        header_vbox.addWidget(header_label)

        subtitle_label = QLabel("Pick a buyer you've dealt with recently instead of retyping their details.")
        subtitle_label.setStyleSheet("color: #7f8c8d; font-size: 13px; font-weight: normal;")
        header_vbox.addWidget(subtitle_label)

        main_layout.addLayout(header_vbox)

        filter_card = QFrame()
        filter_card.setObjectName("filterCard")
        filter_layout = QVBoxLayout(filter_card)
        filter_layout.setContentsMargins(20, 20, 20, 20)
        filter_layout.setSpacing(15)

        grid = QGridLayout()
        grid.setSpacing(15)

        grid.addWidget(QLabel("Name / CNIC / Phone"), 0, 0)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter by name, CNIC, or phone...")
        self.search_input.textChanged.connect(self._run_search)
        grid.addWidget(self.search_input, 0, 1, 1, 3)

        filter_layout.addLayout(grid)
        main_layout.addWidget(filter_card)

        self.table = QTableView(self)
        self.table_model = RecentCustomersTableModel()
        self.table.setModel(self.table_model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._accept_current)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setStretchLastSection(True)

        main_layout.addWidget(self.table, 1)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        main_layout.addWidget(button_box)
        button_box.accepted.connect(self._accept_current)
        button_box.rejected.connect(self.reject)

        ok_btn = button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn:
            ok_btn.setText("Select Customer")
            ok_btn.setStyleSheet("background-color: #27ae60; color: white; border: none;")
            ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        cancel_btn = button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_btn:
            cancel_btn.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6; color: #495057;")
            cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self._run_search()

    def _run_search(self) -> None:
        db = SessionLocal()
        try:
            # Most recent Invoice.datetime per customer, falling back to
            # Customer.created_at for a customer with no invoices yet -
            # a plain created_at ordering would never resurface a
            # customer again after their first invoice (that value never
            # changes), and an inner join would hide freshly-added
            # customers who haven't been invoiced yet.
            last_invoice_subq = (
                db.query(
                    Invoice.customer_id.label("customer_id"),
                    func.max(Invoice.datetime).label("last_invoice_dt"),
                )
                .group_by(Invoice.customer_id)
                .subquery()
            )
            activity_expr = func.coalesce(last_invoice_subq.c.last_invoice_dt, Customer.created_at)
            query = (
                db.query(Customer, last_invoice_subq.c.last_invoice_dt)
                .outerjoin(last_invoice_subq, last_invoice_subq.c.customer_id == Customer.id)
                .filter(Customer.is_deleted == False)
            )
            term = self.search_input.text().strip()
            if term:
                like = f"%{term}%"
                query = query.filter(
                    (Customer.name.ilike(like))
                    | (Customer.cnic.ilike(like))
                    | (Customer.phone.ilike(like))
                )
            query = query.order_by(activity_expr.desc())
            rows = query.limit(self._page_size).all()

            customer_rows: List[RecentCustomerRow] = []
            for customer, last_invoice_dt in rows:
                activity_dt = last_invoice_dt or customer.created_at
                customer_rows.append(
                    RecentCustomerRow(
                        customer_id=customer.id,
                        name=customer.name or "",
                        cnic=customer.cnic or "",
                        phone=customer.phone or "",
                        address=customer.address or "",
                        ntn=customer.ntn or "",
                        customer_type=(customer.type or "").title(),
                        last_activity=activity_dt.strftime("%Y-%m-%d") if activity_dt else "",
                    )
                )
            self.table_model.update_rows(customer_rows)
        finally:
            db.close()

    def _accept_current(self) -> None:
        index = self.table.currentIndex()
        if not index.isValid():
            self.reject()
            return
        row = index.row()
        if row < 0 or row >= self.table_model.rowCount():
            self.reject()
            return
        customer_id = self.table_model._rows[row].customer_id
        db = SessionLocal()
        try:
            customer = db.query(Customer).filter(Customer.id == customer_id).first()
            if customer is None:
                self.reject()
                return
            self._selected_customer = customer
        finally:
            db.close()
        self.accept()

    @property
    def selected_customer(self) -> Optional[Customer]:
        return self._selected_customer
