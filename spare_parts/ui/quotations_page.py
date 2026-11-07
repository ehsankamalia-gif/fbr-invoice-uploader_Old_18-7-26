"""Quotations: a pre-sale price quote - see
spare_parts/services/quotations_service.py for the full rationale (no
stock reservation, honors the quoted price verbatim on conversion).

Item entry closely mirrors purchase_page.py's PurchaseDialog (search/
completer, add/remove line, recalc totals) - the closest existing
analog, since SaleCardWidget is deeply tied to multi-card POS state,
Hold/Resume, and automatic FBR submission on completion that a
quotation has no need for.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from PyQt6.QtCore import QDate, QSize, Qt
from PyQt6.QtGui import QKeySequence, QShortcut, QTextDocument
from PyQt6.QtWidgets import (
    QCompleter,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from spare_parts.db.base import get_spare_session
from spare_parts.errors import SparePartsValidationError
from spare_parts.services import customers_service, parts_service, quotations_service
from spare_parts.ui.sale_card_widget import _get_main_app_company_info
from spare_parts.ui.widgets import NoScrollComboBox, NoScrollDateEdit, NoScrollDoubleSpinBox, NoScrollSpinBox, trash_icon
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
"""

_DANGER_BTN = """
    QPushButton {
        background-color: #fdecea; color: #e74c3c; border: 1px solid #f5c6cb;
        border-radius: 4px; padding: 8px 16px;
    }
    QPushButton:hover { background-color: #fadbd8; }
"""

_REMOVE_LINE_ICON_QSS = """
    QPushButton {
        background-color: #fdecea; color: #e74c3c; border: 1px solid #f5b7b1;
        border-radius: 13px; font-weight: bold; font-size: 13px; padding: 0px;
    }
    QPushButton:hover { background-color: #e74c3c; color: white; border-color: #e74c3c; }
    QPushButton:pressed { background-color: #c0392b; border-color: #c0392b; }
"""

_WALK_IN_LABEL = "(Walk-in / No customer)"
_ITEM_COLUMNS = ["Part", "Qty", "Price", "Discount", "Line Total", ""]


def print_quotation(quotation_id: int, parent=None) -> None:
    """Prints a quotation document - same QTextDocument/QPrinter pattern
    as sale_card_widget.print_sale_receipt, titled "Quotation" rather
    than "Receipt", with no FBR/stock info (a quotation is a document,
    not a fiscal transaction)."""
    try:
        from PyQt6.QtPrintSupport import QPrintDialog, QPrinter
    except ImportError:
        QMessageBox.warning(parent, "Printing Unavailable", "Print support is not installed.")
        return

    db = get_spare_session()
    try:
        quotation = quotations_service.get_quotation(db, quotation_id)
        if not quotation:
            QMessageBox.warning(parent, "Not Found", "Could not reload the quotation to print.")
            return
        company_info = _get_main_app_company_info(db)
        company_name = company_info["name"].strip()
        company_address = company_info["address"].strip()
        company_phone = company_info["phone"].strip()
        customer_name = (
            quotation.customer.name if quotation.customer
            else (quotation.walk_in_customer_name or "Walk-in")
        )

        lines = []
        if company_name:
            lines.append(f"<h2 align='center'>{company_name}</h2>")
        if company_address or company_phone:
            contact_bits = [bit for bit in (company_address, f"Ph: {company_phone}" if company_phone else "") if bit]
            lines.append(f"<p align='center' style='margin-top:-6px;'>{' | '.join(contact_bits)}</p>")
        lines.append(f"<h3 align='center'>Quotation - {quotation.quote_no}</h3>")
        lines.append(f"<p>Date: {quotation.quote_date.strftime('%Y-%m-%d')}<br/>")
        if quotation.valid_until:
            lines.append(f"Valid Until: {quotation.valid_until.strftime('%Y-%m-%d')}<br/>")
        lines.append(f"Customer: {customer_name}</p>")
        lines.append("<table width='100%' cellspacing='4'><tr><th align='left'>Part</th>"
                      "<th align='right'>Qty</th><th align='right'>Price</th>"
                      "<th align='right'>Total</th></tr>")
        for item in quotation.items:
            part_name = item.part.name if item.part else f"Part #{item.part_id}"
            lines.append(
                f"<tr><td>{part_name}</td><td align='right'>{item.qty}</td>"
                f"<td align='right'>{float(item.unit_price):,.2f}</td>"
                f"<td align='right'>{float(item.line_total):,.2f}</td></tr>"
            )
        lines.append("</table>")
        lines.append(
            f"<p align='right'>Subtotal: {float(quotation.subtotal):,.2f}<br/>"
            f"Discount: {float(quotation.discount):,.2f}<br/>"
            f"Tax: {float(quotation.tax_amount):,.2f}<br/>"
            f"<b>Total: {float(quotation.total):,.2f}</b></p>"
        )
        html = "".join(lines)
    finally:
        db.close()

    document = QTextDocument()
    document.setHtml(html)
    printer = QPrinter()
    dialog = QPrintDialog(printer, parent)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        document.print(printer)


class QuotationDialog(QDialog):
    """New quotation entry, or a view/edit of an existing one - editable
    while DRAFT, read-only once CONVERTED/CANCELLED."""

    def __init__(self, quotation_id: int | None = None, parent=None):
        super().__init__(parent)
        self.quotation_id = quotation_id
        self._saving = False
        self._dirty = False
        self._status = "DRAFT"
        self.setWindowTitle("New Quotation" if quotation_id is None else "Quotation")
        self.setMinimumSize(780, 560)

        root = QVBoxLayout(self)

        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("Customer"))
        self.customer_combo = NoScrollComboBox()
        self.customer_combo.setEditable(True)
        self.customer_combo.setInsertPolicy(NoScrollComboBox.InsertPolicy.NoInsert)
        header_row.addWidget(self.customer_combo, 2)

        header_row.addWidget(QLabel("Type"))
        self.sale_type_combo = NoScrollComboBox()
        self.sale_type_combo.addItems(["RETAIL", "WHOLESALE"])
        header_row.addWidget(self.sale_type_combo)

        header_row.addWidget(QLabel("Valid Until"))
        self.valid_until_date = NoScrollDateEdit()
        self.valid_until_date.setCalendarPopup(True)
        self.valid_until_date.setDate(QDate.currentDate().addDays(30))
        header_row.addWidget(self.valid_until_date)
        root.addLayout(header_row)

        notes_row = QHBoxLayout()
        notes_row.addWidget(QLabel("Notes"))
        self.notes_input = QLineEdit()
        notes_row.addWidget(self.notes_input, 1)
        root.addLayout(notes_row)

        search_row = QHBoxLayout()
        self.part_search_input = QLineEdit()
        self.part_search_input.setPlaceholderText("Scan barcode or search part no / name, then Enter...")
        self.part_search_input.returnPressed.connect(self._on_part_search_enter)
        search_row.addWidget(self.part_search_input)
        root.addLayout(search_row)

        self.items_table = QTableWidget(0, len(_ITEM_COLUMNS))
        self.items_table.setHorizontalHeaderLabels(_ITEM_COLUMNS)
        self.items_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.items_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.items_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.items_table.verticalHeader().setMinimumSectionSize(36)
        self.items_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        root.addWidget(self.items_table, 1)

        line_actions_row = QHBoxLayout()
        line_actions_row.addStretch(1)
        self.remove_line_btn = QPushButton("Remove Selected Line")
        self.remove_line_btn.setStyleSheet(_DANGER_BTN)
        self.remove_line_btn.setAutoDefault(False)
        self.remove_line_btn.clicked.connect(self._on_remove_selected_line)
        line_actions_row.addWidget(self.remove_line_btn)
        root.addLayout(line_actions_row)

        totals_row = QHBoxLayout()
        totals_row.addStretch(1)
        totals_row.addWidget(QLabel("Subtotal:"))
        self.subtotal_label = QLabel("0.00")
        self.subtotal_label.setStyleSheet("font-weight: bold;")
        totals_row.addWidget(self.subtotal_label)

        totals_row.addWidget(QLabel("  Discount:"))
        self.discount_spin = NoScrollDoubleSpinBox()
        self.discount_spin.setRange(0, 99_999_999)
        self.discount_spin.setDecimals(2)
        self.discount_spin.valueChanged.connect(self._recalc_totals)
        self.discount_spin.setFixedWidth(110)
        totals_row.addWidget(self.discount_spin)

        totals_row.addWidget(QLabel("  Tax %:"))
        self.tax_percent_spin = NoScrollDoubleSpinBox()
        self.tax_percent_spin.setRange(0, 100)
        self.tax_percent_spin.setDecimals(2)
        self.tax_percent_spin.valueChanged.connect(self._recalc_totals)
        self.tax_percent_spin.setFixedWidth(80)
        totals_row.addWidget(self.tax_percent_spin)

        totals_row.addWidget(QLabel("  Total:"))
        self.total_label = QLabel("0.00")
        self.total_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #2c3e50;")
        totals_row.addWidget(self.total_label)
        root.addLayout(totals_row)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        root.addWidget(self.error_label)

        btn_row = QHBoxLayout()
        self.cancel_quote_btn = QPushButton("Cancel Quotation")
        self.cancel_quote_btn.setStyleSheet(_DANGER_BTN)
        self.cancel_quote_btn.setAutoDefault(False)
        self.cancel_quote_btn.clicked.connect(self._on_cancel_quotation_clicked)
        self.cancel_quote_btn.setVisible(False)
        btn_row.addWidget(self.cancel_quote_btn)
        btn_row.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(_RESET_BTN)
        close_btn.setAutoDefault(False)
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)
        self.convert_btn = QPushButton("Convert to Sale")
        self.convert_btn.setStyleSheet(_PRIMARY_BTN)
        self.convert_btn.clicked.connect(self._on_convert_clicked)
        self.convert_btn.setVisible(False)
        btn_row.addWidget(self.convert_btn)
        self.save_btn = QPushButton("Save Draft (Ctrl+S)")
        self.save_btn.setStyleSheet(_PRIMARY_BTN)
        self.save_btn.clicked.connect(self._on_save_clicked)
        btn_row.addWidget(self.save_btn)
        root.addLayout(btn_row)

        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.reject)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._on_save_clicked)

        self._customers_by_id: dict[int, object] = {}
        self._parts_by_barcode: dict[str, object] = {}
        self._parts_by_part_no: dict[str, object] = {}
        self._parts_completer_map: dict[str, object] = {}
        self._reload_customers()
        self._reload_parts_lookup()

        if quotation_id:
            self._load_quotation(quotation_id)
        else:
            self.part_search_input.setFocus()

    # --- lookups -----------------------------------------------------------

    def _reload_customers(self) -> None:
        db = get_spare_session()
        try:
            self._customers_by_id = {
                c.id: c for c in customers_service.list_customers(db, active_only=True)
            }
            self.customer_combo.clear()
            self.customer_combo.addItem(_WALK_IN_LABEL, None)
            for customer in self._customers_by_id.values():
                self.customer_combo.addItem(f"{customer.name} ({customer.type})", customer.id)
        finally:
            db.close()

    def _reload_parts_lookup(self) -> None:
        db = get_spare_session()
        try:
            parts = parts_service.search_parts(db, active_only=True)
            self._parts_by_barcode = {p.barcode.upper(): p for p in parts if p.barcode}
            self._parts_by_part_no = {p.part_no.upper(): p for p in parts}
            self._parts_completer_map = {f"{p.part_no} - {p.name}": p for p in parts}
            completer = QCompleter(list(self._parts_completer_map.keys()), self)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
            completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
            completer.activated.connect(self._on_part_completer_activated)
            self.part_search_input.setCompleter(completer)
        finally:
            db.close()

    def _typed_walk_in_customer_name(self) -> str:
        if self.customer_combo.currentData():
            return ""
        typed = self.customer_combo.currentText().strip()
        if typed and typed != _WALK_IN_LABEL:
            return typed
        return ""

    def _default_price_for(self, part) -> Decimal:
        is_wholesale = self.sale_type_combo.currentText() == "WHOLESALE"
        return Decimal(str((part.wholesale_price if is_wholesale else part.retail_price) or 0))

    # --- part search / line items -------------------------------------------

    def _on_part_completer_activated(self, text: str) -> None:
        part = self._parts_completer_map.get(text)
        if part:
            self._add_line_item(part)
            self.part_search_input.clear()

    def _on_part_search_enter(self) -> None:
        text = self.part_search_input.text().strip()
        if not text:
            return
        key = text.upper()
        part = self._parts_by_barcode.get(key) or self._parts_by_part_no.get(key)
        if not part:
            matches = [p for label, p in self._parts_completer_map.items() if key in label.upper()]
            part = matches[0] if len(matches) == 1 else None
        if not part:
            QMessageBox.warning(self, "Part Not Found", f"No active part matches '{text}'.")
            return
        self._add_line_item(part)
        self.part_search_input.clear()

    def _find_row_for_part(self, part_id: int) -> int | None:
        for row in range(self.items_table.rowCount()):
            part_item = self.items_table.item(row, 0)
            if part_item and part_item.data(Qt.ItemDataRole.UserRole) == part_id:
                return row
        return None

    def _add_line_item(self, part, qty: int = 1, unit_price=None, discount=0) -> None:
        existing_row = self._find_row_for_part(part.id)
        if existing_row is not None and unit_price is None:
            qty_widget = self.items_table.cellWidget(existing_row, 1)
            qty_widget.setValue(qty_widget.value() + 1)
            self._dirty = True
            self._recalc_totals()
            return

        row = self.items_table.rowCount()
        self.items_table.insertRow(row)

        part_item = QTableWidgetItem(f"{part.part_no} - {part.name}")
        part_item.setFlags(part_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        part_item.setData(Qt.ItemDataRole.UserRole, part.id)
        self.items_table.setItem(row, 0, part_item)

        qty_spin = NoScrollSpinBox()
        qty_spin.setRange(1, 1_000_000)
        qty_spin.setValue(qty)
        qty_spin.valueChanged.connect(self._recalc_totals)
        self.items_table.setCellWidget(row, 1, qty_spin)

        price_spin = NoScrollDoubleSpinBox()
        price_spin.setRange(0, 99_999_999)
        price_spin.setDecimals(2)
        price_spin.setValue(float(unit_price if unit_price is not None else self._default_price_for(part)))
        price_spin.valueChanged.connect(self._recalc_totals)
        self.items_table.setCellWidget(row, 2, price_spin)

        discount_spin = NoScrollDoubleSpinBox()
        discount_spin.setRange(0, 99_999_999)
        discount_spin.setDecimals(2)
        discount_spin.setValue(float(discount or 0))
        discount_spin.valueChanged.connect(self._recalc_totals)
        self.items_table.setCellWidget(row, 3, discount_spin)

        line_total_item = QTableWidgetItem("0.00")
        line_total_item.setFlags(line_total_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.items_table.setItem(row, 4, line_total_item)

        remove_btn = QPushButton()
        remove_btn.setIcon(trash_icon(14))
        remove_btn.setIconSize(QSize(14, 14))
        remove_btn.setFixedSize(26, 26)
        remove_btn.setToolTip("Remove this line")
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.setStyleSheet(_REMOVE_LINE_ICON_QSS)
        remove_btn.setAutoDefault(False)
        remove_btn.clicked.connect(lambda: self._remove_line_item(remove_btn))
        self.items_table.setCellWidget(row, 5, remove_btn)

        self._dirty = True
        self._recalc_totals()

    def _remove_line_item(self, btn) -> None:
        for row in range(self.items_table.rowCount()):
            if self.items_table.cellWidget(row, 5) is btn:
                self.items_table.removeRow(row)
                break
        self._recalc_totals()

    def _on_remove_selected_line(self) -> None:
        row = self.items_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "No Line Selected", "Click a line in the table first.")
            return
        self.items_table.removeRow(row)
        self._recalc_totals()

    def _recalc_totals(self) -> None:
        subtotal = Decimal("0")
        for row in range(self.items_table.rowCount()):
            qty_widget = self.items_table.cellWidget(row, 1)
            price_widget = self.items_table.cellWidget(row, 2)
            discount_widget = self.items_table.cellWidget(row, 3)
            if not (qty_widget and price_widget and discount_widget):
                continue
            qty = qty_widget.value()
            unit_price = Decimal(str(price_widget.value()))
            discount = Decimal(str(discount_widget.value()))
            line_total = (unit_price * qty) - discount
            if line_total < 0:
                line_total = Decimal("0")
            item = self.items_table.item(row, 4)
            if item:
                item.setText(f"{line_total:,.2f}")
            subtotal += line_total

        self.subtotal_label.setText(f"{subtotal:,.2f}")
        header_discount = Decimal(str(self.discount_spin.value()))
        taxable = subtotal - header_discount
        if taxable < 0:
            taxable = Decimal("0")
        tax_pct = Decimal(str(self.tax_percent_spin.value()))
        tax_amount = (taxable * tax_pct / Decimal("100")).quantize(Decimal("0.01"))
        total = taxable + tax_amount
        self.total_label.setText(f"{total:,.2f}")

    # --- load / view mode ----------------------------------------------------

    def _load_quotation(self, quotation_id: int) -> None:
        db = get_spare_session()
        try:
            quotation = quotations_service.get_quotation(db, quotation_id)
            if not quotation:
                QMessageBox.critical(self, "Error", f"Quotation id={quotation_id} not found.")
                self.reject()
                return
            self._status = quotation.status
            self.setWindowTitle(f"Quotation - {quotation.quote_no}")

            if quotation.customer_id:
                idx = self.customer_combo.findData(quotation.customer_id)
                if idx >= 0:
                    self.customer_combo.setCurrentIndex(idx)
            elif quotation.walk_in_customer_name:
                self.customer_combo.setCurrentText(quotation.walk_in_customer_name)

            self.sale_type_combo.setCurrentText(quotation.sale_type)
            if quotation.valid_until:
                self.valid_until_date.setDate(
                    QDate(quotation.valid_until.year, quotation.valid_until.month, quotation.valid_until.day)
                )
            self.notes_input.setText(quotation.notes or "")
            self.discount_spin.blockSignals(True)
            self.discount_spin.setValue(float(quotation.discount or 0))
            self.discount_spin.blockSignals(False)
            self.tax_percent_spin.blockSignals(True)
            self.tax_percent_spin.setValue(float(quotation.tax_percent or 0))
            self.tax_percent_spin.blockSignals(False)

            for item in quotation.items:
                part = item.part
                if part:
                    qty_entered = item.pack_qty if item.sold_as == "PACK" else item.qty
                    self._add_line_item(part, qty=qty_entered, unit_price=item.unit_price, discount=item.discount)

            self._recalc_totals()
            self._dirty = False
        finally:
            db.close()

        if self._status != "DRAFT":
            self._set_view_only_mode()
        else:
            self.cancel_quote_btn.setVisible(True)
            self.convert_btn.setVisible(True)

    def _set_view_only_mode(self) -> None:
        self.customer_combo.setEnabled(False)
        self.sale_type_combo.setEnabled(False)
        self.valid_until_date.setEnabled(False)
        self.notes_input.setReadOnly(True)
        self.discount_spin.setEnabled(False)
        self.tax_percent_spin.setEnabled(False)
        self.part_search_input.setEnabled(False)
        self.remove_line_btn.setEnabled(False)
        self.save_btn.setVisible(False)
        self.cancel_quote_btn.setVisible(False)
        self.convert_btn.setVisible(False)
        for row in range(self.items_table.rowCount()):
            for col in (1, 2, 3):
                widget = self.items_table.cellWidget(row, col)
                if widget:
                    widget.setEnabled(False)
            remove_btn = self.items_table.cellWidget(row, 5)
            if remove_btn:
                remove_btn.setVisible(False)

    # --- save / convert / cancel ---------------------------------------------

    def _collect_items_payload(self) -> list[dict]:
        items = []
        for row in range(self.items_table.rowCount()):
            part_item = self.items_table.item(row, 0)
            qty_widget = self.items_table.cellWidget(row, 1)
            price_widget = self.items_table.cellWidget(row, 2)
            discount_widget = self.items_table.cellWidget(row, 3)
            items.append(dict(
                part_id=part_item.data(Qt.ItemDataRole.UserRole),
                qty_entered=qty_widget.value(),
                unit_price=price_widget.value(),
                discount=discount_widget.value(),
            ))
        return items

    def _on_save_clicked(self) -> None:
        if self._saving:
            return
        self._saving = True
        self.save_btn.setEnabled(False)
        self.error_label.hide()
        try:
            items = self._collect_items_payload()
            if not items:
                raise SparePartsValidationError("Add at least one item.")
            qdate = self.valid_until_date.date()
            valid_until = dt.datetime(qdate.year(), qdate.month(), qdate.day())

            db = get_spare_session()
            try:
                if self.quotation_id:
                    quotation = quotations_service.update_quotation(
                        db, self.quotation_id, items=items,
                        discount=self.discount_spin.value(),
                        tax_percent=self.tax_percent_spin.value(),
                        notes=self.notes_input.text(),
                        valid_until=valid_until,
                    )
                else:
                    quotation = quotations_service.create_quotation(
                        db,
                        sale_type=self.sale_type_combo.currentText(),
                        customer_id=self.customer_combo.currentData(),
                        walk_in_customer_name=self._typed_walk_in_customer_name(),
                        items=items,
                        valid_until=valid_until,
                        discount=self.discount_spin.value(),
                        tax_percent=self.tax_percent_spin.value(),
                        notes=self.notes_input.text(),
                    )
                    self.quotation_id = quotation.id
            finally:
                db.close()
            self._dirty = False
            self.setWindowTitle(f"Quotation - {quotation.quote_no}")
            self.cancel_quote_btn.setVisible(True)
            self.convert_btn.setVisible(True)
            QMessageBox.information(self, "Saved", f"Quotation {quotation.quote_no} saved.")
        except SparePartsValidationError as e:
            self.error_label.setText(str(e))
            self.error_label.show()
        except Exception as e:
            logger.error(f"Unexpected error saving quotation: {e}", exc_info=True)
            self.error_label.setText(f"Unexpected error: {e}")
            self.error_label.show()
        finally:
            self._saving = False
            self.save_btn.setEnabled(True)

    def _on_convert_clicked(self) -> None:
        if not self.quotation_id:
            QMessageBox.information(self, "Save First", "Save this quotation as a draft before converting it.")
            return

        db = get_spare_session()
        try:
            quotation = quotations_service.get_quotation(db, self.quotation_id)
            if not quotation:
                QMessageBox.critical(self, "Error", "Quotation not found.")
                return
            if quotation.sale_type == "WHOLESALE" and quotation.customer_id:
                within, projected, limit = customers_service.check_credit_limit(
                    db, quotation.customer_id, quotation.total,
                )
                if not within:
                    customer = quotation.customer
                    confirm = QMessageBox.question(
                        self, "Credit Limit Exceeded",
                        f"Converting this quotation would put {customer.name if customer else 'this customer'} "
                        f"at Rs. {projected:,.2f} against their Rs. {limit:,.2f} credit limit. "
                        f"Proceed anyway?",
                    )
                    if confirm != QMessageBox.StandardButton.Yes:
                        return
        finally:
            db.close()

        confirm = QMessageBox.question(
            self, "Convert to Sale?",
            "This will create a real sale from this quotation (stock will be reduced) "
            "and lock the quotation from further edits. Continue?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        db = get_spare_session()
        try:
            sale = quotations_service.convert_to_sale(db, self.quotation_id)
        except SparePartsValidationError as e:
            QMessageBox.warning(self, "Could Not Convert", str(e))
            return
        finally:
            db.close()
        QMessageBox.information(self, "Converted", f"Sale {sale.sale_no} created from this quotation.")
        self.accept()

    def _on_cancel_quotation_clicked(self) -> None:
        if not self.quotation_id:
            self.reject()
            return
        confirm = QMessageBox.question(
            self, "Cancel Quotation?", "Mark this quotation as cancelled? This cannot be undone.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        db = get_spare_session()
        try:
            quotations_service.cancel_quotation(db, self.quotation_id)
        except SparePartsValidationError as e:
            QMessageBox.warning(self, "Could Not Cancel", str(e))
            return
        finally:
            db.close()
        self.accept()


class QuotationsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        header = QLabel("Quotations")
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(header)

        toolbar = QHBoxLayout()
        toolbar.addStretch(1)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setStyleSheet(_RESET_BTN)
        refresh_btn.clicked.connect(self.reload)
        toolbar.addWidget(refresh_btn)
        new_btn = QPushButton("+ New Quotation")
        new_btn.setStyleSheet(_PRIMARY_BTN)
        new_btn.clicked.connect(self._on_new_clicked)
        toolbar.addWidget(new_btn)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Quote No.", "Customer", "Date", "Type", "Total", "Status"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._on_open_clicked)
        layout.addWidget(self.table, 1)

        bottom_row = QHBoxLayout()
        open_btn = QPushButton("Open Selected")
        open_btn.setStyleSheet(_RESET_BTN)
        open_btn.clicked.connect(self._on_open_clicked)
        bottom_row.addWidget(open_btn)
        print_btn = QPushButton("Print Selected")
        print_btn.setStyleSheet(_RESET_BTN)
        print_btn.clicked.connect(self._on_print_clicked)
        bottom_row.addWidget(print_btn)
        bottom_row.addStretch(1)
        layout.addLayout(bottom_row)

        self.reload()

    def reload(self) -> None:
        db = get_spare_session()
        try:
            quotations = quotations_service.list_quotations(db)
            self.table.setRowCount(len(quotations))
            for row, quote in enumerate(quotations):
                no_item = QTableWidgetItem(quote.quote_no)
                no_item.setData(Qt.ItemDataRole.UserRole, quote.id)
                self.table.setItem(row, 0, no_item)
                customer_name = quote.customer.name if quote.customer else (quote.walk_in_customer_name or "Walk-in")
                self.table.setItem(row, 1, QTableWidgetItem(customer_name))
                self.table.setItem(row, 2, QTableWidgetItem(quote.quote_date.strftime("%Y-%m-%d")))
                self.table.setItem(row, 3, QTableWidgetItem(quote.sale_type))
                self.table.setItem(row, 4, QTableWidgetItem(f"{float(quote.total):,.2f}"))
                self.table.setItem(row, 5, QTableWidgetItem(quote.status))
        finally:
            db.close()

    def _selected_quotation_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_new_clicked(self) -> None:
        dlg = QuotationDialog(parent=self)
        if dlg.exec():
            self.reload()

    def _on_open_clicked(self) -> None:
        quotation_id = self._selected_quotation_id()
        if not quotation_id:
            QMessageBox.information(self, "No Selection", "Select a quotation first.")
            return
        dlg = QuotationDialog(quotation_id, parent=self)
        dlg.exec()
        self.reload()

    def _on_print_clicked(self) -> None:
        quotation_id = self._selected_quotation_id()
        if not quotation_id:
            QMessageBox.information(self, "No Selection", "Select a quotation first.")
            return
        try:
            print_quotation(quotation_id, parent=self)
        except Exception as e:
            logger.error(f"Printing failed for quotation id={quotation_id}: {e}", exc_info=True)
            QMessageBox.warning(self, "Printing Failed", f"Could not print the quotation:\n{e}")
