"""Popup list of the invoices behind a header card on the Create Invoice page.

Clicking "Submitted Today", "Submitted This Month" or "FBR Submitted" opens this list. It
applies EXACTLY the rules the card's own counter uses (an invoice counts when it has an FBR
invoice number, within the card's date range), so the number on the card always equals the
number of rows here. The round PENDING ball opens the same dialog in its "pending" form: the
invoices saved locally that FBR has not accepted yet (same rule as the Dashboard's Pending
card), with attempts, next retry and the last message. Read-only: it never changes an invoice.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Callable, Optional

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor, QGuiApplication
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.qt_ui.invoice_style import _gradient
from app.qt_ui.theme import _qta

SCOPES = {
    "today": dict(title="Submitted Today", accent="#2578b5", icon="fa5s.calendar-day",
                  empty="No invoices have been submitted to FBR today."),
    "month": dict(title="Submitted This Month", accent="#8340a0", icon="fa5s.calendar-alt",
                  empty="No invoices have been submitted to FBR this month."),
    "all": dict(title="FBR Submitted", accent="#17934d", icon="fa5s.cloud-upload-alt",
                empty="No invoices have been submitted to FBR yet."),
    "pending": dict(title="Pending Upload", accent="#b4540a", icon="fa5s.clock",
                    empty="Nothing is pending - every invoice has been uploaded to FBR."),
}

COLUMNS = ["#", "Invoice No.", "Date & Time", "Buyer", "CNIC", "Model / Chassis", "Amount (Rs.)", "FBR Invoice ID"]
_COL_NO, _COL_INV, _COL_DATE, _COL_BUYER, _COL_CNIC, _COL_BIKE, _COL_AMOUNT, _COL_FBR = range(8)

# Column layout per scope, by key (the submitted lists keep the original columns exactly).
HEADERS = {
    "no": "#", "inv": "Invoice No.", "date": "Date & Time", "buyer": "Buyer", "cnic": "CNIC",
    "bike": "Model / Chassis", "amount": "Amount (Rs.)", "fbr": "FBR Invoice ID",
    "attempts": "Attempts", "status": "Status", "reason": "Last message", "action": "Action",
}
_SUBMITTED_KEYS = ["no", "inv", "date", "buyer", "cnic", "bike", "amount", "fbr"]
_PENDING_KEYS = ["no", "inv", "date", "buyer", "bike", "amount", "attempts", "status", "reason"]


def column_keys(scope: str, with_action: bool = False) -> list[str]:
    keys = list(_PENDING_KEYS if scope == "pending" else _SUBMITTED_KEYS)
    if with_action and scope == "pending":
        keys.append("action")          # a Retry button on every row
    return keys


@dataclass
class InvoiceRow:
    invoice_id: int
    invoice_number: str
    when: Optional[dt.datetime]
    buyer: str
    cnic: str
    model: str
    chassis: str
    amount: float
    fbr_invoice_number: str
    # only filled for the "pending" list
    attempts: int = 0
    max_attempts: int = 5
    next_attempt: Optional[dt.datetime] = None      # UTC, as stored by the upload queue
    reason: str = ""
    is_processing: bool = False

    @property
    def bike(self) -> str:
        return " · ".join(p for p in (self.model, self.chassis) if p)


# ---- which invoices ---------------------------------------------------------------------
def scope_bounds(scope: str, now: Optional[dt.datetime] = None):
    """(start, end) for a scope - the SAME bounds the header counters use. `None`
    means unbounded on that side ("all" has no date limit)."""
    now = now or dt.datetime.now()
    end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    if scope == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0), end_of_day
    if scope == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0), end_of_day
    if scope in ("all", "pending"):
        return None, None
    raise ValueError(f"unknown scope {scope!r}")


def fetch_submitted_invoices(db, scope: str, now: Optional[dt.datetime] = None) -> list[InvoiceRow]:
    """Invoices with an FBR invoice number in the scope's date range, newest first."""
    from app.db.models import Customer, Invoice, InvoiceItem, Motorcycle, ProductModel

    start, end = scope_bounds(scope, now)
    q = (
        db.query(
            Invoice.id, Invoice.invoice_number, Invoice.datetime, Invoice.total_amount,
            Invoice.fbr_invoice_number, Customer.name, Customer.cnic,
            ProductModel.model_name, Motorcycle.chassis_number, InvoiceItem.item_name,
        )
        .outerjoin(Customer, Invoice.customer_id == Customer.id)
        .outerjoin(InvoiceItem, InvoiceItem.invoice_id == Invoice.id)
        .outerjoin(Motorcycle, InvoiceItem.motorcycle_id == Motorcycle.id)
        .outerjoin(ProductModel, Motorcycle.product_model_id == ProductModel.id)
        .filter(Invoice.fbr_invoice_number != None)  # noqa: E711 - same filter as the counters
    )
    if start is not None:
        q = q.filter(Invoice.datetime >= start)
    if end is not None:
        q = q.filter(Invoice.datetime <= end)
    q = q.order_by(Invoice.datetime.desc(), Invoice.id.desc())

    rows: list[InvoiceRow] = []
    seen: set[int] = set()
    for (inv_id, number, when, total, fbr, name, cnic, model, chassis, item_name) in q.all():
        if inv_id in seen:                 # an invoice with several items appears once
            continue
        seen.add(inv_id)
        rows.append(InvoiceRow(
            invoice_id=inv_id, invoice_number=number or "", when=when, buyer=name or "", cnic=cnic or "",
            model=model or "", chassis=chassis or "", amount=float(total or 0), fbr_invoice_number=fbr or "",
        ))
    return rows


def pending_filter():
    """SQL condition for "still waiting for FBR": no FBR invoice number and not marked FAILED
    (FAILED ones have their own Retry list). The header ball AND this list both use it, so the
    number on the ball always equals the number of rows."""
    from sqlalchemy import and_, or_
    from app.db.models import Invoice

    return and_(Invoice.fbr_invoice_number == None,  # noqa: E711
                or_(Invoice.sync_status == None, Invoice.sync_status != "FAILED"))  # noqa: E711


def count_pending(db) -> int:
    from app.db.models import Invoice

    return db.query(Invoice).filter(pending_filter()).count()


def fetch_pending_invoices(db) -> list[InvoiceRow]:
    """Invoices waiting for FBR, oldest first (the order the upload queue sends them)."""
    from app.db.models import Customer, Invoice, InvoiceItem, Motorcycle, ProductModel

    q = (
        db.query(
            Invoice.id, Invoice.invoice_number, Invoice.datetime, Invoice.total_amount,
            Customer.name, Customer.cnic, ProductModel.model_name, Motorcycle.chassis_number,
            Invoice.upload_attempts, Invoice.max_upload_attempts, Invoice.next_upload_attempt,
            Invoice.fbr_response_message, Invoice.is_processing,
        )
        .outerjoin(Customer, Invoice.customer_id == Customer.id)
        .outerjoin(InvoiceItem, InvoiceItem.invoice_id == Invoice.id)
        .outerjoin(Motorcycle, InvoiceItem.motorcycle_id == Motorcycle.id)
        .outerjoin(ProductModel, Motorcycle.product_model_id == ProductModel.id)
        .filter(pending_filter())
        .order_by(Invoice.datetime.asc(), Invoice.id.asc())
    )
    rows: list[InvoiceRow] = []
    seen: set[int] = set()
    for (inv_id, number, when, total, name, cnic, model, chassis, attempts, max_attempts, next_at,
         message, processing) in q.all():
        if inv_id in seen:
            continue
        seen.add(inv_id)
        rows.append(InvoiceRow(
            invoice_id=inv_id, invoice_number=number or "", when=when, buyer=name or "", cnic=cnic or "",
            model=model or "", chassis=chassis or "", amount=float(total or 0), fbr_invoice_number="",
            attempts=int(attempts or 0), max_attempts=int(max_attempts or 5), next_attempt=next_at,
            reason=message or "", is_processing=bool(processing),
        ))
    return rows


def fetch_invoices(db, scope: str, now: Optional[dt.datetime] = None) -> list[InvoiceRow]:
    return fetch_pending_invoices(db) if scope == "pending" else fetch_submitted_invoices(db, scope, now)


# Status shown for a pending invoice, from what the upload queue stores:
STATE_STOPPED, STATE_UPLOADING, STATE_WAITING, STATE_QUEUED = "stopped", "uploading", "waiting", "queued"


def pending_state(row: InvoiceRow, utc_now: Optional[dt.datetime] = None) -> tuple[str, str]:
    """(state, plain-language text) for a pending invoice. The queue stores its retry time in
    UTC; it is shown in local time."""
    utc_now = utc_now or dt.datetime.utcnow()
    if row.is_processing:
        return STATE_UPLOADING, "Uploading now"
    if row.attempts >= row.max_attempts:
        return STATE_STOPPED, "Stopped after %d tries - needs Retry" % row.attempts
    if row.next_attempt and row.next_attempt > utc_now:
        local = row.next_attempt + (dt.datetime.now() - dt.datetime.utcnow())
        return STATE_WAITING, "Waiting - next try %s" % local.strftime("%I:%M %p").lstrip("0")
    return STATE_QUEUED, "Queued - uploads automatically"


def pending_hint(state: str, text: str) -> str:
    """Tooltip for the status cell (the cell itself stays short)."""
    if state == STATE_STOPPED:
        return ("Automatic retries are used up. Open this invoice from the invoice list and click "
                "'Retry FBR Upload' once the internet / FBR settings are fine.")
    return text


# ---- formatting -------------------------------------------------------------------------
def format_amount(value: float) -> str:
    return f"{value:,.2f}"


def format_when(value: Optional[dt.datetime]) -> str:
    return value.strftime("%d %b %Y  %I:%M %p") if value else ""


def subtitle_for(scope: str, now: Optional[dt.datetime] = None) -> str:
    now = now or dt.datetime.now()
    if scope == "today":
        return now.strftime("%A, %d %B %Y")
    if scope == "month":
        return now.strftime("%B %Y")
    if scope == "pending":
        return "Saved locally - not yet accepted by FBR"
    return "All invoices uploaded to FBR"


# ---- the dialog -------------------------------------------------------------------------
class _SortItem(QTableWidgetItem):
    """Sorts by a real value (number / datetime) rather than by the displayed text."""

    def __lt__(self, other):  # noqa: D105
        a, b = self.data(Qt.ItemDataRole.UserRole), other.data(Qt.ItemDataRole.UserRole)
        try:
            return a < b
        except TypeError:
            return str(a) < str(b)


def _qss(accent: str) -> str:
    return f"""
    QDialog#invoiceListDialog {{ background-color: #f4f6fa; }}
    QFrame#listHeader {{ background: {_gradient(accent)}; border: none; }}
    QLabel#listIcon {{ background-color: rgba(255,255,255,0.22); border-radius: 12px; }}
    QLabel#listTitle {{ color: #ffffff; font-size: 20px; font-weight: 800; background: transparent; }}
    QLabel#listSubtitle {{ color: rgba(255,255,255,0.88); font-size: 13px; background: transparent; }}
    QLabel#listCount {{
        color: #ffffff; font-size: 13px; font-weight: 800; background-color: rgba(255,255,255,0.22);
        border: 1px solid rgba(255,255,255,0.45); border-radius: 14px; padding: 5px 14px;
    }}
    QLineEdit#listSearch {{
        background-color: #ffffff; border: 1px solid #c8d1db; border-radius: 10px;
        padding: 9px 14px; font-size: 14px; color: #263445;
    }}
    QLineEdit#listSearch:focus {{ border: 1px solid #3b82c4; }}
    QTableWidget#listTable {{
        background-color: #ffffff; alternate-background-color: #f8fafc; border: 1px solid #dce3ea;
        border-radius: 10px; gridline-color: transparent; font-size: 13px; color: #263445; outline: 0;
        selection-background-color: #dcebf9; selection-color: #1f4068;
    }}
    QTableWidget#listTable::item {{ padding: 6px 10px; border: none; }}
    QHeaderView::section {{
        background-color: #eef2f7; color: #3a4d62; font-size: 12px; font-weight: 700;
        padding: 10px; border: none; border-bottom: 2px solid #dce3ea;
    }}
    QLabel#listEmpty {{ color: #6b7a8b; font-size: 15px; background: transparent; }}
    QLabel#listSummary {{ color: #3a4d62; font-size: 13px; font-weight: 600; background: transparent; }}
    QFrame#listFooter {{ background-color: #ffffff; border: none; border-top: 1px solid #dce3ea; }}
    QPushButton#listClose {{
        background-color: {accent}; color: #ffffff; border: none; border-radius: 9px;
        padding: 10px 28px; font-size: 14px; font-weight: 700;
    }}
    QPushButton#listClose:hover {{ background-color: #2b5f92; }}
    QPushButton#rowRetry {{
        background-color: #fff4d0; color: #6b4200; border: 1px solid #e0a200; border-radius: 8px;
        padding: 0 14px; font-size: 13px; font-weight: 700;
    }}
    QPushButton#rowRetry:hover {{ background-color: #ffe27a; }}
    QPushButton#rowRetry:disabled {{ color: #a3aebb; background-color: #f4f6fa; border-color: #dce3ea; }}
    QPushButton#listCopy {{
        background-color: #ffffff; color: #263445; border: 1px solid #c8d1db; border-radius: 9px;
        padding: 10px 18px; font-size: 13px; font-weight: 600;
    }}
    QPushButton#listCopy:hover {{ background-color: #eef2f7; }}
    QPushButton#listCopy:disabled {{ color: #a3aebb; background-color: #f4f6fa; border-color: #dce3ea; }}
    """


class InvoiceListDialog(QDialog):
    def __init__(self, parent: Optional[QWidget], scope: str, rows: list[InvoiceRow],
                 now: Optional[dt.datetime] = None,
                 on_retry: Optional[Callable[[int], None]] = None,
                 reload: Optional[Callable[[], list[InvoiceRow]]] = None):
        """`on_retry(invoice_id)` (pending list only) adds a Retry button to every row that calls it;
        `reload()` then returns the fresh rows so the list shows the new status."""
        super().__init__(parent)
        meta = SCOPES[scope]
        self.scope = scope
        self.rows = rows
        self._retry_buttons = {}
        self.on_retry = on_retry if scope == "pending" else None
        self.reload = reload
        self.keys = column_keys(scope, with_action=self.on_retry is not None)
        self.col = {k: i for i, k in enumerate(self.keys)}
        self._utc_now = None          # tests can pin the clock used for the pending status text
        self.setObjectName("invoiceListDialog")
        self.setWindowTitle(f"{meta['title']} — Invoices")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.resize(1380 if self.on_retry is not None else 1200, 660)
        self.setMinimumSize(920, 420)
        self.setStyleSheet(_qss(meta["accent"]))

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- header ----------------------------------------------------------------
        header = QFrame()
        header.setObjectName("listHeader")
        h = QHBoxLayout(header)
        h.setContentsMargins(28, 20, 28, 20)
        h.setSpacing(16)
        icon = QLabel()
        icon.setObjectName("listIcon")
        icon.setFixedSize(48, 48)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if _qta is not None:
            try:
                icon.setPixmap(_qta.icon(meta["icon"], color="#ffffff").pixmap(22, 22))
            except Exception:
                pass
        h.addWidget(icon)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        self.title_label = QLabel(meta["title"])
        self.title_label.setObjectName("listTitle")
        self.subtitle_label = QLabel(subtitle_for(scope, now))
        self.subtitle_label.setObjectName("listSubtitle")
        titles.addWidget(self.title_label)
        titles.addWidget(self.subtitle_label)
        h.addLayout(titles, 1)
        self.count_label = QLabel("")
        self.count_label.setObjectName("listCount")
        h.addWidget(self.count_label, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(header)

        # ---- search + table ----------------------------------------------------------
        body = QVBoxLayout()
        body.setContentsMargins(24, 18, 24, 14)
        body.setSpacing(12)
        self.search = QLineEdit()
        self.search.setObjectName("listSearch")
        self.search.setPlaceholderText(
            "Search invoice no., buyer, chassis, status or message…" if scope == "pending"
            else "Search invoice no., buyer, CNIC, chassis or FBR invoice ID…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        body.addWidget(self.search)

        self.table = QTableWidget(0, len(self.keys))
        self.table.setObjectName("listTable")
        self.table.setHorizontalHeaderLabels([HEADERS[k] for k in self.keys])
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(48 if self.on_retry is not None else 40)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.itemSelectionChanged.connect(self._on_selection)
        hh = self.table.horizontalHeader()
        hh.setStretchLastSection(False)
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        c = self.col
        stretch = ["buyer", "bike"] + (["reason"] if scope == "pending" else [])
        for key in stretch:
            hh.setSectionResizeMode(c[key], QHeaderView.ResizeMode.Stretch)
        if "fbr" in c:
            hh.setSectionResizeMode(c["fbr"], QHeaderView.ResizeMode.ResizeToContents)
        widths = {"no": 48, "inv": 100, "date": 168, "cnic": 138, "amount": 112, "attempts": 84, "status": 244,
                  "action": 104}
        for key, width in widths.items():
            if key in c:
                self.table.setColumnWidth(c[key], width)
        body.addWidget(self.table, 1)

        self.empty_label = QLabel(meta["empty"])
        self.empty_label.setObjectName("listEmpty")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.addWidget(self.empty_label, 1)
        wrapper = QWidget()
        wrapper.setLayout(body)
        root.addWidget(wrapper, 1)

        # ---- footer ------------------------------------------------------------------
        footer = QFrame()
        footer.setObjectName("listFooter")
        f = QHBoxLayout(footer)
        f.setContentsMargins(24, 14, 24, 14)
        f.setSpacing(10)
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("listSummary")
        f.addWidget(self.summary_label, 1)
        self.copy_button = QPushButton(self._copy_label())
        self.copy_button.setObjectName("listCopy")
        self.copy_button.setAutoDefault(False)
        self.copy_button.setEnabled(False)
        self.copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_button.clicked.connect(self._copy_fbr_id)
        f.addWidget(self.copy_button)
        self.close_button = QPushButton("Close")
        self.close_button.setObjectName("listClose")
        self.close_button.setDefault(True)
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.clicked.connect(self.accept)
        f.addWidget(self.close_button)
        root.addWidget(footer)

        self._populate()
        self._apply_filter()
        # "#" always counts the rows you can SEE, in the order you see them
        # (a Qt table keeps 'hidden' per row POSITION, so re-apply the filter after every sort)
        self.table.horizontalHeader().sortIndicatorChanged.connect(lambda *_: (self._apply_filter(), self._place_retry_buttons()))

    # ---- content -----------------------------------------------------------------------
    _STATE_COLOURS = {STATE_STOPPED: "#b42318", STATE_UPLOADING: "#1d6fb8",
                      STATE_WAITING: "#a15c07", STATE_QUEUED: "#2f6f4f"}

    def _populate(self) -> None:
        t = self.table
        c = self.col
        t.setSortingEnabled(False)
        t.setRowCount(len(self.rows))
        mono_keys = {"inv", "cnic", "fbr"}
        for r, row in enumerate(self.rows):
            cells = {
                "no": (str(r + 1), r + 1),
                "inv": (row.invoice_number, row.invoice_number),
                "date": (format_when(row.when), row.when or dt.datetime.min),
                "buyer": (row.buyer, row.buyer.lower()),
                "cnic": (row.cnic, row.cnic),
                "bike": (row.bike, row.bike.lower()),
                "amount": (format_amount(row.amount), row.amount),
                "fbr": (row.fbr_invoice_number, row.fbr_invoice_number),
            }
            state, state_text = STATE_QUEUED, ""
            if self.scope == "pending":
                state, state_text = pending_state(row, self._utc_now)
                cells["attempts"] = (f"{row.attempts} / {row.max_attempts}", row.attempts)
                cells["status"] = (state_text, state_text.lower())
                cells["reason"] = (row.reason, row.reason.lower())
            cells["action"] = ("", "")
            for key in self.keys:
                text, sort_key = cells[key]
                item = _SortItem(text)
                item.setData(Qt.ItemDataRole.UserRole, sort_key)
                if key == "amount":
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                elif key in ("no", "attempts"):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if key in mono_keys:
                    font = item.font()
                    font.setFamily("Consolas")
                    item.setFont(font)
                if key == "status":
                    item.setForeground(QColor(self._STATE_COLOURS[state]))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    item.setToolTip(pending_hint(state, state_text))
                if key == "reason" and row.reason:
                    item.setToolTip(row.reason)
                t.setItem(r, c[key], item)
            t.item(r, c["inv"]).setData(Qt.ItemDataRole.UserRole + 1, r)     # index into self.rows
        t.setSortingEnabled(True)
        # submitted: newest first; pending: oldest first (the order the queue uploads them)
        t.sortItems(c["date"], Qt.SortOrder.AscendingOrder if self.scope == "pending" else Qt.SortOrder.DescendingOrder)
        self._place_retry_buttons()

    # ---- retry (pending list) ----------------------------------------------------------------
    def retry_button(self, table_row: int):
        return self._retry_buttons.get(table_row)

    def _place_retry_buttons(self) -> None:
        """One Retry button per row. Rebuilt after every sort/reload so each button always sits
        on - and retries - the invoice shown in its own row."""
        self._retry_buttons = {}
        if self.on_retry is None:
            return
        t = self.table
        col = self.col["action"]
        for r in range(t.rowCount()):
            row = self._row_for(r)
            t.removeCellWidget(r, col)
            if row is None:
                continue
            button = QPushButton("Retry")
            button.setObjectName("rowRetry")
            button.setAutoDefault(False)
            button.setFixedHeight(32)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            uploading = pending_state(row, self._utc_now)[0] == STATE_UPLOADING
            button.setEnabled(not uploading)
            button.setToolTip("Uploading right now" if uploading else
                              f"Reset the attempts and upload invoice {row.invoice_number} to FBR again")
            button.clicked.connect(lambda _checked=False, iid=row.invoice_id: self._retry(iid))
            holder = QWidget()
            lay = QHBoxLayout(holder)
            lay.setContentsMargins(8, 0, 8, 0)
            lay.addWidget(button)
            t.setCellWidget(r, col, holder)
            self._retry_buttons[r] = button

    def _retry(self, invoice_id: int) -> None:
        if self.on_retry is None:
            return
        self.on_retry(invoice_id)
        if self.reload is not None:
            self.set_rows(self.reload())

    def set_rows(self, rows: list[InvoiceRow]) -> None:
        """Replace the rows (keeps the search text) - used after a retry."""
        self.rows = rows
        self._populate()
        self._apply_filter()

    def _row_for(self, table_row: int) -> Optional[InvoiceRow]:
        item = self.table.item(table_row, self.col["inv"])
        if item is None:
            return None
        idx = item.data(Qt.ItemDataRole.UserRole + 1)
        return self.rows[idx] if idx is not None else None

    def _renumber(self) -> None:
        """Number the visible rows 1..n in their current (sorted) order."""
        n = 0
        for r in range(self.table.rowCount()):
            item = self.table.item(r, self.col["no"])
            if item is None:
                continue
            if self.table.isRowHidden(r):
                item.setText("")
                continue
            n += 1
            item.setText(str(n))
            item.setData(Qt.ItemDataRole.UserRole, n)

    def _apply_filter(self) -> None:
        needle = self.search.text().strip().lower()
        shown, total = 0, 0.0
        for r in range(self.table.rowCount()):
            row = self._row_for(r)
            hay = " ".join([row.invoice_number, row.buyer, row.cnic, row.chassis, row.model,
                            row.fbr_invoice_number, row.reason,
                            pending_state(row, self._utc_now)[1] if self.scope == "pending" else ""]).lower() if row else ""
            visible = not needle or needle in hay
            self.table.setRowHidden(r, not visible)
            if visible and row:
                shown += 1
                total += row.amount
        n_all = len(self.rows)
        self.count_label.setText(f"{n_all} invoice{'s' if n_all != 1 else ''}")
        has_rows = n_all > 0
        self.table.setVisible(has_rows)
        self.search.setVisible(has_rows)
        self.empty_label.setVisible(not has_rows)
        if not has_rows:
            self.summary_label.setText("")
        elif needle:
            self.summary_label.setText(f"Showing {shown} of {n_all} · Total Rs. {format_amount(total)}")
        else:
            self.summary_label.setText(f"{n_all} invoice{'s' if n_all != 1 else ''} · Total Rs. {format_amount(total)}")
        self._renumber()

    # ---- selection / copy ----------------------------------------------------------------
    def selected_row(self) -> Optional[InvoiceRow]:
        sel = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        return self._row_for(sel[0].row()) if sel else None

    def _on_selection(self) -> None:
        self.copy_button.setEnabled(self.selected_row() is not None)
        self.copy_button.setText(self._copy_label())

    def _copy_label(self) -> str:
        return "Copy Invoice No." if self.scope == "pending" else "Copy FBR ID"

    def _copy(self, text: str) -> None:
        QGuiApplication.clipboard().setText(text)

    def _copy_fbr_id(self) -> None:
        row = self.selected_row()
        if row is not None:
            self._copy(row.invoice_number if self.scope == "pending" else row.fbr_invoice_number)
            self.copy_button.setText("Copied ✓")

    def _context_menu(self, pos: QPoint) -> None:
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        self.table.selectRow(index.row())
        row = self._row_for(index.row())
        if row is None:
            return
        menu = QMenu(self)
        menu.addAction("Copy invoice number", lambda: self._copy(row.invoice_number))
        if self.scope == "pending":
            if row.reason:
                menu.addAction("Copy last message", lambda: self._copy(row.reason))
        else:
            menu.addAction("Copy FBR invoice ID", lambda: self._copy(row.fbr_invoice_number))
        menu.exec(self.table.viewport().mapToGlobal(pos))


def show_invoice_list(parent, scope: str, now: Optional[dt.datetime] = None) -> None:
    """Load the invoices for a header card and show them (modal). Errors propagate to the
    caller, which reports them (see MainWindow._show_submitted_invoices)."""
    from app.db.session import SessionLocal

    def load() -> list[InvoiceRow]:
        db = SessionLocal()
        try:
            return fetch_invoices(db, scope, now)
        finally:
            db.close()

    # the pending list can re-queue an invoice (the window's existing "Retry FBR Upload" action)
    on_retry = getattr(parent, "_retry_invoice_upload", None) if scope == "pending" else None
    InvoiceListDialog(parent, scope, load(), now, on_retry=on_retry, reload=load).exec()
