from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QDateEdit, QTextEdit, QPushButton, QFrame, QCompleter, 
    QTableView, QHeaderView, QMessageBox, QScrollArea, 
    QGridLayout, QTableWidget, QTableWidgetItem, QTabWidget,
    QComboBox, QSizePolicy, QAbstractItemView
)
from PyQt6.QtCore import Qt, QDate, QStringListModel
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QFont
from app.services.credit_ledger_service import credit_ledger_service
import datetime as dt
from app.core.logger import logger

class CreditLedgerSystemPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Credit Sales & Ledger System")
        self.selected_sale_buyer_id = None
        self.selected_pay_buyer_id = None
        self.selected_ledger_buyer_id = None
        self.setup_ui()
        self.refresh_dashboard()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        self.tabs = QTabWidget()
        
        # 1. Dashboard Tab
        self.dashboard_tab = QWidget()
        self._setup_dashboard_tab()
        self.tabs.addTab(self.dashboard_tab, "Dashboard")
        
        # 2. Sale Entry Tab
        self.sale_tab = QWidget()
        self._setup_sale_tab()
        self.tabs.addTab(self.sale_tab, "Credit Sale Entry")
        
        # 3. Payment Entry Tab
        self.payment_tab = QWidget()
        self._setup_payment_tab()
        self.tabs.addTab(self.payment_tab, "Payment Entry")
        
        # 4. Ledger Statement Tab
        self.ledger_tab = QWidget()
        self._setup_ledger_tab()
        self.tabs.addTab(self.ledger_tab, "Ledger Statement")
        
        main_layout.addWidget(self.tabs)

    # --- TAB: DASHBOARD ---
    def _setup_dashboard_tab(self):
        layout = QVBoxLayout(self.dashboard_tab)
        
        # Stats Cards
        stats_layout = QHBoxLayout()
        self.stat_sales = self._create_stat_card("Total Credit Sales", "0.00", "#3498db")
        self.stat_received = self._create_stat_card("Total Received", "0.00", "#2ecc71")
        self.stat_outstanding = self._create_stat_card("Total Outstanding", "0.00", "#e74c3c")
        stats_layout.addWidget(self.stat_sales)
        stats_layout.addWidget(self.stat_received)
        stats_layout.addWidget(self.stat_outstanding)
        layout.addLayout(stats_layout)
        
        # Buyer Balances Table
        layout.addWidget(QLabel("Buyer-wise Outstanding Balances"))
        self.buyer_table = QTableWidget(0, 2)
        self.buyer_table.setHorizontalHeaderLabels(["Buyer Name", "Outstanding Balance"])
        self.buyer_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.buyer_table)
        
        refresh_btn = QPushButton("Refresh Dashboard")
        refresh_btn.clicked.connect(self.refresh_dashboard)
        layout.addWidget(refresh_btn)

    def _create_stat_card(self, title, val, color):
        card = QFrame()
        card.setStyleSheet(f"background-color: {color}; border-radius: 10px; color: white;")
        l = QVBoxLayout(card)
        t = QLabel(title)
        t.setStyleSheet("font-size: 14px;")
        v = QLabel(val)
        v.setStyleSheet("font-size: 24px; font-weight: bold;")
        l.addWidget(t)
        l.addWidget(v)
        card.setProperty("val_label", v)
        return card

    def refresh_dashboard(self):
        stats = credit_ledger_service.get_dashboard_stats()
        self.stat_sales.property("val_label").setText(f"Rs. {stats['total_sales']:,.2f}")
        self.stat_received.property("val_label").setText(f"Rs. {stats['total_received']:,.2f}")
        self.stat_outstanding.property("val_label").setText(f"Rs. {stats['total_outstanding']:,.2f}")
        
        self.buyer_table.setRowCount(0)
        for b in stats['buyer_balances']:
            row = self.buyer_table.rowCount()
            self.buyer_table.insertRow(row)
            self.buyer_table.setItem(row, 0, QTableWidgetItem(b['name']))
            bal_item = QTableWidgetItem(f"{b['balance']:,.2f}")
            if b['balance'] > 1000000: # Example alert for high outstanding
                bal_item.setForeground(Qt.GlobalColor.red)
            self.buyer_table.setItem(row, 1, bal_item)

    # --- TAB: SALE ENTRY ---
    def _setup_sale_tab(self):
        layout = QVBoxLayout(self.sale_tab)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        grid = QGridLayout(container)
        
        # Header Info
        grid.addWidget(QLabel("Buyer Name:"), 0, 0)
        self.sale_buyer_input = QLineEdit()
        self.sale_buyer_completer = QCompleter()
        self.sale_buyer_input.setCompleter(self.sale_buyer_completer)
        self.sale_buyer_input.textChanged.connect(self._update_buyer_suggestions)
        self.sale_buyer_completer.activated.connect(self._on_buyer_selected)
        self.sale_buyer_input.editingFinished.connect(self._on_buyer_input_finished)
        grid.addWidget(self.sale_buyer_input, 0, 1)
        
        grid.addWidget(QLabel("Buyer Type:"), 0, 2)
        self.buyer_type_combo = QComboBox()
        self.buyer_type_combo.addItems(["Customer", "Dealer"])
        self.buyer_type_combo.setEnabled(False) # Make it read-only as per requirement
        self.buyer_type_combo.setStyleSheet("background-color: #f0f0f0; color: #333;")
        self.buyer_type_combo.currentTextChanged.connect(self._on_buyer_type_changed)
        grid.addWidget(self.buyer_type_combo, 0, 3)
        
        grid.addWidget(QLabel("Sale Date:"), 1, 0)
        self.sale_date_edit = QDateEdit(QDate.currentDate())
        self.sale_date_edit.setCalendarPopup(True)
        grid.addWidget(self.sale_date_edit, 1, 1)
        
        grid.addWidget(QLabel("Duration (Months):"), 1, 2)
        self.sale_duration = QLineEdit("0")
        grid.addWidget(self.sale_duration, 1, 3)
        
        # Items Table
        grid.addWidget(QLabel("Motorcycles:"), 2, 0)
        self.sale_items_table = QTableWidget(0, 5)
        self.sale_items_table.setHorizontalHeaderLabels(["Chassis #", "Model", "Cash Price", "Credit Price", "Action"])
        self.sale_items_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        grid.addWidget(self.sale_items_table, 3, 0, 1, 4)
        
        self.add_item_btn = QPushButton("+ Add Motorcycle")
        self.add_item_btn.clicked.connect(self._add_sale_item_row)
        grid.addWidget(self.add_item_btn, 4, 0)
        
        # Totals
        self.total_credit_label = QLabel("Total Credit: 0.00")
        self.total_credit_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        grid.addWidget(self.total_credit_label, 5, 2, 1, 2)
        
        grid.addWidget(QLabel("Advance Payment:"), 6, 2)
        self.sale_advance = QLineEdit("0")
        self.sale_advance.textChanged.connect(self._calculate_sale_totals)
        grid.addWidget(self.sale_advance, 6, 3)
        
        self.remaining_label = QLabel("Remaining: 0.00")
        self.remaining_label.setStyleSheet("font-weight: bold; color: #e74c3c;")
        grid.addWidget(self.remaining_label, 7, 2, 1, 2)
        
        save_btn = QPushButton("Process Credit Sale")
        save_btn.setStyleSheet("background-color: #27ae60; color: white; padding: 10px;")
        save_btn.clicked.connect(self.process_sale)
        grid.addWidget(save_btn, 8, 0, 1, 4)
        
        scroll.setWidget(container)
        layout.addWidget(scroll)

    def _update_buyer_suggestions(self, text):
        if len(text) < 1: return
        suggestions = credit_ledger_service.get_buyer_suggestions(text)
        names = [s['name'] for s in suggestions]
        self.sale_buyer_completer.setModel(QStringListModel(names))
        # Store metadata for quick lookup if needed
        self.sale_buyer_input.setProperty("suggestions", suggestions)

    def _on_buyer_selected(self, name):
        """Auto-fill buyer type and store ID when a buyer is selected from suggestions."""
        suggestions = self.sale_buyer_input.property("suggestions") or []
        for s in suggestions:
            if s['name'] == name:
                self.selected_sale_buyer_id = s['id']
                btype = "Dealer" if s['type'] == "DEALER" else "Customer"
                self.buyer_type_combo.setEnabled(True)
                self.buyer_type_combo.setCurrentText(btype)
                self.buyer_type_combo.setEnabled(False)
                return

    def _on_buyer_input_finished(self):
        """Handle cases where name is typed fully or pasted without using suggestions."""
        name = self.sale_buyer_input.text().strip()
        if not name: 
            self.selected_sale_buyer_id = None
            return
        
        # If not already filled by selection, do a quick lookup
        info = credit_ledger_service.get_buyer_type(name)
        if info:
            self.selected_sale_buyer_id = info['id']
            self.buyer_type_combo.setEnabled(True)
            self.buyer_type_combo.setCurrentText(info['type'])
            self.buyer_type_combo.setEnabled(False)
        else:
            self.selected_sale_buyer_id = None

    def _on_buyer_type_changed(self, btype):
        if btype == "Customer" and self.sale_items_table.rowCount() > 1:
            QMessageBox.information(self, "Limit", "Customers are usually restricted to a single motorcycle.")
            # self.sale_items_table.setRowCount(1) # Optional enforcement

    def _add_sale_item_row(self):
        if self.buyer_type_combo.currentText() == "Customer" and self.sale_items_table.rowCount() >= 1:
            QMessageBox.warning(self, "Limit", "Customers can only purchase one motorcycle on credit.")
            return
            
        row = self.sale_items_table.rowCount()
        self.sale_items_table.insertRow(row)
        
        chassis_edit = QLineEdit()
        chassis_completer = QCompleter()
        chassis_edit.setCompleter(chassis_completer)
        chassis_edit.textChanged.connect(lambda text, ce=chassis_edit, cc=chassis_completer: self._update_chassis_suggest(text, ce, cc))
        chassis_edit.editingFinished.connect(lambda ce=chassis_edit, r=row: self._on_chassis_selected(ce, r))
        
        self.sale_items_table.setCellWidget(row, 0, chassis_edit)
        self.sale_items_table.setItem(row, 1, QTableWidgetItem("")) # Model
        self.sale_items_table.setItem(row, 2, QTableWidgetItem("0.00")) # Cash Price
        
        credit_price_edit = QLineEdit("0.00")
        credit_price_edit.textChanged.connect(self._calculate_sale_totals)
        self.sale_items_table.setCellWidget(row, 3, credit_price_edit)
        
        del_btn = QPushButton("Delete")
        del_btn.clicked.connect(lambda: self.sale_items_table.removeRow(self.sale_items_table.currentRow()))
        self.sale_items_table.setCellWidget(row, 4, del_btn)

    def _update_chassis_suggest(self, text, edit, completer):
        if len(text) < 1: return
        suggestions = credit_ledger_service.get_chassis_suggestions(text)
        names = [s['chassis'] for s in suggestions]
        completer.setModel(QStringListModel(names))
        # Store metadata for later use if needed
        edit.setProperty("meta", suggestions)

    def _on_chassis_selected(self, edit, row):
        chassis = edit.text()
        meta = edit.property("meta") or []
        for m in meta:
            if m['chassis'] == chassis:
                self.sale_items_table.item(row, 1).setText(m['model'])
                self.sale_items_table.item(row, 2).setText(f"{m['cash_price']:.2f}")
                # Default credit price to cash price + markup if desired
                self.sale_items_table.cellWidget(row, 3).setText(f"{m['cash_price'] * 1.12:.2f}")
                break
        self._calculate_sale_totals()

    def _calculate_sale_totals(self):
        total_credit = 0.0
        for r in range(self.sale_items_table.rowCount()):
            try:
                total_credit += float(self.sale_items_table.cellWidget(r, 3).text() or 0)
            except: pass
        
        self.total_credit_label.setText(f"Total Credit: {total_credit:,.2f}")
        try:
            advance = float(self.sale_advance.text() or 0)
            remaining = total_credit - advance
            self.remaining_label.setText(f"Remaining: {remaining:,.2f}")
        except: pass

    def process_sale(self):
        buyer = self.sale_buyer_input.text().strip()
        if not buyer or not self.selected_sale_buyer_id:
            # Try manual lookup
            info = credit_ledger_service.get_buyer_type(buyer)
            if info:
                self.selected_sale_buyer_id = info['id']
            else:
                QMessageBox.warning(self, "Error", "Buyer name is required.")
                return
            
        items_data = []
        total_cash = 0.0
        total_credit = 0.0
        
        for r in range(self.sale_items_table.rowCount()):
            chassis = self.sale_items_table.cellWidget(r, 0).text().strip()
            if not chassis: continue
            
            try:
                cash_p = float(self.sale_items_table.item(r, 2).text())
                credit_p = float(self.sale_items_table.cellWidget(r, 3).text())
                items_data.append({
                    "chassis_number": chassis,
                    "model": self.sale_items_table.item(r, 1).text(),
                    "cash_price": cash_p,
                    "credit_price": credit_p
                })
                total_cash += cash_p
                total_credit += credit_p
            except ValueError:
                QMessageBox.warning(self, "Error", f"Invalid price in row {r+1}")
                return

        if not items_data:
            QMessageBox.warning(self, "Error", "Add at least one motorcycle.")
            return

        try:
            advance = float(self.sale_advance.text() or 0)
            sale_data = {
                "buyer_id": self.selected_sale_buyer_id,
                "buyer_type": self.buyer_type_combo.currentText(),
                "sale_date": self.sale_date_edit.date().toPyDate(),
                "duration_months": int(self.sale_duration.text() or 0),
                "total_cash_price": total_cash,
                "total_credit_price": total_credit,
                "advance_payment": advance,
                "remaining_amount": total_credit - advance
            }
            
            credit_ledger_service.create_credit_sale(sale_data, items_data)
            QMessageBox.information(self, "Success", "Credit sale processed and ledger updated.")
            self.refresh_dashboard()
            # Clear form...
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # --- TAB: PAYMENT ENTRY ---
    def _setup_payment_tab(self):
        layout = QVBoxLayout(self.payment_tab)
        form = QGridLayout()
        
        form.addWidget(QLabel("Buyer Name:"), 0, 0)
        self.pay_buyer_input = QLineEdit()
        self.pay_buyer_completer = QCompleter()
        self.pay_buyer_input.setCompleter(self.pay_buyer_completer)
        self.pay_buyer_input.textChanged.connect(self._update_pay_buyer_suggestions)
        self.pay_buyer_completer.activated.connect(self._on_pay_buyer_selected)
        form.addWidget(self.pay_buyer_input, 0, 1)
        
        form.addWidget(QLabel("Payment Amount:"), 1, 0)
        self.pay_amount = QLineEdit("0.00")
        self.pay_amount.textChanged.connect(self._calculate_net_payment)
        form.addWidget(self.pay_amount, 1, 1)
        
        form.addWidget(QLabel("Penalty Amount (Late):"), 2, 0)
        self.pay_penalty = QLineEdit("0.00")
        self.pay_penalty.textChanged.connect(self._calculate_net_payment)
        form.addWidget(self.pay_penalty, 2, 1)
        
        form.addWidget(QLabel("Discount Amount (Early):"), 3, 0)
        self.pay_discount = QLineEdit("0.00")
        self.pay_discount.textChanged.connect(self._calculate_net_payment)
        form.addWidget(self.pay_discount, 3, 1)
        
        form.addWidget(QLabel("Net Received Amount:"), 4, 0)
        self.pay_net_received = QLineEdit("0.00")
        self.pay_net_received.setReadOnly(True)
        self.pay_net_received.setStyleSheet("background-color: #ecf0f1; font-weight: bold;")
        form.addWidget(self.pay_net_received, 4, 1)
        
        form.addWidget(QLabel("Date:"), 5, 0)
        self.pay_date = QDateEdit(QDate.currentDate())
        self.pay_date.setCalendarPopup(True)
        form.addWidget(self.pay_date, 5, 1)
        
        form.addWidget(QLabel("Ref (Optional):"), 6, 0)
        self.pay_ref = QLineEdit()
        form.addWidget(self.pay_ref, 6, 1)
        
        pay_btn = QPushButton("Submit Payment")
        pay_btn.setStyleSheet("background-color: #3498db; color: white; padding: 10px;")
        pay_btn.clicked.connect(self.submit_payment)
        form.addWidget(pay_btn, 7, 0, 1, 2)
        
        layout.addLayout(form)
        layout.addStretch()

    def _calculate_net_payment(self):
        try:
            amt = float(self.pay_amount.text() or 0)
            penalty = float(self.pay_penalty.text() or 0)
            discount = float(self.pay_discount.text() or 0)
            net = amt + penalty - discount
            self.pay_net_received.setText(f"{net:.2f}")
        except:
            self.pay_net_received.setText("0.00")

    def _update_pay_buyer_suggestions(self, text):
        if len(text) < 1: return
        suggestions = credit_ledger_service.get_buyer_suggestions(text)
        names = [s['name'] for s in suggestions]
        self.pay_buyer_completer.setModel(QStringListModel(names))
        self.pay_buyer_input.setProperty("suggestions", suggestions)

    def _on_pay_buyer_selected(self, name):
        suggestions = self.pay_buyer_input.property("suggestions") or []
        for s in suggestions:
            if s['name'] == name:
                self.selected_pay_buyer_id = s['id']
                return

    def submit_payment(self):
        buyer = self.pay_buyer_input.text().strip()
        if not buyer or not self.selected_pay_buyer_id:
            # Try manual lookup if ID is missing
            info = credit_ledger_service.get_buyer_type(buyer)
            if info:
                self.selected_pay_buyer_id = info['id']
            else:
                QMessageBox.warning(self, "Error", "Invalid Buyer selected.")
                return
                
        try:
            amt = float(self.pay_amount.text() or 0)
            penalty = float(self.pay_penalty.text() or 0)
            discount = float(self.pay_discount.text() or 0)
            net = float(self.pay_net_received.text() or 0)

            if amt < 0 or penalty < 0 or discount < 0:
                QMessageBox.warning(self, "Validation Error", "Amounts cannot be negative.")
                return
            
            if amt == 0 and penalty == 0 and discount == 0:
                QMessageBox.warning(self, "Validation Error", "Please enter a valid amount.")
                return

            data = {
                "buyer_id": self.selected_pay_buyer_id,
                "amount": amt,
                "penalty_amount": penalty,
                "discount_amount": discount,
                "net_amount": net,
                "payment_date": self.pay_date.date().toPyDate(),
                "invoice_reference": self.pay_ref.text()
            }
            payment = credit_ledger_service.create_payment(data)
            
            # Show receipt dialog with name
            self.show_receipt(payment, buyer)
            
            self.refresh_dashboard()
            self.pay_amount.setText("0.00")
            self.pay_penalty.setText("0.00")
            self.pay_discount.setText("0.00")
            self.pay_ref.clear()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def show_receipt(self, payment, buyer_name):
        # Generate receipt with updated ledger balance
        # We need to get the latest balance for this buyer
        stats = credit_ledger_service.get_dashboard_stats()
        current_bal = 0.0
        for b in stats['buyer_balances']:
            if b['id'] == payment.buyer_id:
                current_bal = b['balance']
                break
                
        receipt_text = f"""
        ========================================
                 PAYMENT RECEIPT
        ========================================
        Date: {payment.payment_date.strftime('%d-%m-%Y')}
        Buyer: {buyer_name}
        ----------------------------------------
        Payment Amount:  Rs. {payment.amount:,.2f}
        Penalty (Late):  Rs. {payment.penalty_amount:,.2f}
        Discount (Early): Rs. {payment.discount_amount:,.2f}
        ----------------------------------------
        NET RECEIVED:    Rs. {payment.net_amount:,.2f}
        ----------------------------------------
        Ref: {payment.invoice_reference or 'N/A'}
        ----------------------------------------
        UPDATED LEDGER BALANCE: Rs. {current_bal:,.2f}
        ========================================
        """
        QMessageBox.information(self, "Payment Receipt", receipt_text)
        # In a real app, I'd use the print_service_v2 here

    # --- TAB: LEDGER STATEMENT ---
    def _setup_ledger_tab(self):
        layout = QVBoxLayout(self.ledger_tab)
        
        filters = QHBoxLayout()
        self.ledger_buyer_input = QLineEdit()
        self.ledger_buyer_input.setPlaceholderText("Buyer Name...")
        self.ledger_buyer_completer = QCompleter()
        self.ledger_buyer_input.setCompleter(self.ledger_buyer_completer)
        self.ledger_buyer_input.textChanged.connect(self._update_ledger_buyer_suggestions)
        self.ledger_buyer_completer.activated.connect(self._on_ledger_buyer_selected)
        filters.addWidget(self.ledger_buyer_input)
        
        self.ledger_chassis_input = QLineEdit()
        self.ledger_chassis_input.setPlaceholderText("Chassis Number...")
        self.ledger_chassis_completer = QCompleter()
        self.ledger_chassis_input.setCompleter(self.ledger_chassis_completer)
        self.ledger_chassis_input.textChanged.connect(self._update_ledger_chassis_suggestions)
        filters.addWidget(self.ledger_chassis_input)
        
        self.start_date = QDateEdit(QDate.currentDate().addMonths(-1))
        self.start_date.setCalendarPopup(True)
        filters.addWidget(QLabel("From:"))
        filters.addWidget(self.start_date)
        
        self.end_date = QDateEdit(QDate.currentDate())
        self.end_date.setCalendarPopup(True)
        filters.addWidget(QLabel("To:"))
        filters.addWidget(self.end_date)
        
        view_btn = QPushButton("View Ledger")
        view_btn.clicked.connect(self.load_ledger)
        filters.addWidget(view_btn)
        
        layout.addLayout(filters)
        
        self.ledger_table = QTableView()
        self.ledger_model = QStandardItemModel()
        self.ledger_model.setHorizontalHeaderLabels(["Date", "Description", "Debit", "Credit", "Balance"])
        self.ledger_table.setModel(self.ledger_model)
        self.ledger_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.ledger_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.ledger_table.setWordWrap(True)
        layout.addWidget(self.ledger_table)

    def _update_ledger_buyer_suggestions(self, text):
        if len(text) < 1: return
        suggestions = credit_ledger_service.get_buyer_suggestions(text)
        names = [s['name'] for s in suggestions]
        self.ledger_buyer_completer.setModel(QStringListModel(names))
        self.ledger_buyer_input.setProperty("suggestions", suggestions)

    def _on_ledger_buyer_selected(self, name):
        suggestions = self.ledger_buyer_input.property("suggestions") or []
        for s in suggestions:
            if s['name'] == name:
                self.selected_ledger_buyer_id = s['id']
                return

    def _update_ledger_chassis_suggestions(self, text):
        if len(text) < 1: return
        suggestions = credit_ledger_service.get_chassis_suggestions(text)
        names = [s['chassis'] for s in suggestions]
        self.ledger_chassis_completer.setModel(QStringListModel(names))

    def load_ledger(self):
        buyer = self.ledger_buyer_input.text().strip()
        if not buyer or not self.selected_ledger_buyer_id:
            # Try manual lookup
            info = credit_ledger_service.get_buyer_type(buyer)
            if info:
                self.selected_ledger_buyer_id = info['id']
            else:
                QMessageBox.warning(self, "Filter Required", "Please enter a valid Buyer Name to view the ledger.")
                return
        
        chassis = self.ledger_chassis_input.text().strip()
        entries = credit_ledger_service.get_ledger(
            self.selected_ledger_buyer_id, 
            self.start_date.date().toPyDate(), 
            self.end_date.date().toPyDate(),
            chassis_number=chassis if chassis else None
        )
        
        self.ledger_model.removeRows(0, self.ledger_model.rowCount())
        for e in entries:
            row = [
                QStandardItem(e.date.strftime('%d-%m-%Y')),
                QStandardItem(e.description),
                QStandardItem(f"{e.debit:,.2f}" if e.debit else "0.00"),
                QStandardItem(f"{e.credit:,.2f}" if e.credit else "0.00"),
                QStandardItem(f"{e.balance:,.2f}")
            ]
            self.ledger_model.appendRow(row)

    def refresh(self):
        self.refresh_dashboard()
