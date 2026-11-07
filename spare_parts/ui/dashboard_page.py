"""Dashboard: at-a-glance stat cards, low-stock alerts, and recent
activity - built entirely from spare_parts/services/reports_service.py.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from spare_parts.db.base import get_spare_session
from spare_parts.services import reports_service

_RESET_BTN = """
    QPushButton {
        background-color: #f8f9fa; color: #6c757d; border: 1px solid #dee2e6;
        border-radius: 4px; padding: 8px 16px;
    }
    QPushButton:hover { background-color: #e2e6ea; }
"""


def _stat_card(title: str, value: str, color: str) -> QFrame:
    card = QFrame()
    card.setStyleSheet(
        f"QFrame {{ background-color: white; border-left: 4px solid {color}; "
        f"border-radius: 4px; padding: 4px; }}"
    )
    layout = QVBoxLayout(card)
    title_label = QLabel(title)
    title_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")
    layout.addWidget(title_label)
    value_label = QLabel(value)
    value_label.setStyleSheet(f"color: {color}; font-size: 22px; font-weight: bold;")
    layout.addWidget(value_label)
    card.value_label = value_label  # type: ignore[attr-defined]
    return card


class DashboardPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        header_row = QHBoxLayout()
        header = QLabel("Dashboard")
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #2c3e50;")
        header_row.addWidget(header)
        header_row.addStretch(1)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setStyleSheet(_RESET_BTN)
        refresh_btn.clicked.connect(self.refresh)
        header_row.addWidget(refresh_btn)
        layout.addLayout(header_row)

        cards_grid = QGridLayout()
        cards_grid.setSpacing(12)
        self.stock_value_card = _stat_card("Total Stock Value", "0.00", "#3498db")
        self.today_sales_card = _stat_card("Today's Sales", "0 / Rs. 0.00", "#27ae60")
        self.today_purchases_card = _stat_card("Today's Purchases", "0 / Rs. 0.00", "#8e44ad")
        self.receivables_card = _stat_card("Total Receivables", "0.00", "#e67e22")
        self.payables_card = _stat_card("Total Payables", "0.00", "#e74c3c")
        cards_grid.addWidget(self.stock_value_card, 0, 0)
        cards_grid.addWidget(self.today_sales_card, 0, 1)
        cards_grid.addWidget(self.today_purchases_card, 0, 2)
        cards_grid.addWidget(self.receivables_card, 0, 3)
        cards_grid.addWidget(self.payables_card, 0, 4)
        layout.addLayout(cards_grid)

        tables_row = QHBoxLayout()

        low_stock_box = QVBoxLayout()
        low_stock_label = QLabel("Low Stock Alerts")
        low_stock_label.setStyleSheet("font-weight: bold; color: #e74c3c;")
        low_stock_box.addWidget(low_stock_label)
        self.low_stock_table = QTableWidget(0, 3)
        self.low_stock_table.setHorizontalHeaderLabels(["Part", "Stock", "Reorder At"])
        self.low_stock_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.low_stock_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.low_stock_table.verticalHeader().setVisible(False)
        low_stock_box.addWidget(self.low_stock_table)
        tables_row.addLayout(low_stock_box, 1)

        recent_sales_box = QVBoxLayout()
        recent_sales_label = QLabel("Recent Sales")
        recent_sales_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        recent_sales_box.addWidget(recent_sales_label)
        self.recent_sales_table = QTableWidget(0, 3)
        self.recent_sales_table.setHorizontalHeaderLabels(["Sale No.", "Date", "Total"])
        self.recent_sales_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.recent_sales_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.recent_sales_table.verticalHeader().setVisible(False)
        recent_sales_box.addWidget(self.recent_sales_table)
        tables_row.addLayout(recent_sales_box, 1)

        recent_purchases_box = QVBoxLayout()
        recent_purchases_label = QLabel("Recent Purchases")
        recent_purchases_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        recent_purchases_box.addWidget(recent_purchases_label)
        self.recent_purchases_table = QTableWidget(0, 3)
        self.recent_purchases_table.setHorizontalHeaderLabels(["Purchase No.", "Date", "Total"])
        self.recent_purchases_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.recent_purchases_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.recent_purchases_table.verticalHeader().setVisible(False)
        recent_purchases_box.addWidget(self.recent_purchases_table)
        tables_row.addLayout(recent_purchases_box, 1)

        layout.addLayout(tables_row, 1)

        self.refresh()

    def refresh(self) -> None:
        db = get_spare_session()
        try:
            summary = reports_service.get_dashboard_summary(db)
        finally:
            db.close()

        self.stock_value_card.value_label.setText(f"Rs. {summary['total_stock_value']:,.2f}")
        self.today_sales_card.value_label.setText(
            f"{summary['today_sales_count']} / Rs. {summary['today_sales_total']:,.2f}"
        )
        self.today_purchases_card.value_label.setText(
            f"{summary['today_purchases_count']} / Rs. {summary['today_purchases_total']:,.2f}"
        )
        self.receivables_card.value_label.setText(f"Rs. {summary['total_receivables']:,.2f}")
        self.payables_card.value_label.setText(f"Rs. {summary['total_payables']:,.2f}")

        low_stock = summary["low_stock_rows"]
        self.low_stock_table.setRowCount(len(low_stock))
        for row, entry in enumerate(low_stock):
            part = entry["part"]
            self.low_stock_table.setItem(row, 0, QTableWidgetItem(f"{part.part_no} - {part.name}"))
            stock_item = QTableWidgetItem(str(entry["current_stock"]))
            stock_item.setForeground(Qt.GlobalColor.red)
            self.low_stock_table.setItem(row, 1, stock_item)
            self.low_stock_table.setItem(row, 2, QTableWidgetItem(str(part.reorder_level)))

        recent_sales = summary["recent_sales"]
        self.recent_sales_table.setRowCount(len(recent_sales))
        for row, sale in enumerate(recent_sales):
            self.recent_sales_table.setItem(row, 0, QTableWidgetItem(sale.sale_no))
            self.recent_sales_table.setItem(row, 1, QTableWidgetItem(sale.sale_date.strftime("%Y-%m-%d")))
            self.recent_sales_table.setItem(row, 2, QTableWidgetItem(f"{float(sale.total):,.2f}"))

        recent_purchases = summary["recent_purchases"]
        self.recent_purchases_table.setRowCount(len(recent_purchases))
        for row, purchase in enumerate(recent_purchases):
            self.recent_purchases_table.setItem(row, 0, QTableWidgetItem(purchase.purchase_no))
            self.recent_purchases_table.setItem(row, 1, QTableWidgetItem(purchase.purchase_date.strftime("%Y-%m-%d")))
            self.recent_purchases_table.setItem(row, 2, QTableWidgetItem(f"{float(purchase.total):,.2f}"))
