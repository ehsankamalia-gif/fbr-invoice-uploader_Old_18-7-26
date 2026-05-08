from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QDateEdit, QTextEdit, QPushButton, QFrame, QCompleter, 
    QTableView, QHeaderView, QMessageBox, QScrollArea, 
    QGridLayout, QTableWidget, QTableWidgetItem, QTabWidget,
    QComboBox, QSizePolicy, QAbstractItemView, QListView,
    QRadioButton, QButtonGroup, QGroupBox, QDialog,
    QGraphicsDropShadowEffect
)
from PyQt6.QtCore import Qt, QDate, QStringListModel, QModelIndex, QTimer, QEvent, QRegularExpression
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QFont, QShortcut, QKeySequence, QKeyEvent, QRegularExpressionValidator
from app.services.credit_ledger_service import credit_ledger_service
from app.services.print_service_v2 import PrintServiceV2
import datetime as dt
from app.core.logger import logger
from app.utils.duration_utils import parse_duration_string, format_duration, calculate_total_days, add_months

class CustomerFinancialSummaryDialog(QDialog):
    """Simple and Professional Customer Financial Summary Design."""
    def __init__(self, customer_id, parent=None):
        super().__init__(parent)
        self.customer_id = customer_id
        self.setWindowTitle("Customer Financial Summary")
        self.resize(1000, 700)
        
        # Add maximize and minimize buttons to the dialog
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint)
        
        self.setup_ui()
        self.load_data()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # 1. Top Section: Customer Info
        info_group = QFrame()
        info_group.setStyleSheet("background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 8px;")
        info_layout = QGridLayout(info_group)
        
        def add_info_label(label, row, col):
            lbl = QLabel(label)
            lbl.setStyleSheet("color: #6c757d; font-weight: bold; border: none;")
            val = QLabel("-")
            val.setStyleSheet("color: #212529; font-weight: bold; font-size: 14px; border: none;")
            info_layout.addWidget(lbl, row, col)
            info_layout.addWidget(val, row, col + 1)
            return val

        self.val_name = add_info_label("Customer Name:", 0, 0)
        self.val_phone = add_info_label("Phone Number:", 0, 2)
        self.val_address = add_info_label("Address:", 1, 0)
        info_layout.setColumnStretch(1, 1)
        info_layout.setColumnStretch(3, 1)
        layout.addWidget(info_group)

        # 2. Compact Financial Summary Cards
        summary_layout = QHBoxLayout()
        self.card_total_units = self._create_summary_card("Total Motorcycles", "0", "#34495e")
        self.card_total_credit = self._create_summary_card("Total Credit", "0.00", "#2980b9")
        self.card_total_paid = self._create_summary_card("Total Paid", "0.00", "#27ae60")
        self.card_balance = self._create_summary_card("Remaining Balance", "0.00", "#e67e22")
        self.card_overdue = self._create_summary_card("Overdue Amount", "0.00", "#c0392b")
        
        summary_layout.addWidget(self.card_total_units)
        summary_layout.addWidget(self.card_total_credit)
        summary_layout.addWidget(self.card_total_paid)
        summary_layout.addWidget(self.card_balance)
        summary_layout.addWidget(self.card_overdue)
        layout.addLayout(summary_layout)

        # Model-wise Summary Section
        self.model_summary_label = QLabel("")
        self.model_summary_label.setStyleSheet("color: #2c3e50; font-weight: 500; font-size: 12px; margin-top: 5px;")
        layout.addWidget(self.model_summary_label)

        # 3. Combined Accounts Table
        layout.addWidget(QLabel("<b>Credit Accounts & Installment History</b>"))
        self.accounts_table = QTableWidget(0, 9)
        self.accounts_table.setHorizontalHeaderLabels([
            "Sale ID", "Motorcycle Model", "Chassis Number", "Credit Type",
            "Credit Amount", "Paid Amount", "Remaining", "Due Date", "Status"
        ])
        
        # Workable Column Resizing
        header = self.accounts_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setCascadingSectionResizes(True)
        
        self.accounts_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.accounts_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.accounts_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.accounts_table.itemClicked.connect(self._on_row_clicked)
        layout.addWidget(self.accounts_table)

    def _create_summary_card(self, title, val, color):
        card = QFrame()
        card.setStyleSheet(f"background-color: {color}; border-radius: 8px; color: white;")
        card.setFixedHeight(80)
        l = QVBoxLayout(card)
        l.setContentsMargins(10, 10, 10, 10)
        t = QLabel(title)
        t.setStyleSheet("font-size: 11px; border: none;")
        v = QLabel(val)
        v.setStyleSheet("font-size: 18px; font-weight: bold; border: none;")
        l.addWidget(t)
        l.addWidget(v)
        card.setProperty("val_label", v)
        return card

    def load_data(self):
        # Fetch Customer Details
        cust = credit_ledger_service.get_customer_details(self.customer_id)
        if cust:
            self.val_name.setText(cust['name'])
            self.val_phone.setText(cust['phone'])
            self.val_address.setText(cust['address'])

        # Fetch All Active Accounts
        accounts = credit_ledger_service.get_customer_active_finance_accounts(self.customer_id)
        # Note: We might also want to fetch CLOSED accounts for a full summary, but the requirement says "active" in some places and "all" in others.
        # Let's fetch both if possible or just use active for now as per dashboard context.
        
        # For simple/backward compatibility, also consider Old System data from BuyerLedger
        # In a real scenario, we'd query CreditSale and FinanceCreditSale tables.
        
        total_credit = 0.0
        total_paid = 0.0
        total_overdue = 0.0
        total_units = 0
        model_counts = {} # model_name -> count
        
        self.accounts_table.setRowCount(0)
        
        # Process Advanced Finance Accounts
        for acc in accounts:
            row = self.accounts_table.rowCount()
            self.accounts_table.insertRow(row)
            
            paid = acc.credit_price - acc.remaining_balance
            total_credit += acc.credit_price
            total_paid += paid
            total_units += 1
            
            # Count models from Advanced Finance
            m_name = acc.model.strip().upper() if acc.model else "UNKNOWN"
            model_counts[m_name] = model_counts.get(m_name, 0) + 1
            
            if acc.status == "OVERDUE":
                total_overdue += acc.remaining_balance

            items = [
                acc.sale_id, acc.model, acc.chassis_no, "Advanced Finance",
                f"{acc.credit_price:,.2f}", f"{paid:,.2f}", f"{acc.remaining_balance:,.2f}",
                acc.due_date.strftime('%d-%m-%Y'), acc.status
            ]
            
            for col, text in enumerate(items):
                item = QTableWidgetItem(str(text))
                if acc.status == "OVERDUE":
                    item.setForeground(Qt.GlobalColor.red)
                item.setData(Qt.ItemDataRole.UserRole, {"type": "ADVANCED", "id": acc.id})
                self.accounts_table.setItem(row, col, item)

        # Process Old System Data (Requirement 7)
        old_entries = credit_ledger_service.get_ledger(self.customer_id)
        if old_entries:
            # We treat the OLD system as a single running account for simplicity in the summary
            # We identify the latest balance
            latest_old = old_entries[-1]
            
            row = self.accounts_table.rowCount()
            self.accounts_table.insertRow(row)
            
            # Aggregate totals for cards
            old_total_debit = sum(e.debit for e in old_entries)
            old_total_credit = sum(e.credit for e in old_entries)
            
            # Count motorcycles in old system by counting 'SALE' reference entries
            # or entries with debit > 0 and reference_type="SALE"
            old_sale_entries = [e for e in old_entries if e.debit > 0 and e.reference_type == "SALE"]
            old_units = len(old_sale_entries)
            
            # Parse models from description if possible for old system
            # Example description: "Motorcycle Sale - CD70 - Chassis: HB472402"
            import re
            for e in old_sale_entries:
                desc = e.description or ""
                # Try to find model between "Sale - " and " - Chassis"
                model_match = re.search(r'Sale\s*-\s*([^-]+)\s*-', desc, re.IGNORECASE)
                if model_match:
                    m_name = model_match.group(1).strip().upper()
                else:
                    m_name = "OLD SYSTEM"
                model_counts[m_name] = model_counts.get(m_name, 0) + 1

            total_credit += old_total_debit
            total_paid += old_total_credit
            total_units += old_units
            
            items = [
                "OLD-SYSTEM", "Running Credit", "Multiple", "Old Running Credit",
                f"{old_total_debit:,.2f}", f"{old_total_credit:,.2f}", f"{latest_old.balance:,.2f}",
                "N/A", "ACTIVE" if latest_old.balance > 0 else "CLOSED"
            ]
            
            for col, text in enumerate(items):
                item = QTableWidgetItem(str(text))
                item.setData(Qt.ItemDataRole.UserRole, {"type": "OLD", "id": self.customer_id})
                self.accounts_table.setItem(row, col, item)

        # Update Summary Cards
        self.card_total_units.property("val_label").setText(str(total_units))
        self.card_total_credit.property("val_label").setText(f"Rs. {total_credit:,.2f}")
        self.card_total_paid.property("val_label").setText(f"Rs. {total_paid:,.2f}")
        self.card_balance.property("val_label").setText(f"Rs. {(total_credit - total_paid):,.2f}")
        self.card_overdue.property("val_label").setText(f"Rs. {total_overdue:,.2f}")

        # Update Model Summary Label
        if model_counts:
            summary_parts = [f"{m} = {count}" for m, count in sorted(model_counts.items())]
            self.model_summary_label.setText(f"Model Summary:  " + " | ".join(summary_parts))
        else:
            self.model_summary_label.setText("")

    def _on_row_clicked(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data: return
        
        # Show detailed ledger popup for this specific account
        detail_dlg = QDialog(self)
        detail_dlg.setWindowTitle(f"Ledger History - {self.accounts_table.item(item.row(), 0).text()}")
        detail_dlg.resize(800, 500)
        
        # Add maximize and minimize buttons to the dialog
        detail_dlg.setWindowFlags(detail_dlg.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint)
        
        layout = QVBoxLayout(detail_dlg)
        
        table = QTableWidget(0, 5)
        table.setHorizontalHeaderLabels(["Date", "Description", "Debit", "Credit", "Balance"])
        
        # Workable Column Resizing
        header = table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setCascadingSectionResizes(True)
        
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.setWordWrap(True)
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(table)
        
        if data['type'] == "ADVANCED":
            entries = credit_ledger_service.get_finance_sale_ledger(data['id'])
            for e in entries:
                row = table.rowCount()
                table.insertRow(row)
                table.setItem(row, 0, QTableWidgetItem(e.entry_date.strftime('%d-%m-%Y')))
                table.setItem(row, 1, QTableWidgetItem(e.description))
                table.setItem(row, 2, QTableWidgetItem(f"{e.debit:,.2f}"))
                table.setItem(row, 3, QTableWidgetItem(f"{e.credit:,.2f}"))
                table.setItem(row, 4, QTableWidgetItem(f"{e.balance:,.2f}"))
        
        elif data['type'] == "OLD":
            entries = credit_ledger_service.get_ledger(data['id'])
            for e in entries:
                row = table.rowCount()
                table.insertRow(row)
                table.setItem(row, 0, QTableWidgetItem(e.date.strftime('%d-%m-%Y')))
                table.setItem(row, 1, QTableWidgetItem(e.description))
                table.setItem(row, 2, QTableWidgetItem(f"{e.debit:,.2f}"))
                table.setItem(row, 3, QTableWidgetItem(f"{e.credit:,.2f}"))
                table.setItem(row, 4, QTableWidgetItem(f"{e.balance:,.2f}"))
        
        detail_dlg.exec()

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

class ModernStatCard(QFrame):
    """Modern financial summary card with gradients and shadows."""
    def __init__(self, title, val, color_start, color_end, icon="💰", parent=None):
        super().__init__(parent)
        self.setFixedSize(280, 110)
        self.setObjectName("statCard")
        self.setStyleSheet(f"""
            #statCard {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {color_start}, stop:1 {color_end});
                border-radius: 15px;
                color: white;
            }}
            #statCard:hover {{
                border: 2px solid white;
            }}
        """)
        
        # Shadow effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(Qt.GlobalColor.gray)
        self.setGraphicsEffect(shadow)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        
        header_layout = QHBoxLayout()
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-size: 13px; font-weight: 500; opacity: 0.9; border: none; background: transparent;")
        
        self.icon_label = QLabel(icon)
        self.icon_label.setStyleSheet("font-size: 18px; border: none; background: transparent;")
        
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.icon_label)
        layout.addLayout(header_layout)
        
        self.val_label = QLabel(val)
        self.val_label.setStyleSheet("font-size: 22px; font-weight: bold; border: none; background: transparent;")
        layout.addWidget(self.val_label)
        
        self.trend_label = QLabel("Active Records")
        self.trend_label.setStyleSheet("font-size: 10px; opacity: 0.8; border: none; background: transparent;")
        layout.addWidget(self.trend_label)

    def update_value(self, val):
        self.val_label.setText(val)

class CreditLedgerSystemPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Credit Sales & Ledger System")
        self.selected_sale_buyer_id = None
        self.selected_pay_buyer_id = None
        self.selected_ledger_buyer_id = None
        self.current_customer_details = None
        self.print_service = PrintServiceV2()
        self._apply_dashboard_styles()
        self.setup_ui()
        self.refresh_dashboard()

    def _apply_dashboard_styles(self):
        self.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #dfe6e9; background: white; border-radius: 5px; }
            QTabBar::tab { background: #f1f2f6; padding: 10px 20px; border-top-left-radius: 5px; border-top-right-radius: 5px; margin-right: 2px; }
            QTabBar::tab:selected { background: white; border-bottom-color: white; font-weight: bold; }
            
            QTableWidget {
                border: none;
                background-color: white;
                alternate-background-color: #f9f9f9;
                selection-background-color: #e3f2fd;
                selection-color: #1976d2;
                gridline-color: #f1f1f1;
            }
            QHeaderView::section {
                background-color: #f8f9fa;
                padding: 10px;
                border: none;
                border-bottom: 2px solid #dfe6e9;
                font-weight: bold;
                color: #2d3436;
            }
            QPushButton#actionBtn {
                background-color: white;
                border: 1px solid #dfe6e9;
                border-radius: 8px;
                padding: 8px 15px;
                font-weight: 500;
            }
            QPushButton#actionBtn:hover {
                background-color: #f1f2f6;
                border-color: #b2bec3;
            }
            QLineEdit#searchBar {
                padding: 8px 15px;
                border: 1px solid #dfe6e9;
                border-radius: 10px;
                background: white;
            }
            QLineEdit#searchBar:focus {
                border: 1px solid #3498db;
            }
        """)

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
        
        # 3. Installment Recovery (Payment Entry)
        self.payment_tab = QWidget()
        self._setup_payment_tab()
        self.tabs.addTab(self.payment_tab, "Installment Recovery")

        # 4. Customer Ledger (Ledger Statement)
        self.ledger_tab = QWidget()
        self._setup_ledger_tab()
        self.tabs.addTab(self.ledger_tab, "Customer Ledger")

        # 5. Active Accounts
        self.active_accounts_tab = QWidget()
        self._setup_active_accounts_tab()
        self.tabs.addTab(self.active_accounts_tab, "Active Accounts")

        # 6. Due Accounts
        self.due_accounts_tab = QWidget()
        self._setup_due_accounts_tab()
        self.tabs.addTab(self.due_accounts_tab, "Due Accounts")

        # Auto-refresh tabs
        self.tabs.currentChanged.connect(self._on_tab_changed)
        
        main_layout.addWidget(self.tabs)

    def _on_tab_changed(self, index):
        if index == 0:
            self.refresh_dashboard()
        elif index == 4:
            self.load_active_accounts()
        elif index == 5:
            self.load_due_accounts()

    # --- TAB: DASHBOARD ---
    def _setup_dashboard_tab(self):
        layout = QVBoxLayout(self.dashboard_tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        # 1. Quick Actions Bar
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(10)
        
        def create_action_btn(text, icon_emoji, callback):
            btn = QPushButton(f"{icon_emoji} {text}")
            btn.setObjectName("actionBtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(callback)
            return btn

        self.btn_new_sale = create_action_btn("Add Credit Sale", "➕", lambda: self.tabs.setCurrentIndex(1))
        self.btn_recovery = create_action_btn("Recover Installment", "💰", lambda: self.tabs.setCurrentIndex(2))
        self.btn_ledger = create_action_btn("View Ledger", "📖", lambda: self.tabs.setCurrentIndex(3))
        self.btn_refresh = create_action_btn("Refresh", "🔄", self.refresh_dashboard)
        
        actions_layout.addWidget(self.btn_new_sale)
        actions_layout.addWidget(self.btn_recovery)
        actions_layout.addWidget(self.btn_ledger)
        actions_layout.addStretch()
        actions_layout.addWidget(self.btn_refresh)
        layout.addLayout(actions_layout)

        # 2. Stats Cards
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(15)
        self.stat_sales = ModernStatCard("Total Credit Sales", "Rs. 0.00", "#3498db", "#2980b9", "📈")
        self.stat_received = ModernStatCard("Total Received", "Rs. 0.00", "#2ecc71", "#27ae60", "📥")
        self.stat_outstanding = ModernStatCard("Total Outstanding", "Rs. 0.00", "#e74c3c", "#c0392b", "💸")
        
        stats_layout.addWidget(self.stat_sales)
        stats_layout.addWidget(self.stat_received)
        stats_layout.addWidget(self.stat_outstanding)
        layout.addLayout(stats_layout)
        
        # 3. Search & Filter Bar
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(10)
        
        self.db_search_input = QLineEdit()
        self.db_search_input.setObjectName("searchBar")
        self.db_search_input.setPlaceholderText("🔍 Search customer by name or chassis...")
        self.db_search_input.setFixedWidth(350)
        self.db_search_input.textChanged.connect(self._filter_dashboard_table)
        
        self.db_status_filter = QComboBox()
        self.db_status_filter.addItems(["All Accounts", "Active Only", "Overdue Only", "Cleared Accounts"])
        self.db_status_filter.setFixedWidth(150)
        self.db_status_filter.currentIndexChanged.connect(self._filter_dashboard_table)
        
        filter_layout.addWidget(self.db_search_input)
        filter_layout.addWidget(self.db_status_filter)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # 4. Main Content Area (Table + Recent Payments)
        content_layout = QHBoxLayout()
        
        # Left side: Table
        table_container = QFrame()
        table_container.setStyleSheet("background: white; border-radius: 10px; border: 1px solid #dfe6e9;")
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)

        self.buyer_table = QTableWidget(0, 6)
        self.buyer_table.setHorizontalHeaderLabels([
            "S.No", "Customer Name", "Outstanding Balance", "Account Status", "Total Units", "Last Payment"
        ])
        
        self.buyer_table.setShowGrid(False)
        self.buyer_table.setAlternatingRowColors(True)
        self.buyer_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.buyer_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.buyer_table.verticalHeader().setVisible(False)
        
        # Workable Column Resizing
        header = self.buyer_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setCascadingSectionResizes(True)
        
        self.buyer_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.buyer_table.itemClicked.connect(self._on_buyer_clicked)
        
        table_layout.addWidget(self.buyer_table)
        content_layout.addWidget(table_container, 3) # 3 parts width

        # Right side: Recent Activity
        activity_panel = QFrame()
        activity_panel.setFixedWidth(300)
        activity_panel.setStyleSheet("background: #f8f9fa; border-radius: 10px; border: 1px solid #dfe6e9;")
        activity_layout = QVBoxLayout(activity_panel)
        
        activity_title = QLabel("🕒 Recent Payments")
        activity_title.setStyleSheet("font-weight: bold; font-size: 14px; color: #2d3436; border: none;")
        activity_layout.addWidget(activity_title)
        
        self.recent_payments_list = QTableWidget(0, 2)
        self.recent_payments_list.setHorizontalHeaderLabels(["Customer", "Amount"])
        
        # Workable Column Resizing
        rh = self.recent_payments_list.horizontalHeader()
        rh.setStretchLastSection(False)
        rh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        
        self.recent_payments_list.verticalHeader().setVisible(False)
        self.recent_payments_list.setShowGrid(False)
        self.recent_payments_list.setStyleSheet("background: transparent; border: none;")
        self.recent_payments_list.itemClicked.connect(self._on_recent_payment_clicked)
        activity_layout.addWidget(self.recent_payments_list)
        
        content_layout.addWidget(activity_panel, 1) # 1 part width
        
        layout.addLayout(content_layout)

    def _filter_dashboard_table(self):
        """Dynamic client-side filtering of the dashboard table."""
        search_text = self.db_search_input.text().lower()
        status_filter = self.db_status_filter.currentText()
        
        for row in range(self.buyer_table.rowCount()):
            name = self.buyer_table.item(row, 1).text().lower()
            balance_str = self.buyer_table.item(row, 2).text().replace(",", "")
            status = self.buyer_table.item(row, 3).text()
            
            show_row = True
            
            # Search filter
            if search_text and search_text not in name:
                show_row = False
                
            # Status filter
            if show_row:
                if status_filter == "Active Only" and balance_str == "0.00":
                    show_row = False
                elif status_filter == "Overdue Only" and status != "OVERDUE":
                    show_row = False
                elif status_filter == "Cleared Accounts" and balance_str != "0.00":
                    show_row = False
                    
            self.buyer_table.setRowHidden(row, not show_row)

    def refresh_dashboard(self):
        stats = credit_ledger_service.get_dashboard_stats()
        # Update Dashboard Stats
        self.stat_sales.update_value(f"Rs. {stats['total_sales']:,.2f}")
        self.stat_received.update_value(f"Rs. {stats['total_received']:,.2f}")
        self.stat_outstanding.update_value(f"Rs. {stats['total_outstanding']:,.2f}")
        
        # Populate Buyer Balances Table
        self.buyer_table.setRowCount(0)
        
        # Connect click event
        try:
            self.buyer_table.itemClicked.disconnect()
        except: pass
        self.buyer_table.itemClicked.connect(self._on_buyer_clicked)

        # 1. Populate Main Table
        for i, b in enumerate(stats['buyer_balances'], 1):
            row = self.buyer_table.rowCount()
            self.buyer_table.insertRow(row)
            
            sn_item = QTableWidgetItem(str(i))
            sn_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.buyer_table.setItem(row, 0, sn_item)
            
            name_item = QTableWidgetItem(b['name'])
            name_item.setData(Qt.ItemDataRole.UserRole, b['id'])
            name_item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            self.buyer_table.setItem(row, 1, name_item)
            
            bal_item = QTableWidgetItem(f"{b['balance']:,.2f}")
            bal_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if b['balance'] > 500000:
                bal_item.setForeground(Qt.GlobalColor.red)
            self.buyer_table.setItem(row, 2, bal_item)
            
            status = "ACTIVE"
            if b['balance'] == 0:
                status = "CLEARED"
            
            # Check for overdue (this would ideally come from service)
            # For UI logic, let's assume if balance > 0 and no payment in 60 days, it might be overdue
            # but better to rely on service. Let's just use ACTIVE/CLEARED for now.
            
            status_item = QTableWidgetItem(status)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if status == "CLEARED":
                status_item.setForeground(Qt.GlobalColor.darkGreen)
            elif status == "ACTIVE":
                status_item.setForeground(Qt.GlobalColor.blue)
            self.buyer_table.setItem(row, 3, status_item)

            units = b.get('total_units', 0)
            units_item = QTableWidgetItem(str(units))
            units_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.buyer_table.setItem(row, 4, units_item)

            last_pay = b.get('last_payment_date', 'N/A')
            last_pay_item = QTableWidgetItem(str(last_pay))
            last_pay_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.buyer_table.setItem(row, 5, last_pay_item)
            
            self.buyer_table.setRowHeight(row, 45)

        # 2. Populate Recent Payments (Top 10)
        self.recent_payments_list.setRowCount(0)
        # We can derive this from consolidated data or fetch separately. 
        # For now, let's show buyers who recently paid.
        recent_payers = [b for b in stats['buyer_balances'] if b['last_payment_date'] != 'N/A']
        # Sort by date descending (simple string sort for YYYY-MM-DD or parse)
        # Assuming format is DD-MM-YYYY as set in service
        recent_payers.sort(key=lambda x: dt.datetime.strptime(x['last_payment_date'], '%d-%m-%Y'), reverse=True)
        
        for p in recent_payers[:10]:
            row = self.recent_payments_list.rowCount()
            self.recent_payments_list.insertRow(row)
            
            n = QTableWidgetItem(p['name'])
            n.setData(Qt.ItemDataRole.UserRole, p['id'])
            n.setFont(QFont("Segoe UI", 9))
            
            # We don't have the exact 'last amount' in this stat call, 
            # but we can show the date instead or update service later.
            # Let's show the date for now as it's useful.
            d = QTableWidgetItem(p['last_payment_date'])
            d.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            d.setForeground(Qt.GlobalColor.gray)
            
            self.recent_payments_list.setItem(row, 0, n)
            self.recent_payments_list.setItem(row, 1, d)
            self.recent_payments_list.setRowHeight(row, 35)

    def _on_buyer_clicked(self, item):
        """Open the professional Financial Summary window (Requirement 1)."""
        # Get buyer ID from row 1 (Name column)
        buyer_id = self.buyer_table.item(item.row(), 1).data(Qt.ItemDataRole.UserRole)
        if buyer_id:
            dlg = CustomerFinancialSummaryDialog(buyer_id, self)
            dlg.exec()

    def _on_recent_payment_clicked(self, item):
        """Open Financial Summary from recent payments list."""
        buyer_id = self.recent_payments_list.item(item.row(), 0).data(Qt.ItemDataRole.UserRole)
        if buyer_id:
            dlg = CustomerFinancialSummaryDialog(buyer_id, self)
            dlg.exec()

    # --- TAB: SALE ENTRY ---
    def _setup_sale_tab(self):
        layout = QVBoxLayout(self.sale_tab)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        grid = QGridLayout(container)
        
        # Credit Type Selection (Requirement)
        grid.addWidget(QLabel("Credit Method:"), 0, 0)
        type_layout = QHBoxLayout()
        self.radio_old = QRadioButton("Old Running Credit")
        self.radio_advanced = QRadioButton("Advanced Separate Finance")
        self.radio_old.setChecked(True)
        self.radio_group = QButtonGroup()
        self.radio_group.addButton(self.radio_old)
        self.radio_group.addButton(self.radio_advanced)
        type_layout.addWidget(self.radio_old)
        type_layout.addWidget(self.radio_advanced)
        grid.addLayout(type_layout, 0, 1, 1, 3)
        self.radio_group.buttonClicked.connect(self._on_credit_type_changed)
        
        # Header Info
        grid.addWidget(QLabel("Buyer Name:"), 1, 0)
        self.sale_buyer_input = SharedLineEdit()
        self.sale_buyer_input.setPlaceholderText("Search by Name, Phone or CNIC...")
        self.sale_buyer_completer = BuyerCompleter(self.sale_buyer_input)
        self.sale_buyer_input.setCompleter(self.sale_buyer_completer)
        self.sale_buyer_input.textChanged.connect(self._update_buyer_suggestions)
        self.sale_buyer_completer.activated[QModelIndex].connect(self._on_buyer_selected_index)
        self.sale_buyer_input.editingFinished.connect(self._on_buyer_input_finished)
        grid.addWidget(self.sale_buyer_input, 1, 1)
        
        grid.addWidget(QLabel("Buyer Type:"), 1, 2)
        self.buyer_type_combo = QComboBox()
        self.buyer_type_combo.addItems(["Customer", "Dealer"])
        self.buyer_type_combo.setEnabled(False) # Read-only
        self.buyer_type_combo.setStyleSheet("background-color: #f0f0f0; color: #333;")
        grid.addWidget(self.buyer_type_combo, 1, 3)
        
        grid.addWidget(QLabel("Sale Date:"), 2, 0)
        self.sale_date_edit = QDateEdit(QDate.currentDate())
        self.sale_date_edit.setCalendarPopup(True)
        self.sale_date_edit.dateChanged.connect(self._calculate_sale_totals)
        grid.addWidget(self.sale_date_edit, 2, 1)
        
        grid.addWidget(QLabel("Due Date (Advanced):"), 2, 2)
        self.sale_due_date = QDateEdit(QDate.currentDate().addMonths(1))
        self.sale_due_date.setCalendarPopup(True)
        self.sale_due_date.setEnabled(False)
        grid.addWidget(self.sale_due_date, 2, 3)
        
        # Duration and Installment in one row
        grid.addWidget(QLabel("Duration:"), 3, 0)
        duration_layout = QVBoxLayout()
        self.sale_duration = QLineEdit("0,0")
        self.sale_duration.setPlaceholderText("Months,Days (e.g. 1,15)")
        self.sale_duration.setToolTip("Format: Months,Days. Example: '1,15' for 1 Month 15 Days")
        
        # Add a validator to only allow numbers and one comma
        duration_regex = QRegularExpression(r"^[0-9]*,?[0-9]*$")
        validator = QRegularExpressionValidator(duration_regex, self.sale_duration)
        self.sale_duration.setValidator(validator)
        
        self.sale_duration.textChanged.connect(self._calculate_sale_totals)
        duration_layout.addWidget(self.sale_duration)
        
        self.duration_hint = QLabel("0 Months")
        self.duration_hint.setStyleSheet("color: #3498db; font-weight: 500; margin-top: -5px;")
        duration_layout.addWidget(self.duration_hint)
        grid.addLayout(duration_layout, 3, 1)

        grid.addWidget(QLabel("Installment:"), 3, 2)
        self.installment_amount_edit = QLineEdit("0.00")
        self.installment_amount_edit.setReadOnly(True)
        self.installment_amount_edit.setStyleSheet("background-color: #f8f9fa; font-weight: bold; color: #2ecc71; font-size: 14px;")
        grid.addWidget(self.installment_amount_edit, 3, 3)
        
        # Items Table
        self.items_group = QGroupBox("Motorcycle Details")
        self.items_group.setStyleSheet("""
            QGroupBox { 
                font-weight: bold; 
                border: 1px solid #dfe6e9; 
                border-radius: 8px; 
                margin-top: 20px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        items_layout = QVBoxLayout(self.items_group)
        self.sale_items_table = QTableWidget(0, 7)
        self.sale_items_table.setHorizontalHeaderLabels(["Chassis no", "Model", "Color", "Price", "Credit Price", "Description", "Action"])
        
        # Workable Table Styling for Items
        self.sale_items_table.setShowGrid(False)
        self.sale_items_table.setAlternatingRowColors(True)
        self.sale_items_table.verticalHeader().setVisible(False)
        self.sale_items_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.sale_items_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.sale_items_table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #dfe6e9;
                border-radius: 8px;
                background-color: white;
                alternate-background-color: #fbfcfc;
            }
            QHeaderView::section {
                background-color: #f1f2f6;
                padding: 10px;
                border: none;
                font-weight: bold;
                color: #2d3436;
                border-bottom: 1px solid #dfe6e9;
            }
        """)
        
        header = self.sale_items_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setCascadingSectionResizes(True)
        items_layout.addWidget(self.sale_items_table)
        
        self.add_item_btn = QPushButton("➕ Add Another Motorcycle")
        self.add_item_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #2471a3;
            }
        """)
        self.add_item_btn.clicked.connect(self._add_sale_item_row)
        items_layout.addWidget(self.add_item_btn)
        grid.addWidget(self.items_group, 4, 0, 1, 4)
        
        # Totals Section
        totals_frame = QFrame()
        totals_frame.setStyleSheet("""
            QFrame {
                background: white;
                border: 1px solid #dfe6e9;
                border-radius: 12px;
            }
            QLabel { border: none; background: transparent; }
        """)
        totals_layout = QVBoxLayout(totals_frame)
        totals_layout.setContentsMargins(20, 15, 20, 15)
        totals_layout.setSpacing(12)
        
        # Total Credit Row
        credit_layout = QHBoxLayout()
        credit_lbl = QLabel("Total Credit Amount:")
        credit_lbl.setStyleSheet("color: #636e72; font-weight: 500; font-size: 13px;")
        self.total_credit_label = QLabel("Rs. 0.00")
        self.total_credit_label.setStyleSheet("font-weight: bold; font-size: 18px; color: #2d3436;")
        credit_layout.addWidget(credit_lbl)
        credit_layout.addStretch()
        credit_layout.addWidget(self.total_credit_label)
        totals_layout.addLayout(credit_layout)
        
        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #f1f2f6; min-height: 1px; max-height: 1px;")
        totals_layout.addWidget(line)

        # Advance Row
        advance_layout = QHBoxLayout()
        advance_lbl = QLabel("Advance / Down Payment:")
        advance_lbl.setStyleSheet("color: #636e72; font-weight: 500; font-size: 13px;")
        
        self.sale_advance_mode = QComboBox()
        self.sale_advance_mode.addItems(["Cash", "Bank Transfer", "Credit Card", "Cheque", "Online/Other"])
        self.sale_advance_mode.setFixedWidth(120)
        self.sale_advance_mode.setStyleSheet("font-size: 11px;")
        
        self.sale_advance = QLineEdit("0")
        self.sale_advance.setFixedWidth(120)
        self.sale_advance.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.sale_advance.setStyleSheet("""
            QLineEdit {
                padding: 6px 10px;
                border: 1px solid #dfe6e9;
                border-radius: 6px;
                background: #f8f9fa;
                font-weight: bold;
                font-size: 14px;
            }
            QLineEdit:focus { border: 1px solid #3498db; background: white; }
        """)
        self.sale_advance.textChanged.connect(self._calculate_sale_totals)
        advance_layout.addWidget(advance_lbl)
        advance_layout.addStretch()
        advance_layout.addWidget(self.sale_advance_mode)
        advance_layout.addWidget(self.sale_advance)
        totals_layout.addLayout(advance_layout)
        
        # Remaining Row
        remaining_layout = QHBoxLayout()
        remaining_lbl = QLabel("Net Remaining Balance:")
        remaining_lbl.setStyleSheet("color: #e74c3c; font-weight: bold; font-size: 13px;")
        self.remaining_label = QLabel("Rs. 0.00")
        self.remaining_label.setStyleSheet("font-weight: bold; color: #e74c3c; font-size: 18px;")
        remaining_layout.addWidget(remaining_lbl)
        remaining_layout.addStretch()
        remaining_layout.addWidget(self.remaining_label)
        totals_layout.addLayout(remaining_layout)
        
        grid.addWidget(totals_frame, 5, 2, 1, 2)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 20, 0, 0)
        self.process_btn = QPushButton("Save Credit Sale")
        self.process_btn.setFixedWidth(200)
        self.process_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                padding: 12px;
                border-radius: 8px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #219150; }
        """)
        self.process_btn.clicked.connect(self.process_sale)
        btn_layout.addWidget(self.process_btn)

        self.clear_btn = QPushButton("Clear Form")
        self.clear_btn.setFixedWidth(120)
        self.clear_btn.setStyleSheet("padding: 12px; border-radius: 8px;")
        self.clear_btn.clicked.connect(self._clear_sale_form)
        btn_layout.addWidget(self.clear_btn)

        self.print_btn = QPushButton("Print Agreement")
        self.print_btn.setFixedWidth(150)
        self.print_btn.setEnabled(False)
        self.print_btn.setStyleSheet("padding: 12px; border-radius: 8px;")
        btn_layout.addWidget(self.print_btn)
        btn_layout.addStretch()
        grid.addLayout(btn_layout, 6, 0, 1, 4)
        
        scroll.setWidget(container)
        layout.addWidget(scroll)

        QTimer.singleShot(100, self._add_sale_item_row)

    def _on_credit_type_changed(self, button):
        is_advanced = button.text() == "Advanced Separate Finance"
        self.sale_due_date.setEnabled(is_advanced)
        # Advanced Finance is usually 1 motorcycle per Sale ID
        if is_advanced and self.sale_items_table.rowCount() > 1:
            QMessageBox.information(self, "System Info", "Advanced Separate Finance handles each motorcycle as an independent account.")
            while self.sale_items_table.rowCount() > 1:
                self.sale_items_table.removeRow(1)
        
        self.add_item_btn.setEnabled(not is_advanced)
        self._calculate_sale_totals()

    def _clear_sale_form(self):
        self.sale_buyer_input.clear()
        self.selected_sale_buyer_id = None
        self.sale_duration.setText("0,0")
        self.sale_advance.setText("0")
        self.sale_items_table.setRowCount(0)
        self._add_sale_item_row()
        self.radio_old.setChecked(True)
        self._on_credit_type_changed(self.radio_old)
        self._calculate_sale_totals()
        self._update_table_height()

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
        self.sale_items_table.setRowHeight(row, 40)
        
        # Define a common style for input fields inside table to make them look "integrated"
        cell_style = """
            QLineEdit {
                border: 1px solid transparent;
                background: transparent;
                padding: 5px;
            }
            QLineEdit:focus {
                border-bottom: 2px solid #3498db;
                background: #f1f9ff;
            }
        """
        
        chassis_edit = SharedLineEdit()
        chassis_edit.setPlaceholderText("Chassis Number")
        chassis_edit.setStyleSheet(cell_style)
        
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
        model_edit.setStyleSheet(cell_style)
        model_edit.installEventFilter(self)
        self.sale_items_table.setCellWidget(row, 1, model_edit)

        color_edit = SharedLineEdit()
        color_edit.setPlaceholderText("Color")
        color_edit.setStyleSheet(cell_style)
        color_edit.installEventFilter(self)
        self.sale_items_table.setCellWidget(row, 2, color_edit)

        cash_price_edit = QLineEdit("0.00")
        cash_price_edit.setReadOnly(True)
        cash_price_edit.setStyleSheet("background-color: #f8f9fa; color: #7f8c8d; border: none; padding: 5px;")
        cash_price_edit.installEventFilter(self)
        self.sale_items_table.setCellWidget(row, 3, cash_price_edit)
        
        price_edit = QLineEdit("0.00")
        price_edit.setStyleSheet(cell_style)
        price_edit.textChanged.connect(self._calculate_sale_totals)
        price_edit.installEventFilter(self)
        self.sale_items_table.setCellWidget(row, 4, price_edit)

        desc_edit = SharedLineEdit() 
        desc_edit.setPlaceholderText("Description / Item Details")
        desc_edit.setStyleSheet(cell_style)
        desc_edit.installEventFilter(self)
        self.sale_items_table.setCellWidget(row, 5, desc_edit)
        
        del_btn = QPushButton("🗑️")
        del_btn.setToolTip("Delete this row")
        del_btn.setFixedWidth(40)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: #e74c3c;
                font-size: 16px;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #fff5f5;
                border-radius: 4px;
            }
        """)
        del_btn.clicked.connect(lambda: self._remove_sale_item_row(row))
        self.sale_items_table.setCellWidget(row, 6, del_btn)

        # Focus on chassis field
        chassis_edit.setFocus()
        self._update_table_height()

    def _remove_sale_item_row(self, row_idx):
        # We need to find the actual row index because rows might have shifted
        for r in range(self.sale_items_table.rowCount()):
            if self.sale_items_table.cellWidget(r, 6) == self.sender():
                self.sale_items_table.removeRow(r)
                break
        self._calculate_sale_totals()
        self._update_table_height()

    def eventFilter(self, source, event):
        """Handle Enter and Tab for table navigation."""
        if event.type() == QEvent.Type.KeyPress:
            # Handle Enter key
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                # Find which row this widget belongs to
                for r in range(self.sale_items_table.rowCount()):
                    for c in (0, 1, 2, 4, 5): # Chassis, Model, Color, Credit Price, Description
                        if self.sale_items_table.cellWidget(r, c) == source:
                            if r == self.sale_items_table.rowCount() - 1:
                                chassis_widget = self.sale_items_table.cellWidget(r, 0)
                                if chassis_widget and chassis_widget.text().strip():
                                    self._add_sale_item_row()
                                    return True
                            break
            
            # Handle Tab key in the last data column (Description)
            if event.key() == Qt.Key.Key_Tab:
                for r in range(self.sale_items_table.rowCount()):
                    if self.sale_items_table.cellWidget(r, 5) == source:
                        if r == self.sale_items_table.rowCount() - 1:
                            chassis_widget = self.sale_items_table.cellWidget(r, 0)
                            if chassis_widget and chassis_widget.text().strip():
                                self._add_sale_item_row()
                                return True
                            
        return super().eventFilter(source, event)

    def _update_table_height(self):
        """Dynamically resize table height based on number of rows."""
        row_count = self.sale_items_table.rowCount()
        header_height = self.sale_items_table.horizontalHeader().height() or 40
        row_height = 40 # Constant as defined in _add_sale_item_row
        
        # Calculate total height (header + rows + padding)
        total_height = header_height + (row_count * row_height) + 10
        
        # Limit the height to a reasonable range (e.g., 150 to 500 px)
        final_height = max(150, min(total_height, 500))
        self.sale_items_table.setFixedHeight(final_height)

    def _calculate_sale_totals(self):
        total_credit = 0.0
        for r in range(self.sale_items_table.rowCount()):
            try:
                total_credit += float(self.sale_items_table.cellWidget(r, 4).text() or 0)
            except: pass
        
        self.total_credit_label.setText(f"Rs. {total_credit:,.2f}")
        try:
            advance = float(self.sale_advance.text() or 0)
            remaining = total_credit - advance
            self.remaining_label.setText(f"Rs. {remaining:,.2f}")
            
            # Parse duration and update UI
            try:
                input_str = self.sale_duration.text().strip()
                months, days = parse_duration_string(input_str)
                self.duration_hint.setText(format_duration(months, days))
                self.duration_hint.setStyleSheet("color: #3498db; font-weight: 500; margin-top: -5px;")
                
                # --- TWO-STEP DUE DATE CALCULATION ---
                sale_date = self.sale_date_edit.date().toPyDate()
                
                # STEP 1: Add Months first
                temp_date = add_months(sale_date, months)
                
                # STEP 2: Add Days after month calculation
                final_due_date = temp_date + dt.timedelta(days=days)
                
                # Update UI
                self.sale_due_date.setDate(QDate(final_due_date.year, final_due_date.month, final_due_date.day))

                total_days = calculate_total_days(months, days)
                
                # Installment calculation for Advanced Finance
                if self.radio_advanced.isChecked():
                    if total_days > 0:
                        effective_months = total_days / 30.0
                        inst = remaining / effective_months
                        self.installment_amount_edit.setText(f"Rs. {inst:,.2f}")
                    else:
                        self.installment_amount_edit.setText("Rs. 0.00")
                else:
                    self.installment_amount_edit.setText("Rs. 0.00")
            except ValueError as ve:
                self.duration_hint.setText(str(ve))
                self.duration_hint.setStyleSheet("color: #e74c3c; font-size: 10px; margin-top: -5px;")
                self.installment_amount_edit.setText("Invalid Duration")
        except Exception as e:
            logger.error(f"Error calculating totals: {e}")

    def process_sale(self):
        buyer_name = self.sale_buyer_input.text().strip()
        if not buyer_name or not self.selected_sale_buyer_id:
            QMessageBox.warning(self, "Validation Error", "Please select a valid buyer from suggestions.")
            return

        is_advanced = self.radio_advanced.isChecked()
        
        items_data = []
        total_credit = 0.0
        
        for r in range(self.sale_items_table.rowCount()):
            chassis = self.sale_items_table.cellWidget(r, 0).text().strip()
            if not chassis: continue
            
            try:
                cash_p = float(self.sale_items_table.cellWidget(r, 3).text() or 0)
                credit_p = float(self.sale_items_table.cellWidget(r, 4).text() or 0)
                items_data.append({
                    "chassis_number": chassis,
                    "model": self.sale_items_table.cellWidget(r, 1).text().strip(),
                    "color": self.sale_items_table.cellWidget(r, 2).text().strip(),
                    "description": self.sale_items_table.cellWidget(r, 5).text().strip(),
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
            
            # Parse duration components
            try:
                duration_m, duration_d = parse_duration_string(self.sale_duration.text())
            except ValueError as ve:
                QMessageBox.warning(self, "Validation Error", str(ve))
                return

            if is_advanced:
                # Advanced Separate Finance Logic
                item = items_data[0]
                
                # For installment calculation
                total_days = calculate_total_days(duration_m, duration_d)
                effective_months = total_days / 30.0 if total_days > 0 else 0
                
                sale_data = {
                    "customer_id": self.selected_sale_buyer_id,
                    "customer_name": buyer_name,
                    "chassis_no": item['chassis_number'],
                    "model": item['model'],
                    "cash_price": item['cash_price'],
                    "credit_price": item['credit_price'],
                    "down_payment": advance,
                    "down_payment_method": self.sale_advance_mode.currentText(),
                    "duration_months": duration_m,
                    "duration_days": duration_d,
                    "installment_amount": (item['credit_price'] - advance) / effective_months if effective_months > 0 else 0,
                    "sale_date": self.sale_date_edit.date().toPyDate(),
                    "due_date": self.sale_due_date.date().toPyDate(),
                    "remaining_balance": item['credit_price'] - advance,
                    "status": "ACTIVE",
                    "notes": item['description']
                }
                sale = credit_ledger_service.create_finance_sale(sale_data)
                QMessageBox.information(self, "Success", f"Advanced Finance account {sale.sale_id} created successfully.")
                self.print_btn.setEnabled(True)
            else:
                # Old Running Credit System Logic
                sale_data = {
                    "buyer_id": self.selected_sale_buyer_id,
                    "buyer_type": self.buyer_type_combo.currentText(),
                    "sale_date": self.sale_date_edit.date().toPyDate(),
                    "duration_months": duration_m,
                    "duration_days": duration_d,
                    "total_credit_price": total_credit,
                    "advance_payment": advance,
                    "advance_payment_mode": self.sale_advance_mode.currentText(),
                    "remaining_amount": total_credit - advance
                }
                credit_ledger_service.create_credit_sale(sale_data, items_data)
                QMessageBox.information(self, "Success", "Old credit sale processed and running balance updated.")

            self.refresh_dashboard()
            self._clear_sale_form()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # --- TAB: INSTALLMENT RECOVERY ---
    def _setup_payment_tab(self):
        layout = QVBoxLayout(self.payment_tab)
        layout.setSpacing(15)
        
        # 1. Top Section: Search and Core Form (Horizontal)
        top_hbox = QHBoxLayout()
        
        # Left Side: Recovery Form
        self.recovery_form_group = QGroupBox("Payment Details")
        form_layout = QGridLayout(self.recovery_form_group)
        form_layout.setVerticalSpacing(12)
        
        form_layout.addWidget(QLabel("Buyer Name:"), 0, 0)
        self.pay_buyer_input = SharedLineEdit()
        self.pay_buyer_input.setPlaceholderText("Search by Name, Phone or CNIC...")
        self.pay_buyer_completer = BuyerCompleter(self.pay_buyer_input)
        self.pay_buyer_input.setCompleter(self.pay_buyer_completer)
        self.pay_buyer_input.textChanged.connect(self._update_pay_buyer_suggestions)
        self.pay_buyer_completer.activated[QModelIndex].connect(self._on_pay_buyer_selected_index)
        form_layout.addWidget(self.pay_buyer_input, 0, 1)
        
        form_layout.addWidget(QLabel("Finance Account:"), 1, 0)
        self.pay_account_combo = QComboBox()
        self.pay_account_combo.setMinimumWidth(400)
        self.pay_account_combo.addItem("--- OLD RUNNING CREDIT ---", None)
        self.pay_account_combo.currentIndexChanged.connect(self._on_pay_account_changed)
        form_layout.addWidget(self.pay_account_combo, 1, 1)

        form_layout.addWidget(QLabel("Payment Amount:"), 2, 0)
        self.pay_amount = QLineEdit("0.00")
        self.pay_amount.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.pay_amount.textChanged.connect(self._calculate_net_payment)
        form_layout.addWidget(self.pay_amount, 2, 1)
        
        form_layout.addWidget(QLabel("Penalty (Late):"), 3, 0)
        self.pay_penalty = QLineEdit("0.00")
        self.pay_penalty.textChanged.connect(self._calculate_net_payment)
        form_layout.addWidget(self.pay_penalty, 3, 1)
        
        form_layout.addWidget(QLabel("Discount (Early):"), 4, 0)
        self.pay_discount = QLineEdit("0.00")
        self.pay_discount.textChanged.connect(self._calculate_net_payment)
        form_layout.addWidget(self.pay_discount, 4, 1)
        
        form_layout.addWidget(QLabel("Net Received:"), 5, 0)
        self.pay_net_received = QLineEdit("0.00")
        self.pay_net_received.setReadOnly(True)
        self.pay_net_received.setStyleSheet("background-color: #f1f2f6; font-weight: bold; color: #2ecc71; font-size: 16px;")
        form_layout.addWidget(self.pay_net_received, 5, 1)
        
        form_layout.addWidget(QLabel("Date:"), 6, 0)
        self.pay_date = QDateEdit(QDate.currentDate())
        self.pay_date.setCalendarPopup(True)
        form_layout.addWidget(self.pay_date, 6, 1)

        form_layout.addWidget(QLabel("Payment Mode:"), 7, 0)
        self.pay_mode_combo = QComboBox()
        self.pay_mode_combo.addItems(["Cash", "Bank Transfer", "Credit Card", "Cheque", "Online/Other"])
        form_layout.addWidget(self.pay_mode_combo, 7, 1)
        
        form_layout.addWidget(QLabel("Reference/Notes:"), 8, 0)
        self.pay_ref = QLineEdit()
        self.pay_ref.setPlaceholderText("Check #, Txn ID, or remarks...")
        form_layout.addWidget(self.pay_ref, 8, 1)
        
        self.submit_pay_btn = QPushButton("Submit Payment")
        self.submit_pay_btn.setStyleSheet("background-color: #3498db; color: white; padding: 12px; font-weight: bold; font-size: 14px;")
        self.submit_pay_btn.clicked.connect(self.submit_payment)
        form_layout.addWidget(self.submit_pay_btn, 9, 0, 1, 2)
        
        top_hbox.addWidget(self.recovery_form_group, 2)
        
        # Right Side: Account Details Panel
        self.details_panel = QGroupBox("Selected Account Details")
        details_layout = QGridLayout(self.details_panel)
        details_layout.setSpacing(10)
        
        def add_detail_row(label, row):
            lbl = QLabel(label)
            lbl.setStyleSheet("color: #7f8c8d; font-weight: bold;")
            val = QLabel("-")
            val.setStyleSheet("color: #2c3e50; font-weight: bold;")
            details_layout.addWidget(lbl, row, 0)
            details_layout.addWidget(val, row, 1)
            return val

        self.det_sale_id = add_detail_row("Sale ID:", 0)
        self.det_type = add_detail_row("Account Type:", 1)
        self.det_model = add_detail_row("Motorcycle:", 2)
        self.det_chassis = add_detail_row("Chassis No:", 3)
        self.det_engine = add_detail_row("Engine No:", 4)
        self.det_sale_date = add_detail_row("Sale Date:", 5)
        self.det_due_date = add_detail_row("Due Date:", 6)
        self.det_credit_amt = add_detail_row("Credit Amount:", 7)
        self.det_paid_amt = add_detail_row("Paid Amount:", 8)
        self.det_remaining = add_detail_row("Remaining:", 9)
        self.det_installment = add_detail_row("Installment:", 10)
        self.det_status = add_detail_row("Status:", 11)
        
        details_layout.setRowStretch(12, 1)
        top_hbox.addWidget(self.details_panel, 1)
        
        layout.addLayout(top_hbox)
        
        # 2. Bottom Section: Customer Accounts Table
        self.cust_accounts_group = QGroupBox("Customer's Active Finance Accounts")
        table_layout = QVBoxLayout(self.cust_accounts_group)
        self.cust_accounts_table = QTableWidget(0, 10)
        self.cust_accounts_table.setHorizontalHeaderLabels([
            "Sale ID", "Motorcycle", "Chassis No", "Engine No", 
            "Sale Date", "Due Date", "Credit Amt", "Paid", "Remaining", "Status"
        ])
        
        # Workable Column Resizing
        ch = self.cust_accounts_table.horizontalHeader()
        ch.setStretchLastSection(False)
        ch.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        ch.setCascadingSectionResizes(True)
        
        self.cust_accounts_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.cust_accounts_table.setStyleSheet("QTableWidget { gridline-color: #ecf0f1; }")
        table_layout.addWidget(self.cust_accounts_table)
        
        layout.addWidget(self.cust_accounts_group)

    def _on_pay_account_changed(self, index):
        data = self.pay_account_combo.itemData(index)
        
        # Reset Panel
        for attr in [self.det_sale_id, self.det_type, self.det_model, self.det_chassis, 
                    self.det_engine, self.det_sale_date, self.det_due_date, self.det_credit_amt, 
                    self.det_paid_amt, self.det_remaining, self.det_installment, self.det_status]:
            attr.setText("-")
            attr.setStyleSheet("color: #2c3e50; font-weight: bold;")

        if data: # Advanced Finance Account
            self.pay_penalty.setEnabled(False)
            self.pay_discount.setEnabled(False)
            self.pay_penalty.setText("0.00")
            self.pay_discount.setText("0.00")
            
            # Fill Details Panel
            self.det_sale_id.setText(data['sale_id'])
            self.det_type.setText("Advanced Separate Finance")
            self.det_model.setText(data['model'])
            self.det_chassis.setText(data['chassis'])
            self.det_engine.setText(data['engine'])
            self.det_sale_date.setText(data['sale_date'].strftime('%d-%m-%Y'))
            self.det_due_date.setText(data['due_date'].strftime('%d-%m-%Y'))
            self.det_credit_amt.setText(f"Rs. {data['credit_amt']:,.2f}")
            self.det_paid_amt.setText(f"Rs. {data['paid_amt']:,.2f}")
            self.det_remaining.setText(f"Rs. {data['remaining']:,.2f}")
            self.det_installment.setText(f"Rs. {data['installment']:,.2f}")
            self.det_status.setText(data['status'])
            
            # Highlight overdue in panel
            if data['status'] == "OVERDUE":
                self.det_status.setStyleSheet("color: #e74c3c; font-weight: bold;")
                self.det_due_date.setStyleSheet("color: #e74c3c; font-weight: bold;")
            
            # Set suggested amount
            self.pay_amount.setText(f"{data['installment']:.2f}")
            self.pay_amount.setFocus()
            self.pay_amount.selectAll()
        else: # Old Running Credit
            self.pay_penalty.setEnabled(True)
            self.pay_discount.setEnabled(True)
            self.det_type.setText("Old Running Credit")
            self.pay_amount.setText("0.00")

    def _apply_pay_buyer_selection(self, name, buyer_id):
        self.pay_buyer_input.blockSignals(True)
        self.pay_buyer_input.setText(name)
        self.pay_buyer_input.blockSignals(False)
        self.selected_pay_buyer_id = buyer_id
        
        # 1. Load active advanced finance accounts into dropdown
        self.pay_account_combo.clear()
        self.pay_account_combo.addItem("--- OLD RUNNING CREDIT ---", None)
        
        accounts = credit_ledger_service.get_customer_active_finance_accounts(buyer_id)
        
        # 2. Refresh Bottom Table
        self.cust_accounts_table.setRowCount(0)
        
        for acc in accounts:
            paid = acc.credit_price - acc.remaining_balance
            
            # Format dropdown text (Requirement 2)
            # NEW-0001 | CD70 2024 | Ch#: 9CD70K243512 | Due: 08/07/2026 | Balance: 160,000
            dropdown_text = (f"{acc.sale_id} | {acc.model} | Ch#: {acc.chassis_no} | "
                           f"Due: {acc.due_date.strftime('%d/%m/%Y')} | Bal: {acc.remaining_balance:,.0f}")
            
            meta = {
                "id": acc.id,
                "sale_id": acc.sale_id,
                "model": acc.model,
                "chassis": acc.chassis_no,
                "engine": acc.engine_no or "N/A",
                "sale_date": acc.sale_date,
                "due_date": acc.due_date,
                "credit_amt": acc.credit_price,
                "paid_amt": paid,
                "installment": acc.installment_amount,
                "remaining": acc.remaining_balance,
                "status": acc.status
            }
            self.pay_account_combo.addItem(dropdown_text, meta)
            
            # Add to table (Requirement 5)
            row = self.cust_accounts_table.rowCount()
            self.cust_accounts_table.insertRow(row)
            
            items = [
                acc.sale_id, acc.model, acc.chassis_no, acc.engine_no or "N/A",
                acc.sale_date.strftime('%d-%m-%Y'), acc.due_date.strftime('%d-%m-%Y'),
                f"{acc.credit_price:,.2f}", f"{paid:,.2f}", f"{acc.remaining_balance:,.2f}", acc.status
            ]
            
            for col, text in enumerate(items):
                item = QTableWidgetItem(str(text))
                if acc.status == "OVERDUE": # Requirement 6
                    item.setForeground(Qt.GlobalColor.red)
                self.cust_accounts_table.setItem(row, col, item)

    def submit_payment(self):
        buyer = self.pay_buyer_input.text().strip()
        if not buyer or not self.selected_pay_buyer_id:
            QMessageBox.warning(self, "Error", "Invalid Buyer selected.")
            return
            
        try:
            amt = float(self.pay_amount.text() or 0)
            net = float(self.pay_net_received.text() or 0)
            account_data = self.pay_account_combo.currentData()
            
            if amt <= 0:
                QMessageBox.warning(self, "Validation Error", "Please enter a valid amount.")
                return

            if account_data: # Advanced Finance account (Requirement 3)
                # Validation: Check if payment exceeds balance
                if amt > account_data['remaining'] + 0.01:
                    QMessageBox.warning(self, "Validation Error", f"Payment amount exceeds the remaining balance (Rs. {account_data['remaining']:,.2f}).")
                    return

                data = {
                    "customer_id": self.selected_pay_buyer_id,
                    "sale_id": account_data['id'],
                    "paid_amount": amt,
                    "payment_date": self.pay_date.date().toPyDate(),
                    "payment_method": self.pay_mode_combo.currentText(),
                    "reference_no": self.pay_ref.text(),
                    "notes": f"Net: {net:.2f}"
                }
                payment = credit_ledger_service.create_finance_installment(data)
                QMessageBox.information(self, "Success", f"Installment for {account_data['sale_id']} recorded.")
                
                # Refresh data for this customer
                self._apply_pay_buyer_selection(buyer, self.selected_pay_buyer_id)
            else: # OLD RUNNING CREDIT (Requirement 3)
                penalty = float(self.pay_penalty.text() or 0)
                discount = float(self.pay_discount.text() or 0)
                data = {
                    "buyer_id": self.selected_pay_buyer_id,
                    "amount": amt,
                    "penalty_amount": penalty,
                    "discount_amount": discount,
                    "net_amount": net,
                    "payment_date": self.pay_date.date().toPyDate(),
                    "payment_mode": self.pay_mode_combo.currentText(),
                    "invoice_reference": self.pay_ref.text()
                }
                payment = credit_ledger_service.create_payment(data)
                self.show_receipt(payment, buyer)
            
            self.refresh_dashboard()
            self._clear_payment_form()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _clear_payment_form(self):
        self.pay_amount.setText("0.00")
        self.pay_penalty.setText("0.00")
        self.pay_discount.setText("0.00")
        self.pay_ref.clear()
        self.pay_buyer_input.clear()
        self.pay_account_combo.clear()
        self.pay_account_combo.addItem("--- OLD RUNNING CREDIT ---", None)
        self.selected_pay_buyer_id = None
        self.cust_accounts_table.setRowCount(0)
        # Clear details panel
        self._on_pay_account_changed(-1)

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

    # --- TAB: ACTIVE ACCOUNTS ---
    def _setup_active_accounts_tab(self):
        layout = QVBoxLayout(self.active_accounts_tab)
        
        # Search & Export
        top_layout = QHBoxLayout()
        self.active_search = QLineEdit()
        self.active_search.setPlaceholderText("Search by Sale ID, Customer or Chassis...")
        self.active_search.textChanged.connect(self.load_active_accounts)
        top_layout.addWidget(self.active_search)
        
        export_btn = QPushButton("Export to CSV")
        top_layout.addWidget(export_btn)
        layout.addLayout(top_layout)
        
        self.active_table = QTableWidget(0, 8)
        self.active_table.setHorizontalHeaderLabels([
            "Sale ID", "Customer", "Motorcycle", "Credit Price", 
            "Paid Amount", "Remaining", "Due Date", "Status"
        ])
        
        # Workable Column Resizing
        ah = self.active_table.horizontalHeader()
        ah.setStretchLastSection(False)
        ah.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        ah.setCascadingSectionResizes(True)
        
        self.active_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        layout.addWidget(self.active_table)

    def load_active_accounts(self):
        query = self.active_search.text().strip()
        accounts = credit_ledger_service.get_active_finance_accounts(query)
        
        self.active_table.setRowCount(0)
        for acc in accounts:
            row = self.active_table.rowCount()
            self.active_table.insertRow(row)
            
            paid = acc.credit_price - acc.remaining_balance
            
            self.active_table.setItem(row, 0, QTableWidgetItem(acc.sale_id))
            self.active_table.setItem(row, 1, QTableWidgetItem(acc.customer_name))
            self.active_table.setItem(row, 2, QTableWidgetItem(f"{acc.model} ({acc.chassis_no})"))
            self.active_table.setItem(row, 3, QTableWidgetItem(f"{acc.credit_price:,.2f}"))
            self.active_table.setItem(row, 4, QTableWidgetItem(f"{paid:,.2f}"))
            self.active_table.setItem(row, 5, QTableWidgetItem(f"{acc.remaining_balance:,.2f}"))
            self.active_table.setItem(row, 6, QTableWidgetItem(acc.due_date.strftime('%d-%m-%Y')))
            
            status_item = QTableWidgetItem(acc.status)
            if acc.status == "OVERDUE":
                status_item.setForeground(Qt.GlobalColor.red)
            self.active_table.setItem(row, 7, status_item)

    # --- TAB: DUE ACCOUNTS ---
    def _setup_due_accounts_tab(self):
        layout = QVBoxLayout(self.due_accounts_tab)
        
        self.due_table = QTableWidget(0, 7)
        self.due_table.setHorizontalHeaderLabels([
            "Sale ID", "Customer", "Chassis No", "Remaining", 
            "Due Date", "Overdue Days", "Action"
        ])
        
        # Workable Column Resizing
        dh = self.due_table.horizontalHeader()
        dh.setStretchLastSection(False)
        dh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        dh.setCascadingSectionResizes(True)
        
        self.due_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        layout.addWidget(self.due_table)

    def load_due_accounts(self):
        try:
            due_data = credit_ledger_service.get_due_finance_accounts()
            
            self.due_table.setRowCount(0)
            if not due_data:
                # Optional: Show message or empty placeholder if no overdue accounts
                return

            for item in due_data:
                acc = item['account']
                days = item['overdue_days']
                
                row = self.due_table.rowCount()
                self.due_table.insertRow(row)
                
                # Use QTableWidgetItem properly for all columns
                self.due_table.setItem(row, 0, QTableWidgetItem(str(acc.sale_id)))
                self.due_table.setItem(row, 1, QTableWidgetItem(str(acc.customer_name)))
                self.due_table.setItem(row, 2, QTableWidgetItem(str(acc.chassis_no)))
                self.due_table.setItem(row, 3, QTableWidgetItem(f"{acc.remaining_balance:,.2f}"))
                self.due_table.setItem(row, 4, QTableWidgetItem(acc.due_date.strftime('%d-%m-%Y')))
                
                days_item = QTableWidgetItem(str(days))
                days_item.setForeground(Qt.GlobalColor.red)
                days_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.due_table.setItem(row, 5, days_item)
                
                pay_btn = QPushButton("Collect")
                pay_btn.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold;")
                # Use a proper closure for the button click
                pay_btn.clicked.connect(lambda checked, a=acc: self._open_payment_for_account(a))
                self.due_table.setCellWidget(row, 6, pay_btn)
                
        except Exception as e:
            logger.error(f"Error loading due accounts: {e}")
            QMessageBox.critical(self, "Error", f"Could not load due accounts: {str(e)}")

    def _open_payment_for_account(self, account):
        self.tabs.setCurrentIndex(2) # Switch to Payment tab
        self._apply_pay_buyer_selection(account.customer_name, account.customer_id)
        # Find index in combo
        for i in range(self.pay_account_combo.count()):
            if self.pay_account_combo.itemData(i) == account.id:
                self.pay_account_combo.setCurrentIndex(i)
                break

    # --- TAB: CUSTOMER LEDGER ---
    def _setup_ledger_tab(self):
        layout = QVBoxLayout(self.ledger_tab)
        
        # Filters
        filters = QGridLayout()
        filters.addWidget(QLabel("Buyer Name:"), 0, 0)
        self.ledger_buyer_input = SharedLineEdit()
        self.ledger_buyer_input.setPlaceholderText("Search Buyer...")
        self.ledger_buyer_completer = BuyerCompleter(self.ledger_buyer_input)
        self.ledger_buyer_input.setCompleter(self.ledger_buyer_completer)
        self.ledger_buyer_input.textChanged.connect(self._update_ledger_buyer_suggestions)
        self.ledger_buyer_completer.activated[QModelIndex].connect(self._on_ledger_buyer_selected_index)
        filters.addWidget(self.ledger_buyer_input, 0, 1)
        
        filters.addWidget(QLabel("Select Ledger:"), 1, 0)
        self.ledger_account_combo = QComboBox()
        self.ledger_account_combo.addItem("--- MASTER LEDGER (ALL) ---", "MASTER")
        filters.addWidget(self.ledger_account_combo, 1, 1)

        self.start_date = QDateEdit(QDate.currentDate().addMonths(-1))
        self.start_date.setCalendarPopup(True)
        filters.addWidget(QLabel("From:"), 0, 2)
        filters.addWidget(self.start_date, 0, 3)
        
        self.end_date = QDateEdit(QDate.currentDate())
        self.end_date.setCalendarPopup(True)
        filters.addWidget(QLabel("To:"), 1, 2)
        filters.addWidget(self.end_date, 1, 3)
        
        view_btn = QPushButton("View Ledger")
        view_btn.clicked.connect(self.load_ledger)
        filters.addWidget(view_btn, 0, 4)
        
        self.print_ledger_btn = QPushButton("Print Ledger")
        self.print_ledger_btn.setStyleSheet("background-color: #2c3e50; color: white;")
        self.print_ledger_btn.clicked.connect(self.print_ledger)
        filters.addWidget(self.print_ledger_btn, 1, 4)
        
        layout.addLayout(filters)
        
        # Customer Info Header
        self.customer_info_card = QFrame()
        self.customer_info_card.setStyleSheet("""
            QFrame { background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 5px; margin-bottom: 5px; }
            QLabel { font-size: 13px; color: #2c3e50; }
        """)
        info_layout = QGridLayout(self.customer_info_card)
        self.lbl_cust_name = QLabel("Name: -")
        self.lbl_cust_phone = QLabel("Phone: -")
        self.lbl_cust_balance = QLabel("Outstanding: -")
        info_layout.addWidget(self.lbl_cust_name, 0, 0)
        info_layout.addWidget(self.lbl_cust_phone, 0, 1)
        info_layout.addWidget(self.lbl_cust_balance, 0, 2)
        layout.addWidget(self.customer_info_card)
        
        self.ledger_table = QTableWidget(0, 6)
        self.ledger_table.setHorizontalHeaderLabels(["Date", "Description", "Sale ID", "Debit", "Credit", "Balance"])
        
        # Workable Column Resizing
        lh = self.ledger_table.horizontalHeader()
        lh.setStretchLastSection(False)
        lh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        lh.setCascadingSectionResizes(True)
        
        self.ledger_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # Multi-line formatting (Requirement 3 & 8)
        self.ledger_table.setWordWrap(True)
        self.ledger_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.ledger_table.setStyleSheet("""
            QTableWidget::item { padding: 5px; vertical-align: top; }
        """)
        
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
        
        # Load account options for ledger
        self.ledger_account_combo.clear()
        self.ledger_account_combo.addItem("--- MASTER LEDGER (ALL) ---", "MASTER")
        self.ledger_account_combo.addItem("--- OLD RUNNING CREDIT ---", "OLD")
        accounts = credit_ledger_service.get_customer_active_finance_accounts(buyer_id)
        for acc in accounts:
            self.ledger_account_combo.addItem(f"Finance: {acc.sale_id} ({acc.model})", acc.id)

    def load_ledger(self):
        if not self.selected_ledger_buyer_id:
            QMessageBox.warning(self, "Selection Required", "Please select a customer first.")
            return
            
        l_type = self.ledger_account_combo.currentData()
        self.ledger_table.setRowCount(0)
        
        # Update Customer Header
        cust_details = credit_ledger_service.get_customer_details(self.selected_ledger_buyer_id)
        if cust_details:
            self.lbl_cust_name.setText(f"Name: {cust_details['name']}")
            self.lbl_cust_phone.setText(f"Phone: {cust_details['phone']}")
            self.current_customer_details = cust_details
        
        if l_type == "MASTER":
            entries = credit_ledger_service.get_combined_ledger(
                self.selected_ledger_buyer_id,
                self.start_date.date().toPyDate(),
                self.end_date.date().toPyDate()
            )
            for e in entries:
                row = self.ledger_table.rowCount()
                self.ledger_table.insertRow(row)
                self.ledger_table.setItem(row, 0, QTableWidgetItem(e['date'].strftime('%d-%m-%Y')))
                self.ledger_table.setItem(row, 1, QTableWidgetItem(e['description']))
                self.ledger_table.setItem(row, 2, QTableWidgetItem(e['sale_id']))
                self.ledger_table.setItem(row, 3, QTableWidgetItem(f"{e['debit']:,.2f}"))
                self.ledger_table.setItem(row, 4, QTableWidgetItem(f"{e['credit']:,.2f}"))
                self.ledger_table.setItem(row, 5, QTableWidgetItem(f"{e['combined_balance']:,.2f}"))
            if entries:
                self.lbl_cust_balance.setText(f"Outstanding: Rs. {entries[-1]['combined_balance']:,.2f}")
        
        elif l_type == "OLD":
            entries = credit_ledger_service.get_ledger(
                self.selected_ledger_buyer_id,
                self.start_date.date().toPyDate(),
                self.end_date.date().toPyDate()
            )
            for e in entries:
                row = self.ledger_table.rowCount()
                self.ledger_table.insertRow(row)
                self.ledger_table.setItem(row, 0, QTableWidgetItem(e.date.strftime('%d-%m-%Y')))
                self.ledger_table.setItem(row, 1, QTableWidgetItem(e.description))
                self.ledger_table.setItem(row, 2, QTableWidgetItem("OLD-SYSTEM"))
                self.ledger_table.setItem(row, 3, QTableWidgetItem(f"{e.debit:,.2f}"))
                self.ledger_table.setItem(row, 4, QTableWidgetItem(f"{e.credit:,.2f}"))
                self.ledger_table.setItem(row, 5, QTableWidgetItem(f"{e.balance:,.2f}"))
            if entries:
                self.lbl_cust_balance.setText(f"Outstanding: Rs. {entries[-1].balance:,.2f}")
        
        else:
            entries = credit_ledger_service.get_finance_sale_ledger(l_type)
            for e in entries:
                row = self.ledger_table.rowCount()
                self.ledger_table.insertRow(row)
                self.ledger_table.setItem(row, 0, QTableWidgetItem(e.entry_date.strftime('%d-%m-%Y')))
                self.ledger_table.setItem(row, 1, QTableWidgetItem(e.description))
                self.ledger_table.setItem(row, 2, QTableWidgetItem(e.sale.sale_id if e.sale else "N/A"))
                self.ledger_table.setItem(row, 3, QTableWidgetItem(f"{e.debit:,.2f}"))
                self.ledger_table.setItem(row, 4, QTableWidgetItem(f"{e.credit:,.2f}"))
                self.ledger_table.setItem(row, 5, QTableWidgetItem(f"{e.balance:,.2f}"))
            if entries:
                self.lbl_cust_balance.setText(f"Outstanding: Rs. {entries[-1].balance:,.2f}")

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
