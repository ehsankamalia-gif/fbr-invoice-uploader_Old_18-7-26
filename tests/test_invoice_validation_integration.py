"""The real desktop invoice page + the real _validate_invoice_form, against a throwaway
in-memory database (MainWindow.__init__ is NOT run, so no sync service starts and no live
database is touched). Proves a failed submit is shown inline, the dialog is only a fallback,
and pass/fail results are unchanged."""
import datetime as dt
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication, QMainWindow
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import app.db.session as dbs
from app.db.models import Base, Motorcycle, ProductModel


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    from app.qt_ui.theme import apply_theme

    apply_theme(app)
    return app


@pytest.fixture()
def window(qapp, monkeypatch):
    """A MainWindow with only the invoice page built, on an in-memory DB."""
    import app.qt_ui.main_window as mw
    from app.services.settings_service import settings_service

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    original_bind = dbs.SessionLocal.kw.get("bind")
    dbs.SessionLocal.configure(bind=engine)

    db = dbs.SessionLocal()
    model = ProductModel(model_name="CD70", make="Honda")
    db.add(model)
    db.flush()
    db.add(Motorcycle(
        chassis_number="HB473270", engine_number="ENG-OWN", product_model_id=model.id, year=2025,
        color="RED", cost_price=0.0, sale_price=0.0, status="IN_STOCK", purchase_date=dt.datetime.now(),
    ))
    db.add(Motorcycle(
        chassis_number="HB000001", engine_number="ENG-TAKEN", product_model_id=model.id, year=2025,
        color="RED", cost_price=0.0, sale_price=0.0, status="IN_STOCK", purchase_date=dt.datetime.now(),
    ))
    db.commit()
    db.close()

    monkeypatch.setattr(settings_service, "get_active_environment", lambda: "SANDBOX")
    monkeypatch.setattr(settings_service, "get_active_settings", lambda: {
        "usin": "RE", "pos_id": "1", "tax_rate": 18.0, "env": "SANDBOX",
        "item_name": "Motorcycle", "item_code": "MOTO", "pct_code": "8711.2010"})

    class Harness(mw.MainWindow):
        def __init__(self):
            QMainWindow.__init__(self)                 # deliberately NOT MainWindow.__init__
            self._last_cnic_toast = None
            self._last_cnic_autofill = None
            self._last_ntn_lookup = None
            self._dealer_completer_map = {}
            self._is_dealer_selected = False
            self._upload_status_style = None
            self._ab_last_width = 1400
            self._is_sidebar_collapsed = False
            self.dialogs = []

        def _show_error(self, title, message):         # record instead of opening a modal
            self.dialogs.append((title, message))

    h = Harness()
    h.resize(1300, 900)
    h.setCentralWidget(h._create_invoice_page())
    h.show()
    qapp.processEvents()
    try:
        yield h
    finally:
        # Tear down cleanly: the invoice page starts a 5s status-refresh timer and the
        # window owns completers/timers; leaving them to interpreter shutdown crashes Qt.
        for name in ("_upload_status_timer", "_dealer_completer_timer", "_chassis_completer_timer"):
            timer = getattr(h, name, None)
            if timer is not None:
                timer.stop()
        # NOT h.close(): MainWindow.closeEvent disposes the application's global DB
        # engine, which would wipe the shared in-memory tables other tests rely on.
        if getattr(h, "_invoice_validation", None) is not None:
            h._invoice_validation.stop()
        h.hide()
        h.deleteLater()
        qapp.sendPostedEvents(None, 0)           # QEvent.DeferredDelete
        qapp.processEvents()
        dbs.SessionLocal.configure(bind=original_bind)


def _fill_valid(h, chassis="HB473270", engine="ENG-OWN"):
    h.invoice_buyer_cnic_input.setText("33302-0085847-5")
    h.invoice_buyer_name_input.setText("MUHAMMAD ALI")
    h.invoice_buyer_father_input.setText("AHMED KHAN")
    h.invoice_buyer_phone_input.setText("03021425133")
    h.invoice_buyer_address_input.setText("HOUSE 12 LAHORE")
    h.invoice_model_combo.clear()
    h.invoice_model_combo.addItem("CD70")
    h.invoice_color_combo.clear()
    h.invoice_color_combo.addItem("RED")
    h.invoice_chassis_input.setText(chassis)
    h.invoice_engine_input.setText(engine)
    h.invoice_amount_spin.setValue(650)


def test_the_validator_is_wired_to_every_required_field(window):
    names = [f.key for f in window._invoice_validation._fields]
    assert names == ["CNIC", "Buyer Name", "Father Name", "Cell (Phone)", "Address", "Model", "Color",
                     "Chassis Number", "Engine Number", "Amount (Excl. Tax)"]


def test_an_empty_form_fails_and_is_shown_inline_not_in_a_dialog(window):
    assert window._validate_invoice_form() is False       # same result as before
    assert window.dialogs == []                           # no pop-up: errors are on the form
    shown = {k for k, _ in window._invoice_validation.visible_errors()}
    assert {"CNIC", "Buyer Name", "Cell (Phone)", "Model", "Color", "Chassis Number",
            "Engine Number", "Amount (Excl. Tax)"} <= shown
    assert window.invoice_buyer_cnic_input.property("vstate") == "invalid"
    banner = window.findChild(type(window._invoice_validation._banner))
    assert banner is not None and banner.isVisible()


def test_a_valid_form_passes_with_no_errors_shown(window):
    _fill_valid(window)
    assert window._validate_invoice_form() is True
    assert window.dialogs == []
    assert window._invoice_validation.visible_errors() == []


def test_bad_formats_are_caught_inline_with_the_existing_messages(window):
    _fill_valid(window)
    window.invoice_buyer_cnic_input.setText("33302-0085")
    window.invoice_buyer_phone_input.setText("0302142")
    assert window._validate_invoice_form() is False
    msgs = dict(window._invoice_validation.visible_errors())
    assert msgs["CNIC"] == "CNIC format must be 12345-1234567-1."
    assert msgs["Cell (Phone)"] == "Cell must be 03XXXXXXXXX."
    assert window.dialogs == []


def test_a_duplicate_engine_from_the_database_is_attached_to_the_engine_field(window):
    _fill_valid(window, chassis="HB473270", engine="ENG-TAKEN")      # engine belongs to another chassis
    assert window._validate_invoice_form() is False
    msgs = dict(window._invoice_validation.visible_errors())
    assert msgs["Engine Number"].startswith("Duplicate Engine Number: ENG-TAKEN")
    assert window.dialogs == []
    window.invoice_engine_input.setText("ENG-FREE")                  # editing the field clears it
    assert window.invoice_engine_input.property("vstate") == "valid"


def test_an_error_with_no_field_still_falls_back_to_the_dialog(window):
    _fill_valid(window)
    window.invoice_number_input.setText("")                # "Invoice number is not valid." has no input to mark
    assert window._validate_invoice_form() is False
    assert len(window.dialogs) == 1
    assert "Invoice number is not valid." in window.dialogs[0][1]


def test_reset_clears_the_validation_state(window):
    window._validate_invoice_form()
    assert window._invoice_validation.visible_errors()
    window._reset_invoice_form()
    assert window._invoice_validation.visible_errors() == []
    assert window.invoice_buyer_cnic_input.property("vstate") in (None, "neutral")


def test_submit_button_gating_is_unchanged_and_explained_by_a_tooltip(window):
    window._check_invoice_form_completeness()
    assert not window.invoice_submit_btn.isEnabled()                 # still disabled until complete
    assert window.invoice_submit_btn.toolTip().startswith("Still needed:")
    _fill_valid(window)
    window._check_invoice_form_completeness()
    assert window.invoice_submit_btn.isEnabled()
    assert window.invoice_submit_btn.toolTip() == ""


def test_the_old_bottom_hint_is_hidden_but_still_filled_in(window):
    assert not window.invoice_validation_hint_label.isVisible()
    window._check_invoice_form_completeness()
    assert "Missing/invalid" in window.invoice_validation_hint_label.text()


# ---- the post-submit result dialog, through the real handler -----------------------------
def _make_invoice(sync_status, fbr_number, message):
    from app.db.models import Invoice

    db = dbs.SessionLocal()
    inv = Invoice(
        invoice_number="RE-0051", pos_id="1", usin="RE-0051", total_sale_value=650.0, total_tax_charged=117.0,
        total_quantity=1.0, total_amount=767.0, sync_status=sync_status, is_fiscalized=bool(fbr_number),
        fbr_invoice_number=fbr_number, fbr_response_message=message,
    )
    db.add(inv)
    db.commit()
    inv_id = inv.id
    db.close()
    return inv_id


@pytest.fixture()
def shown_notices(monkeypatch):
    from app.qt_ui.notice_dialog import NoticeDialog

    shown = []
    monkeypatch.setattr(NoticeDialog, "exec", lambda self: shown.append(self) or 0)
    return shown


def _quiet_handler(window, monkeypatch):
    """Keep the handler's follow-up work (counters, SMS, form clearing) out of the way."""
    for name in ("_clear_invoice_form_after_submission", "_update_fbr_submitted_counter",
                 "_update_today_submitted_counter", "_update_month_submitted_counter",
                 "_update_invoice_upload_status", "_display_invoice_qr"):
        monkeypatch.setattr(window, name, lambda *a, **k: None)
    import app.services.sms_service as sms

    monkeypatch.setattr(sms.sms_service, "queue_invoice_sms", lambda *a, **k: None)


def test_failed_fbr_upload_shows_the_saved_locally_dialog_with_the_reason(window, monkeypatch, shown_notices):
    _quiet_handler(window, monkeypatch)
    inv_id = _make_invoice("FAILED", None, "Invalid data received.Invalid Invoice Type")
    window._handle_submission_success(inv_id)
    assert len(shown_notices) == 1
    d = shown_notices[0]
    assert d.kind == "warning" and d.windowTitle() == "Local Save Success"
    assert "RE-0051" in d.message_label.text()
    assert d.callout_text.text() == "Invalid data received.Invalid Invoice Type"
    assert "Reports section" in d.hint_label.text()


def test_successful_fbr_upload_shows_the_green_dialog_with_the_fbr_id(window, monkeypatch, shown_notices):
    _quiet_handler(window, monkeypatch)
    inv_id = _make_invoice("SYNCED", "966416FKNU37578229", "Success")
    window._handle_submission_success(inv_id)
    d = shown_notices[0]
    assert d.kind == "success" and d.windowTitle() == "Submission Success"
    assert d.detail_values["FBR Invoice ID"].text() == "966416FKNU37578229"


# ---- the reported bug, through the real form ----------------------------------------------
def test_color_shows_its_value_not_an_error_after_a_model_is_chosen(window):
    """Reported: after choosing a model the Color field showed "RED" AND "Color is required."
    (the colour list is rebuilt with signals blocked)."""
    from app.db.models import Price, ProductModel

    db = dbs.SessionLocal()
    model = db.query(ProductModel).filter_by(model_name="CD70").one()
    db.add(Price(product_model_id=model.id, base_price=650, tax_amount=117, levy_amount=19.5, total_price=786.5,
                 effective_date=dt.datetime.now(), optional_features={"colors": "RED,BLACK"}))
    db.commit()
    db.close()

    v = window._invoice_validation
    v.reveal_all(focus_first=False)                       # the user already tried to submit: Color is flagged
    assert window.invoice_color_combo.property("vstate") == "invalid"

    window.invoice_model_combo.blockSignals(True)
    window.invoice_model_combo.clear()
    window.invoice_model_combo.addItem("CD70")
    window.invoice_model_combo.blockSignals(False)
    window._on_invoice_model_changed("CD70")              # fills Color with signals blocked

    assert window.invoice_color_combo.currentText() == "RED"
    assert window.invoice_color_combo.property("vstate") == "valid"
    assert "Color" not in [k for k, _ in v.visible_errors()]
    color_field = next(f for f in v._fields if f.key == "Color")
    assert not color_field.label.isVisible()              # no red "Color is required." under a filled field


def test_completeness_check_brings_the_inline_state_up_to_date(window):
    v = window._invoice_validation
    v.reveal_all(focus_first=False)
    window.invoice_buyer_name_input.blockSignals(True)
    window.invoice_buyer_name_input.setText("MUHAMMAD ALI")          # autofill-style silent fill
    window.invoice_buyer_name_input.blockSignals(False)
    assert window.invoice_buyer_name_input.property("vstate") == "invalid"
    window._check_invoice_form_completeness()                         # runs right after such fills in the app
    assert window.invoice_buyer_name_input.property("vstate") == "valid"


# ---- clickable header cards ------------------------------------------------------------------
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest


@pytest.fixture()
def opened_lists(monkeypatch):
    """Record which list the page asks for instead of opening a modal dialog."""
    from app.qt_ui import invoice_list_dialog

    opened = []
    monkeypatch.setattr(invoice_list_dialog, "show_invoice_list", lambda parent, scope, now=None: opened.append(scope))
    return opened


def test_clicking_each_count_card_opens_its_own_list(window, opened_lists):
    for card, scope in ((window.invoice_today_stat_widget, "today"),
                        (window.invoice_month_stat_widget, "month"),
                        (window.invoice_fbr_stat_value.parentWidget(), "all")):
        QTest.mouseClick(card, Qt.MouseButton.LeftButton)
        assert opened_lists[-1] == scope
    assert opened_lists == ["today", "month", "all"]


def test_clicking_the_number_or_the_icon_on_a_card_also_opens_it(window, opened_lists):
    QTest.mouseClick(window.invoice_today_stat_value, Qt.MouseButton.LeftButton)      # the big number
    assert opened_lists == ["today"]
    QTest.mouseClick(window.invoice_month_stat_value, Qt.MouseButton.LeftButton)
    assert opened_lists == ["today", "month"]


def test_the_environment_card_is_not_clickable(window, opened_lists):
    QTest.mouseClick(window.invoice_env_badge, Qt.MouseButton.LeftButton)
    QTest.mouseClick(window.invoice_env_value_label, Qt.MouseButton.LeftButton)
    assert opened_lists == []
    assert window.invoice_env_badge.cursor().shape() != Qt.CursorShape.PointingHandCursor


def test_cards_look_and_behave_like_buttons(window):
    for card in (window.invoice_today_stat_widget, window.invoice_month_stat_widget):
        assert card.cursor().shape() == Qt.CursorShape.PointingHandCursor
        assert card.toolTip().startswith("Click to view")
        assert card.focusPolicy() == Qt.FocusPolicy.StrongFocus
        assert ":hover" in card.styleSheet()                    # hover lift is on for clickable cards
    assert ":hover" not in window.invoice_env_badge.styleSheet()


def test_enter_and_space_on_a_focused_card_open_it(window, opened_lists):
    card = window.invoice_today_stat_widget
    QTest.keyClick(card, Qt.Key.Key_Return)
    QTest.keyClick(card, Qt.Key.Key_Space)
    QTest.keyClick(card, Qt.Key.Key_A)                           # any other key does nothing
    assert opened_lists == ["today", "today"]


def test_a_right_click_does_not_open_the_list(window, opened_lists):
    QTest.mouseClick(window.invoice_today_stat_widget, Qt.MouseButton.RightButton)
    assert opened_lists == []


def test_a_failure_loading_the_list_is_reported_not_raised(window, monkeypatch):
    from app.qt_ui import invoice_list_dialog

    def boom(parent, scope, now=None):
        raise RuntimeError("db down")

    monkeypatch.setattr(invoice_list_dialog, "show_invoice_list", boom)
    window._show_submitted_invoices("today")                    # must not raise
    assert window.dialogs and window.dialogs[0][0] == "Could Not Load Invoices"
    assert "db down" in window.dialogs[0][1]


def _seed_invoices():
    """Two today, one earlier this month, one last month, one today that never reached FBR."""
    from app.db.models import Invoice

    now = dt.datetime.now()
    first_of_month = now.replace(day=1, hour=0, minute=0, second=1, microsecond=0)
    last_month = first_of_month - dt.timedelta(days=3)
    db = dbs.SessionLocal()
    for number, when, fbr in (
        ("P-1", now.replace(hour=0, minute=0, second=2, microsecond=0), "FBR-1"),
        ("P-2", now.replace(hour=0, minute=0, second=3, microsecond=0), "FBR-2"),
        ("P-3", first_of_month, "FBR-3"),
        ("P-4", last_month, "FBR-4"),
        ("P-5", now.replace(hour=0, minute=0, second=4, microsecond=0), None),
    ):
        db.add(Invoice(invoice_number=number, pos_id="1", usin=number, datetime=when, total_sale_value=1.0,
                       total_tax_charged=0.0, total_quantity=1.0, total_amount=100.0, fbr_invoice_number=fbr))
    db.commit()
    db.close()


def test_each_cards_number_equals_the_length_of_its_list(window):
    """The whole point: the number on the card and the rows behind it can never disagree."""
    from app.qt_ui import invoice_list_dialog as ild

    _seed_invoices()
    window._update_today_submitted_counter()
    window._update_month_submitted_counter()
    window._update_fbr_submitted_counter()
    db = dbs.SessionLocal()
    try:
        counts = {s: len(ild.fetch_submitted_invoices(db, s)) for s in ("today", "month", "all")}
    finally:
        db.close()
    assert int(window.invoice_today_stat_value.text()) == counts["today"]
    assert int(window.invoice_month_stat_value.text()) == counts["month"]
    assert int(window.invoice_fbr_stat_value.text()) == counts["all"]
    assert counts["all"] == 4 and counts["all"] >= counts["month"] >= counts["today"]
