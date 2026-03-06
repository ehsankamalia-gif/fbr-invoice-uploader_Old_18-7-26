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
)

from app.db.session import SessionLocal
from app.db.models import Customer, CustomerType


class DealerRow:
    def __init__(
        self,
        business_name: str,
        contact_name: str,
        cnic: str,
        phone: str,
        address: str,
        ntn: str,
    ) -> None:
        self.business_name = business_name
        self.contact_name = contact_name
        self.cnic = cnic
        self.phone = phone
        self.address = address
        self.ntn = ntn


class DealerSearchTableModel(QAbstractTableModel):
    headers = ["Business", "Contact", "CNIC", "Phone", "Address", "NTN"]

    def __init__(self) -> None:
        super().__init__()
        self._rows: List[DealerRow] = []

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
                return row.business_name
            if col == 1:
                return row.contact_name
            if col == 2:
                return row.cnic
            if col == 3:
                return row.phone
            if col == 4:
                return row.address
            if col == 5:
                return row.ntn
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self.headers):
                return self.headers[section]
        return super().headerData(section, orientation, role)

    def update_rows(self, rows: List[DealerRow]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()


class DealerSearchDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Search Dealer")
        self.resize(800, 500)

        self._selected_dealer: Optional[Customer] = None

        layout = QVBoxLayout(self)

        filter_layout = QGridLayout()
        layout.addLayout(filter_layout)

        self.business_input = QLineEdit()
        self.name_input = QLineEdit()
        self.address_input = QLineEdit()

        filter_layout.addWidget(QLabel("Business"), 0, 0)
        filter_layout.addWidget(self.business_input, 0, 1)
        filter_layout.addWidget(QLabel("Name"), 0, 2)
        filter_layout.addWidget(self.name_input, 0, 3)
        filter_layout.addWidget(QLabel("Address"), 1, 0)
        filter_layout.addWidget(self.address_input, 1, 1, 1, 3)

        self.table = QTableView(self)
        self.table_model = DealerSearchTableModel()
        self.table.setModel(self.table_model)
        self.table.doubleClicked.connect(self._accept_current)
        layout.addWidget(self.table, 1)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(button_box)
        button_box.accepted.connect(self._accept_current)
        button_box.rejected.connect(self.reject)

        search_button = QPushButton("Search")
        filter_layout.addWidget(search_button, 2, 3)
        search_button.clicked.connect(self._run_search)

        self._current_page = 0
        self._page_size = 50

        self._run_search()

    def _run_search(self) -> None:
        db = SessionLocal()
        try:
            query = db.query(Customer).filter(
                Customer.type == CustomerType.DEALER,
                Customer.is_deleted == False,
            )
            business = self.business_input.text().strip()
            if business:
                query = query.filter(Customer.business_name.ilike(f"%{business}%"))
            name = self.name_input.text().strip()
            if name:
                query = query.filter(Customer.name.ilike(f"%{name}%"))
            address = self.address_input.text().strip()
            if address:
                query = query.filter(Customer.address.ilike(f"%{address}%"))
            query = query.order_by(Customer.business_name.asc())
            rows = query.limit(self._page_size).offset(self._current_page * self._page_size).all()
            dealer_rows: List[DealerRow] = []
            for d in rows:
                dealer_rows.append(
                    DealerRow(
                        business_name=d.business_name or "",
                        contact_name=d.name or "",
                        cnic=d.cnic or "",
                        phone=d.phone or "",
                        address=d.address or "",
                        ntn=d.ntn or "",
                    )
                )
            self.table_model.update_rows(dealer_rows)
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
        business = self.table_model._rows[row].business_name
        db = SessionLocal()
        try:
            dealer = db.query(Customer).filter(
                Customer.type == CustomerType.DEALER,
                Customer.is_deleted == False,
                Customer.business_name == business,
            ).first()
            if dealer is None:
                self.reject()
                return
            self._selected_dealer = dealer
        finally:
            db.close()
        self.accept()

    @property
    def selected_dealer(self) -> Optional[Customer]:
        return self._selected_dealer
