"""Top-level container for the whole Spare Parts module.

This is the ONE widget app/qt_ui/main_window.py embeds as a page (see
spare_parts/__init__.py rule #3). Every later phase (purchases, sales,
ledgers, reports, dashboard) adds its own tab inside this widget's
QTabWidget - main_window.py is not touched again after the initial
one-time integration.

Running migrations here (not only via the standalone
`python -m spare_parts.db.migrations` script) means the module's tables
self-create the first time this page is ever opened, the same way the
rest of the app's database self-heals on startup - no separate manual
step required for a normal user.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QMessageBox, QTabWidget, QVBoxLayout, QWidget

from spare_parts.db.migrations import run_migrations
from spare_parts.logging_config import get_logger
from spare_parts.ui.categories_brands_page import CategoriesBrandsPage
from spare_parts.ui.customers_page import CustomersPage
from spare_parts.ui.dashboard_page import DashboardPage
from spare_parts.ui.ledger_page import LedgerPage
from spare_parts.ui.parts_page import PartsPage
from spare_parts.ui.payments_page import PaymentsPage
from spare_parts.ui.pos_page import PosPage
from spare_parts.ui.purchase_page import PurchasesPage
from spare_parts.ui.quotations_page import QuotationsPage
from spare_parts.ui.reports_page import ReportsPage
from spare_parts.ui.returns_page import ReturnsPage
from spare_parts.ui.sales_page import SalesPage
from spare_parts.ui.settings_page import SettingsPage
from spare_parts.ui.stock_take_page import StockTakePage
from spare_parts.ui.suppliers_page import SuppliersPage

logger = get_logger(__name__)


class SparePartsModuleWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        try:
            run_migrations()
        except Exception as e:
            logger.error(f"Spare Parts migration failed: {e}", exc_info=True)
            error_label = QLabel(
                "Spare Parts module failed to initialize its database tables.\n"
                "See spare_parts logs for details."
            )
            error_label.setStyleSheet("color: #e74c3c; padding: 20px; font-weight: bold;")
            layout.addWidget(error_label)
            QMessageBox.critical(
                self, "Spare Parts - Initialization Error",
                f"Could not set up the Spare Parts database tables:\n\n{e}",
            )
            return

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.dashboard_page = DashboardPage()
        self.tabs.addTab(self.dashboard_page, "Dashboard")

        self.pos_page = PosPage()
        self.tabs.addTab(self.pos_page, "Sales Counter")

        self.sales_page = SalesPage()
        self.tabs.addTab(self.sales_page, "Sales")

        self.quotations_page = QuotationsPage()
        self.tabs.addTab(self.quotations_page, "Quotations")

        self.parts_page = PartsPage()
        self.tabs.addTab(self.parts_page, "Parts")

        self.categories_brands_page = CategoriesBrandsPage()
        self.tabs.addTab(self.categories_brands_page, "Categories & Brands")

        self.suppliers_page = SuppliersPage()
        self.tabs.addTab(self.suppliers_page, "Suppliers")

        self.purchases_page = PurchasesPage()
        self.tabs.addTab(self.purchases_page, "Purchases")

        self.stock_take_page = StockTakePage()
        self.tabs.addTab(self.stock_take_page, "Stock Take")

        self.customers_page = CustomersPage()
        self.tabs.addTab(self.customers_page, "Customers")

        self.returns_page = ReturnsPage()
        self.tabs.addTab(self.returns_page, "Returns")

        self.payments_page = PaymentsPage()
        self.tabs.addTab(self.payments_page, "Payments")

        self.ledger_page = LedgerPage()
        self.tabs.addTab(self.ledger_page, "Ledgers")

        self.reports_page = ReportsPage()
        self.tabs.addTab(self.reports_page, "Reports")

        self.settings_page = SettingsPage()
        self.tabs.addTab(self.settings_page, "Settings")

        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if widget is self.ledger_page:
            self.ledger_page.refresh_party_lists()
        elif widget is self.dashboard_page:
            self.dashboard_page.refresh()
        elif widget is self.reports_page:
            self.reports_page.refresh()
        elif widget is self.pos_page:
            self.pos_page.refresh_held_count()
            self.pos_page.refresh_open_cards_parts_lookup()
        elif widget is self.categories_brands_page:
            self.categories_brands_page.reload()
        elif widget is self.returns_page:
            self.returns_page.refresh_lookup_completers()
        elif widget is self.sales_page:
            self.sales_page.reload()
        elif widget is self.quotations_page:
            self.quotations_page.reload()
        elif widget is self.stock_take_page:
            self.stock_take_page.reload()
        elif widget is self.settings_page:
            self.settings_page.reload()
