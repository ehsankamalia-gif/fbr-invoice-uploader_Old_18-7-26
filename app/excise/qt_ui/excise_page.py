
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class ExciseRecordPage(QWidget):
    def __init__(self, db_session):
        super().__init__()
        self.db_session = db_session
        self.setWindowTitle("Excise Record Management")
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        # Title
        title_label = QLabel("Excise Record Management System")
        title_label.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #2c3e50;")
        layout.addWidget(title_label)

        # Search Area
        search_layout = QHBoxLayout()
        search_label = QLabel("Search by Chassis/Engine Number:")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter chassis or engine number...")
        self.search_input.setMinimumHeight(40)
        self.search_btn = QPushButton("Search")
        self.search_btn.setMinimumHeight(40)
        self.search_btn.setMinimumWidth(100)
        self.search_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        self.search_btn.clicked.connect(self.handle_search)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input, 1)
        search_layout.addWidget(self.search_btn)
        layout.addLayout(search_layout)

        # Buttons for actions
        buttons_layout = QHBoxLayout()
        self.add_btn = QPushButton("Add New Record")
        self.add_btn.setMinimumHeight(45)
        self.add_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #229954;
            }
        """)
        self.refresh_btn = QPushButton("Refresh List")
        self.refresh_btn.setMinimumHeight(45)
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #f39c12;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #e67e22;
            }
        """)
        self.refresh_btn.clicked.connect(self.load_records)
        buttons_layout.addWidget(self.add_btn)
        buttons_layout.addWidget(self.refresh_btn)
        buttons_layout.addStretch(1)
        layout.addLayout(buttons_layout)

        # Records Table
        self.records_table = QTableWidget()
        self.records_table.setColumnCount(8)
        self.records_table.setHorizontalHeaderLabels([
            "Record #",
            "Chassis #",
            "Engine #",
            "Customer Name",
            "Model",
            "Status",
            "Total Amount",
            "Created At"
        ])
        self.records_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.records_table.setAlternatingRowColors(True)
        self.records_table.setStyleSheet("""
            QTableWidget {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                gridline-color: #f0f0f0;
            }
            QHeaderView::section {
                background-color: #2c3e50;
                color: white;
                padding: 8px;
                border: none;
                font-weight: bold;
            }
            QTableWidget::item {
                padding: 8px;
            }
        """)
        layout.addWidget(self.records_table, 1)

        self.setLayout(layout)
        self.load_records()

    def load_records(self):
        """Load records from the database and populate the table"""
        from app.excise.services import excise_service
        self.records_table.setRowCount(0)
        try:
            records = excise_service.get_all_excise_records(self.db_session)
            for record in records:
                row_pos = self.records_table.rowCount()
                self.records_table.insertRow(row_pos)
                self.records_table.setItem(row_pos, 0, QTableWidgetItem(str(record.record_number)))
                self.records_table.setItem(row_pos, 1, QTableWidgetItem(str(record.chassis_number)))
                self.records_table.setItem(row_pos, 2, QTableWidgetItem(str(record.engine_number)))
                self.records_table.setItem(row_pos, 3, QTableWidgetItem(str(record.customer_name)))
                self.records_table.setItem(row_pos, 4, QTableWidgetItem(str(record.motorcycle_model or "")))
                self.records_table.setItem(row_pos, 5, QTableWidgetItem(str(record.status)))
                self.records_table.setItem(row_pos, 6, QTableWidgetItem(str(record.total_amount or "")))
                self.records_table.setItem(row_pos, 7, QTableWidgetItem(record.created_at.strftime("%Y-%m-%d %H:%M:%S")))
        except Exception as e:
            print(f"Error loading excise records: {e}")

    def handle_search(self):
        """Handle search button click"""
        search_text = self.search_input.text().strip()
        if not search_text:
            self.load_records()
            return

        from app.excise.services import excise_service
        self.records_table.setRowCount(0)
        try:
            # Try by chassis
            record = excise_service.get_excise_record_by_chassis(self.db_session, search_text)
            if record:
                records = [record]
            else:
                # If not found, load all (in real scenario, we'd implement proper search)
                records = excise_service.get_all_excise_records(self.db_session)

            for rec in records:
                row_pos = self.records_table.rowCount()
                self.records_table.insertRow(row_pos)
                self.records_table.setItem(row_pos, 0, QTableWidgetItem(str(rec.record_number)))
                self.records_table.setItem(row_pos, 1, QTableWidgetItem(str(rec.chassis_number)))
                self.records_table.setItem(row_pos, 2, QTableWidgetItem(str(rec.engine_number)))
                self.records_table.setItem(row_pos, 3, QTableWidgetItem(str(rec.customer_name)))
                self.records_table.setItem(row_pos, 4, QTableWidgetItem(str(rec.motorcycle_model or "")))
                self.records_table.setItem(row_pos, 5, QTableWidgetItem(str(rec.status)))
                self.records_table.setItem(row_pos, 6, QTableWidgetItem(str(rec.total_amount or "")))
                self.records_table.setItem(row_pos, 7, QTableWidgetItem(rec.created_at.strftime("%Y-%m-%d %H:%M:%S")))
        except Exception as e:
            print(f"Error searching records: {e}")
