"""Popup list of the invoices behind the Create Invoice header cards."""
import datetime as dt
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, Customer, Invoice, InvoiceItem, Motorcycle, ProductModel
from app.qt_ui import invoice_list_dialog as ild
from app.qt_ui.invoice_list_dialog import InvoiceListDialog, InvoiceRow

NOW = dt.datetime(2026, 11, 25, 17, 30)          # a Wednesday, mid-month


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


def _invoice(db, number, when, fbr="FBR-" , name="ALI", amount=1000.0, chassis=None, model="CD70", customer=True):
    cust = None
    if customer:
        cust = db.query(Customer).filter_by(cnic=f"cnic-{name}").first()
        if cust is None:
            cust = Customer(cnic=f"cnic-{name}", name=name)
            db.add(cust)
            db.flush()
    inv = Invoice(invoice_number=number, pos_id="1", usin=number, datetime=when, customer_id=cust.id if cust else None,
                  total_sale_value=amount, total_tax_charged=0.0, total_quantity=1.0, total_amount=amount,
                  fbr_invoice_number=(fbr + number) if fbr else None)
    db.add(inv)
    db.flush()
    if chassis:
        pm = db.query(ProductModel).filter_by(model_name=model).first() or ProductModel(model_name=model)
        db.add(pm)
        db.flush()
        bike = Motorcycle(chassis_number=chassis, engine_number="E-" + chassis, product_model_id=pm.id, year=2025,
                          color="RED", cost_price=0.0, sale_price=0.0, status="SOLD", purchase_date=when)
        db.add(bike)
        db.flush()
        db.add(InvoiceItem(invoice_id=inv.id, motorcycle_id=bike.id, item_code="X", item_name="Motorcycle",
                           quantity=1, tax_rate=18, sale_value=amount, tax_charged=0.0, total_amount=amount))
    db.commit()
    return inv


# ---- which invoices -----------------------------------------------------------------------
def test_scope_bounds_match_the_counters_definition():
    start, end = ild.scope_bounds("today", NOW)
    assert start == dt.datetime(2026, 11, 25, 0, 0, 0) and end == dt.datetime(2026, 11, 25, 23, 59, 59, 999999)
    start, end = ild.scope_bounds("month", NOW)
    assert start == dt.datetime(2026, 11, 1, 0, 0, 0) and end == dt.datetime(2026, 11, 25, 23, 59, 59, 999999)
    assert ild.scope_bounds("all", NOW) == (None, None)
    with pytest.raises(ValueError):
        ild.scope_bounds("week", NOW)


def test_today_includes_the_whole_day_and_nothing_else(db):
    _invoice(db, "A-start", dt.datetime(2026, 11, 25, 0, 0, 0))
    _invoice(db, "A-end", dt.datetime(2026, 11, 25, 23, 59, 59))
    _invoice(db, "A-yesterday", dt.datetime(2026, 11, 24, 23, 59, 59))
    _invoice(db, "A-tomorrow", dt.datetime(2026, 11, 26, 0, 0, 1))
    assert {r.invoice_number for r in ild.fetch_submitted_invoices(db, "today", NOW)} == {"A-start", "A-end"}


def test_month_runs_from_the_first_to_the_end_of_today(db):
    _invoice(db, "M-first", dt.datetime(2026, 11, 1, 0, 0, 0))
    _invoice(db, "M-today", dt.datetime(2026, 11, 25, 9, 0))
    _invoice(db, "M-prev", dt.datetime(2026, 10, 31, 23, 59, 59))
    _invoice(db, "M-future", dt.datetime(2026, 11, 26, 9, 0))
    assert {r.invoice_number for r in ild.fetch_submitted_invoices(db, "month", NOW)} == {"M-first", "M-today"}


def test_all_has_no_date_limit(db):
    _invoice(db, "L-old", dt.datetime(2024, 1, 5))
    _invoice(db, "L-new", dt.datetime(2026, 11, 25, 9, 0))
    assert len(ild.fetch_submitted_invoices(db, "all", NOW)) == 2


def test_only_invoices_with_an_fbr_number_are_listed(db):
    _invoice(db, "OK", dt.datetime(2026, 11, 25, 9, 0))
    _invoice(db, "NOT-UPLOADED", dt.datetime(2026, 11, 25, 9, 0), fbr=None)
    assert [r.invoice_number for r in ild.fetch_submitted_invoices(db, "today", NOW)] == ["OK"]


def test_newest_first_and_fields_are_filled_in(db):
    _invoice(db, "RE-1", dt.datetime(2026, 11, 25, 8, 0), name="OLD BUYER", amount=100.0)
    _invoice(db, "RE-2", dt.datetime(2026, 11, 25, 12, 0), name="NEW BUYER", amount=250.5, chassis="HB465367", model="CD70")
    rows = ild.fetch_submitted_invoices(db, "today", NOW)
    assert [r.invoice_number for r in rows] == ["RE-2", "RE-1"]
    top = rows[0]
    assert (top.buyer, top.cnic, top.model, top.chassis, top.amount) == ("NEW BUYER", "cnic-NEW BUYER", "CD70", "HB465367", 250.5)
    assert top.fbr_invoice_number == "FBR-RE-2" and top.bike == "CD70 · HB465367"


def test_an_invoice_with_two_items_is_listed_once(db):
    inv = _invoice(db, "TWO", dt.datetime(2026, 11, 25, 9, 0), chassis="C1")
    pm = db.query(ProductModel).first()
    bike2 = Motorcycle(chassis_number="C2", engine_number="E2", product_model_id=pm.id, year=2025, color="RED",
                       cost_price=0.0, sale_price=0.0, status="SOLD", purchase_date=NOW)
    db.add(bike2)
    db.flush()
    db.add(InvoiceItem(invoice_id=inv.id, motorcycle_id=bike2.id, item_code="X", item_name="M", quantity=1,
                       tax_rate=18, sale_value=1.0, tax_charged=0.0, total_amount=1.0))
    db.commit()
    assert len(ild.fetch_submitted_invoices(db, "today", NOW)) == 1


def test_an_invoice_with_no_customer_or_bike_still_lists(db):
    _invoice(db, "BARE", dt.datetime(2026, 11, 25, 9, 0), customer=False)
    row = ild.fetch_submitted_invoices(db, "today", NOW)[0]
    assert row.buyer == "" and row.cnic == "" and row.bike == ""


def test_formatting_helpers():
    assert ild.format_amount(1234567.5) == "1,234,567.50"
    assert ild.format_when(dt.datetime(2026, 11, 25, 17, 30)) == "25 Nov 2026  05:30 PM"
    assert ild.format_when(None) == ""
    assert ild.subtitle_for("today", NOW) == "Wednesday, 25 November 2026"
    assert ild.subtitle_for("month", NOW) == "November 2026"
    assert "FBR" in ild.subtitle_for("all", NOW)


# ---- the dialog -------------------------------------------------------------------------------
def _rows(n=5):
    names = ["MUHAMMAD ALI", "AHMED KHAN", "BILAL HUSSAIN", "SAIMA BIBI", "TARIQ MEHMOOD"]
    return [InvoiceRow(i + 1, f"RE-{100 + i}", NOW - dt.timedelta(hours=i), names[i % 5], f"3330{i}-0085847-1",
                       "CD70" if i % 2 == 0 else "CG125", f"HB4653{i}", [9000.0, 100000.0, 250.0, 75000.5, 1500.0][i % 5],
                       f"966416FKNU{i}") for i in range(n)]


def _visible(d):
    return [d.table.item(r, 1).text() for r in range(d.table.rowCount()) if not d.table.isRowHidden(r)]


def test_dialog_shows_the_scope_title_subtitle_count_and_total(qapp):
    d = InvoiceListDialog(None, "today", _rows(), NOW)
    d.show()
    qapp.processEvents()
    assert d.title_label.text() == "Submitted Today" and d.subtitle_label.text() == "Wednesday, 25 November 2026"
    assert d.count_label.text() == "5 invoices"
    assert d.table.rowCount() == 5
    assert "Total Rs. 185,750.50" in d.summary_label.text()
    assert d.windowTitle().startswith("Submitted Today")


def test_each_scope_has_its_own_title_and_colour(qapp):
    seen = {}
    for scope in ("today", "month", "all"):
        d = InvoiceListDialog(None, scope, _rows(2), NOW)
        seen[scope] = (d.title_label.text(), ild.SCOPES[scope]["accent"])
    assert [t for t, _ in seen.values()] == ["Submitted Today", "Submitted This Month", "FBR Submitted"]
    assert len({a for _, a in seen.values()}) == 3


def test_singular_count_wording(qapp):
    d = InvoiceListDialog(None, "all", _rows(1), NOW)
    assert d.count_label.text() == "1 invoice"


def test_empty_state_is_friendly_and_hides_the_table(qapp):
    d = InvoiceListDialog(None, "today", [], NOW)
    d.show()
    qapp.processEvents()
    assert d.empty_label.isVisible() and not d.table.isVisible() and not d.search.isVisible()
    assert "today" in d.empty_label.text()
    assert d.count_label.text() == "0 invoices"


def test_default_order_is_newest_first(qapp):
    d = InvoiceListDialog(None, "today", _rows(), NOW)
    assert _visible(d) == ["RE-100", "RE-101", "RE-102", "RE-103", "RE-104"]


def test_search_filters_by_buyer_chassis_cnic_invoice_and_fbr_id(qapp):
    d = InvoiceListDialog(None, "today", _rows(), NOW)
    d.show()
    for needle, expected in (("bilal", ["RE-102"]), ("HB46531", ["RE-101"]), ("33304", ["RE-104"]),
                             ("re-103", ["RE-103"]), ("966416FKNU2", ["RE-102"]), ("zzz", [])):
        d.search.setText(needle)
        assert _visible(d) == expected, needle
    d.search.setText("")
    assert len(_visible(d)) == 5


def test_summary_reflects_the_filter(qapp):
    d = InvoiceListDialog(None, "today", _rows(), NOW)
    d.search.setText("cg125")                                  # rows 1 and 3
    assert d.summary_label.text().startswith("Showing 2 of 5")
    assert "Total Rs. 175,000.50" in d.summary_label.text()    # 100000 + 75000.5


def test_amount_sorts_numerically_not_alphabetically(qapp):
    d = InvoiceListDialog(None, "today", _rows(), NOW)
    d.table.sortItems(6, Qt.SortOrder.AscendingOrder)
    assert [d.table.item(r, 6).text() for r in range(5)] == ["250.00", "1,500.00", "9,000.00", "75,000.50", "100,000.00"]


def test_hash_column_counts_what_is_visible_in_the_current_order(qapp):
    d = InvoiceListDialog(None, "today", _rows(), NOW)
    d.search.setText("cg125")
    numbers = [d.table.item(r, 0).text() for r in range(5) if not d.table.isRowHidden(r)]
    assert numbers == ["1", "2"]


def test_sorting_while_a_filter_is_active_keeps_hidden_rows_correct(qapp):
    d = InvoiceListDialog(None, "today", _rows(), NOW)
    d.show()
    d.search.setText("cd70")                                   # rows 0, 2, 4
    d.table.horizontalHeader().setSortIndicator(6, Qt.SortOrder.DescendingOrder)   # triggers a sort
    qapp.processEvents()
    visible = _visible(d)
    assert sorted(visible) == ["RE-100", "RE-102", "RE-104"]   # still exactly the matches
    assert visible == ["RE-100", "RE-104", "RE-102"]           # 9,000 > 1,500 > 250


def test_selecting_a_row_enables_copy_and_copy_puts_the_fbr_id_on_the_clipboard(qapp):
    d = InvoiceListDialog(None, "today", _rows(), NOW)
    d.show()
    assert not d.copy_button.isEnabled() and d.selected_row() is None
    d.table.selectRow(1)
    assert d.copy_button.isEnabled()
    expected = d.selected_row().fbr_invoice_number
    d.copy_button.click()
    assert QApplication.clipboard().text() == expected
    assert "Copied" in d.copy_button.text()
    d.table.selectRow(2)                                        # a new selection resets the button label
    assert d.copy_button.text() == "Copy FBR ID"


def test_close_button_closes(qapp):
    d = InvoiceListDialog(None, "today", _rows(), NOW)
    d.show()
    d.close_button.click()
    assert d.result() == d.DialogCode.Accepted


def test_it_is_read_only(qapp):
    d = InvoiceListDialog(None, "today", _rows(), NOW)
    from PyQt6.QtWidgets import QAbstractItemView

    assert d.table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
