"""The round PENDING ball and the pending-invoices popup list."""
import datetime as dt
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, Customer, Invoice
from app.qt_ui import invoice_list_dialog as ild
from app.qt_ui import invoice_style
from app.qt_ui.invoice_list_dialog import InvoiceListDialog, InvoiceRow

UTC_NOW = dt.datetime(2026, 11, 25, 12, 0, 0)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    from app.qt_ui.theme import apply_theme

    apply_theme(app)
    return app


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _inv(db, number, when=None, sync="PENDING", fbr=None, attempts=0, next_at=None, message=None, processing=False,
         name="ALI", amount=500.0):
    cust = db.query(Customer).filter_by(cnic=f"c-{name}").first()
    if cust is None:
        cust = Customer(cnic=f"c-{name}", name=name)
        db.add(cust)
        db.flush()
    inv = Invoice(invoice_number=number, pos_id="1", usin=number, datetime=when or dt.datetime(2026, 11, 20, 9, 0),
                  customer_id=cust.id, total_sale_value=amount, total_tax_charged=0.0, total_quantity=1.0,
                  total_amount=amount, fbr_invoice_number=fbr, sync_status=sync, upload_attempts=attempts,
                  next_upload_attempt=next_at, fbr_response_message=message, is_processing=processing)
    db.add(inv)
    db.commit()
    return inv


# ---- which invoices are pending ------------------------------------------------------------
def test_pending_means_no_fbr_number_and_not_failed(db):
    _inv(db, "WAITING", sync="PENDING")
    _inv(db, "OLD-NULL-STATUS", sync=None)
    _inv(db, "DONE", sync="SYNCED", fbr="FBR-1")
    _inv(db, "FAILED-ONE", sync="FAILED")
    names = {r.invoice_number for r in ild.fetch_pending_invoices(db)}
    assert names == {"WAITING", "OLD-NULL-STATUS"}
    assert ild.count_pending(db) == 2


def test_the_count_always_equals_the_list_length(db):
    for i in range(7):
        _inv(db, f"P{i}")
    _inv(db, "F", sync="FAILED")
    _inv(db, "S", sync="SYNCED", fbr="X")
    assert ild.count_pending(db) == len(ild.fetch_pending_invoices(db)) == 7


def test_oldest_first_with_queue_fields(db):
    _inv(db, "NEW", when=dt.datetime(2026, 11, 24, 9, 0))
    _inv(db, "OLD", when=dt.datetime(2026, 11, 1, 9, 0), attempts=3, message="Network Error - Queued for retry: x",
         next_at=UTC_NOW + dt.timedelta(minutes=8))
    rows = ild.fetch_pending_invoices(db)
    assert [r.invoice_number for r in rows] == ["OLD", "NEW"]
    assert rows[0].attempts == 3 and rows[0].reason.startswith("Network Error") and rows[0].max_attempts == 5


def test_fetch_dispatch_and_scope_helpers(db):
    _inv(db, "A")
    assert [r.invoice_number for r in ild.fetch_invoices(db, "pending")] == ["A"]
    assert ild.scope_bounds("pending") == (None, None)
    assert "FBR" in ild.subtitle_for("pending")
    assert ild.column_keys("pending")[-3:] == ["attempts", "status", "reason"]
    assert ild.column_keys("today") == ["no", "inv", "date", "buyer", "cnic", "bike", "amount", "fbr"]


# ---- status text -----------------------------------------------------------------------------
def _row(**kw):
    base = dict(invoice_id=1, invoice_number="X", when=None, buyer="", cnic="", model="", chassis="", amount=1.0,
                fbr_invoice_number="")
    base.update(kw)
    return InvoiceRow(**base)


def test_status_stopped_after_max_attempts_tells_what_to_do():
    state, text = ild.pending_state(_row(attempts=5), UTC_NOW)
    assert state == ild.STATE_STOPPED and "Stopped after 5" in text and "Retry" in text
    assert "Retry FBR Upload" in ild.pending_hint(state, text)


def test_status_waiting_until_next_try():
    state, text = ild.pending_state(_row(attempts=2, next_attempt=UTC_NOW + dt.timedelta(minutes=4)), UTC_NOW)
    assert state == ild.STATE_WAITING and text.startswith("Waiting")


def test_status_queued_when_due_and_uploading_when_processing():
    assert ild.pending_state(_row(attempts=1, next_attempt=UTC_NOW - dt.timedelta(minutes=1)), UTC_NOW)[0] == ild.STATE_QUEUED
    assert ild.pending_state(_row(), UTC_NOW)[0] == ild.STATE_QUEUED
    assert ild.pending_state(_row(is_processing=True, attempts=5), UTC_NOW)[0] == ild.STATE_UPLOADING


# ---- the dialog ------------------------------------------------------------------------------
def _rows():
    return [
        _row(invoice_id=1, invoice_number="INV-1", when=dt.datetime(2026, 11, 20, 9, 0), buyer="MUHAMMAD ALI",
             model="CD70", chassis="HB1", amount=9000.0, attempts=5, reason="Network Error (Max Retries) - Queued"),
        _row(invoice_id=2, invoice_number="INV-2", when=dt.datetime(2026, 11, 21, 9, 0), buyer="BILAL HUSSAIN",
             amount=250.0, attempts=1, next_attempt=UTC_NOW + dt.timedelta(minutes=2), reason="timeout"),
        _row(invoice_id=3, invoice_number="INV-3", when=dt.datetime(2026, 11, 22, 9, 0), buyer="SAIMA BIBI",
             amount=75000.5),
    ]


def _dialog(qapp):
    d = InvoiceListDialog(None, "pending", _rows())
    return d


def test_dialog_shows_pending_columns_and_count(qapp):
    d = _dialog(qapp)
    heads = [d.table.horizontalHeaderItem(i).text() for i in range(d.table.columnCount())]
    assert heads == ["#", "Invoice No.", "Date & Time", "Buyer", "Model / Chassis", "Amount (Rs.)", "Attempts",
                     "Status", "Last message"]
    assert d.count_label.text() == "3 invoices" and d.title_label.text() == "Pending Upload"
    d.deleteLater()


def test_dialog_lists_oldest_first_with_attempts_and_status(qapp):
    d = _dialog(qapp)
    c = d.col
    order = [d.table.item(r, c["inv"]).text() for r in range(3)]
    assert order == ["INV-1", "INV-2", "INV-3"]
    assert d.table.item(0, c["attempts"]).text() == "5 / 5"
    assert d.table.item(0, c["status"]).text().startswith("Stopped after 5")
    assert "Retry FBR Upload" in d.table.item(0, c["status"]).toolTip()
    assert d.table.item(0, c["reason"]).toolTip().startswith("Network Error")
    d.deleteLater()


def test_search_matches_status_and_message(qapp):
    d = _dialog(qapp)
    d.search.setText("timeout")
    shown = [d.table.item(r, d.col["inv"]).text() for r in range(3) if not d.table.isRowHidden(r)]
    assert shown == ["INV-2"]
    d.search.setText("stopped after")
    shown = [d.table.item(r, d.col["inv"]).text() for r in range(3) if not d.table.isRowHidden(r)]
    assert shown == ["INV-1"]
    d.deleteLater()


def test_copy_button_copies_the_invoice_number(qapp):
    d = _dialog(qapp)
    assert d.copy_button.text() == "Copy Invoice No."
    d.table.selectRow(0)
    d.copy_button.click()
    assert QApplication.clipboard().text() == "INV-1" and "Copied" in d.copy_button.text()
    d.deleteLater()


def test_empty_pending_list_says_everything_is_uploaded(qapp):
    d = InvoiceListDialog(None, "pending", [])
    assert "every invoice has been uploaded" in d.empty_label.text()
    assert d.table.isHidden() or not d.table.isVisible()
    d.deleteLater()


def test_submitted_lists_are_unchanged(qapp):
    d = InvoiceListDialog(None, "all", [])
    assert d.table.columnCount() == 8 and d.copy_button.text() == "Copy FBR ID"
    d.deleteLater()


# ---- the ball --------------------------------------------------------------------------------
def test_ball_shows_the_count_and_switches_colour_at_zero(qapp):
    ball = invoice_style.build_pending_ball(None, 3)
    assert ball.count() == 3 and ball.display_text() == "3" and ball.palette_stops() is invoice_style.BALL_PENDING
    ball.setCount(0)
    assert ball.palette_stops() is invoice_style.BALL_CLEAR
    ball.setText("1,204")
    assert ball.count() == 1204 and ball.display_text() == "999+"
    ball.setText("not a number")
    assert ball.count() == 1204
    ball.setCount(-5)
    assert ball.count() == 0
    ball.deleteLater()


def test_ball_is_round_and_paints(qapp):
    ball = invoice_style.build_pending_ball(None, 12)
    assert ball.width() == ball.height() == invoice_style.BALL_SIZE
    img = ball.grab().toImage()
    centre = img.pixelColor(img.width() // 2, img.height() // 2)
    corner = img.pixelColor(1, 1)
    assert centre.alpha() == 255                  # the ball is solid in the middle...
    assert corner.alpha() < 40                    # ...and transparent in the corners (it is round)
    ball.deleteLater()


def _luminance(hex_colour):
    h = hex_colour.lstrip("#")
    chans = []
    for i in (0, 2, 4):
        v = int(h[i:i + 2], 16) / 255
        chans.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
    return 0.2126 * chans[0] + 0.7152 * chans[1] + 0.0722 * chans[2]


@pytest.mark.parametrize("stops", [invoice_style.BALL_PENDING, invoice_style.BALL_CLEAR])
def test_the_balls_text_is_readable_on_its_colours(stops):
    lt = _luminance(stops["text"])
    for key, minimum in (("mid", 3.0), ("rim", 4.5)):     # the number sits on mid, the caption near the rim
        lb = _luminance(stops[key])
        ratio = (max(lt, lb) + 0.05) / (min(lt, lb) + 0.05)
        assert ratio >= minimum, (key, stops[key], ratio)


def test_the_waiting_ball_is_yellow():
    h = invoice_style.BALL_PENDING["mid"].lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    assert r > 230 and g > 190 and b < 90                 # yellow: high red + green, low blue


# ---- Retry button on every pending row -------------------------------------------------------
def _retry_dialog(qapp, calls, rows=None, reload=None):
    return InvoiceListDialog(None, "pending", rows if rows is not None else _rows(), on_retry=calls.append, reload=reload)


def test_no_retry_column_without_a_handler(qapp):
    d = _dialog(qapp)
    assert "action" not in d.col and d.retry_button(0) is None
    d.deleteLater()


def test_every_row_gets_its_own_retry_button(qapp):
    calls = []
    d = _retry_dialog(qapp, calls)
    assert d.table.horizontalHeaderItem(d.table.columnCount() - 1).text() == "Action"
    assert len(d._retry_buttons) == 3 and all(b.text() == "Retry" for b in d._retry_buttons.values())
    d.retry_button(1).click()
    assert calls == [2]                                    # row 1 = INV-2 (invoice_id 2)
    d.deleteLater()


def test_each_button_retries_the_invoice_in_its_own_row_after_sorting(qapp):
    from PyQt6.QtCore import Qt

    calls = []
    d = _retry_dialog(qapp, calls)
    d.table.sortItems(d.col["amount"], Qt.SortOrder.DescendingOrder)     # 75,000.50 / 9,000 / 250
    d.table.horizontalHeader().sortIndicatorChanged.emit(d.col["amount"], Qt.SortOrder.DescendingOrder)
    for r in range(3):
        d.retry_button(r).click()
        invoice_no = d.table.item(r, d.col["inv"]).text()
        assert calls[-1] == {"INV-1": 1, "INV-2": 2, "INV-3": 3}[invoice_no]
    d.deleteLater()


def test_an_invoice_that_is_uploading_cannot_be_retried(qapp):
    rows = [_row(invoice_id=9, invoice_number="BUSY", is_processing=True, when=dt.datetime(2026, 11, 1))]
    d = _retry_dialog(qapp, [], rows)
    assert not d.retry_button(0).isEnabled()
    d.deleteLater()


def test_after_a_retry_the_list_reloads_and_keeps_the_search(qapp):
    calls = []
    fresh = [_row(invoice_id=2, invoice_number="INV-2", when=dt.datetime(2026, 11, 21), attempts=0,
                  buyer="BILAL HUSSAIN")]
    d = _retry_dialog(qapp, calls, reload=lambda: fresh)
    d.search.setText("bilal")
    d.retry_button(1).click()
    assert d.table.rowCount() == 1 and d.table.item(0, d.col["attempts"]).text() == "0 / 5"
    assert d.search.text() == "bilal" and d.count_label.text() == "1 invoice"
    assert len(d._retry_buttons) == 1
    d.deleteLater()


def test_retry_disappears_when_the_invoice_was_uploaded_meanwhile(qapp):
    d = _retry_dialog(qapp, [], reload=lambda: [])
    d.retry_button(0).click()
    assert d.table.rowCount() == 0 and "every invoice has been uploaded" in d.empty_label.text()
    d.deleteLater()


def test_show_invoice_list_wires_retry_to_the_window_action(qapp, db, monkeypatch):
    import app.db.session as dbs

    _inv(db, "WIRED")
    monkeypatch.setattr(dbs, "SessionLocal", lambda: db)
    seen = {}

    from PyQt6.QtWidgets import QWidget

    class Window(QWidget):
        def _retry_invoice_upload(self, invoice_id):
            seen["retried"] = invoice_id

    def fake_exec(self):
        seen["has_retry"] = self.on_retry is not None
        if self.on_retry is not None:
            self.retry_button(0).click()
        seen["reloaded_rows"] = len(self.rows)

    monkeypatch.setattr(InvoiceListDialog, "exec", fake_exec)
    ild.show_invoice_list(Window(), "pending")
    assert seen["has_retry"] and seen["retried"] == db.query(Invoice).filter_by(invoice_number="WIRED").one().id
    assert seen["reloaded_rows"] == 1
    seen.clear()
    ild.show_invoice_list(Window(), "all")                  # submitted lists have no retry
    assert seen["has_retry"] is False
