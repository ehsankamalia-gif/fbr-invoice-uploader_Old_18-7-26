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
        
        # Use QListView for better control and focus handling
        popup = QListView()
        popup.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        popup.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        popup.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # Ensure the popup is wide enough for detailed info
        popup.setMinimumWidth(500)
        # Standard attributes for popup completion
        popup.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setPopup(popup)

    def pathFromIndex(self, index: QModelIndex) -> str:
        # Returning empty string prevents the LineEdit from being updated during navigation.
        return ""

class ChassisCompleter(QCompleter):
    """Custom completer for Chassis numbers."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setFilterMode(Qt.MatchFlag.MatchContains)
        
        popup = QListView()
        popup.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        popup.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        popup.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        popup.setMinimumWidth(400)
        popup.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setPopup(popup)

    def pathFromIndex(self, index: QModelIndex) -> str:
        return ""

class SharedLineEdit(QLineEdit):
    """Custom LineEdit that handles uppercase conversion and consistent completer behavior."""
    def keyPressEvent(self, event):
        completer = self.completer()
        
        # 1. Handle Completer interactions first
        if completer and completer.popup() and completer.popup().isVisible():
            # A. Handle Navigation Keys
            if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
                # We must manually manage the highlight to prevent focus issues in QTableWidget
                popup = completer.popup()
                curr_index = popup.currentIndex()
                row = curr_index.row() if curr_index.isValid() else -1
                
                if event.key() == Qt.Key.Key_Down:
                    row += 1
                elif event.key() == Qt.Key.Key_Up:
                    row -= 1
                elif event.key() == Qt.Key.Key_PageDown:
                    row += 5
                elif event.key() == Qt.Key.Key_PageUp:
                    row -= 5
                
                max_row = completer.completionModel().rowCount()
                row = max(0, min(row, max_row - 1))
                
                new_index = completer.completionModel().index(row, 0)
                if new_index.isValid():
                    popup.setCurrentIndex(new_index)
                    popup.scrollTo(new_index)
                return
            
            # B. Handle Selection Keys (Enter/Return)
            if event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return):
                index = completer.popup().currentIndex()
                if index.isValid():
                    # Get the correct index from the completion model
                    completion_index = completer.completionModel().mapToSource(index)
                    completer.activated[QModelIndex].emit(completion_index)
                    completer.popup().hide()
                    return
            
            # C. Handle Escape
            if event.key() == Qt.Key.Key_Escape:
                completer.popup().hide()
                return

        # 2. Auto-uppercase behavior for typing
        if event.text().isalpha():
            upper_event = QKeyEvent(
                event.type(), 
                event.key(), 
                event.modifiers(), 
                event.text().upper()
            )
            super().keyPressEvent(upper_event)
            return

        super().keyPressEvent(event)

    def focusInEvent(self, event):
        """Ensure the widget is ready for interaction when focused."""
        super().focusInEvent(event)
        if self.completer():
            # Standard setup for QCompleter in QTableWidget
            self.completer().setWidget(self)
            popup = self.completer().popup()
            popup.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

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

        # Auto-refresh dashboard when switching to it
        self.tabs.currentChanged.connect(lambda index: self.refresh_dashboard() if index == 0 else None)
        
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
        self.sale_buyer_input = SharedLineEdit()
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
        
        self.sale_items_table = QTableWidget(0, 7)
        self.sale_items_table.setHorizontalHeaderLabels(["Chassis no", "Model", "Color", "Price", "Credit Price", "Description", "Action"])
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

    def _update_chassis_suggestions(self, text):
        """Fetch chassis suggestions and update the completer for the sender widget."""
        source = self.sender()
        if not source or not text: return
        
        # Auto-uppercase
        if text != text.upper():
            source.blockSignals(True)
            source.setText(text.upper())
            source.blockSignals(False)
            text = text.upper()

        completer = source.completer()
        if not completer: return

        suggestions = credit_ledger_service.get_chassis_suggestions(text)
        model = QStandardItemModel(completer)
        for s in suggestions:
            formatted = f"{s['chassis']} | {s['model']} | {s['color']}"
            item = QStandardItem(formatted)
            # Store metadata
            item.setData(s['chassis'], Qt.ItemDataRole.UserRole)
            item.setData(s['model'], Qt.ItemDataRole.UserRole + 1)
            item.setData(s['cash_price'], Qt.ItemDataRole.UserRole + 2)
            item.setData(s['color'], Qt.ItemDataRole.UserRole + 3)
            model.appendRow(item)
            
        completer.setModel(model)
        completer.setCompletionPrefix("")
        if suggestions:
            completer.complete()

    def _on_chassis_selected(self, index: QModelIndex):
        """Handle chassis selection from the completer."""
        chassis = index.data(Qt.ItemDataRole.UserRole)
        model_name = index.data(Qt.ItemDataRole.UserRole + 1)
        price = index.data(Qt.ItemDataRole.UserRole + 2)
        color = index.data(Qt.ItemDataRole.UserRole + 3)
        
        # We need to find which widget triggered this
        completer = self.sender()
        if not completer: return
        
        source = completer.widget()
        if not source: return
        
        # Apply selection to the row
        QTimer.singleShot(0, lambda: self._apply_chassis_selection(source, chassis, model_name, price, color))

    def _apply_chassis_selection(self, source, chassis, model_name, price, color):
        # Find row
        row = -1
        for r in range(self.sale_items_table.rowCount()):
            if self.sale_items_table.cellWidget(r, 0) == source:
                row = r
                break
        
        if row == -1: return

        source.blockSignals(True)
        source.setText(chassis)
        source.blockSignals(False)
        
        # Auto-fill Model field
        model_edit = self.sale_items_table.cellWidget(row, 1)
        if model_edit and not model_edit.text().strip():
            model_edit.setText(model_name)

        # Auto-fill Color field
        color_edit = self.sale_items_table.cellWidget(row, 2)
        if color_edit and not color_edit.text().strip():
            color_edit.setText(color)
            
        # Auto-fill Cash Price (Price) field
        cash_price_edit = self.sale_items_table.cellWidget(row, 3)
        if cash_price_edit and (not cash_price_edit.text() or cash_price_edit.text() == "0.00"):
            cash_price_edit.setText(f"{price:.2f}")

        # Auto-fill Credit Price field
        price_edit = self.sale_items_table.cellWidget(row, 4)
        if price_edit and (not price_edit.text() or price_edit.text() == "0.00"):
            price_edit.setText(f"{price:.2f}")
            
        # Move focus to Credit Price field
        if price_edit:
            price_edit.setFocus()
            price_edit.selectAll() # Select text for easy editing

    def _validate_chassis_input(self):
        """Validate if the manually entered chassis number is already sold on credit."""
        source = self.sender()
        if not source: return
        
        chassis = source.text().strip().upper()
        if not chassis: return
        
        if not credit_ledger_service.check_chassis_unique(chassis):
            QMessageBox.warning(self, "Invalid Chassis", f"Chassis number {chassis} has already been sold on credit and cannot be sold again.")
            source.clear()
            source.setFocus()

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
        """Adds a new row to the motorcycles table."""
        if self.buyer_type_combo.currentText() == "Customer" and self.sale_items_table.rowCount() >= 1:
            QMessageBox.warning(self, "Limit", "Customers can only purchase one motorcycle on credit.")
            return
            
        row = self.sale_items_table.rowCount()
        self.sale_items_table.insertRow(row)
        
        chassis_edit = SharedLineEdit()
        chassis_edit.setPlaceholderText("Chassis Number")
        
        # Add Chassis Completer
        chassis_completer = ChassisCompleter(chassis_edit)
        chassis_edit.setCompleter(chassis_completer)
        chassis_edit.textChanged.connect(self._update_chassis_suggestions)
        chassis_completer.activated[QModelIndex].connect(self._on_chassis_selected)
        chassis_edit.editingFinished.connect(self._validate_chassis_input)
        
        chassis_edit.installEventFilter(self)
        self.sale_items_table.setCellWidget(row, 0, chassis_edit)

        model_edit = SharedLineEdit()
        model_edit.setPlaceholderText("Model")
        model_edit.installEventFilter(self)
        self.sale_items_table.setCellWidget(row, 1, model_edit)

        color_edit = SharedLineEdit()
        color_edit.setPlaceholderText("Color")
        color_edit.installEventFilter(self)
        self.sale_items_table.setCellWidget(row, 2, color_edit)

        cash_price_edit = QLineEdit("0.00")
        cash_price_edit.setReadOnly(True)
        cash_price_edit.setStyleSheet("background-color: #f0f0f0; color: #333;")
        cash_price_edit.installEventFilter(self)
        self.sale_items_table.setCellWidget(row, 3, cash_price_edit)
        
        price_edit = QLineEdit("0.00")
        price_edit.textChanged.connect(self._calculate_sale_totals)
        price_edit.installEventFilter(self)
        self.sale_items_table.setCellWidget(row, 4, price_edit)

        desc_edit = SharedLineEdit() 
        desc_edit.setPlaceholderText("Description / Item Details")
        desc_edit.installEventFilter(self)
        self.sale_items_table.setCellWidget(row, 5, desc_edit)
        
        del_btn = QPushButton("Delete")
        del_btn.clicked.connect(lambda: self._remove_sale_item_row(row))
        self.sale_items_table.setCellWidget(row, 6, del_btn)

        # Focus on chassis field
        chassis_edit.setFocus()

    def _remove_sale_item_row(self, row_idx):
        # We need to find the actual row index because rows might have shifted
        for r in range(self.sale_items_table.rowCount()):
            if self.sale_items_table.cellWidget(r, 6) == self.sender():
                self.sale_items_table.removeRow(r)
                break
        self._calculate_sale_totals()

    def eventFilter(self, source, event):
        """Handle Enter and Tab for table navigation."""
        if event.type() == QEvent.Type.KeyPress:
            # Handle Enter key
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                # Find which row this widget belongs to
                for r in range(self.sale_items_table.rowCount()):
                    for c in (0, 1, 2, 4, 5): # Chassis, Model, Color, Credit Price, Description (skip read-only Price)
                        if self.sale_items_table.cellWidget(r, c) == source:
                            if r == self.sale_items_table.rowCount() - 1:
                                credit_price_widget = self.sale_items_table.cellWidget(r, 4)
                                if credit_price_widget and credit_price_widget.text().strip() != "0.00":
                                    self._add_sale_item_row()
                                    return True
                            break
            
            # Handle Tab key in the last data column (Description)
            if event.key() == Qt.Key.Key_Tab:
                for r in range(self.sale_items_table.rowCount()):
                    if self.sale_items_table.cellWidget(r, 5) == source:
                        if r == self.sale_items_table.rowCount() - 1:
                            credit_price_widget = self.sale_items_table.cellWidget(r, 4)
                            if credit_price_widget and credit_price_widget.text().strip() != "0.00":
                                self._add_sale_item_row()
                                return True
                            
        return super().eventFilter(source, event)

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
        total_credit = 0.0
        
        for r in range(self.sale_items_table.rowCount()):
            chassis = self.sale_items_table.cellWidget(r, 0).text().strip()
            model = self.sale_items_table.cellWidget(r, 1).text().strip()
            color = self.sale_items_table.cellWidget(r, 2).text().strip()
            cash_p_text = self.sale_items_table.cellWidget(r, 3).text().strip()
            credit_p_text = self.sale_items_table.cellWidget(r, 4).text().strip()
            desc = self.sale_items_table.cellWidget(r, 5).text().strip()
            
            if not chassis and not credit_p_text: continue
            
            if not chassis:
                QMessageBox.warning(self, "Error", f"Chassis number is required in row {r+1}")
                return
            
            try:
                cash_p = float(cash_p_text or 0)
                credit_p = float(credit_p_text or 0)
                items_data.append({
                    "chassis_number": chassis,
                    "model": model,
                    "color": color,
                    "description": desc,
                    "cash_price": cash_p,
                    "credit_price": credit_p
                })
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
        self.pay_buyer_input = SharedLineEdit()
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
        
        # Filters
        filters = QHBoxLayout()
        filters.addWidget(QLabel("Buyer Name:"))
        self.ledger_buyer_input = SharedLineEdit()
        self.ledger_buyer_input.setPlaceholderText("Search Buyer...")
        self.ledger_buyer_completer = BuyerCompleter(self.ledger_buyer_input)
        self.ledger_buyer_input.setCompleter(self.ledger_buyer_completer)
        self.ledger_buyer_input.textChanged.connect(self._update_ledger_buyer_suggestions)
        self.ledger_buyer_completer.activated[QModelIndex].connect(self._on_ledger_buyer_selected_index)
        filters.addWidget(self.ledger_buyer_input)
        
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
        
        entries = credit_ledger_service.get_ledger(
            self.selected_ledger_buyer_id, 
            self.start_date.date().toPyDate(), 
            self.end_date.date().toPyDate()
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
