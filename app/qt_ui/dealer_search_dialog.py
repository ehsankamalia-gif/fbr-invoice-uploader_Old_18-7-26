from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSize
from PyQt6.QtGui import QIcon, QFont, QColor
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
        self.setWindowTitle("Search Dealer Registry")
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

        self._selected_dealer: Optional[Customer] = None
        self._current_page = 0
        self._page_size = 50

        # Main Layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(25, 25, 25, 25)
        main_layout.setSpacing(20)

        # Header Section
        header_vbox = QVBoxLayout()
        header_vbox.setSpacing(2)
        
        header_label = QLabel("Search Dealer Registry")
        header_label.setObjectName("pageHeader")
        header_vbox.addWidget(header_label)
        
        subtitle_label = QLabel("Quickly find and select registered dealers from your network.")
        subtitle_label.setStyleSheet("color: #7f8c8d; font-size: 13px; font-weight: normal;")
        header_vbox.addWidget(subtitle_label)
        
        main_layout.addLayout(header_vbox)

        # Filter Card
        filter_card = QFrame()
        filter_card.setObjectName("filterCard")
        filter_layout = QVBoxLayout(filter_card)
        filter_layout.setContentsMargins(20, 20, 20, 20)
        filter_layout.setSpacing(15)

        grid = QGridLayout()
        grid.setSpacing(15)

        # Labels and Inputs
        grid.addWidget(QLabel("Business Name"), 0, 0)
        self.business_input = QLineEdit()
        self.business_input.setPlaceholderText("Filter by business name...")
        self.business_input.textChanged.connect(self._run_search)
        grid.addWidget(self.business_input, 0, 1)

        grid.addWidget(QLabel("Contact Name"), 0, 2)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Filter by contact name...")
        self.name_input.textChanged.connect(self._run_search)
        grid.addWidget(self.name_input, 0, 3)

        grid.addWidget(QLabel("Address"), 1, 0)
        self.address_input = QLineEdit()
        self.address_input.setPlaceholderText("Search by city or full address...")
        self.address_input.textChanged.connect(self._run_search)
        grid.addWidget(self.address_input, 1, 1, 1, 3)

        filter_layout.addLayout(grid)

        # Action Buttons for filter
        action_row = QHBoxLayout()
        action_row.addStretch()
        
        self.search_button = QPushButton("Search")
        self.search_button.setObjectName("searchBtn")
        self.search_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.search_button.clicked.connect(self._run_search)
        action_row.addWidget(self.search_button)
        
        filter_layout.addLayout(action_row)
        main_layout.addWidget(filter_card)

        # Table Section
        self.table = QTableView(self)
        self.table_model = DealerSearchTableModel()
        self.table.setModel(self.table_model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._accept_current)
        
        # Header configuration
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setStretchLastSection(True)
        
        main_layout.addWidget(self.table, 1)

        # Bottom Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        main_layout.addWidget(button_box)
        button_box.accepted.connect(self._accept_current)
        button_box.rejected.connect(self.reject)
        
        # Style the buttons inside the box
        ok_btn = button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn:
            ok_btn.setText("Select Dealer")
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
