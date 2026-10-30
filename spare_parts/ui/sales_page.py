"""Sales: a durable list of every sale with its FBR submission status,
independent of the POS counter flow. Submission to FBR is manually
triggered here (never automatic on sale completion) since a call can
take up to ~70s and the POS counter is designed to move to the next
customer instantly - see spare_parts/services/fbr_submission_service.py.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from spare_parts.db.base import get_spare_session
from spare_parts.errors import SparePartsValidationError
from spare_parts.services import fbr_submission_service, sales_service
from spare_parts.ui.sale_card_widget import print_sale_receipt
from spare_parts.logging_config import get_logger

logger = get_logger(__name__)

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
    QPushButton:disabled { background-color: #f8f9fa; color: #bdc3c7; }
"""

_STATUS_COLORS = {
    "SUBMITTED": "#27ae60",
    "FAILED": "#e74c3c",
    "NOT_SUBMITTED": "#7f8c8d",
}


class FbrResponseDialog(QDialog):
    """Read-only view of a sale's last FBR error and/or raw response."""

    def __init__(self, sale, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"FBR Response - {sale.sale_no}")
        self.setMinimumSize(560, 400)
        layout = QVBoxLayout(self)

        status_label = QLabel(f"Status: {sale.fbr_submission_status}")
        status_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(status_label)

        if sale.fbr_invoice_number:
            layout.addWidget(QLabel(f"FBR Invoice Number: {sale.fbr_invoice_number}"))
        if sale.fbr_submitted_at:
            layout.addWidget(QLabel(f"Last attempt: {sale.fbr_submitted_at.strftime('%Y-%m-%d %H:%M:%S')}"))

        if sale.fbr_last_error:
            layout.addWidget(QLabel("Last Error:"))
            error_box = QPlainTextEdit(sale.fbr_last_error)
            error_box.setReadOnly(True)
            error_box.setMaximumHeight(80)
            layout.addWidget(error_box)

        layout.addWidget(QLabel("Raw FBR Response:"))
        response_box = QPlainTextEdit(sale.fbr_last_response or "(none yet)")
        response_box.setReadOnly(True)
        layout.addWidget(response_box, 1)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(_RESET_BTN)
        close_btn.clicked.connect(self.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)


class SalesPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._submitting = False
        self._row_sale_ids: list[int] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        header = QLabel("Sales")
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(header)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["Sale No.", "Type", "Customer", "Date", "Total", "Payment Method", "FBR Status", "FBR Invoice No."]
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)

        action_row = QHBoxLayout()
        self.submit_btn = QPushButton("Submit to FBR")
        self.submit_btn.setStyleSheet(_PRIMARY_BTN)
        self.submit_btn.clicked.connect(self._on_submit_clicked)
        action_row.addWidget(self.submit_btn)

        self.view_response_btn = QPushButton("View FBR Response")
        self.view_response_btn.setStyleSheet(_RESET_BTN)
        self.view_response_btn.clicked.connect(self._on_view_response_clicked)
        action_row.addWidget(self.view_response_btn)

        self.print_btn = QPushButton("Print Receipt")
        self.print_btn.setStyleSheet(_RESET_BTN)
        self.print_btn.setToolTip(
            "Prints the receipt with the FBR invoice number and QR code if "
            "this sale has already been submitted to FBR."
        )
        self.print_btn.clicked.connect(self._on_print_receipt_clicked)
        action_row.addWidget(self.print_btn)

        action_row.addStretch(1)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setStyleSheet(_RESET_BTN)
        refresh_btn.clicked.connect(self.reload)
        action_row.addWidget(refresh_btn)
        layout.addLayout(action_row)

        self.reload()

    def _selected_sale_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._row_sale_ids):
            return None
        return self._row_sale_ids[row]

    def reload(self) -> None:
        db = get_spare_session()
        try:
            sales = sales_service.list_sales(db)
            self._row_sale_ids = [s.id for s in sales]
            self.table.setRowCount(len(sales))
            for row, sale in enumerate(sales):
                self.table.setItem(row, 0, QTableWidgetItem(sale.sale_no))
                self.table.setItem(row, 1, QTableWidgetItem(sale.sale_type))
                customer_name = sale.customer.name if sale.customer else (sale.walk_in_customer_name or "Walk-in")
                self.table.setItem(row, 2, QTableWidgetItem(customer_name))
                self.table.setItem(row, 3, QTableWidgetItem(sale.sale_date.strftime("%Y-%m-%d %H:%M")))
                self.table.setItem(row, 4, QTableWidgetItem(f"{float(sale.total):,.2f}"))
                self.table.setItem(row, 5, QTableWidgetItem(sale.payment_method or ""))

                status_item = QTableWidgetItem(sale.fbr_submission_status)
                color = _STATUS_COLORS.get(sale.fbr_submission_status)
                if color:
                    status_item.setForeground(QColor(color))
                self.table.setItem(row, 6, status_item)
                self.table.setItem(row, 7, QTableWidgetItem(sale.fbr_invoice_number or ""))
        finally:
            db.close()

    def _on_submit_clicked(self) -> None:
        if self._submitting:
            return
        sale_id = self._selected_sale_id()
        if sale_id is None:
            QMessageBox.information(self, "No Selection", "Select a sale first.")
            return

        db = get_spare_session()
        try:
            sale = sales_service.get_sale(db, sale_id)
            if not sale:
                QMessageBox.critical(self, "Error", f"Sale id={sale_id} not found.")
                return
            if sale.status == "CANCELLED":
                QMessageBox.warning(self, "Not Submittable", "A cancelled sale cannot be submitted to FBR.")
                return
            force = False
            if sale.fbr_submission_status == "SUBMITTED":
                answer = QMessageBox.question(
                    self, "Resubmit?",
                    f"Sale {sale.sale_no} was already submitted to FBR "
                    f"(Invoice Number: {sale.fbr_invoice_number}).\n\nResubmit anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return
                force = True
        finally:
            db.close()

        self._submitting = True
        self.submit_btn.setEnabled(False)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            db = get_spare_session()
            try:
                sale = fbr_submission_service.submit_sale_to_fbr(db, sale_id, force=force)
            finally:
                db.close()
            QMessageBox.information(
                self, "Submitted",
                f"Sale {sale.sale_no} submitted to FBR.\nInvoice Number: {sale.fbr_invoice_number}",
            )
        except SparePartsValidationError as e:
            QMessageBox.critical(self, "FBR Submission Failed", str(e))
        except Exception as e:
            logger.error(f"Unexpected error submitting sale {sale_id} to FBR: {e}", exc_info=True)
            QMessageBox.critical(self, "Unexpected Error", str(e))
        finally:
            QApplication.restoreOverrideCursor()
            self._submitting = False
            self.submit_btn.setEnabled(True)
            self.reload()

    def _on_view_response_clicked(self) -> None:
        sale_id = self._selected_sale_id()
        if sale_id is None:
            QMessageBox.information(self, "No Selection", "Select a sale first.")
            return
        db = get_spare_session()
        try:
            sale = sales_service.get_sale(db, sale_id)
            if not sale:
                QMessageBox.critical(self, "Error", f"Sale id={sale_id} not found.")
                return
            dlg = FbrResponseDialog(sale, parent=self)
            dlg.exec()
        finally:
            db.close()

    def _on_print_receipt_clicked(self) -> None:
        sale_id = self._selected_sale_id()
        if sale_id is None:
            QMessageBox.information(self, "No Selection", "Select a sale first.")
            return
        try:
            print_sale_receipt(sale_id, parent=self)
        except Exception as e:
            logger.error(f"Receipt printing failed for sale id={sale_id}: {e}", exc_info=True)
            QMessageBox.warning(self, "Printing Failed", f"Could not print the receipt:\n{e}")
