"""Reports: Stock, Sales, Purchases, and Receivables & Payables - each a
sub-tab, built entirely from spare_parts/services/reports_service.py.
"""
from __future__ import annotations

import datetime as dt

from PyQt6.QtCore import QDate, Qt, QTimer
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from spare_parts.db.base import get_spare_session
from spare_parts.services import parts_service, reports_service, suppliers_service
from spare_parts.ui.purchase_page import PurchaseDialog
from spare_parts.ui.stock_ledger_dialog import StockLedgerDialog
from spare_parts.ui.widgets import NoScrollComboBox, NoScrollDateEdit, NoScrollSpinBox

_PRIMARY_BTN = """
    QPushButton {
        background-color: #3498db; color: white; border: none;
        border-radius: 4px; padding: 8px 16px; font-weight: bold;
    }
    QPushButton:hover { background-color: #2980b9; }
    QPushButton:disabled { background-color: #bdc3c7; }
"""

_RESET_BTN = """
    QPushButton {
        background-color: #f8f9fa; color: #6c757d; border: 1px solid #dee2e6;
        border-radius: 4px; padding: 8px 16px;
    }
    QPushButton:hover { background-color: #e2e6ea; }
"""


def _date_range_to_datetimes(from_edit: NoScrollDateEdit, to_edit: NoScrollDateEdit) -> tuple[dt.datetime, dt.datetime]:
    date_from = dt.datetime.combine(from_edit.date().toPyDate(), dt.time.min)
    date_to = dt.datetime.combine(to_edit.date().toPyDate(), dt.time.max)
    return date_from, date_to


class _StockReportTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Check stock: search part no, name, barcode...")
        self.search_input.textChanged.connect(self._on_search_text_changed)
        toolbar.addWidget(self.search_input, 2)

        self.low_stock_checkbox = QCheckBox("Low stock only")
        self.low_stock_checkbox.stateChanged.connect(self._reload)
        toolbar.addWidget(self.low_stock_checkbox)
        toolbar.addStretch(1)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setStyleSheet(_RESET_BTN)
        refresh_btn.clicked.connect(self._reload)
        toolbar.addWidget(refresh_btn)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Part", "Current Stock", "Reorder At", "Cost Price", "Stock Value"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._on_view_ledger_clicked)
        layout.addWidget(self.table, 1)

        bottom_row = QHBoxLayout()
        view_ledger_btn = QPushButton("View Stock Ledger")
        view_ledger_btn.setStyleSheet(_RESET_BTN)
        view_ledger_btn.clicked.connect(self._on_view_ledger_clicked)
        bottom_row.addWidget(view_ledger_btn)
        bottom_row.addStretch(1)
        self.total_label = QLabel("")
        self.total_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #2c3e50;")
        bottom_row.addWidget(self.total_label)
        layout.addLayout(bottom_row)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_timer.timeout.connect(self._reload)

        self._reload()

    def _on_search_text_changed(self, _text: str) -> None:
        self._search_timer.start()

    def _reload(self) -> None:
        db = get_spare_session()
        try:
            rows = reports_service.get_stock_report(
                db, query=self.search_input.text(), low_stock_only=self.low_stock_checkbox.isChecked(),
            )
        finally:
            db.close()

        self.table.setRowCount(len(rows))
        total_value = 0
        for row, entry in enumerate(rows):
            part = entry["part"]
            part_item = QTableWidgetItem(f"{part.part_no} - {part.name}")
            part_item.setData(Qt.ItemDataRole.UserRole, part.id)
            self.table.setItem(row, 0, part_item)
            stock_item = QTableWidgetItem(str(entry["current_stock"]))
            if entry["is_low"]:
                stock_item.setForeground(Qt.GlobalColor.red)
            self.table.setItem(row, 1, stock_item)
            self.table.setItem(row, 2, QTableWidgetItem(str(part.reorder_level)))
            self.table.setItem(row, 3, QTableWidgetItem(f"{float(part.cost_price):,.2f}"))
            self.table.setItem(row, 4, QTableWidgetItem(f"{entry['stock_value']:,.2f}"))
            total_value += entry["stock_value"]
        self.total_label.setText(f"Total Stock Value: Rs. {total_value:,.2f}")

    def _on_view_ledger_clicked(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "No Selection", "Select a part first.")
            return
        part_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        dlg = StockLedgerDialog(part_id=part_id, parent=self)
        dlg.exec()


class _ReorderSuggestionsTab(QWidget):
    """Parts at/below reorder_level with a suggested reorder quantity -
    check the ones to include, adjust quantity if needed, then "Create
    Purchase from Selected" opens PurchaseDialog pre-filled (supplier is
    still picked there, same required step as any new purchase - see
    purchase_page.PurchaseDialog's prefill_items param)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        toolbar.addStretch(1)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setStyleSheet(_RESET_BTN)
        refresh_btn.clicked.connect(self._reload)
        toolbar.addWidget(refresh_btn)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Include", "Part", "Current Stock", "Reorder Level", "Suggested Qty"]
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)

        bottom_row = QHBoxLayout()
        bottom_row.addStretch(1)
        create_purchase_btn = QPushButton("Create Purchase from Selected")
        create_purchase_btn.setStyleSheet(_PRIMARY_BTN)
        create_purchase_btn.clicked.connect(self._on_create_purchase_clicked)
        bottom_row.addWidget(create_purchase_btn)
        layout.addLayout(bottom_row)

        self._row_part_ids: list[int] = []
        self._reload()

    def _reload(self) -> None:
        db = get_spare_session()
        try:
            rows = reports_service.get_reorder_suggestions(db)
            self._row_part_ids = [entry["part"].id for entry in rows]
            self.table.setRowCount(len(rows))
            for row, entry in enumerate(rows):
                part = entry["part"]

                checkbox = QCheckBox()
                checkbox.setChecked(True)
                checkbox_container = QWidget()
                checkbox_layout = QHBoxLayout(checkbox_container)
                checkbox_layout.addWidget(checkbox)
                checkbox_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                checkbox_layout.setContentsMargins(0, 0, 0, 0)
                self.table.setCellWidget(row, 0, checkbox_container)

                self.table.setItem(row, 1, QTableWidgetItem(f"{part.part_no} - {part.name}"))
                self.table.setItem(row, 2, QTableWidgetItem(str(entry["current_stock"])))
                self.table.setItem(row, 3, QTableWidgetItem(str(entry["reorder_level"])))

                qty_spin = NoScrollSpinBox()
                qty_spin.setRange(1, 1_000_000)
                qty_spin.setValue(max(1, entry["suggested_qty"]))
                self.table.setCellWidget(row, 4, qty_spin)
        finally:
            db.close()

    def _on_create_purchase_clicked(self) -> None:
        db = get_spare_session()
        try:
            prefill_items = []
            for row, part_id in enumerate(self._row_part_ids):
                checkbox_container = self.table.cellWidget(row, 0)
                checkbox = checkbox_container.findChild(QCheckBox) if checkbox_container else None
                if not checkbox or not checkbox.isChecked():
                    continue
                qty_spin = self.table.cellWidget(row, 4)
                qty = qty_spin.value() if qty_spin else 1
                part = parts_service.get_part(db, part_id)
                if part:
                    prefill_items.append(dict(part=part, qty=qty))
        finally:
            db.close()

        if not prefill_items:
            QMessageBox.information(self, "No Selection", "Check at least one part to include.")
            return

        dlg = PurchaseDialog(prefill_items=prefill_items, parent=self)
        if dlg.exec():
            self._reload()


class _SalesReportTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("From"))
        self.from_date = NoScrollDateEdit()
        self.from_date.setCalendarPopup(True)
        self.from_date.setDate(QDate.currentDate().addDays(-30))
        toolbar.addWidget(self.from_date)

        toolbar.addWidget(QLabel("To"))
        self.to_date = NoScrollDateEdit()
        self.to_date.setCalendarPopup(True)
        self.to_date.setDate(QDate.currentDate())
        toolbar.addWidget(self.to_date)

        self.type_filter = NoScrollComboBox()
        self.type_filter.addItems(["All Types", "RETAIL", "WHOLESALE"])
        toolbar.addWidget(self.type_filter)
        toolbar.addStretch(1)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setStyleSheet(_RESET_BTN)
        refresh_btn.clicked.connect(self._reload)
        toolbar.addWidget(refresh_btn)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Sale No.", "Type", "Customer", "Date", "Total", "Paid", "Due"]
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)

        self.totals_label = QLabel("")
        self.totals_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #2c3e50;")
        self.totals_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.totals_label)

        self._reload()

    def _reload(self) -> None:
        date_from, date_to = _date_range_to_datetimes(self.from_date, self.to_date)
        sale_type = self.type_filter.currentText()
        db = get_spare_session()
        try:
            report = reports_service.get_sales_report(
                db, date_from=date_from, date_to=date_to,
                sale_type=None if sale_type == "All Types" else sale_type,
            )
            rows = report["rows"]
            self.table.setRowCount(len(rows))
            for row, sale in enumerate(rows):
                self.table.setItem(row, 0, QTableWidgetItem(sale.sale_no))
                self.table.setItem(row, 1, QTableWidgetItem(sale.sale_type))
                self.table.setItem(row, 2, QTableWidgetItem(sale.customer.name if sale.customer else "Walk-in"))
                self.table.setItem(row, 3, QTableWidgetItem(sale.sale_date.strftime("%Y-%m-%d")))
                self.table.setItem(row, 4, QTableWidgetItem(f"{float(sale.total):,.2f}"))
                self.table.setItem(row, 5, QTableWidgetItem(f"{float(sale.paid):,.2f}"))
                self.table.setItem(row, 6, QTableWidgetItem(f"{float(sale.due):,.2f}"))
        finally:
            db.close()

        t = report["totals"]
        self.totals_label.setText(
            f"{t['count']} sales - Subtotal: Rs. {t['subtotal']:,.2f} | "
            f"Tax: Rs. {t['tax_amount']:,.2f} | Total: Rs. {t['total']:,.2f} | "
            f"Paid: Rs. {t['paid']:,.2f} | Due: Rs. {t['due']:,.2f}"
        )


_PROFIT_PERIOD_LABELS = [
    ("Daily (Today)", reports_service.PERIOD_DAILY),
    ("Monthly (This Month)", reports_service.PERIOD_MONTHLY),
    ("Quarterly (This Quarter)", reports_service.PERIOD_QUARTERLY),
    ("Custom", reports_service.PERIOD_CUSTOM),
]


class _ProfitReportTab(QWidget):
    """Gross profit (Revenue - COGS) over Daily/Monthly/Quarterly/Custom
    periods - see reports_service.get_profit_report. The From/To date
    editors are auto-filled and locked for the three presets (there's
    only one "today"/"this month"/"this quarter"); Custom unlocks them
    for a manual range, same editors the Sales/Purchases tabs use."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Period"))
        self.period_combo = NoScrollComboBox()
        for label, value in _PROFIT_PERIOD_LABELS:
            self.period_combo.addItem(label, value)
        self.period_combo.currentIndexChanged.connect(self._on_period_changed)
        toolbar.addWidget(self.period_combo)

        toolbar.addWidget(QLabel("From"))
        self.from_date = NoScrollDateEdit()
        self.from_date.setCalendarPopup(True)
        toolbar.addWidget(self.from_date)

        toolbar.addWidget(QLabel("To"))
        self.to_date = NoScrollDateEdit()
        self.to_date.setCalendarPopup(True)
        toolbar.addWidget(self.to_date)
        toolbar.addStretch(1)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setStyleSheet(_RESET_BTN)
        refresh_btn.clicked.connect(self._reload)
        toolbar.addWidget(refresh_btn)
        layout.addLayout(toolbar)

        summary_row = QHBoxLayout()
        self.revenue_label = self._make_summary_label(summary_row, "Revenue", "#2c3e50")
        self.cogs_label = self._make_summary_label(summary_row, "COGS", "#e67e22")
        self.profit_label = self._make_summary_label(summary_row, "Gross Profit", "#27ae60")
        self.margin_label = self._make_summary_label(summary_row, "Margin", "#3498db")
        summary_row.addStretch(1)
        layout.addLayout(summary_row)

        self.estimate_note_label = QLabel("")
        self.estimate_note_label.setStyleSheet("color: #e67e22; font-size: 11px;")
        self.estimate_note_label.setWordWrap(True)
        self.estimate_note_label.hide()
        layout.addWidget(self.estimate_note_label)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Sale No.", "Customer", "Date", "Revenue", "COGS", "Profit", "Margin %"]
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)

        self._on_period_changed()  # sets From/To for the default (Daily) period and loads

    def _make_summary_label(self, row: QHBoxLayout, title: str, color: str) -> QLabel:
        box = QVBoxLayout()
        caption = QLabel(title)
        caption.setStyleSheet("color: #6c757d; font-size: 11px;")
        box.addWidget(caption)
        value_label = QLabel("Rs. 0.00")
        value_label.setStyleSheet(f"font-weight: bold; font-size: 16px; color: {color};")
        box.addWidget(value_label)
        container = QWidget()
        container.setLayout(box)
        row.addWidget(container)
        return value_label

    def _on_period_changed(self) -> None:
        period = self.period_combo.currentData()
        is_custom = period == reports_service.PERIOD_CUSTOM
        self.from_date.setEnabled(is_custom)
        self.to_date.setEnabled(is_custom)
        if not is_custom:
            date_from, date_to = reports_service.profit_period_range(period)
            self.from_date.setDate(QDate(date_from.year, date_from.month, date_from.day))
            self.to_date.setDate(QDate(date_to.year, date_to.month, date_to.day))
        self._reload()

    def _reload(self) -> None:
        date_from, date_to = _date_range_to_datetimes(self.from_date, self.to_date)
        db = get_spare_session()
        try:
            report = reports_service.get_profit_report(db, date_from=date_from, date_to=date_to)
            rows = report["rows"]
            self.table.setRowCount(len(rows))
            for row, entry in enumerate(rows):
                sale = entry["sale"]
                self.table.setItem(row, 0, QTableWidgetItem(sale.sale_no))
                self.table.setItem(row, 1, QTableWidgetItem(sale.customer.name if sale.customer else (sale.walk_in_customer_name or "Walk-in")))
                self.table.setItem(row, 2, QTableWidgetItem(sale.sale_date.strftime("%Y-%m-%d")))
                self.table.setItem(row, 3, QTableWidgetItem(f"{entry['revenue']:,.2f}"))
                self.table.setItem(row, 4, QTableWidgetItem(f"{entry['cogs']:,.2f}"))
                profit_item = QTableWidgetItem(f"{entry['gross_profit']:,.2f}")
                if entry["gross_profit"] < 0:
                    profit_item.setForeground(Qt.GlobalColor.red)
                self.table.setItem(row, 5, profit_item)
                margin_item = QTableWidgetItem(f"{entry['margin_pct']:,.1f}%")
                if entry["has_estimated_cost"]:
                    margin_item.setToolTip("This sale has at least one line without a cost snapshot - today's cost price was used as an estimate.")
                self.table.setItem(row, 6, margin_item)
        finally:
            db.close()

        t = report["totals"]
        self.revenue_label.setText(f"Rs. {t['revenue']:,.2f}")
        self.cogs_label.setText(f"Rs. {t['cogs']:,.2f}")
        self.profit_label.setText(f"Rs. {t['gross_profit']:,.2f}")
        self.margin_label.setText(f"{t['margin_pct']:,.1f}%")

        if t["estimated_rows_count"] > 0:
            self.estimate_note_label.setText(
                f"Note: {t['estimated_rows_count']} sale(s) in this range predate per-sale cost "
                "tracking and use today's cost price as an estimate - their profit figure may not "
                "be exact."
            )
            self.estimate_note_label.show()
        else:
            self.estimate_note_label.hide()


class _WarrantyLookupTab(QWidget):
    """Search sold lines that still carry a warranty - see
    reports_service.search_warranty. Filter-driven (search box, not a
    glance-and-go list), same category as Sales/Profit."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search part no/name, sale no, or customer...")
        self.search_input.textChanged.connect(self._on_search_text_changed)
        toolbar.addWidget(self.search_input, 2)
        toolbar.addStretch(1)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setStyleSheet(_RESET_BTN)
        refresh_btn.clicked.connect(self._reload)
        toolbar.addWidget(refresh_btn)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Part", "Sale No.", "Customer", "Sale Date", "Warranty Expires", "Status"]
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_timer.timeout.connect(self._reload)

        self._reload()

    def _on_search_text_changed(self, _text: str) -> None:
        self._search_timer.start()

    def _reload(self) -> None:
        db = get_spare_session()
        try:
            rows = reports_service.search_warranty(db, query=self.search_input.text())
        finally:
            db.close()

        self.table.setRowCount(len(rows))
        for row, entry in enumerate(rows):
            part = entry["part"]
            sale = entry["sale"]
            self.table.setItem(row, 0, QTableWidgetItem(f"{part.part_no} - {part.name}"))
            self.table.setItem(row, 1, QTableWidgetItem(sale.sale_no))
            self.table.setItem(row, 2, QTableWidgetItem(entry["customer_name"]))
            self.table.setItem(row, 3, QTableWidgetItem(sale.sale_date.strftime("%Y-%m-%d")))
            self.table.setItem(row, 4, QTableWidgetItem(entry["warranty_expires_at"].strftime("%Y-%m-%d")))
            status_item = QTableWidgetItem("Active" if entry["is_active"] else "Expired")
            if not entry["is_active"]:
                status_item.setForeground(Qt.GlobalColor.red)
            self.table.setItem(row, 5, status_item)


class _PurchasesReportTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("From"))
        self.from_date = NoScrollDateEdit()
        self.from_date.setCalendarPopup(True)
        self.from_date.setDate(QDate.currentDate().addDays(-30))
        toolbar.addWidget(self.from_date)

        toolbar.addWidget(QLabel("To"))
        self.to_date = NoScrollDateEdit()
        self.to_date.setCalendarPopup(True)
        self.to_date.setDate(QDate.currentDate())
        toolbar.addWidget(self.to_date)

        self.supplier_filter = NoScrollComboBox()
        self.supplier_filter.addItem("All Suppliers", None)
        toolbar.addWidget(self.supplier_filter, 1)
        toolbar.addStretch(1)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setStyleSheet(_RESET_BTN)
        refresh_btn.clicked.connect(self._reload)
        toolbar.addWidget(refresh_btn)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Purchase No.", "Supplier", "Date", "Total", "Paid", "Due"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)

        self.totals_label = QLabel("")
        self.totals_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #2c3e50;")
        self.totals_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.totals_label)

        self._reload_suppliers()
        self._reload()

    def _reload_suppliers(self) -> None:
        db = get_spare_session()
        try:
            self.supplier_filter.blockSignals(True)
            self.supplier_filter.clear()
            self.supplier_filter.addItem("All Suppliers", None)
            for supplier in suppliers_service.list_suppliers(db, active_only=False):
                self.supplier_filter.addItem(supplier.name, supplier.id)
            self.supplier_filter.blockSignals(False)
        finally:
            db.close()

    def _reload(self) -> None:
        date_from, date_to = _date_range_to_datetimes(self.from_date, self.to_date)
        db = get_spare_session()
        try:
            report = reports_service.get_purchases_report(
                db, date_from=date_from, date_to=date_to,
                supplier_id=self.supplier_filter.currentData(),
            )
            rows = report["rows"]
            self.table.setRowCount(len(rows))
            for row, purchase in enumerate(rows):
                self.table.setItem(row, 0, QTableWidgetItem(purchase.purchase_no))
                self.table.setItem(row, 1, QTableWidgetItem(purchase.supplier.name if purchase.supplier else ""))
                self.table.setItem(row, 2, QTableWidgetItem(purchase.purchase_date.strftime("%Y-%m-%d")))
                self.table.setItem(row, 3, QTableWidgetItem(f"{float(purchase.total):,.2f}"))
                self.table.setItem(row, 4, QTableWidgetItem(f"{float(purchase.paid):,.2f}"))
                self.table.setItem(row, 5, QTableWidgetItem(f"{float(purchase.due):,.2f}"))
        finally:
            db.close()

        t = report["totals"]
        self.totals_label.setText(
            f"{t['count']} purchases - Subtotal: Rs. {t['subtotal']:,.2f} | "
            f"Total: Rs. {t['total']:,.2f} | Paid: Rs. {t['paid']:,.2f} | Due: Rs. {t['due']:,.2f}"
        )


class _ReceivablesPayablesTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        toolbar.addStretch(1)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setStyleSheet(_RESET_BTN)
        refresh_btn.clicked.connect(self._reload)
        toolbar.addWidget(refresh_btn)
        layout.addLayout(toolbar)

        columns_row = QHBoxLayout()

        receivables_box = QVBoxLayout()
        receivables_label = QLabel("Receivables (customers who owe us)")
        receivables_label.setStyleSheet("font-weight: bold; color: #e67e22;")
        receivables_box.addWidget(receivables_label)
        self.receivables_table = QTableWidget(0, 2)
        self.receivables_table.setHorizontalHeaderLabels(["Customer", "Balance"])
        self.receivables_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.receivables_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.receivables_table.verticalHeader().setVisible(False)
        receivables_box.addWidget(self.receivables_table)
        self.receivables_total_label = QLabel("")
        self.receivables_total_label.setStyleSheet("font-weight: bold; color: #e67e22;")
        self.receivables_total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        receivables_box.addWidget(self.receivables_total_label)
        columns_row.addLayout(receivables_box, 1)

        payables_box = QVBoxLayout()
        payables_label = QLabel("Payables (what we owe suppliers)")
        payables_label.setStyleSheet("font-weight: bold; color: #e74c3c;")
        payables_box.addWidget(payables_label)
        self.payables_table = QTableWidget(0, 2)
        self.payables_table.setHorizontalHeaderLabels(["Supplier", "Balance"])
        self.payables_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.payables_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.payables_table.verticalHeader().setVisible(False)
        payables_box.addWidget(self.payables_table)
        self.payables_total_label = QLabel("")
        self.payables_total_label.setStyleSheet("font-weight: bold; color: #e74c3c;")
        self.payables_total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        payables_box.addWidget(self.payables_total_label)
        columns_row.addLayout(payables_box, 1)

        layout.addLayout(columns_row, 1)

        self._reload()

    def _reload(self) -> None:
        db = get_spare_session()
        try:
            report = reports_service.get_receivables_payables_report(db)
        finally:
            db.close()

        receivables = report["receivables"]
        self.receivables_table.setRowCount(len(receivables))
        for row, entry in enumerate(receivables):
            self.receivables_table.setItem(row, 0, QTableWidgetItem(entry["party"].name))
            self.receivables_table.setItem(row, 1, QTableWidgetItem(f"{entry['balance']:,.2f}"))
        self.receivables_total_label.setText(f"Total Receivables: Rs. {report['total_receivables']:,.2f}")

        payables = report["payables"]
        self.payables_table.setRowCount(len(payables))
        for row, entry in enumerate(payables):
            self.payables_table.setItem(row, 0, QTableWidgetItem(entry["party"].name))
            self.payables_table.setItem(row, 1, QTableWidgetItem(f"{entry['balance']:,.2f}"))
        self.payables_total_label.setText(f"Total Payables: Rs. {report['total_payables']:,.2f}")


class ReportsPage(QWidget):
    """Top-level Reports tab: Stock / Reorder Suggestions / Sales / Profit /
    Warranty / Purchases / Receivables & Payables."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        sub_tabs = QTabWidget()
        self.stock_tab = _StockReportTab()
        self.reorder_suggestions_tab = _ReorderSuggestionsTab()
        self.sales_tab = _SalesReportTab()
        self.profit_tab = _ProfitReportTab()
        self.warranty_tab = _WarrantyLookupTab()
        self.purchases_tab = _PurchasesReportTab()
        self.receivables_payables_tab = _ReceivablesPayablesTab()
        sub_tabs.addTab(self.stock_tab, "Stock")
        sub_tabs.addTab(self.reorder_suggestions_tab, "Reorder Suggestions")
        sub_tabs.addTab(self.sales_tab, "Sales")
        sub_tabs.addTab(self.profit_tab, "Profit")
        sub_tabs.addTab(self.warranty_tab, "Warranty")
        sub_tabs.addTab(self.purchases_tab, "Purchases")
        sub_tabs.addTab(self.receivables_payables_tab, "Receivables && Payables")
        layout.addWidget(sub_tabs)

    def refresh(self) -> None:
        """Called by the host widget when this tab is selected, so the
        quick-glance sub-tabs (Stock levels, Reorder Suggestions,
        Receivables & Payables) don't show stale data after a
        sale/purchase/payment was recorded elsewhere. The Sales/Profit/
        Warranty/Purchases sub-tabs already have their own Refresh
        buttons since they're filter-driven, not glance-and-go."""
        self.stock_tab._reload()
        self.reorder_suggestions_tab._reload()
        self.receivables_payables_tab._reload()
