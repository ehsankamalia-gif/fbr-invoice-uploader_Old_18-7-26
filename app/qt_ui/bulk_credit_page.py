from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QDateEdit, QTextEdit, QPushButton, QFrame, QCompleter, 
    QTableView, QHeaderView, QMessageBox, QScrollArea, 
    QAbstractItemView, QGridLayout, QTableWidget, QTableWidgetItem,
    QTabWidget
)
from PyQt6.QtCore import Qt, QDate, pyqtSignal, QStringListModel
from PyQt6.QtGui import QStandardItemModel, QStandardItem
from app.services.bulk_credit_service import bulk_credit_service
from app.services.credit_book_service import credit_book_service # Reuse customer suggest
from app.services.customer_service import customer_service
import datetime as dt
from app.core.logger import logger

class BulkCreditPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bulk Credit Purchase")
        self.selected_customer_id = None
        self.setup_ui()
        self.load_history()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # Header
        header_label = QLabel("Bulk Motorcycle Credit Purchase")
        header_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #2c3e50;")
        main_layout.addWidget(header_label)

        self.tabs = QTabWidget()
        
        # --- TAB 1: NEW PURCHASE ---
        new_purchase_tab = QWidget()
        self.tabs.addTab(new_purchase_tab, "New Bulk Order")
        tab_layout = QVBoxLayout(new_purchase_tab)

        # 1. Header Info (Customer & Date)
        header_frame = QFrame()
        header_frame.setStyleSheet("background-color: white; border-radius: 8px; border: 1px solid #dcdde1;")
        header_grid = QGridLayout(header_frame)
        header_grid.setContentsMargins(15, 15, 15, 15)

        header_grid.addWidget(QLabel("Date:"), 0, 0)
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        header_grid.addWidget(self.date_edit, 0, 1)

        header_grid.addWidget(QLabel("Customer/Dealer:"), 0, 2)
        self.customer_input = QLineEdit()
        self.customer_completer = QCompleter()
        self.customer_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.customer_input.setCompleter(self.customer_completer)
        self.customer_input.textChanged.connect(self._update_customer_suggest)
        self.customer_input.editingFinished.connect(self._on_customer_selected)
        header_grid.addWidget(self.customer_input, 0, 3)

        tab_layout.addWidget(header_frame)

        # 2. Items Table
        items_group = QFrame()
        items_group.setStyleSheet("background-color: white; border-radius: 8px; border: 1px solid #dcdde1;")
        items_layout = QVBoxLayout(items_group)
        
        items_header = QHBoxLayout()
        items_header.addWidget(QLabel("Motorcycles in this Order"))
        items_header.addStretch()
        
        self.add_item_btn = QPushButton("+ Add Motorcycle")
        self.add_item_btn.clicked.connect(self.add_empty_row)
        items_header.addWidget(self.add_item_btn)
        items_layout.addLayout(items_header)

        self.items_table = QTableWidget(0, 7)
        self.items_table.setHorizontalHeaderLabels([
            "Chassis #", "Engine #", "Model", "Color", "Price", "Discount", "Net Price"
        ])
        self.items_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.items_table.cellChanged.connect(self._on_cell_changed)
        items_layout.addWidget(self.items_table)

        tab_layout.addWidget(items_group)

        # 3. Totals and Financing
        footer_frame = QFrame()
        footer_frame.setStyleSheet("background-color: #f8f9fa; border-radius: 8px; border: 1px solid #dcdde1;")
        footer_grid = QGridLayout(footer_frame)
        footer_grid.setContentsMargins(15, 15, 15, 15)

        footer_grid.addWidget(QLabel("Total Amount:"), 0, 0)
        self.total_amount_label = QLabel("0.00")
        self.total_amount_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        footer_grid.addWidget(self.total_amount_label, 0, 1)

        footer_grid.addWidget(QLabel("Total Advance:"), 0, 2)
        self.advance_input = QLineEdit("0")
        self.advance_input.textChanged.connect(self._calculate_totals)
        footer_grid.addWidget(self.advance_input, 0, 3)

        footer_grid.addWidget(QLabel("Remaining Balance:"), 1, 0)
        self.balance_label = QLabel("0.00")
        self.balance_label.setStyleSheet("font-weight: bold; font-size: 16px; color: #e74c3c;")
        footer_grid.addWidget(self.balance_label, 1, 1)

        footer_grid.addWidget(QLabel("Duration (Months):"), 1, 2)
        self.months_input = QLineEdit("0")
        footer_grid.addWidget(self.months_input, 1, 3)

        footer_grid.addWidget(QLabel("Description:"), 2, 0)
        self.desc_input = QTextEdit()
        self.desc_input.setMaximumHeight(60)
        footer_grid.addWidget(self.desc_input, 2, 1, 1, 3)

        self.save_btn = QPushButton("Process Bulk Purchase")
        self.save_btn.setStyleSheet("background-color: #27ae60; color: white; padding: 12px; font-weight: bold;")
        self.save_btn.clicked.connect(self.save_bulk_purchase)
        footer_grid.addWidget(self.save_btn, 3, 0, 1, 4)

        tab_layout.addWidget(footer_frame)

        # --- TAB 2: HISTORY ---
        history_tab = QWidget()
        self.tabs.addTab(history_tab, "Purchase History")
        history_layout = QVBoxLayout(history_tab)

        self.history_table = QTableView()
        self.history_model = QStandardItemModel()
        self.history_model.setHorizontalHeaderLabels(["Date", "Customer", "Total", "Advance", "Balance", "Items", "Status"])
        self.history_table.setModel(self.history_model)
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        history_layout.addWidget(self.history_table)

        main_layout.addWidget(self.tabs)

    # --- Logic ---

    def _update_customer_suggest(self, text):
        if len(text) < 1: return
        suggestions = credit_book_service.search_suggestions(text)
        self.customer_completer.setModel(QStringListModel(suggestions))

    def _on_customer_selected(self):
        name = self.customer_input.text().strip()
        # Find ID if exists
        customers = customer_service.search_customers(name)
        if customers:
            self.selected_customer_id = customers[0].id

    def add_empty_row(self):
        row = self.items_table.rowCount()
        self.items_table.insertRow(row)
        
        # Setup chassis suggest for the new row
        chassis_input = QLineEdit()
        completer = QCompleter()
        chassis_input.setCompleter(completer)
        chassis_input.textChanged.connect(lambda text, inp=chassis_input, comp=completer: self._update_chassis_suggest(text, inp, comp))
        chassis_input.editingFinished.connect(lambda inp=chassis_input, r=row: self._on_chassis_entered(inp, r))
        
        self.items_table.setCellWidget(row, 0, chassis_input)
        
        # Set default values for numeric fields
        self.items_table.setItem(row, 4, QTableWidgetItem("0.00"))
        self.items_table.setItem(row, 5, QTableWidgetItem("0.00"))
        self.items_table.setItem(row, 6, QTableWidgetItem("0.00"))

    def _update_chassis_suggest(self, text, input_widget, completer):
        if len(text) < 1: return
        results = bulk_credit_service.search_available_motorcycles(text)
        suggestions = [m.chassis_number for m in results]
        completer.setModel(QStringListModel(suggestions))

    def _on_chassis_entered(self, input_widget, row):
        chassis_no = input_widget.text().strip()
        if not chassis_no: return
        
        details = credit_book_service.get_chassis_details(chassis_no)
        if details:
            self.items_table.blockSignals(True)
            self.items_table.setItem(row, 1, QTableWidgetItem(details.get('engine_no', '')))
            self.items_table.setItem(row, 2, QTableWidgetItem(details.get('model', '')))
            self.items_table.setItem(row, 3, QTableWidgetItem(details.get('color', '')))
            self.items_table.setItem(row, 4, QTableWidgetItem(f"{details.get('price', 0):.2f}"))
            self._update_row_net(row)
            self.items_table.blockSignals(False)
            self._calculate_totals()

    def _on_cell_changed(self, row, col):
        if col in [4, 5]: # Price or Discount changed
            self._update_row_net(row)
            self._calculate_totals()

    def _update_row_net(self, row):
        try:
            price = float(self.items_table.item(row, 4).text() or 0)
            discount = float(self.items_table.item(row, 5).text() or 0)
            net = price - discount
            self.items_table.setItem(row, 6, QTableWidgetItem(f"{net:.2f}"))
        except:
            pass

    def _calculate_totals(self):
        total = 0.0
        for row in range(self.items_table.rowCount()):
            try:
                total += float(self.items_table.item(row, 6).text() or 0)
            except: pass
        
        self.total_amount_label.setText(f"{total:,.2f}")
        try:
            advance = float(self.advance_input.text() or 0)
            balance = total - advance
            self.balance_label.setText(f"{balance:,.2f}")
        except:
            self.balance_label.setText("Error")

    def save_bulk_purchase(self):
        customer_name = self.customer_input.text().strip()
        if not customer_name:
            QMessageBox.warning(self, "Error", "Customer name is required.")
            return

        if self.items_table.rowCount() == 0:
            QMessageBox.warning(self, "Error", "Add at least one motorcycle.")
            return

        try:
            total_amt = float(self.total_amount_label.text().replace(',', ''))
            advance = float(self.advance_input.text() or 0)
            balance = total_amt - advance
            
            header = {
                "date": self.date_edit.date().toPyDate(),
                "customer_id": self.selected_customer_id,
                "customer_name": customer_name,
                "total_amount": total_amt,
                "total_advance": advance,
                "remaining_balance": balance,
                "months": int(self.months_input.text() or 0),
                "description": self.desc_input.toPlainText()
            }

            items = []
            for row in range(self.items_table.rowCount()):
                items.append({
                    "chassis_no": self.items_table.cellWidget(row, 0).text(),
                    "model": self.items_table.item(row, 2).text(),
                    "color": self.items_table.item(row, 3).text(),
                    "unit_price": float(self.items_table.item(row, 4).text()),
                    "discount": float(self.items_table.item(row, 5).text()),
                    "net_price": float(self.items_table.item(row, 6).text())
                })

            bulk_credit_service.create_bulk_purchase(header, items)
            QMessageBox.information(self, "Success", "Bulk purchase processed successfully.")
            self.clear_form()
            self.load_history()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to process purchase: {str(e)}")

    def clear_form(self):
        self.customer_input.clear()
        self.items_table.setRowCount(0)
        self.advance_input.setText("0")
        self.months_input.setText("0")
        self.desc_input.clear()
        self._calculate_totals()

    def load_history(self):
        try:
            self.history_model.removeRows(0, self.history_model.rowCount())
            purchases = bulk_credit_service.get_all_purchases()
            for p in purchases:
                row = [
                    QStandardItem(p.date.strftime("%d-%m-%Y")),
                    QStandardItem(p.customer_name),
                    QStandardItem(f"{p.total_amount:,.2f}"),
                    QStandardItem(f"{p.total_advance:,.2f}"),
                    QStandardItem(f"{p.remaining_balance:,.2f}"),
                    QStandardItem(str(len(p.items))),
                    QStandardItem(p.status)
                ]
                self.history_model.appendRow(row)
        except Exception as e:
            logger.error(f"Error loading history: {e}")

    def refresh(self):
        self.load_history()
