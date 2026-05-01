from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QDateEdit, QTextEdit, QPushButton, QFormLayout, 
    QFrame, QCompleter, QTableView, QHeaderView, QMessageBox,
    QScrollArea, QSizePolicy, QAbstractItemView, QGridLayout
)
from PyQt6.QtCore import Qt, QDate, pyqtSignal, QStringListModel, QTimer
from PyQt6.QtGui import QFont, QStandardItemModel, QStandardItem
from app.services.credit_book_service import credit_book_service
import datetime as dt
from app.core.logger import logger

class CreditBookPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Credit Book")
        self.setup_ui()
        self.load_data()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # Header
        header_label = QLabel("Credit Book Management")
        header_label.setObjectName("pageHeader")
        header_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #2c3e50;")
        main_layout.addWidget(header_label)

        # Scrollable Area for Form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(20)

        # --- Form Section ---
        form_frame = QFrame()
        form_frame.setObjectName("formGroup")
        form_frame.setStyleSheet("""
            QFrame#formGroup {
                background-color: #ffffff;
                border-radius: 8px;
                border: 1px solid #dcdde1;
            }
        """)
        form_layout = QGridLayout(form_frame)
        form_layout.setContentsMargins(25, 25, 25, 25)
        form_layout.setSpacing(15)

        # 1. Date Field (Top)
        form_layout.addWidget(QLabel("Date:"), 0, 0)
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("dd-MM-yyyy")
        self.date_edit.setMinimumWidth(200)
        form_layout.addWidget(self.date_edit, 0, 1)

        # 2. Customer Name
        form_layout.addWidget(QLabel("Customer/Dealer Name:"), 1, 0)
        self.customer_input = QLineEdit()
        self.customer_input.setPlaceholderText("Enter or search customer/dealer...")
        self.customer_completer = QCompleter()
        self.customer_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.customer_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.customer_input.setCompleter(self.customer_completer)
        self.customer_input.textChanged.connect(self.update_customer_suggestions)
        form_layout.addWidget(self.customer_input, 1, 1, 1, 3)

        # 3. Chassis Number
        form_layout.addWidget(QLabel("Chassis Number:"), 2, 0)
        self.chassis_input = QLineEdit()
        self.chassis_input.setPlaceholderText("Enter or search chassis...")
        self.chassis_completer = QCompleter()
        self.chassis_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.chassis_input.setCompleter(self.chassis_completer)
        self.chassis_input.textChanged.connect(self.update_chassis_suggestions)
        self.chassis_input.editingFinished.connect(self.on_chassis_selected)
        form_layout.addWidget(self.chassis_input, 2, 1)

        # 4, 5, 6. Auto-filled fields
        form_layout.addWidget(QLabel("Model:"), 2, 2)
        self.model_input = QLineEdit()
        self.model_input.setReadOnly(True)
        self.model_input.setStyleSheet("background-color: #f5f6fa;")
        form_layout.addWidget(self.model_input, 2, 3)

        form_layout.addWidget(QLabel("Color:"), 3, 0)
        self.color_input = QLineEdit()
        self.color_input.setReadOnly(True)
        self.color_input.setStyleSheet("background-color: #f5f6fa;")
        form_layout.addWidget(self.color_input, 3, 1)

        form_layout.addWidget(QLabel("Price:"), 3, 2)
        self.price_input = QLineEdit()
        self.price_input.setReadOnly(True)
        self.price_input.setStyleSheet("background-color: #f5f6fa;")
        form_layout.addWidget(self.price_input, 3, 3)

        # 7, 8. Manual Inputs
        form_layout.addWidget(QLabel("Decided Credit Amount:"), 4, 0)
        self.decided_amount_input = QLineEdit()
        self.decided_amount_input.setPlaceholderText("0.00")
        self.decided_amount_input.textChanged.connect(self.calculate_remaining)
        form_layout.addWidget(self.decided_amount_input, 4, 1)

        form_layout.addWidget(QLabel("Advance:"), 4, 2)
        self.advance_input = QLineEdit()
        self.advance_input.setPlaceholderText("0.00")
        self.advance_input.textChanged.connect(self.calculate_remaining)
        form_layout.addWidget(self.advance_input, 4, 3)

        # 9. Duration
        duration_layout = QHBoxLayout()
        self.months_input = QLineEdit()
        self.months_input.setPlaceholderText("Months")
        self.days_input = QLineEdit()
        self.days_input.setPlaceholderText("Days")
        duration_layout.addWidget(self.months_input)
        duration_layout.addWidget(QLabel("M"))
        duration_layout.addWidget(self.days_input)
        duration_layout.addWidget(QLabel("D"))
        
        form_layout.addWidget(QLabel("Duration:"), 5, 0)
        form_layout.addLayout(duration_layout, 5, 1)

        # 10. Remaining Balance
        form_layout.addWidget(QLabel("Remaining Balance:"), 5, 2)
        self.remaining_input = QLineEdit()
        self.remaining_input.setReadOnly(True)
        self.remaining_input.setStyleSheet("background-color: #f1f2f6; font-weight: bold; color: #e74c3c;")
        form_layout.addWidget(self.remaining_input, 5, 3)

        # 11. Description
        form_layout.addWidget(QLabel("Description:"), 6, 0)
        self.description_input = QTextEdit()
        self.description_input.setPlaceholderText("Add any additional notes here...")
        self.description_input.setMaximumHeight(80)
        form_layout.addWidget(self.description_input, 6, 1, 1, 3)

        # Buttons
        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("Save Entry")
        self.save_btn.setObjectName("primaryButton")
        self.save_btn.setStyleSheet("""
            QPushButton#primaryButton {
                background-color: #3498db;
                color: white;
                padding: 10px 20px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton#primaryButton:hover {
                background-color: #2980b9;
            }
        """)
        self.save_btn.clicked.connect(self.save_entry)
        
        self.print_btn = QPushButton("Print Receipt")
        self.print_btn.setStyleSheet("padding: 10px 20px; background-color: #2ecc71; color: white; font-weight: bold; border-radius: 5px;")
        self.print_btn.clicked.connect(self.print_receipt)
        
        self.clear_btn = QPushButton("Clear Form")
        self.clear_btn.setStyleSheet("padding: 10px 20px;")
        self.clear_btn.clicked.connect(self.clear_form)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.clear_btn)
        btn_layout.addWidget(self.print_btn)
        btn_layout.addWidget(self.save_btn)
        form_layout.addLayout(btn_layout, 7, 0, 1, 4)

        container_layout.addWidget(form_frame)

        # --- Table Section ---
        table_frame = QFrame()
        table_layout = QVBoxLayout(table_frame)
        
        table_header = QLabel("Recent Credit Entries")
        table_header.setStyleSheet("font-size: 18px; font-weight: bold; margin-top: 10px;")
        table_layout.addWidget(table_header)

        self.table_view = QTableView()
        self.table_model = QStandardItemModel()
        self.table_model.setHorizontalHeaderLabels([
            "Date", "Customer", "Chassis", "Model", "Amount", "Advance", "Remaining", "Duration"
        ])
        self.table_view.setModel(self.table_model)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setStyleSheet("QTableView { border: 1px solid #dcdde1; }")
        
        table_layout.addWidget(self.table_view)
        container_layout.addWidget(table_frame)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    # --- Logic ---

    def update_customer_suggestions(self, text):
        if len(text) < 1:
            return
        suggestions = credit_book_service.search_suggestions(text)
        model = QStringListModel(suggestions)
        self.customer_completer.setModel(model)

    def update_chassis_suggestions(self, text):
        if len(text) < 1:
            return
        suggestions = credit_book_service.search_chassis_suggestions(text)
        model = QStringListModel(suggestions)
        self.chassis_completer.setModel(model)

    def on_chassis_selected(self):
        chassis_no = self.chassis_input.text().strip()
        if not chassis_no:
            return
        
        details = credit_book_service.get_chassis_details(chassis_no)
        if details:
            self.model_input.setText(details.get("model", ""))
            self.color_input.setText(details.get("color", ""))
            price = details.get("price", 0)
            self.price_input.setText(f"{price:.2f}")
            # Automatically set decided amount to price if empty
            if not self.decided_amount_input.text():
                self.decided_amount_input.setText(f"{price:.2f}")

    def calculate_remaining(self):
        try:
            decided = float(self.decided_amount_input.text() or 0)
            advance = float(self.advance_input.text() or 0)
            remaining = decided - advance
            self.remaining_input.setText(f"{remaining:.2f}")
        except ValueError:
            self.remaining_input.setText("0.00")

    def clear_form(self):
        self.date_edit.setDate(QDate.currentDate())
        self.customer_input.clear()
        self.chassis_input.clear()
        self.model_input.clear()
        self.color_input.clear()
        self.price_input.clear()
        self.decided_amount_input.clear()
        self.advance_input.clear()
        self.months_input.clear()
        self.days_input.clear()
        self.remaining_input.clear()
        self.description_input.clear()

    def print_receipt(self):
        """Generates a simple HTML receipt and opens the print dialog."""
        customer = self.customer_input.text().strip()
        if not customer:
            QMessageBox.warning(self, "Input Error", "Please enter a customer name before printing.")
            return

        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; color: #333; }}
                .header {{ text-align: center; border-bottom: 2px solid #333; padding-bottom: 10px; margin-bottom: 20px; }}
                .title {{ font-size: 24px; font-weight: bold; }}
                .content {{ margin-bottom: 20px; }}
                .row {{ display: flex; justify-content: space-between; margin-bottom: 10px; }}
                .label {{ font-weight: bold; }}
                .footer {{ margin-top: 50px; border-top: 1px solid #ccc; padding-top: 10px; text-align: center; font-size: 12px; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
                .total-row {{ font-weight: bold; background-color: #f9f9f9; }}
            </style>
        </head>
        <body>
            <div class="header">
                <div class="title">CREDIT BOOK RECEIPT</div>
                <div>Date: {self.date_edit.date().toString("dd-MM-yyyy")}</div>
            </div>
            
            <div class="content">
                <div class="row">
                    <span><span class="label">Customer:</span> {customer}</span>
                    <span><span class="label">Chassis #:</span> {self.chassis_input.text()}</span>
                </div>
                <div class="row">
                    <span><span class="label">Model:</span> {self.model_input.text()}</span>
                    <span><span class="label">Color:</span> {self.color_input.text()}</span>
                </div>
            </div>

            <table>
                <thead>
                    <tr>
                        <th>Description</th>
                        <th>Amount</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>Decided Credit Amount</td>
                        <td>Rs. {float(self.decided_amount_input.text() or 0):,.2f}</td>
                    </tr>
                    <tr>
                        <td>Advance Paid</td>
                        <td>Rs. {float(self.advance_input.text() or 0):,.2f}</td>
                    </tr>
                    <tr class="total-row">
                        <td>Remaining Balance</td>
                        <td>Rs. {float(self.remaining_input.text() or 0):,.2f}</td>
                    </tr>
                </tbody>
            </table>

            <div style="margin-top: 20px;">
                <span class="label">Duration:</span> {self.months_input.text()} Months, {self.days_input.text()} Days
            </div>

            <div style="margin-top: 20px;">
                <span class="label">Notes:</span><br>
                {self.description_input.toPlainText()}
            </div>

            <div class="footer">
                <p>Thank you for your business!</p>
                <p>Generated on: {dt.datetime.now().strftime("%d-%m-%Y %H:%M:%S")}</p>
            </div>
        </body>
        </html>
        """
        
        try:
            from app.services.print_service_v2 import print_service_v2
            print_service_v2.print_html_with_dialog(html, self)
        except Exception as e:
            QMessageBox.critical(self, "Print Error", f"Could not open print dialog: {str(e)}")

    def save_entry(self):
        # Validation
        customer = self.customer_input.text().strip()
        chassis = self.chassis_input.text().strip()
        try:
            decided = float(self.decided_amount_input.text() or 0)
            advance = float(self.advance_input.text() or 0)
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Please enter valid numeric amounts.")
            return

        if not customer or not chassis:
            QMessageBox.warning(self, "Input Error", "Customer name and Chassis number are required.")
            return

        data = {
            "date": self.date_edit.date().toPyDate(),
            "customer_name": customer,
            "chassis_no": chassis,
            "model": self.model_input.text(),
            "color": self.color_input.text(),
            "price": float(self.price_input.text() or 0),
            "decided_amount": decided,
            "advance": advance,
            "months": int(self.months_input.text() or 0),
            "days": int(self.days_input.text() or 0),
            "remaining_balance": decided - advance,
            "description": self.description_input.toPlainText()
        }

        try:
            credit_book_service.create_entry(data)
            QMessageBox.information(self, "Success", "Credit entry saved successfully.")
            self.clear_form()
            self.load_data()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save entry: {str(e)}")

    def refresh(self):
        self.load_data()

    def load_data(self):
        """Load recent entries into the table."""
        try:
            self.table_model.removeRows(0, self.table_model.rowCount())
            entries = credit_book_service.get_all_entries()
            for entry in entries:
                row = [
                    QStandardItem(entry.date.strftime("%d-%m-%Y") if entry.date else ""),
                    QStandardItem(str(entry.customer_name)),
                    QStandardItem(str(entry.chassis_no)),
                    QStandardItem(str(entry.model)),
                    QStandardItem(f"{entry.decided_amount:,.2f}"),
                    QStandardItem(f"{entry.advance:,.2f}"),
                    QStandardItem(f"{entry.remaining_balance:,.2f}"),
                    QStandardItem(f"{entry.months}M {entry.days}D")
                ]
                self.table_model.appendRow(row)
        except Exception as e:
            logger.error(f"Error loading credit book data: {e}")
