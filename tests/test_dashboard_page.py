"""The redesigned Dashboard page inside the real MainWindow class (without starting the app's services)."""
import datetime as dt
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMainWindow
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import app.db.session as dbs
from app.db.models import Base, Customer, Invoice


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    from app.qt_ui.theme import apply_theme

    apply_theme(app)
    return app


def _seed():
    now = dt.datetime.now()
    db = dbs.SessionLocal()
    cust = Customer(cnic="33302-1111111-1", name="MUHAMMAD AKRAM")
    db.add(cust)
    db.flush()
    spec = [  # number, days ago, amount, fbr, sync, message
        ("D-1", 0, 200000.0, "FBR-1", "SYNCED", None),
        ("D-2", 0, 100000.0, None, "PENDING", "Network Error - Queued for retry: timed out"),
        ("D-3", 1, 50000.0, "FBR-3", "SYNCED", None),
        ("D-4", 3, 70000.0, None, "FAILED", "FBR: Invalid Invoice Type"),
        ("D-5", 12, 30000.0, "FBR-5", "SYNCED", None),
    ]
    for number, ago, amount, fbr, sync, message in spec:
        when = (now - dt.timedelta(days=ago)).replace(hour=0, minute=0, second=5, microsecond=0)
        db.add(Invoice(invoice_number=number, pos_id="1", usin=number, datetime=when, customer_id=cust.id,
                       total_sale_value=amount, total_tax_charged=0.0, total_quantity=1.0, total_amount=amount,
                       fbr_invoice_number=fbr, sync_status=sync, fbr_response_message=message))
    db.commit()
    db.close()


@pytest.fixture()
def window(qapp, monkeypatch):
    import app.qt_ui.main_window as mw

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    original = dbs.SessionLocal.kw.get("bind")
    dbs.SessionLocal.configure(bind=engine)

    class Harness(mw.MainWindow):
        def __init__(self):
            QMainWindow.__init__(self)                       # deliberately NOT MainWindow.__init__
            self._ab_last_width = 1400
            self._is_sidebar_collapsed = False
            self._upload_status_style = None
            self.calls = []

        def _select_page(self, key):
            self.calls.append(("page", key))

        def _show_submitted_invoices(self, scope):
            self.calls.append(("list", scope))

        def _open_failed_invoices_dialog(self):
            self.calls.append(("failed-dialog",))

        def _retry_invoice_upload(self, invoice_id, dialog=None):
            self.calls.append(("retry", invoice_id))

        def _show_error(self, title, message):
            self.calls.append(("error", title))

    h = Harness()
    h.resize(1400, 1000)
    h.setCentralWidget(h._create_dashboard_page())
    h.show()
    qapp.processEvents()
    yield h
    h.hide()
    h.deleteLater()
    qapp.sendPostedEvents(None, 0)
    qapp.processEvents()
    dbs.SessionLocal.configure(bind=original)


def test_every_widget_name_other_code_relies_on_still_exists(window):
    for name in ("dash_total_card", "dash_synced_card", "dash_pending_card", "dash_failed_card",
                 "dash_booking_host", "dash_booking_grid", "_dash_booking_card_widgets", "dash_table_model",
                 "dash_table_view", "dash_table_auto_scroll"):
        assert hasattr(window, name), name
    for card in (window.dash_total_card, window.dash_synced_card, window.dash_pending_card, window.dash_failed_card):
        assert hasattr(card, "value_label") and hasattr(card, "subtitle_label")


def test_the_new_panels_exist(window):
    for name in ("dash_quick_actions", "dash_glance_invoices", "dash_glance_sales", "dash_glance_month_invoices",
                 "dash_glance_month_sales", "dash_trend_card", "dash_attention", "dash_subtitle_label"):
        assert hasattr(window, name), name


def test_refresh_fills_the_status_cards_and_the_new_panels(window):
    _seed()
    window._refresh_dashboard()
    assert window.dash_total_card.value_label.text() == "5"
    assert window.dash_synced_card.value_label.text() == "3"
    assert window.dash_pending_card.value_label.text() == "1"
    assert window.dash_failed_card.value_label.text() == "1"
    assert window.dash_synced_card.subtitle_label.text() == "60% of all invoices"
    # today: D-1 (200,000) + D-2 (100,000)
    assert window.dash_glance_invoices.value_label.text() == "2"
    assert window.dash_glance_sales.value_label.text() == "Rs. 300,000"
    assert "vs yesterday" in window.dash_glance_sales.compare_label.text()
    # trend chart: 7 days, total of D-1..D-4
    assert len(window.dash_trend_card.chart.points()) == 7
    assert "Rs. 420,000" in window.dash_trend_card.summary_label.text()
    # attention: failed first, then pending
    assert (window.dash_attention.failed_badge.text(), window.dash_attention.pending_badge.text()) == ("1 failed", "1 pending")
    assert window.dash_attention.row_count() == 2


def test_the_cards_numbers_agree_with_the_pending_ball_rule_and_the_list(window):
    from app.qt_ui import invoice_list_dialog as ild

    _seed()
    window._refresh_dashboard()
    db = dbs.SessionLocal()
    try:
        assert int(window.dash_pending_card.value_label.text()) == ild.count_pending(db) == len(ild.fetch_pending_invoices(db))
        assert int(window.dash_synced_card.value_label.text()) == len(ild.fetch_submitted_invoices(db, "all"))
    finally:
        db.close()


def test_clicking_the_status_cards_opens_the_right_lists(window):
    QTest.mouseClick(window.dash_synced_card, Qt.MouseButton.LeftButton)
    QTest.mouseClick(window.dash_pending_card, Qt.MouseButton.LeftButton)
    QTest.mouseClick(window.dash_failed_card, Qt.MouseButton.LeftButton)
    QTest.mouseClick(window.dash_total_card, Qt.MouseButton.LeftButton)          # not clickable
    assert window.calls == [("list", "all"), ("list", "pending"), ("failed-dialog",)]
    assert window.dash_pending_card.cursor().shape() == Qt.CursorShape.PointingHandCursor
    assert window.dash_total_card.cursor().shape() != Qt.CursorShape.PointingHandCursor


def test_quick_actions_open_their_pages(window):
    for key, tile in window.dash_quick_actions.tiles.items():
        QTest.mouseClick(tile, Qt.MouseButton.LeftButton)
    assert window.calls == [("page", "invoice"), ("page", "print_document"), ("page", "credit_ledger"),
                            ("page", "spare_parts")]


def test_the_page_keys_the_quick_actions_use_are_real_pages():
    import inspect
    import app.qt_ui.main_window as mw

    source = inspect.getsource(mw.MainWindow._init_ui) if hasattr(mw.MainWindow, "_init_ui") else ""
    src = inspect.getsource(mw)
    for key in ("invoice", "print_document", "credit_ledger", "spare_parts"):
        assert f'self._add_page("{key}"' in src, key


def test_the_attention_retry_button_retries_that_invoice(window):
    _seed()
    window._refresh_dashboard()
    db = dbs.SessionLocal()
    failed_id = db.query(Invoice).filter_by(invoice_number="D-4").one().id
    db.close()
    first = window.dash_attention.rows_host.itemAt(0).widget()          # failed rows come first
    first.retry_button.click()
    assert window.calls == [("retry", failed_id)]


def test_attention_links_open_the_lists(window):
    _seed()
    window._refresh_dashboard()
    window.dash_attention.pending_btn.click()
    window.dash_attention.failed_btn.click()
    assert window.calls == [("list", "pending"), ("failed-dialog",)]


def test_the_30_day_switch_reloads_the_chart(window):
    _seed()
    window._refresh_dashboard()
    window.dash_trend_card.btn_30.click()
    assert len(window.dash_trend_card.chart.points()) == 30
    assert "last 30 days" in window.dash_trend_card.summary_label.text()
    assert "Rs. 450,000" in window.dash_trend_card.summary_label.text()     # D-5 (12 days ago) is now inside
    window.dash_trend_card.btn_7.click()
    assert len(window.dash_trend_card.chart.points()) == 7


def test_the_selected_range_survives_a_refresh(window):
    _seed()
    window.dash_trend_card.btn_30.click()
    window._refresh_dashboard()
    assert len(window.dash_trend_card.chart.points()) == 30


def test_a_failure_in_the_new_panels_cannot_break_the_rest_of_the_dashboard(window, monkeypatch):
    from app.services import dashboard_insights as di

    _seed()

    def boom(*a, **k):
        raise RuntimeError("insights exploded")

    monkeypatch.setattr(di, "glance", boom)
    window._refresh_dashboard()                                           # must not raise
    assert window.dash_total_card.value_label.text() == "5"              # the cards still updated
    assert window.dash_table_model.rowCount() == 5                        # and so did the recent table


def test_all_clear_when_nothing_is_waiting(window):
    window._refresh_dashboard()                                           # empty database
    assert window.dash_attention.row_count() == 0
    assert not window.dash_attention.failed_badge.isVisible()
    assert window.dash_total_card.value_label.text() == "0"
    assert window.dash_failed_card.subtitle_label.text() == "Nothing failed"


def test_staff_without_access_do_not_get_those_shortcuts(qapp, monkeypatch):
    import app.qt_ui.main_window as mw

    monkeypatch.setattr(mw.auth_session, "is_logged_in", lambda: True)
    monkeypatch.setattr(mw.auth_session, "has_permission", lambda key: key == "invoice")

    class Probe(mw.MainWindow):
        def __init__(self):
            QMainWindow.__init__(self)

    probe = Probe()
    assert probe._dashboard_action_allowed("invoice") is True
    assert probe._dashboard_action_allowed("credit_ledger") is False       # a restricted module this user lacks
    assert probe._dashboard_action_allowed("print_document") is False
    assert probe._dashboard_action_allowed("spare_parts") is True          # not a restricted module: same as the sidebar
    probe.deleteLater()
