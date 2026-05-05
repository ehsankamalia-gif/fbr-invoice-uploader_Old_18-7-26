from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QDateEdit, QTextEdit, QPushButton, QFrame, QCompleter, 
    QTableView, QHeaderView, QMessageBox, QScrollArea, 
    QGridLayout, QTableWidget, QTableWidgetItem, QTabWidget,
    QComboBox, QSizePolicy, QAbstractItemView, QListView
)
from PyQt6.QtCore import Qt, QDate, QStringListModel, QModelIndex, QTimer, QEvent
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QFont, QShortcut, QKeySequence, QKeyEvent
from app.services.credit_ledger_service import credit_ledger_service
from app.services.print_service_v2 import PrintServiceV2
import datetime as dt
from app.core.logger import logger

class BuyerCompleter(QCompleter):
    """Custom completer that prevents auto-fill on arrow key navigation."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setFilterMode(Qt.MatchFlag.MatchContains)
        # DisplayRole is used for search, UserRole for final completion
        self.setCompletionRole(Qt.ItemDataRole.UserRole)
        
        # Use QListView for better control and focus handling
        popup = QListView()
        popup.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        popup.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        popup.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setPopup(popup)

    def pathFromIndex(self, index: QModelIndex) -> str:
        # Returning empty string prevents the LineEdit from being updated during navigation.
        # This is CRITICAL to prevent auto-fill while arrowing through the list.
        return ""

class ChassisLineEdit(QLineEdit):
    """Custom LineEdit that redirects arrow keys to the completer popup."""
    def keyPressEvent(self, event):
        # Auto-uppercase behavior without using setText() (Requirement 6)
        if event.text().isalpha():
            upper_event = QKeyEvent(
                event.type(), 
                event.key(), 
                event.modifiers(), 
                event.text().upper()
            )
            super().keyPressEvent(upper_event)
            return

        completer = self.completer()
        if completer and completer.popup().isVisible():
            if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
                # Redirect arrow keys to the popup list without moving focus (Requirement 2)
                completer.popup().keyPressEvent(event)
                return
            if event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return):
                # Trigger selection for the highlighted item
                index = completer.popup().currentIndex()
                if index.isValid():
                    completer.activated[QModelIndex].emit(index)
                completer.popup().hide()
                return
            if event.key() == Qt.Key.Key_Escape:
                completer.popup().hide()
                return
        super().keyPressEvent(event)

class CreditLedgerSystemPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Credit Sales & Ledger System")
        self.selected_sale_buyer_id = None
        self.selected_pay_buyer_id = None
        self.selected_ledger_buyer_id = None
        self.current_customer_details = None
        self.print_service = PrintServiceV2()
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
        self.sale_buyer_input.setPlaceholderText("Search by Name, Phone or CNIC...")
        self.sale_buyer_completer = BuyerCompleter(self.sale_buyer_input)
        self.sale_buyer_input.setCompleter(self.sale_buyer_completer)
        self.sale_buyer_input.textChanged.connect(self._update_buyer_suggestions)
        self.sale_buyer_completer.activated[QModelIndex].connect(self._on_buyer_selected_index)
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
        self.sale_items_table = QTableWidget(0, 6)
        self.sale_items_table.setHorizontalHeaderLabels(["Chassis #", "Model", "Color", "Cash Price", "Credit Price", "Action"])
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
        
        # Shortcuts (Requirement: Ctrl + N for new row)
        self.new_row_shortcut = QShortcut(QKeySequence("Ctrl+N"), self.sale_tab)
        self.new_row_shortcut.activated.connect(self._add_sale_item_row)

        scroll.setWidget(container)
        layout.addWidget(scroll)

        # Requirement: Automatically add one empty row on load
        QTimer.singleShot(100, self._add_sale_item_row)

    def _format_buyer_suggestion(self, s):
        """Format buyer details for dropdown display: Name | Type | Phone | CNIC"""
        btype = "Dealer" if s['type'] == "DEALER" else "Customer"
        return f"{s['name']} | {btype} | {s['phone']} | {s['cnic']}"

    def _update_buyer_suggestions(self, text):
        if not text: return
        
        # Auto-uppercase behavior
        if text != text.upper():
            self.sale_buyer_input.blockSignals(True)
            self.sale_buyer_input.setText(text.upper())
            self.sale_buyer_input.blockSignals(False)
            text = text.upper()

        suggestions = credit_ledger_service.get_buyer_suggestions(text)
        model = QStandardItemModel(self.sale_buyer_completer)
        for s in suggestions:
            formatted = self._format_buyer_suggestion(s)
            item = QStandardItem(formatted)
            # Store metadata in UserRoles
            item.setData(s['name'], Qt.ItemDataRole.UserRole)
            item.setData(s['id'], Qt.ItemDataRole.UserRole + 1)
            item.setData(s['type'], Qt.ItemDataRole.UserRole + 2)
            model.appendRow(item)
            
        self.sale_buyer_completer.setModel(model)
        # Reset prefix to prevent internal filtering
        self.sale_buyer_completer.setCompletionPrefix("")
        if suggestions:
            self.sale_buyer_completer.complete()

    def _on_buyer_selected_index(self, index: QModelIndex):
        """Handle selection from the completer popup using index (prevents auto-fill issues)."""
        name = index.data(Qt.ItemDataRole.UserRole)
        buyer_id = index.data(Qt.ItemDataRole.UserRole + 1)
        buyer_type = index.data(Qt.ItemDataRole.UserRole + 2)
        
        # We use singleShot to ensure the text is set AFTER the completer's internal 
        # event handling finishes, which prevents it from being overwritten.
        QTimer.singleShot(0, lambda: self._apply_buyer_selection(name, buyer_id, buyer_type))

    def _apply_buyer_selection(self, name, buyer_id, buyer_type):
        # Fill ONLY the name (Requirement 1)
        self.sale_buyer_input.blockSignals(True)
        self.sale_buyer_input.setText(name)
        self.sale_buyer_input.blockSignals(False)
        self.selected_sale_buyer_id = buyer_id
        
        # Auto-fill buyer type (Requirement 5)
        btype = "Dealer" if buyer_type == "DEALER" else "Customer"
        self.buyer_type_combo.setEnabled(True)
        self.buyer_type_combo.setCurrentText(btype)
        self.buyer_type_combo.setEnabled(False)

    def _on_buyer_input_finished(self):
        """Handle cases where name is typed fully or pasted without using suggestions."""
        name = self.sale_buyer_input.text().strip().upper()
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
        """Adds a new row to the motorcycles table. Requirement: Smart Row Handling (No duplicate empty rows)"""
        if self.buyer_type_combo.currentText() == "Customer" and self.sale_items_table.rowCount() >= 1:
            QMessageBox.warning(self, "Limit", "Customers can only purchase one motorcycle on credit.")
            return
            
        # Check if last row is empty before adding a new one
        if self.sale_items_table.rowCount() > 0:
            last_row = self.sale_items_table.rowCount() - 1
            chassis_widget = self.sale_items_table.cellWidget(last_row, 0)
            if chassis_widget and isinstance(chassis_widget, QLineEdit):
                if not chassis_widget.text().strip():
                    # Focus the existing empty row instead of adding a new one
                    chassis_widget.setFocus()
                    return

        row = self.sale_items_table.rowCount()
        self.sale_items_table.insertRow(row)
        
        chassis_edit = ChassisLineEdit()
        chassis_edit.setPlaceholderText("Scan/Type Chassis #")
        chassis_completer = BuyerCompleter(chassis_edit) # Reuse logic for non-autofill
        chassis_edit.setCompleter(chassis_completer)
        chassis_edit.textChanged.connect(lambda text, ce=chassis_edit, cc=chassis_completer: self._update_chassis_suggest(text, ce, cc))
        chassis_completer.activated[QModelIndex].connect(lambda index, ce=chassis_edit, r=row: self._on_chassis_selected_index(index, ce, r))
        chassis_edit.editingFinished.connect(lambda ce=chassis_edit, r=row: self._on_chassis_selected(ce, r))
        
        # Install event filter for Enter and Tab handling
        chassis_edit.installEventFilter(self)
        
        self.sale_items_table.setCellWidget(row, 0, chassis_edit)
        self.sale_items_table.setItem(row, 1, QTableWidgetItem("")) # Model
        
        color_item = QTableWidgetItem("")
        color_item.setFlags(color_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.sale_items_table.setItem(row, 2, color_item) # Color (Read-only)
        
        cash_price_item = QTableWidgetItem("0.00")
        cash_price_item.setFlags(cash_price_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.sale_items_table.setItem(row, 3, cash_price_item) # Cash Price (Read-only)
        
        credit_price_edit = QLineEdit("0.00")
        credit_price_edit.textChanged.connect(self._calculate_sale_totals)
        credit_price_edit.installEventFilter(self) # Tab from last column
        self.sale_items_table.setCellWidget(row, 4, credit_price_edit)
        
        del_btn = QPushButton("Delete")
        del_btn.clicked.connect(lambda: self._remove_sale_item_row(row))
        self.sale_items_table.setCellWidget(row, 5, del_btn)

        # Requirement: Automatically focus on Chassis # field
        chassis_edit.setFocus()

    def _remove_sale_item_row(self, row_idx):
        # We need to find the actual row index because rows might have shifted
        for r in range(self.sale_items_table.rowCount()):
            if self.sale_items_table.cellWidget(r, 5) == self.sender():
                self.sale_items_table.removeRow(r)
                break
        self._calculate_sale_totals()

    def eventFilter(self, source, event):
        """Requirement: Handle Enter in last row and Tab in last column."""
        if event.type() == QEvent.Type.KeyPress:
            # Handle Enter key
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                # Find which row this widget belongs to
                for r in range(self.sale_items_table.rowCount()):
                    for c in (0, 4): # Only Chassis and Credit Price edits have event filter
                        if self.sale_items_table.cellWidget(r, c) == source:
                            # If it's the last row, add a new one
                            if r == self.sale_items_table.rowCount() - 1:
                                # Only add if current row has data
                                chassis_widget = self.sale_items_table.cellWidget(r, 0)
                                if chassis_widget and chassis_widget.text().strip():
                                    self._add_sale_item_row()
                                    return True
                            break
            
            # Handle Tab key in the last column (Credit Price)
            if event.key() == Qt.Key.Key_Tab:
                for r in range(self.sale_items_table.rowCount()):
                    if self.sale_items_table.cellWidget(r, 4) == source: # Last editable column
                        if r == self.sale_items_table.rowCount() - 1:
                            # Only add if current row has data
                            chassis_widget = self.sale_items_table.cellWidget(r, 0)
                            if chassis_widget and chassis_widget.text().strip():
                                self._add_sale_item_row()
                                return True
                            
        return super().eventFilter(source, event)

    def _update_chassis_suggest(self, text, edit, completer):
        search_text = (text or "").strip().upper()
        if not search_text: 
            completer.popup().hide()
            return

        try:
            # Fetch from DB
            suggestions = credit_ledger_service.get_chassis_suggestions(search_text)
            
            # Create model for the completer
            model = QStandardItemModel(completer)
            for s in suggestions:
                display_text = f"{s['chassis']} | {s['model']} | {s['color']}"
                if s.get('fbr_inv') and s['fbr_inv'] != "AVAILABLE":
                    display_text += f" | FBR: {s['fbr_inv']}"
                
                item = QStandardItem(display_text)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                item.setData(s['chassis'], Qt.ItemDataRole.UserRole)
                item.setData(s, Qt.ItemDataRole.UserRole + 1)
                model.appendRow(item)
                
            completer.setModel(model)
            
            # Requirement: Show Dropdown Immediately without flickering
            if suggestions:
                # We do NOT use setCompletionPrefix here as we manually fetched matches
                completer.complete()
            else:
                completer.popup().hide()
            
        except Exception as e:
            logger.error(f"Error updating chassis suggestions: {e}")

    def _on_chassis_selected_index(self, index, edit, row):
        """Handle selection from the chassis completer popup."""
        chassis = index.data(Qt.ItemDataRole.UserRole)
        m_data = index.data(Qt.ItemDataRole.UserRole + 1)
        
        # Set the clean chassis number
        edit.setText(chassis)
        
        if m_data:
            self._apply_chassis_details(m_data, row)

    def _apply_chassis_details(self, m_data, row):
        # Double check FBR invoice status (Requirement: Validation on Selection)
        if not credit_ledger_service.validate_fbr_invoice(m_data['chassis']):
            QMessageBox.critical(self, "Validation Error", 
                f"Chassis {m_data['chassis']} does not have a fiscalized FBR invoice.\n"
                "Credit sale is not allowed.")
            # Clear fields
            chassis_edit = self.sale_items_table.cellWidget(row, 0)
            if chassis_edit: chassis_edit.clear()
            self.sale_items_table.item(row, 1).setText("")
            self.sale_items_table.item(row, 2).setText("")
            self.sale_items_table.item(row, 3).setText("0.00")
            credit_widget = self.sale_items_table.cellWidget(row, 4)
            if credit_widget: credit_widget.setText("0.00")
            return

        # Auto-fill: Model, Color, Cash Price, and Credit Price
        self.sale_items_table.item(row, 1).setText(m_data['model'])
        self.sale_items_table.item(row, 2).setText(m_data.get('color', ''))
        
        price_str = f"{m_data['cash_price']:.2f}"
        self.sale_items_table.item(row, 3).setText(price_str)
        
        credit_widget = self.sale_items_table.cellWidget(row, 4)
        if credit_widget:
            credit_widget.setText(price_str)
            # Smooth transition: Move focus to Credit Price field
            QTimer.singleShot(100, credit_widget.setFocus)
            
        self._calculate_sale_totals()

    def _on_chassis_selected(self, edit, row):
        chassis = edit.text().strip()
        if not chassis: return
        
        # If already filled by selection, don't re-fetch
        if self.sale_items_table.item(row, 1).text():
            return

        results = credit_ledger_service.get_chassis_suggestions(chassis)
        m_data = None
        for r in results:
            if r['chassis'] == chassis:
                m_data = r
                break
        
        if m_data:
            self._apply_chassis_details(m_data, row)
        else:
            # Check if it exists but is missing FBR invoice
            exists_in_db = credit_ledger_service.check_chassis_exists(chassis)
            if exists_in_db:
                QMessageBox.warning(self, "Invalid Chassis", 
                    f"Chassis {chassis} exists but does not have a valid FBR invoice.\n"
                    "Only FBR-invoiced motorcycles can be sold on credit.")
            
            # Clear if invalid chassis or missing FBR
            self.sale_items_table.item(row, 1).setText("")
            self.sale_items_table.item(row, 2).setText("")
            self.sale_items_table.item(row, 3).setText("0.00")
            credit_widget = self.sale_items_table.cellWidget(row, 4)
            if credit_widget: credit_widget.setText("0.00")
            
        self._calculate_sale_totals()

    def _calculate_sale_totals(self):
        total_credit = 0.0
        for r in range(self.sale_items_table.rowCount()):
            try:
                total_credit += float(self.sale_items_table.cellWidget(r, 4).text() or 0)
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
                cash_p = float(self.sale_items_table.item(r, 3).text())
                credit_p = float(self.sale_items_table.cellWidget(r, 4).text())
                items_data.append({
                    "chassis_number": chassis,
                    "model": self.sale_items_table.item(r, 1).text(),
                    "color": self.sale_items_table.item(r, 2).text(),
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
        self.pay_buyer_input.setPlaceholderText("Search by Name, Phone or CNIC...")
        self.pay_buyer_completer = BuyerCompleter(self.pay_buyer_input)
        self.pay_buyer_input.setCompleter(self.pay_buyer_completer)
        self.pay_buyer_input.textChanged.connect(self._update_pay_buyer_suggestions)
        self.pay_buyer_completer.activated[QModelIndex].connect(self._on_pay_buyer_selected_index)
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
        if not text: return
        
        # Auto-uppercase behavior
        if text != text.upper():
            self.pay_buyer_input.blockSignals(True)
            self.pay_buyer_input.setText(text.upper())
            self.pay_buyer_input.blockSignals(False)
            text = text.upper()

        suggestions = credit_ledger_service.get_buyer_suggestions(text)
        model = QStandardItemModel(self.pay_buyer_completer)
        for s in suggestions:
            formatted = self._format_buyer_suggestion(s)
            item = QStandardItem(formatted)
            # Store metadata in UserRoles
            item.setData(s['name'], Qt.ItemDataRole.UserRole)
            item.setData(s['id'], Qt.ItemDataRole.UserRole + 1)
            model.appendRow(item)
            
        self.pay_buyer_completer.setModel(model)
        # Reset prefix to prevent internal filtering
        self.pay_buyer_completer.setCompletionPrefix("")
        if suggestions:
            self.pay_buyer_completer.complete()

    def _on_pay_buyer_selected_index(self, index: QModelIndex):
        name = index.data(Qt.ItemDataRole.UserRole)
        buyer_id = index.data(Qt.ItemDataRole.UserRole + 1)
        QTimer.singleShot(0, lambda: self._apply_pay_buyer_selection(name, buyer_id))

    def _apply_pay_buyer_selection(self, name, buyer_id):
        self.pay_buyer_input.blockSignals(True)
        self.pay_buyer_input.setText(name)
        self.pay_buyer_input.blockSignals(False)
        self.selected_pay_buyer_id = buyer_id

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
        self.ledger_buyer_input.setPlaceholderText("Search by Name, Phone or CNIC...")
        self.ledger_buyer_completer = BuyerCompleter(self.ledger_buyer_input)
        self.ledger_buyer_input.setCompleter(self.ledger_buyer_completer)
        self.ledger_buyer_input.textChanged.connect(self._update_ledger_buyer_suggestions)
        self.ledger_buyer_completer.activated[QModelIndex].connect(self._on_ledger_buyer_selected_index)
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
        
        self.print_ledger_btn = QPushButton("Print Ledger")
        self.print_ledger_btn.setStyleSheet("background-color: #2c3e50; color: white;")
        self.print_ledger_btn.clicked.connect(self.print_ledger)
        filters.addWidget(self.print_ledger_btn)
        
        layout.addLayout(filters)
        
        # Customer Info Header
        self.customer_info_card = QFrame()
        self.customer_info_card.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 5px;
                margin-bottom: 5px;
            }
            QLabel {
                font-size: 13px;
                color: #2c3e50;
            }
            .header-label {
                font-weight: bold;
                color: #7f8c8d;
            }
        """)
        info_layout = QGridLayout(self.customer_info_card)
        
        self.lbl_cust_name = QLabel("Name: -")
        self.lbl_cust_father = QLabel("Father Name: -")
        self.lbl_cust_address = QLabel("Address: -")
        self.lbl_cust_phone = QLabel("Phone: -")
        
        info_layout.addWidget(self.lbl_cust_name, 0, 0)
        info_layout.addWidget(self.lbl_cust_father, 0, 1)
        info_layout.addWidget(self.lbl_cust_phone, 1, 0)
        info_layout.addWidget(self.lbl_cust_address, 1, 1)
        
        layout.addWidget(self.customer_info_card)
        
        self.ledger_table = QTableView()
        self.ledger_model = QStandardItemModel()
        self.ledger_model.setHorizontalHeaderLabels(["Date", "Description", "Debit", "Credit", "Balance"])
        self.ledger_table.setModel(self.ledger_model)
        self.ledger_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.ledger_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.ledger_table.setWordWrap(True)
        layout.addWidget(self.ledger_table)

    def _update_ledger_buyer_suggestions(self, text):
        if not text: return
        
        # Auto-uppercase behavior
        if text != text.upper():
            self.ledger_buyer_input.blockSignals(True)
            self.ledger_buyer_input.setText(text.upper())
            self.ledger_buyer_input.blockSignals(False)
            text = text.upper()

        suggestions = credit_ledger_service.get_buyer_suggestions(text)
        model = QStandardItemModel(self.ledger_buyer_completer)
        for s in suggestions:
            formatted = self._format_buyer_suggestion(s)
            item = QStandardItem(formatted)
            # Store metadata in UserRoles
            item.setData(s['name'], Qt.ItemDataRole.UserRole)
            item.setData(s['id'], Qt.ItemDataRole.UserRole + 1)
            model.appendRow(item)
            
        self.ledger_buyer_completer.setModel(model)
        # Reset prefix to prevent internal filtering
        self.ledger_buyer_completer.setCompletionPrefix("")
        if suggestions:
            self.ledger_buyer_completer.complete()

    def _on_ledger_buyer_selected_index(self, index: QModelIndex):
        name = index.data(Qt.ItemDataRole.UserRole)
        buyer_id = index.data(Qt.ItemDataRole.UserRole + 1)
        QTimer.singleShot(0, lambda: self._apply_ledger_buyer_selection(name, buyer_id))

    def _apply_ledger_buyer_selection(self, name, buyer_id):
        self.ledger_buyer_input.blockSignals(True)
        self.ledger_buyer_input.setText(name)
        self.ledger_buyer_input.blockSignals(False)
        self.selected_ledger_buyer_id = buyer_id

    def _update_ledger_chassis_suggestions(self, text):
        if len(text) < 1: return
        suggestions = credit_ledger_service.get_chassis_suggestions(text)
        names = [s['chassis'] for s in suggestions]
        self.ledger_chassis_completer.setModel(QStringListModel(names))

    def load_ledger(self):
        buyer_name = self.ledger_buyer_input.text().strip()
        if not buyer_name or not self.selected_ledger_buyer_id:
            # Try manual lookup
            info = credit_ledger_service.get_buyer_type(buyer_name)
            if info:
                self.selected_ledger_buyer_id = info['id']
            else:
                QMessageBox.warning(self, "Filter Required", "Please enter a valid Buyer Name to view the ledger.")
                return
        
        # Update Customer Header
        cust_details = credit_ledger_service.get_customer_details(self.selected_ledger_buyer_id)
        if cust_details:
            self.lbl_cust_name.setText(f"Name: {cust_details['name']}")
            self.lbl_cust_father.setText(f"Father Name: {cust_details['father_name']}")
            self.lbl_cust_address.setText(f"Address: {cust_details['address']}")
            self.lbl_cust_phone.setText(f"Phone: {cust_details['phone']}")
            self.current_customer_details = cust_details
        
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

    def print_ledger(self):
        """Generates and prints a professional ledger statement."""
        if not hasattr(self, 'current_customer_details') or not self.current_customer_details:
            QMessageBox.warning(self, "Print Error", "Please load a customer ledger first.")
            return

        entries = []
        for r in range(self.ledger_model.rowCount()):
            entries.append({
                "date": self.ledger_model.item(r, 0).text(),
                "description": self.ledger_model.item(r, 1).text(),
                "debit": self.ledger_model.item(r, 2).text().replace(',', ''),
                "credit": self.ledger_model.item(r, 3).text().replace(',', ''),
                "balance": self.ledger_model.item(r, 4).text().replace(',', '')
            })

        if not entries:
            QMessageBox.warning(self, "Print Error", "No transactions found to print.")
            return

        ledger_data = {
            "customer": self.current_customer_details,
            "entries": entries,
            "date_range": f"{self.start_date.date().toString('dd-MM-yyyy')} to {self.end_date.date().toString('dd-MM-yyyy')}"
        }

        try:
            html = self.print_service.render_ledger_statement(ledger_data)
            self.print_service.print_custom_html(html, self)
        except Exception as e:
            logger.error(f"Failed to print ledger: {e}")
            QMessageBox.critical(self, "Print Error", f"Failed to generate print: {e}")

    def refresh(self):
        self.refresh_dashboard()
