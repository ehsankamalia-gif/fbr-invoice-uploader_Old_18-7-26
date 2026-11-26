"""Customer Ledger -> "Print Ledger" button: it used to crash the application (it read a table model that
does not exist). It must build the statement from the rows on screen, and never take the app down."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication, QMessageBox, QTableWidgetItem
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    from app.qt_ui.theme import apply_theme

    apply_theme(app)
    return app


@pytest.fixture()
def page(qapp, monkeypatch):
    import app.db.session as dbs
    from app.db.models import Base

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    original = dbs.SessionLocal.kw.get("bind")
    dbs.SessionLocal.configure(bind=engine)

    from app.qt_ui.credit_ledger_system_page import CreditLedgerSystemPage

    shown = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda p, t, m, *a, **k: shown.append(("warning", t, m))))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda p, t, m, *a, **k: shown.append(("critical", t, m))))
    w = CreditLedgerSystemPage()
    w.shown = shown
    w.printed = []
    monkeypatch.setattr(w.print_service, "print_custom_html", lambda html, parent=None, on_done=None: w.printed.append(html))
    yield w
    w.hide()
    w.deleteLater()
    dbs.SessionLocal.configure(bind=original)


def _fill_like_the_screenshot(page):
    rows = [
        ("27-11-2026", "Motorcycle Finance - CG125 - Chassis: ED587485\nCustomer committed to clear payment within 2 months.",
         "FIN-20261127-003", "285,000.00", "0.00", "285,000.00"),
        ("27-11-2026", "Down Payment Received - FIN-20261127-003 (via Cash)",
         "FIN-20261127-003", "0.00", "100,000.00", "185,000.00"),
    ]
    page.ledger_table.setRowCount(0)
    for values in rows:
        r = page.ledger_table.rowCount()
        page.ledger_table.insertRow(r)
        for c, v in enumerate(values):
            page.ledger_table.setItem(r, c, QTableWidgetItem(v))
    page.current_customer_details = {
        "name": "IMITIAZ NAWAZ BUTT", "father_name": "N/A", "address": "N/A",
        "phone": "03126061875", "cnic": "33302-1234567-8",
    }


def test_print_ledger_builds_the_statement_from_the_rows_on_screen(page):
    _fill_like_the_screenshot(page)
    page.print_ledger()                                   # used to raise AttributeError -> app crash
    assert page.shown == []
    assert len(page.printed) == 1
    html = page.printed[0]
    assert "IMITIAZ NAWAZ BUTT" in html and "03126061875" in html
    assert "Motorcycle Finance - CG125 - Chassis: ED587485" in html
    assert "285,000.00" in html and "100,000.00" in html and "185,000.00" in html
    assert "Total Debits: Rs. 285,000.00" in html and "Total Credits: Rs. 100,000.00" in html
    assert "Outstanding Balance: Rs. 185,000.00" in html


def test_the_collected_rows_use_the_right_columns(page):
    _fill_like_the_screenshot(page)
    entries = page._collect_ledger_entries_for_print()
    assert entries[0]["date"] == "27-11-2026"
    assert entries[0]["debit"] == "285000.00" and entries[0]["credit"] == "0.00" and entries[0]["balance"] == "285000.00"
    assert entries[1]["debit"] == "0.00" and entries[1]["credit"] == "100000.00" and entries[1]["balance"] == "185000.00"
    assert "Sale ID" not in entries[0] and entries[0]["description"].startswith("Motorcycle Finance")


def test_a_row_with_missing_cells_does_not_crash(page):
    _fill_like_the_screenshot(page)
    page.ledger_table.takeItem(0, 5)                      # a cell that was never filled in
    page.ledger_table.takeItem(1, 3)
    page.print_ledger()
    assert page.shown == [] and len(page.printed) == 1


def test_without_a_loaded_ledger_it_asks_for_one_instead_of_crashing(page):
    page.current_customer_details = None
    page.print_ledger()
    assert page.printed == [] and page.shown[-1][1] == "Print Error" and "load a customer ledger" in page.shown[-1][2]


def test_an_empty_ledger_says_there_is_nothing_to_print(page):
    _fill_like_the_screenshot(page)
    page.ledger_table.setRowCount(0)
    page.print_ledger()
    assert page.printed == [] and "No transactions" in page.shown[-1][2]


def test_any_failure_while_printing_is_reported_not_raised(page, monkeypatch):
    _fill_like_the_screenshot(page)

    def boom(*a, **k):
        raise RuntimeError("printer exploded")

    monkeypatch.setattr(page.print_service, "render_ledger_statement", boom)
    page.print_ledger()                                   # must not raise (a raise would abort the app)
    kind, title, message = page.shown[-1]
    assert kind == "critical" and title == "Print Error" and "printer exploded" in message


def test_the_print_button_is_wired_to_the_fixed_handler(page):
    _fill_like_the_screenshot(page)
    page.print_ledger_btn.click()
    assert len(page.printed) == 1


def test_no_reference_to_the_missing_ledger_model_remains():
    import inspect
    from app.qt_ui import credit_ledger_system_page as mod

    assert "ledger_model" not in inspect.getsource(mod)


# ---- the statement renderer itself -----------------------------------------------------------------
def _render(entries):
    from app.services.print_service_v2 import PrintServiceV2

    return PrintServiceV2().render_ledger_statement({
        "customer": {"name": "IMITIAZ NAWAZ BUTT", "phone": "0312"},
        "entries": entries,
        "date_range": "27-10-2026 to 27-11-2026",
    })


def test_the_renderer_accepts_the_balance_as_text_or_as_a_number():
    as_text = _render([{"date": "d", "description": "x", "debit": "10", "credit": "0", "balance": "185000.00"}])
    as_number = _render([{"date": "d", "description": "x", "debit": 10, "credit": 0, "balance": 185000.0}])
    assert "Outstanding Balance: Rs. 185,000.00" in as_text and "Outstanding Balance: Rs. 185,000.00" in as_number


def test_the_renderer_handles_an_empty_balance_and_no_entries():
    assert "Outstanding Balance: Rs. 0.00" in _render([{"date": "d", "description": "x", "debit": "", "credit": "", "balance": ""}])
    assert "Outstanding Balance: Rs. 0.00" in _render([])


def test_special_characters_in_a_description_cannot_break_the_statement():
    html = _render([{"date": "d", "description": "A & B <b>bold</b>\nsecond line", "debit": "1", "credit": "0", "balance": "1"}])
    assert "A &amp; B &lt;b&gt;bold&lt;/b&gt;<br>second line" in html
    assert "<b>bold</b>" not in html
