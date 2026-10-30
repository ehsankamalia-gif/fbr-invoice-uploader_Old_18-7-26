"""One sale-in-progress "card" for the multi-card POS screen
(spare_parts/ui/pos_page.py). Each card holds its own customer, items,
and totals completely independently of any other open card. Retail vs
Wholesale is chosen per LINE, not for the whole card - each row picks
its own price (retail_price or wholesale_price) and whether PACK selling
is available; the card's header "Sale Type" display is just the computed
overall mix (WHOLESALE if any line is wholesale, else RETAIL), used for
the saved sale's number series and the "wholesale needs a customer" rule.
Nothing here ever touches the stock ledger directly (see
spare_parts/__init__.py) - finalizing always goes through
sales_service.create_sale, and holding always goes through
held_sales_service.create_held_sale/update_held_sale.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Callable, Optional

from PyQt6.QtCore import QSignalBlocker, QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QImage, QTextDocument
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
from spare_parts.services import customers_service, held_sales_service, parts_service, sales_service, stock_service
from spare_parts.services.settings_service import get_settings
from spare_parts.ui.customers_page import CustomerDialog
from spare_parts.ui.widgets import NoScrollComboBox, NoScrollDoubleSpinBox, NoScrollSpinBox, trash_icon
from spare_parts.logging_config import get_logger

logger = get_logger(__name__)


def _build_fbr_qr_image(data: str) -> Optional[QImage]:
    """QR code for the printed receipt, encoding the FBR invoice number.

    Independent of app/qt_ui/main_window.py's own qrcode usage - this
    module has no FBR verification-URL field to encode (see
    fbr_submission_service.py's response parsing), so the QR simply
    encodes the invoice number itself."""
    try:
        import io

        import qrcode

        qr = qrcode.QRCode(version=1, box_size=4, border=2)
        qr.add_data(data)
        qr.make(fit=True)
        pil_image = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        pil_image.save(buffer, format="PNG")
        qimage = QImage()
        qimage.loadFromData(buffer.getvalue(), "PNG")
        return qimage
    except Exception as e:
        logger.error(f"Failed to build FBR QR code image: {e}", exc_info=True)
        return None


def _get_main_app_company_info(db) -> dict:
    """Reads the main application's single Company's name/address/phone
    (companies table) for the receipt header.

    This is a deliberate, narrow exception to spare_parts/__init__.py
    rule #2 ("no query ever references a non-sp_ table") - explicitly
    requested so this info does not need to be re-entered as a separate,
    independent setting inside this module. It is a read-only raw SQL
    query over the shared connection (see spare_parts/db/base.py), never
    an ORM import of app.db.models.Company, and the only such exception
    anywhere in this package."""
    try:
        from sqlalchemy import text
        row = db.execute(text("SELECT name, address, phone FROM companies LIMIT 1")).fetchone()
        if not row:
            return {"name": "", "address": "", "phone": ""}
        return {"name": row[0] or "", "address": row[1] or "", "phone": row[2] or ""}
    except Exception as e:
        logger.error(f"Failed to read the main application's company info: {e}", exc_info=True)
        return {"name": "", "address": "", "phone": ""}


# Paper width in mm for each thermal format - used both to size the
# printer's page and to pick the QR image's display size on it.
_THERMAL_WIDTH_MM = {"THERMAL_80MM": 80, "THERMAL_58MM": 58}
# Generous page height so a long item list never gets truncated - a
# thermal/receipt printer's own Windows driver advances and cuts the
# continuous roll to fit the actual content printed, it does not print
# this much blank paper.
_THERMAL_PAGE_HEIGHT_MM = 1000


def _build_receipt_html_a4(sale, company_name, company_address, company_phone, customer_name, fbr_invoice_number):
    lines = []
    if company_name:
        lines.append(f"<h2 align='center'>{company_name}</h2>")
    if company_address or company_phone:
        contact_bits = [bit for bit in (company_address, f"Ph: {company_phone}" if company_phone else "") if bit]
        lines.append(f"<p align='center' style='margin-top:-6px;'>{' | '.join(contact_bits)}</p>")
    lines.append(f"<h3 align='center'>Receipt - {sale.sale_no}</h3>")
    lines.append(f"<p>Date: {sale.sale_date.strftime('%Y-%m-%d %H:%M')}<br/>")
    lines.append(f"Customer: {customer_name}<br/>")
    lines.append(f"Payment: {sale.payment_method}</p>")
    lines.append("<table width='100%' cellspacing='4'><tr><th align='left'>Part</th>"
                  "<th align='right'>Qty</th><th align='right'>Price</th>"
                  "<th align='right'>Total</th></tr>")
    for item in sale.items:
        part_name = item.part.name if item.part else f"Part #{item.part_id}"
        lines.append(
            f"<tr><td>{part_name}</td><td align='right'>{item.qty}</td>"
            f"<td align='right'>{float(item.unit_price):,.2f}</td>"
            f"<td align='right'>{float(item.line_total):,.2f}</td></tr>"
        )
    lines.append("</table>")
    lines.append(
        f"<p align='right'>Subtotal: {float(sale.subtotal):,.2f}<br/>"
        f"Discount: {float(sale.discount):,.2f}<br/>"
        f"Tax: {float(sale.tax_amount):,.2f}<br/>"
        f"<b>Total: {float(sale.total):,.2f}</b><br/>"
        f"Paid: {float(sale.paid):,.2f}<br/>"
        f"Due: {float(sale.due):,.2f}</p>"
    )
    if fbr_invoice_number:
        lines.append(
            "<hr/><p align='center'>FBR Invoice No: <b>" + fbr_invoice_number + "</b><br/>"
            "<img src='fbr_qr_code' width='100' height='100'/></p>"
        )
    return "".join(lines)


def _build_receipt_html_thermal(
    sale, company_name, company_address, company_phone, customer_name, fbr_invoice_number, width_mm,
):
    """Narrow, single-column receipt layout for an 80mm/58mm thermal
    printer - no wide 4-column table (it would squeeze the part name
    unreadably on 58mm), each item instead prints its name on its own
    line with qty/price/total on the line below."""
    qr_px = 70 if width_mm <= 58 else 90
    dash = "<hr style='border:none; border-top:1px dashed #000; margin:4px 0;'/>"
    lines = ["<div style=\"font-family: 'Courier New', monospace; font-size: 11px;\">"]
    if company_name:
        lines.append(f"<p align='center' style='font-size:14px; font-weight:bold; margin:0;'>{company_name}</p>")
    if company_address or company_phone:
        contact_bits = [bit for bit in (company_address, f"Ph: {company_phone}" if company_phone else "") if bit]
        lines.append(f"<p align='center' style='margin:0;'>{' | '.join(contact_bits)}</p>")
    lines.append(f"<p align='center' style='margin:4px 0;'>Receipt - {sale.sale_no}</p>")
    lines.append(dash)
    lines.append(
        f"<p style='margin:0;'>Date: {sale.sale_date.strftime('%Y-%m-%d %H:%M')}<br/>"
        f"Customer: {customer_name}<br/>"
        f"Payment: {sale.payment_method}</p>"
    )
    lines.append(dash)
    for item in sale.items:
        part_name = item.part.name if item.part else f"Part #{item.part_id}"
        lines.append(f"<p style='margin:3px 0 0 0;'>{part_name}</p>")
        lines.append(
            "<table width='100%' style='margin:0;'><tr>"
            f"<td>{item.qty} x {float(item.unit_price):,.2f}</td>"
            f"<td align='right'><b>{float(item.line_total):,.2f}</b></td></tr></table>"
        )
    lines.append(dash)
    lines.append(
        "<table width='100%' style='margin:0;'>"
        f"<tr><td>Subtotal</td><td align='right'>{float(sale.subtotal):,.2f}</td></tr>"
        f"<tr><td>Discount</td><td align='right'>{float(sale.discount):,.2f}</td></tr>"
        f"<tr><td>Tax</td><td align='right'>{float(sale.tax_amount):,.2f}</td></tr>"
        f"<tr><td><b>Total</b></td><td align='right'><b>{float(sale.total):,.2f}</b></td></tr>"
        f"<tr><td>Paid</td><td align='right'>{float(sale.paid):,.2f}</td></tr>"
        f"<tr><td>Due</td><td align='right'>{float(sale.due):,.2f}</td></tr>"
        "</table>"
    )
    if fbr_invoice_number:
        lines.append(dash)
        lines.append(
            f"<p align='center' style='margin:0;'>FBR Invoice No:<br/><b>{fbr_invoice_number}</b></p>"
            f"<p align='center' style='margin:4px 0;'><img src='fbr_qr_code' width='{qr_px}' height='{qr_px}'/></p>"
        )
    lines.append("</div>")
    return "".join(lines)


def print_sale_receipt(sale_id: int, parent=None) -> None:
    """Builds and prints one sale's receipt, independent of any
    SaleCardWidget instance - usable both right after completing a sale
    on the POS screen (SaleCardWidget.print_receipt) and as a later
    reprint from the Sales tab (spare_parts/ui/sales_page.py), e.g. once
    a sale that printed before its FBR submission has since been
    submitted and should now show the FBR invoice number/QR code.

    Prints through the normal Qt/Windows Print dialog either way - a
    thermal printer just needs to already be installed as a Windows
    printer (true of virtually every USB/Bluetooth thermal receipt
    printer sold today). spare_parts/ui/settings_page.py's "Receipt
    Paper Format" setting picks between the standard A4 layout and a
    narrow 80mm/58mm one sized for that printer's paper width."""
    try:
        from PyQt6.QtCore import QMarginsF, QSizeF
        from PyQt6.QtGui import QPageLayout, QPageSize
        from PyQt6.QtPrintSupport import QPrintDialog, QPrinter
    except ImportError:
        QMessageBox.warning(parent, "Printing Unavailable", "Print support is not installed.")
        return

    db = get_spare_session()
    try:
        sale = sales_service.get_sale(db, sale_id)
        if not sale:
            QMessageBox.warning(parent, "Not Found", "Could not reload the sale to print.")
            return
        company_info = _get_main_app_company_info(db)
        company_name = company_info["name"].strip()
        company_address = company_info["address"].strip()
        company_phone = company_info["phone"].strip()
        customer_name = (
            sale.customer.name if sale.customer else (sale.walk_in_customer_name or "Walk-in")
        )
        fbr_invoice_number = (
            sale.fbr_invoice_number if sale.fbr_submission_status == "SUBMITTED" else None
        )
        paper_format = (get_settings(db).receipt_paper_format or "A4").strip().upper()
        thermal_width_mm = _THERMAL_WIDTH_MM.get(paper_format)
        if thermal_width_mm:
            html = _build_receipt_html_thermal(
                sale, company_name, company_address, company_phone, customer_name,
                fbr_invoice_number, thermal_width_mm,
            )
        else:
            html = _build_receipt_html_a4(
                sale, company_name, company_address, company_phone, customer_name, fbr_invoice_number,
            )
    finally:
        db.close()

    document = QTextDocument()
    if fbr_invoice_number:
        qr_image = _build_fbr_qr_image(fbr_invoice_number)
        if qr_image is not None:
            document.addResource(QTextDocument.ResourceType.ImageResource, QUrl("fbr_qr_code"), qr_image)
    document.setHtml(html)
    printer = QPrinter()
    if thermal_width_mm:
        printer.setPageLayout(QPageLayout(
            QPageSize(QSizeF(thermal_width_mm, _THERMAL_PAGE_HEIGHT_MM), QPageSize.Unit.Millimeter),
            QPageLayout.Orientation.Portrait,
            QMarginsF(2, 2, 2, 2),
        ))
    dialog = QPrintDialog(printer, parent)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        document.print(printer)

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
        background-color: #e74c3c; color: white; border: none;
        border-radius: 4px; padding: 8px 16px; font-weight: bold;
    }
    QPushButton:hover { background-color: #c0392b; }
"""

_REMOVE_LINE_ICON_QSS = """
    QPushButton {
        background-color: #fdecea; color: #e74c3c; border: 1px solid #f5b7b1;
        border-radius: 13px; font-weight: bold; font-size: 13px; padding: 0px;
    }
    QPushButton:hover { background-color: #e74c3c; color: white; border-color: #e74c3c; }
    QPushButton:pressed { background-color: #c0392b; border-color: #c0392b; }
"""

_PART_SEARCH_INPUT_QSS = """
    QLineEdit#partSearchInput {
        font-size: 15px;
        font-weight: 600;
        padding: 9px 14px;
        border: 2px solid #3498db;
        border-radius: 8px;
        background-color: #ffffff;
        color: #2c3e50;
    }
    QLineEdit#partSearchInput:focus {
        border: 2px solid #1b4f72;
        background-color: #eaf4fc;
    }
"""

_PART_SEARCH_POPUP_QSS = """
    QListView {
        font-size: 13px;
        border: 1px solid #3498db;
        outline: 0;
        background-color: #ffffff;
        selection-background-color: #3498db;
        selection-color: white;
    }
    QListView::item { padding: 4px 8px; }
"""

_WALK_IN_LABEL = "(Walk-in / No customer)"
_ITEM_COLUMNS = ["Part", "Type", "Brand", "Sell As", "Qty", "Unit Price", "Discount", "Line Total", ""]


class SaleCardWidget(QWidget):
    """A single POS card. `reserved_qty_fn(part_id, exclude_held_sale_id)`
    is supplied by PosPage and returns how much of that part is already
    committed to OTHER open cards + held drafts, so this card can warn
    (not block - the real guard is the stock-ledger check at finalize
    time) before the same part gets oversold across simultaneous sales."""

    totals_changed = pyqtSignal()
    label_changed = pyqtSignal()

    def __init__(
        self,
        parent=None,
        *,
        reserved_qty_fn: Optional[Callable[[int, Optional[int]], int]] = None,
    ):
        super().__init__(parent)
        self._reserved_qty_fn = reserved_qty_fn
        self.held_sale_id: Optional[int] = None
        self.custom_label: Optional[str] = None
        self._dirty = False
        self._saving = False
        # Guards against the part search box adding the same item twice
        # for one Enter keypress - see _on_part_completer_activated and
        # _on_part_search_enter.
        self._suppress_part_search_add = False

        root = QVBoxLayout(self)

        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("Sale Type:"))
        self.overall_type_label = QLabel("RETAIL")
        self.overall_type_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        self.overall_type_label.setToolTip(
            "Set per line below (Retail or Wholesale) - this just shows the "
            "overall mix for this card."
        )
        header_row.addWidget(self.overall_type_label)

        header_row.addWidget(QLabel("Customer"))
        self.customer_combo = NoScrollComboBox()
        self.customer_combo.setEditable(True)
        self.customer_combo.setInsertPolicy(NoScrollComboBox.InsertPolicy.NoInsert)
        self.customer_combo.currentIndexChanged.connect(self._on_customer_changed)
        # Also catches free-typed text that doesn't match any existing
        # customer (currentIndexChanged alone only fires on an actual
        # selection) - see display_label().
        self.customer_combo.currentTextChanged.connect(self.label_changed.emit)
        header_row.addWidget(self.customer_combo, 2)
        self.add_customer_btn = QPushButton("+")
        self.add_customer_btn.setFixedWidth(28)
        self.add_customer_btn.setToolTip("Add new customer")
        self.add_customer_btn.setAutoDefault(False)
        self.add_customer_btn.clicked.connect(self._on_add_customer)
        header_row.addWidget(self.add_customer_btn)

        header_row.addWidget(QLabel("Payment"))
        self.payment_method_combo = NoScrollComboBox()
        self.payment_method_combo.addItems(["Cash", "Card", "Bank Transfer", "Credit"])
        header_row.addWidget(self.payment_method_combo)
        root.addLayout(header_row)

        ref_row = QHBoxLayout()
        ref_row.addWidget(QLabel("Reference"))
        self.reference_input = QLineEdit()
        self.reference_input.setPlaceholderText("Optional - customer name/phone, shown in Held Sales")
        self.reference_input.textChanged.connect(self.label_changed.emit)
        ref_row.addWidget(self.reference_input, 1)
        ref_row.addWidget(QLabel("Notes"))
        self.notes_input = QLineEdit()
        ref_row.addWidget(self.notes_input, 1)
        root.addLayout(ref_row)

        # Made visually prominent (bordered, bold, larger) since this is
        # the field used for nearly every action on this card - a cashier
        # should never have to hunt for it among the smaller form fields.
        search_row = QHBoxLayout()
        search_icon_label = QLabel("\U0001F50D")
        search_icon_label.setStyleSheet("font-size: 18px;")
        search_row.addWidget(search_icon_label)
        self.part_search_input = QLineEdit()
        self.part_search_input.setObjectName("partSearchInput")
        self.part_search_input.setPlaceholderText(
            "Scan barcode or search part no / name, then Enter..."
        )
        self.part_search_input.setMinimumHeight(42)
        self.part_search_input.setStyleSheet(_PART_SEARCH_INPUT_QSS)
        self.part_search_input.returnPressed.connect(self._on_part_search_enter)
        search_row.addWidget(self.part_search_input, 1)
        root.addLayout(search_row)

        self.items_table = QTableWidget(0, len(_ITEM_COLUMNS))
        self.items_table.setHorizontalHeaderLabels(_ITEM_COLUMNS)
        self.items_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.items_table.horizontalHeader().setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)
        self.items_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        # Shown (not hidden) so Qt's built-in 1, 2, 3... row numbering acts
        # as a serial-number column - it stays correct automatically as
        # lines are added/removed/reordered, no manual renumbering needed.
        self.items_table.verticalHeader().setVisible(True)
        self.items_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.items_table.verticalHeader().setMinimumSectionSize(36)
        self.items_table.verticalHeader().setMinimumWidth(32)
        self.items_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        root.addWidget(self.items_table, 1)

        line_actions_row = QHBoxLayout()
        line_actions_row.addStretch(1)
        remove_line_btn = QPushButton("Remove Selected Line")
        remove_line_btn.setStyleSheet(_DANGER_BTN)
        remove_line_btn.setAutoDefault(False)
        remove_line_btn.clicked.connect(self._on_remove_selected_line)
        line_actions_row.addWidget(remove_line_btn)
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
        self.discount_spin.setFixedWidth(100)
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

        totals_row.addWidget(QLabel("  Paid:"))
        self.paid_spin = NoScrollDoubleSpinBox()
        self.paid_spin.setRange(0, 99_999_999)
        self.paid_spin.setDecimals(2)
        self.paid_spin.valueChanged.connect(self._recalc_totals)
        self.paid_spin.setFixedWidth(100)
        totals_row.addWidget(self.paid_spin)

        totals_row.addWidget(QLabel("  Due:"))
        self.due_label = QLabel("0.00")
        self.due_label.setStyleSheet("font-weight: bold; color: #e74c3c;")
        totals_row.addWidget(self.due_label)
        root.addLayout(totals_row)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        root.addWidget(self.error_label)

        self._customers_by_id: dict[int, object] = {}
        self._parts_by_barcode: dict[str, object] = {}
        self._parts_by_part_no: dict[str, object] = {}
        self._parts_completer_map: dict[str, object] = {}
        # Maps each completer suggestion's full DISPLAYED text (which
        # includes the stock quantity, e.g. "HD-1 - Brake Pad  (Stock:
        # 25)") back to the clean "PartNo - Name" key used everywhere
        # else (_parts_completer_map, etc.) - kept separate so the stock
        # NUMBER is never part of what _parts_completer_map itself
        # matches/stores.
        self._completer_label_to_key: dict[str, str] = {}
        self._brand_name_by_id: dict[int, str] = {}

        self._reload_customers()
        self._load_default_tax_percent()
        self.refresh_parts_lookup()
        self.part_search_input.setFocus()

    # --- lookups -------------------------------------------------------------

    def _load_default_tax_percent(self) -> None:
        db = get_spare_session()
        try:
            settings = get_settings(db)
            with QSignalBlocker(self.tax_percent_spin):
                self.tax_percent_spin.setValue(float(settings.default_tax_percent or 0))
        finally:
            db.close()

    def _reload_customers(self) -> None:
        db = get_spare_session()
        try:
            self._customers_by_id = {
                c.id: c for c in customers_service.list_customers(db, active_only=True)
            }
            current = self.customer_combo.currentData()
            with QSignalBlocker(self.customer_combo):
                self.customer_combo.clear()
                self.customer_combo.addItem(_WALK_IN_LABEL, None)
                for customer in self._customers_by_id.values():
                    self.customer_combo.addItem(f"{customer.name} ({customer.type})", customer.id)
                if current is not None:
                    idx = self.customer_combo.findData(current)
                    if idx >= 0:
                        self.customer_combo.setCurrentIndex(idx)
        finally:
            db.close()

    def refresh_parts_lookup(self) -> None:
        """Re-snapshots parts (incl. brand names and current stock) and
        the search completer from the database. Called at construction
        time and again by PosPage whenever the Sales Counter tab regains
        focus - otherwise a card left open while a part's brand/price/
        stock/etc. is edited elsewhere in the app would keep showing
        what it cached when it was built, since _add_line_item works off
        this card's own copy of each part, not a live read of the
        database."""
        db = get_spare_session()
        try:
            parts = parts_service.search_parts(db, active_only=True)
            stock_by_id = stock_service.get_current_stock_bulk(db, [p.id for p in parts])
            self._parts_by_barcode = {p.barcode.upper(): p for p in parts if p.barcode}
            self._parts_by_part_no = {p.part_no.upper(): p for p in parts}
            self._parts_completer_map = {f"{p.part_no} - {p.name}": p for p in parts}
            # Looked up by brand_id (a plain column, safe on a detached
            # part) rather than part.brand (a lazy relationship) - parts
            # here outlive this session's close() below, and a lazy
            # relationship access on a detached instance would raise
            # DetachedInstanceError.
            self._brand_name_by_id = {b.id: b.name for b in parts_service.list_brands(db)}
            self.part_search_input.setCompleter(
                self._build_parts_completer(parts, stock_by_id)
            )
        finally:
            db.close()

    def _build_parts_completer(self, parts, stock_by_id: dict[int, int]) -> QCompleter:
        """Plain string-list QCompleter - the exact same setup already
        proven reliable elsewhere in this app (e.g. purchase_page.py's
        part search): a bare Python list of strings, Qt's own
        auto-created default popup, MatchContains filtering. No custom
        model, view, or delegate - two earlier, more elaborate attempts
        at this (a multi-column QTreeView popup, then a custom paint
        delegate) both turned out unreliable in practice. Each
        suggestion's text includes the stock quantity so it's visible in
        the dropdown; self._completer_label_to_key maps that full text
        back to the plain "PartNo - Name" key used everywhere else, so
        the stock NUMBER itself is never part of what _parts_completer_map
        matches or stores."""
        self._completer_label_to_key = {}
        labels = []
        for part in parts:
            key = f"{part.part_no} - {part.name}"
            qty = stock_by_id.get(part.id, 0)
            label = f"{key}   (Stock: {qty})"
            labels.append(label)
            self._completer_label_to_key[label] = key

        completer = QCompleter(labels, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.popup().setStyleSheet(_PART_SEARCH_POPUP_QSS)

        completer.activated.connect(self._on_part_completer_activated)
        return completer

    def _on_add_customer(self) -> None:
        dlg = CustomerDialog(parent=self)
        if dlg.exec():
            self._reload_customers()
            self.customer_combo.setCurrentIndex(self.customer_combo.count() - 1)

    # --- sale type / customer interplay --------------------------------------

    def _on_customer_changed(self, _index: int) -> None:
        # No longer forces existing lines to a type - type is per-line now
        # (see _on_line_type_changed). This only affects the default type
        # offered to the NEXT line added, via default_line_type().
        self.label_changed.emit()

    def default_line_type(self) -> str:
        """The type a freshly-added line should start as: the selected
        customer's registered type as a convenience default, or RETAIL."""
        customer_id = self.customer_combo.currentData()
        customer = self._customers_by_id.get(customer_id) if customer_id else None
        return customer.type if customer else "RETAIL"

    def _compute_overall_type(self) -> tuple[str, bool]:
        """(sale_type_for_the_header, is_mixed). The header SpSale record
        still needs exactly one sale_type (number series, "wholesale
        needs a customer" rule, reports) even though pricing is chosen
        per line - WHOLESALE wins if any line is wholesale, so the
        customer/credit checks apply whenever wholesale pricing is used
        anywhere in the cart. Defaults to RETAIL for an empty cart."""
        types = set()
        for row in range(self.items_table.rowCount()):
            type_combo = self.items_table.cellWidget(row, 1)
            if type_combo is not None:
                types.add(type_combo.currentText())
        if not types:
            return "RETAIL", False
        overall = "WHOLESALE" if "WHOLESALE" in types else "RETAIL"
        return overall, len(types) > 1

    def _update_overall_type_label(self) -> None:
        overall, is_mixed = self._compute_overall_type()
        self.overall_type_label.setText(f"{overall} (Mixed)" if is_mixed else overall)
        self.label_changed.emit()

    def _on_line_type_changed(self, type_combo) -> None:
        """type_combo identifies its row by widget identity, not a
        captured index - a row's position can shift as other rows are
        added/removed (same pattern as _remove_line_item's button)."""
        row = None
        for r in range(self.items_table.rowCount()):
            if self.items_table.cellWidget(r, 1) is type_combo:
                row = r
                break
        if row is None:
            return

        is_wholesale = type_combo.currentText() == "WHOLESALE"
        sell_as_combo = self.items_table.cellWidget(row, 3)
        price_spin = self.items_table.cellWidget(row, 5)
        part_item = self.items_table.item(row, 0)
        if sell_as_combo is not None:
            sell_as_combo.setEnabled(is_wholesale)
            if not is_wholesale:
                with QSignalBlocker(sell_as_combo):
                    sell_as_combo.setCurrentIndex(sell_as_combo.findData("UNIT"))

        part_id = part_item.data(Qt.ItemDataRole.UserRole) if part_item else None
        part = None
        if part_id and price_spin is not None:
            db = get_spare_session()
            try:
                part = parts_service.get_part(db, part_id)
            finally:
                db.close()
            if part:
                new_price = part.wholesale_price if is_wholesale else part.retail_price
                with QSignalBlocker(price_spin):
                    price_spin.setValue(float(Decimal(str(new_price or 0))))

        self._recalc_totals()
        self._update_overall_type_label()

        customer_id = self.customer_combo.currentData()
        if is_wholesale and not customer_id:
            QMessageBox.information(
                self, "Customer Required",
                "Wholesale pricing on this line requires selecting a "
                "customer before completing the sale.",
            )
        if is_wholesale and part and 1 < (part.min_wholesale_qty or 1):
            qty_spin = self.items_table.cellWidget(row, 4)
            qty_value = qty_spin.value() if qty_spin else 0
            if qty_value < part.min_wholesale_qty:
                QMessageBox.information(
                    self, "Minimum Wholesale Quantity",
                    f"'{part.name}' has a minimum wholesale quantity of "
                    f"{part.min_wholesale_qty}. Adjust the quantity if needed.",
                )

    # --- part search / line items ---------------------------------------------

    def _on_part_completer_activated(self, text: str) -> None:
        # A single Enter keypress that accepts a completer suggestion can
        # fire BOTH this signal and the line edit's own returnPressed (see
        # _on_part_search_enter) - without this guard, the part gets added
        # once here and then "added again" (really just merged, bumping
        # qty to 2) when the other handler also runs for the same keypress.
        if self._suppress_part_search_add:
            return
        # text is the suggestion's full displayed text (includes the
        # stock quantity) - translate back to the plain "PartNo - Name"
        # key _parts_completer_map actually uses.
        key_text = self._completer_label_to_key.get(text, text)
        part = self._parts_completer_map.get(key_text)
        if part:
            self._suppress_part_search_add = True
            self._add_line_item(part)
            self.part_search_input.clear()
            QTimer.singleShot(0, self._clear_part_search_add_guard)

    def _on_part_search_enter(self) -> None:
        if self._suppress_part_search_add:
            return
        raw_text = self.part_search_input.text().strip()
        if not raw_text:
            return
        # Qt can auto-fill the box with a suggestion's full displayed
        # text (including the stock suffix) as the user arrows through
        # the popup, independently of which signal ends up calling this
        # - recover the plain "PartNo - Name" text first, same as a
        # normal completer selection would, so this never has to match
        # a stock-number suffix it was never meant to search.
        text = self._completer_label_to_key.get(raw_text, raw_text)
        key = text.upper()
        part = self._parts_by_barcode.get(key) or self._parts_by_part_no.get(key)
        if not part:
            # Partial part-code search (e.g. "8533" finding "P-8533"):
            # checked against the PART NO specifically, before the
            # broader "PartNo - Name" search below - otherwise typing a
            # fragment of one part's code that also happens to appear
            # somewhere in a DIFFERENT part's name makes this ambiguous
            # (2+ matches) and fails with "Not Found" even though the
            # suggestion dropdown would have shown the right part alone.
            code_matches = [p for p in self._parts_by_part_no.values() if key in p.part_no.upper()]
            if len(code_matches) == 1:
                part = code_matches[0]
        if not part:
            matches = [p for label, p in self._parts_completer_map.items() if key in label.upper()]
            part = matches[0] if len(matches) == 1 else None
        if not part:
            QMessageBox.warning(self, "Part Not Found", f"No active part matches '{raw_text}'.")
            return
        self._suppress_part_search_add = True
        self._add_line_item(part)
        self.part_search_input.clear()
        QTimer.singleShot(0, self._clear_part_search_add_guard)

    def _clear_part_search_add_guard(self) -> None:
        self._suppress_part_search_add = False

    def _current_unit_price(self, part, is_wholesale: bool) -> Decimal:
        price = part.wholesale_price if is_wholesale else part.retail_price
        return Decimal(str(price or 0))

    def _find_unit_row_for_part(self, part_id: int) -> Optional[int]:
        for row in range(self.items_table.rowCount()):
            part_item = self.items_table.item(row, 0)
            sell_as_widget = self.items_table.cellWidget(row, 3)
            if not part_item or not sell_as_widget:
                continue
            if (
                part_item.data(Qt.ItemDataRole.UserRole) == part_id
                and sell_as_widget.currentData() == "UNIT"
            ):
                return row
        return None

    def qty_reserved_for_part(self, part_id: int) -> int:
        """This card's own current total quantity for a part, across all
        its lines (UNIT + PACK, in base units) - used by PosPage to add
        up what's committed to a part across every OTHER open card."""
        total = 0
        for row in range(self.items_table.rowCount()):
            part_item = self.items_table.item(row, 0)
            qty_widget = self.items_table.cellWidget(row, 4)
            if part_item and qty_widget and part_item.data(Qt.ItemDataRole.UserRole) == part_id:
                sell_as_widget = self.items_table.cellWidget(row, 3)
                if sell_as_widget and sell_as_widget.currentData() == "PACK":
                    pack_size = int(sell_as_widget.property("pack_size") or 1)
                    total += qty_widget.value() * pack_size
                else:
                    total += qty_widget.value()
        return total

    def _warn_if_oversold(self, part, new_total_qty_this_card: int) -> None:
        if not self._reserved_qty_fn:
            return
        db = get_spare_session()
        try:
            current_stock = stock_service.get_current_stock(db, part.id)
        finally:
            db.close()
        reserved_elsewhere = self._reserved_qty_fn(part.id, self.held_sale_id)
        available = current_stock - reserved_elsewhere
        if new_total_qty_this_card > available:
            QMessageBox.warning(
                self, "Limited Stock Across Open Sales",
                f"'{part.name}' has {current_stock} in stock, but {reserved_elsewhere} "
                f"is already in other open cards or held sales - only about "
                f"{max(0, available)} is actually free. This card now has "
                f"{new_total_qty_this_card}. Double-check before completing.",
            )

    def _add_line_item(self, part) -> None:
        existing_row = self._find_unit_row_for_part(part.id)
        if existing_row is not None:
            qty_widget = self.items_table.cellWidget(existing_row, 4)
            qty_widget.setValue(qty_widget.value() + 1)
            self._dirty = True
            self.items_table.setCurrentCell(existing_row, 4)
            qty_widget.setFocus()
            qty_widget.selectAll()
            self._warn_if_oversold(part, self.qty_reserved_for_part(part.id))
            return

        default_type = self.default_line_type()
        is_wholesale = default_type == "WHOLESALE"
        row = self.items_table.rowCount()
        self.items_table.insertRow(row)

        part_item = QTableWidgetItem(f"{part.part_no} - {part.name}")
        part_item.setFlags(part_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        part_item.setData(Qt.ItemDataRole.UserRole, part.id)
        self.items_table.setItem(row, 0, part_item)

        type_combo = NoScrollComboBox()
        type_combo.addItems(["RETAIL", "WHOLESALE"])
        type_combo.setCurrentText(default_type)
        # Resolves its own row by widget identity at call time, not a
        # captured index, since a row's position can shift later (same
        # pattern as the remove button below).
        type_combo.currentTextChanged.connect(
            lambda _text, combo=type_combo: self._on_line_type_changed(combo)
        )
        self.items_table.setCellWidget(row, 1, type_combo)

        brand_item = QTableWidgetItem(self._brand_name_by_id.get(part.brand_id, ""))
        brand_item.setFlags(brand_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.items_table.setItem(row, 2, brand_item)

        sell_as_combo = NoScrollComboBox()
        # Displayed as "Piece"/"Pack" - the stored sold_as value underneath
        # (read via currentData(), never currentText()) stays "UNIT"/"PACK"
        # exactly as before.
        sell_as_combo.addItem("Piece", "UNIT")
        sell_as_combo.addItem("Pack", "PACK")
        sell_as_combo.setProperty("pack_size", int(part.pack_size or 1))
        sell_as_combo.setProperty("min_wholesale_qty", int(part.min_wholesale_qty or 1))
        sell_as_combo.setEnabled(is_wholesale)
        sell_as_combo.currentTextChanged.connect(self._recalc_totals)
        self.items_table.setCellWidget(row, 3, sell_as_combo)

        qty_spin = NoScrollSpinBox()
        qty_spin.setRange(1, 1_000_000)
        qty_spin.setValue(1)
        qty_spin.valueChanged.connect(self._recalc_totals)
        self.items_table.setCellWidget(row, 4, qty_spin)

        price_spin = NoScrollDoubleSpinBox()
        price_spin.setRange(0, 99_999_999)
        price_spin.setDecimals(2)
        price_spin.setValue(float(self._current_unit_price(part, is_wholesale)))
        price_spin.valueChanged.connect(self._recalc_totals)
        self.items_table.setCellWidget(row, 5, price_spin)

        discount_spin = NoScrollDoubleSpinBox()
        discount_spin.setRange(0, 99_999_999)
        discount_spin.setDecimals(2)
        discount_spin.valueChanged.connect(self._recalc_totals)
        self.items_table.setCellWidget(row, 6, discount_spin)

        line_total_item = QTableWidgetItem("0.00")
        line_total_item.setFlags(line_total_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.items_table.setItem(row, 7, line_total_item)

        remove_btn = QPushButton()
        remove_btn.setIcon(trash_icon(14))
        remove_btn.setIconSize(QSize(14, 14))
        remove_btn.setFixedSize(26, 26)
        remove_btn.setToolTip("Remove this line")
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.setStyleSheet(_REMOVE_LINE_ICON_QSS)
        remove_btn.setAutoDefault(False)
        remove_btn.clicked.connect(lambda: self._remove_line_item(remove_btn))
        self.items_table.setCellWidget(row, 8, remove_btn)

        self._dirty = True
        self._recalc_totals()
        self._update_overall_type_label()
        qty_spin.setFocus()
        qty_spin.selectAll()

        if is_wholesale and 1 < (part.min_wholesale_qty or 1):
            QMessageBox.information(
                self, "Minimum Wholesale Quantity",
                f"'{part.name}' has a minimum wholesale quantity of "
                f"{part.min_wholesale_qty}. Adjust the quantity if needed.",
            )

        self._warn_if_oversold(part, self.qty_reserved_for_part(part.id))

    def _remove_line_item(self, btn) -> None:
        for row in range(self.items_table.rowCount()):
            if self.items_table.cellWidget(row, 8) is btn:
                self.items_table.removeRow(row)
                break
        self._dirty = True
        self._recalc_totals()
        self._update_overall_type_label()

    def _on_remove_selected_line(self) -> None:
        row = self.items_table.currentRow()
        if row < 0:
            QMessageBox.information(
                self, "No Line Selected",
                "Click a line in the table first, then click Remove Selected Line.",
            )
            return
        self.items_table.removeRow(row)
        self._dirty = True
        self._recalc_totals()
        self._update_overall_type_label()

    def _recalc_totals(self) -> None:
        subtotal = Decimal("0")
        for row in range(self.items_table.rowCount()):
            sell_as_widget = self.items_table.cellWidget(row, 3)
            qty_widget = self.items_table.cellWidget(row, 4)
            price_widget = self.items_table.cellWidget(row, 5)
            discount_widget = self.items_table.cellWidget(row, 6)
            if not (sell_as_widget and qty_widget and price_widget and discount_widget):
                continue
            sold_as = sell_as_widget.currentData()
            pack_size = int(sell_as_widget.property("pack_size") or 1)
            base_qty = qty_widget.value() * (pack_size if sold_as == "PACK" else 1)
            unit_price = Decimal(str(price_widget.value()))
            discount = Decimal(str(discount_widget.value()))
            line_total = (unit_price * base_qty) - discount
            if line_total < 0:
                line_total = Decimal("0")
            item = self.items_table.item(row, 7)
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
        paid = Decimal(str(self.paid_spin.value()))
        due = total - paid
        self.due_label.setText(f"{due:,.2f}")
        self.totals_changed.emit()

    # --- public helpers for PosPage -------------------------------------------

    def is_empty(self) -> bool:
        return self.items_table.rowCount() == 0

    def is_dirty(self) -> bool:
        return self._dirty

    def current_total(self) -> Decimal:
        return Decimal(self.total_label.text().replace(",", "") or "0")

    def display_label(self) -> str:
        """Priority: an explicit rename always wins; otherwise a
        registered customer actually selected from the Customer dropdown;
        otherwise whatever the cashier typed into the (editable) Customer
        field without selecting a match - it's still a name they entered,
        so it should show up even though it isn't a registered customer;
        otherwise whatever's in Reference; otherwise just "Walk-in"."""
        if self.custom_label:
            return self.custom_label
        customer_id = self.customer_combo.currentData()
        customer = self._customers_by_id.get(customer_id) if customer_id else None
        if customer:
            return customer.name
        typed_customer_text = self.customer_combo.currentText().strip()
        if typed_customer_text and typed_customer_text != _WALK_IN_LABEL:
            return typed_customer_text
        reference = self.reference_input.text().strip()
        if reference:
            return reference
        return "Walk-in"

    def _typed_walk_in_customer_name(self) -> str:
        """The name typed directly into the (editable) Customer field
        without selecting/creating a registered SpCustomer - persisted
        on the sale (SpSale.walk_in_customer_name) so it still shows on
        the receipt/sales list, unlike display_label() above which is
        only ever used for the POS card's own tab label and never
        reaches the saved sale. Deliberately ignores custom_label/
        reference (those aren't customer names) and returns "" whenever
        a registered customer was actually selected, since
        sales_service.create_sale ignores this value in that case
        anyway."""
        if self.customer_combo.currentData():
            return ""
        typed = self.customer_combo.currentText().strip()
        if typed and typed != _WALK_IN_LABEL:
            return typed
        return ""

    def _collect_items_payload(self) -> list[dict]:
        items = []
        for row in range(self.items_table.rowCount()):
            part_item = self.items_table.item(row, 0)
            type_widget = self.items_table.cellWidget(row, 1)
            sell_as_widget = self.items_table.cellWidget(row, 3)
            qty_widget = self.items_table.cellWidget(row, 4)
            price_widget = self.items_table.cellWidget(row, 5)
            discount_widget = self.items_table.cellWidget(row, 6)
            items.append(dict(
                part_id=part_item.data(Qt.ItemDataRole.UserRole),
                # Only held_sales_service reads this key (sales_service's
                # own validator ignores unknown keys) - it's how a mixed
                # card's exact per-line mix survives Hold -> Resume.
                price_type=type_widget.currentText() if type_widget else "RETAIL",
                sold_as=sell_as_widget.currentData(),
                qty_entered=qty_widget.value(),
                unit_price=price_widget.value(),
                discount=discount_widget.value(),
            ))
        return items

    def _check_credit_limit(self, customer_id) -> bool:
        """Returns True if it's OK to proceed (within limit, no customer,
        or the cashier confirmed anyway); False to abort the save."""
        due_amount = self.current_total() - Decimal(str(self.paid_spin.value()))
        if not customer_id or due_amount <= 0:
            return True
        db = get_spare_session()
        try:
            within, projected, limit = customers_service.check_credit_limit(db, customer_id, due_amount)
        finally:
            db.close()
        if within:
            return True
        customer = self._customers_by_id.get(customer_id)
        confirm = QMessageBox.question(
            self, "Credit Limit Exceeded",
            f"This sale would put {customer.name if customer else 'this customer'} "
            f"at Rs. {projected:,.2f} against their Rs. {limit:,.2f} credit limit. "
            f"Proceed anyway?",
        )
        return confirm == QMessageBox.StandardButton.Yes

    def complete_sale(self) -> Optional[object]:
        """Finalizes this card into a real sale (stock IS decremented
        here, via sales_service.create_sale). Returns the saved SpSale
        on success, or None if validation failed or the cashier cancelled
        (an error is already shown to the user in that case)."""
        if self._saving:
            return None
        self._saving = True
        self.error_label.hide()
        try:
            sale_type, _is_mixed = self._compute_overall_type()
            customer_id = self.customer_combo.currentData()
            items = self._collect_items_payload()

            if not self._check_credit_limit(customer_id):
                return None

            db = get_spare_session()
            try:
                sale = sales_service.create_sale(
                    db,
                    sale_type=sale_type,
                    customer_id=customer_id,
                    walk_in_customer_name=self._typed_walk_in_customer_name(),
                    items=items,
                    discount=self.discount_spin.value(),
                    tax_percent=self.tax_percent_spin.value(),
                    paid=self.paid_spin.value(),
                    payment_method=self.payment_method_combo.currentText(),
                    notes=self.notes_input.text(),
                )
            finally:
                db.close()

            if self.held_sale_id:
                db2 = get_spare_session()
                try:
                    held_sales_service.delete_held_sale(db2, self.held_sale_id)
                finally:
                    db2.close()
                self.held_sale_id = None

            self._dirty = False
            logger.info(f"POS card completed sale {sale.sale_no} (id={sale.id}).")
            return sale
        except SparePartsValidationError as e:
            self.error_label.setText(str(e))
            self.error_label.show()
            return None
        except Exception as e:
            logger.error(f"Unexpected error completing POS card sale: {e}", exc_info=True)
            self.error_label.setText(f"Unexpected error: {e}")
            self.error_label.show()
            return None
        finally:
            self._saving = False

    def hold_sale(self) -> bool:
        """Saves this card as a draft (no stock effect) via
        held_sales_service - updates the existing draft record if this
        card was already linked to one, otherwise creates a new one."""
        if self._saving:
            return False
        self._saving = True
        self.error_label.hide()
        try:
            items = self._collect_items_payload()
            sale_type, _is_mixed = self._compute_overall_type()
            db = get_spare_session()
            try:
                if self.held_sale_id:
                    held = held_sales_service.update_held_sale(
                        db, self.held_sale_id,
                        reference=self.reference_input.text(),
                        card_label=self.custom_label or "",
                        sale_type=sale_type,
                        customer_id=self.customer_combo.currentData(),
                        items=items,
                        discount=self.discount_spin.value(),
                        tax_percent=self.tax_percent_spin.value(),
                        paid=self.paid_spin.value(),
                        payment_method=self.payment_method_combo.currentText(),
                        notes=self.notes_input.text(),
                    )
                else:
                    held = held_sales_service.create_held_sale(
                        db,
                        reference=self.reference_input.text(),
                        card_label=self.custom_label or "",
                        sale_type=sale_type,
                        customer_id=self.customer_combo.currentData(),
                        items=items,
                        discount=self.discount_spin.value(),
                        tax_percent=self.tax_percent_spin.value(),
                        paid=self.paid_spin.value(),
                        payment_method=self.payment_method_combo.currentText(),
                        notes=self.notes_input.text(),
                    )
            finally:
                db.close()
            self.held_sale_id = held.id
            self._dirty = False
            logger.info(f"POS card held as {held.hold_no} (id={held.id}).")
            return True
        except SparePartsValidationError as e:
            self.error_label.setText(str(e))
            self.error_label.show()
            return False
        except Exception as e:
            logger.error(f"Unexpected error holding POS card: {e}", exc_info=True)
            self.error_label.setText(f"Unexpected error: {e}")
            self.error_label.show()
            return False
        finally:
            self._saving = False

    def discard(self) -> None:
        """Called when the cashier explicitly discards this card. If it
        was linked to a held draft, that draft is removed too - the
        cashier just said they don't want this sale's state kept."""
        if self.held_sale_id:
            db = get_spare_session()
            try:
                held_sales_service.delete_held_sale(db, self.held_sale_id)
            finally:
                db.close()
            self.held_sale_id = None

    def load_from_held_sale(self, held) -> list[str]:
        """Populates this (freshly-constructed, empty) card from a draft.
        Returns the list of part labels whose price had changed since
        the sale was held, so the caller can show one summary notice
        (price is always rechecked/refreshed against the part's current
        price, never the stale stored one).

        Each line's own price_type (RETAIL/WHOLESALE) is restored
        exactly as it was set when held - a mixed card's precise mix
        survives Hold -> Resume, not just the draft's overall sale_type.
        Falls back to held.sale_type for any item saved before
        price_type existed (migration v6)."""
        self.held_sale_id = held.id
        self.reference_input.setText(held.reference or "")
        self.custom_label = held.card_label or None
        if held.customer_id:
            idx = self.customer_combo.findData(held.customer_id)
            if idx >= 0:
                with QSignalBlocker(self.customer_combo):
                    self.customer_combo.setCurrentIndex(idx)
        self.payment_method_combo.setCurrentText(held.payment_method or "Cash")
        self.notes_input.setText(held.notes or "")
        with QSignalBlocker(self.discount_spin):
            self.discount_spin.setValue(float(held.discount or 0))
        with QSignalBlocker(self.tax_percent_spin):
            self.tax_percent_spin.setValue(float(held.tax_percent or 0))
        with QSignalBlocker(self.paid_spin):
            self.paid_spin.setValue(float(held.paid or 0))

        repriced: list[str] = []
        db = get_spare_session()
        try:
            for item in held.items:
                part = parts_service.get_part(db, item.part_id)
                if not part:
                    continue
                line_type = (item.price_type or held.sale_type or "RETAIL").upper()
                is_wholesale_line = line_type == "WHOLESALE"
                current_price = part.wholesale_price if is_wholesale_line else part.retail_price
                current_price = Decimal(str(current_price or 0))
                stored_price = Decimal(str(item.unit_price))
                use_price = current_price if current_price != stored_price else stored_price
                if current_price != stored_price:
                    repriced.append(part.name)

                row = self.items_table.rowCount()
                self.items_table.insertRow(row)

                part_cell = QTableWidgetItem(f"{part.part_no} - {part.name}")
                part_cell.setFlags(part_cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                part_cell.setData(Qt.ItemDataRole.UserRole, part.id)
                self.items_table.setItem(row, 0, part_cell)

                type_combo = NoScrollComboBox()
                type_combo.addItems(["RETAIL", "WHOLESALE"])
                type_combo.setCurrentText(line_type)
                type_combo.currentTextChanged.connect(
                    lambda _text, combo=type_combo: self._on_line_type_changed(combo)
                )
                self.items_table.setCellWidget(row, 1, type_combo)

                brand_item = QTableWidgetItem(self._brand_name_by_id.get(part.brand_id, ""))
                brand_item.setFlags(brand_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.items_table.setItem(row, 2, brand_item)

                sell_as_combo = NoScrollComboBox()
                sell_as_combo.addItem("Piece", "UNIT")
                sell_as_combo.addItem("Pack", "PACK")
                sell_as_combo.setCurrentIndex(sell_as_combo.findData(item.sold_as or "UNIT"))
                sell_as_combo.setProperty("pack_size", int(part.pack_size or 1))
                sell_as_combo.setProperty("min_wholesale_qty", int(part.min_wholesale_qty or 1))
                sell_as_combo.setEnabled(is_wholesale_line)
                sell_as_combo.currentTextChanged.connect(self._recalc_totals)
                self.items_table.setCellWidget(row, 3, sell_as_combo)

                qty_spin = NoScrollSpinBox()
                qty_spin.setRange(1, 1_000_000)
                qty_spin.setValue(item.pack_qty if item.sold_as == "PACK" and item.pack_qty else item.qty)
                qty_spin.valueChanged.connect(self._recalc_totals)
                self.items_table.setCellWidget(row, 4, qty_spin)

                price_spin = NoScrollDoubleSpinBox()
                price_spin.setRange(0, 99_999_999)
                price_spin.setDecimals(2)
                price_spin.setValue(float(use_price))
                price_spin.valueChanged.connect(self._recalc_totals)
                self.items_table.setCellWidget(row, 5, price_spin)

                discount_spin = NoScrollDoubleSpinBox()
                discount_spin.setRange(0, 99_999_999)
                discount_spin.setDecimals(2)
                discount_spin.setValue(float(item.discount or 0))
                discount_spin.valueChanged.connect(self._recalc_totals)
                self.items_table.setCellWidget(row, 6, discount_spin)

                line_total_item = QTableWidgetItem("0.00")
                line_total_item.setFlags(line_total_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.items_table.setItem(row, 7, line_total_item)

                remove_btn = QPushButton()
                remove_btn.setIcon(trash_icon(14))
                remove_btn.setIconSize(QSize(14, 14))
                remove_btn.setFixedSize(26, 26)
                remove_btn.setToolTip("Remove this line")
                remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                remove_btn.setStyleSheet(_REMOVE_LINE_ICON_QSS)
                remove_btn.setAutoDefault(False)
                remove_btn.clicked.connect(lambda: self._remove_line_item(remove_btn))
                self.items_table.setCellWidget(row, 8, remove_btn)
        finally:
            db.close()

        self._recalc_totals()
        self._update_overall_type_label()
        self._dirty = False
        return repriced

    def print_receipt(self, sale_id: int) -> None:
        print_sale_receipt(sale_id, parent=self)
