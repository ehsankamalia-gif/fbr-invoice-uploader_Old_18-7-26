"""Inline validation for the desktop invoice form: same rules as before, new presentation."""
import os
import re
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtCore import QEvent
from PyQt6.QtGui import QFocusEvent
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QDoubleSpinBox, QFrame, QGridLayout, QLabel, QLineEdit,
)

from app.qt_ui import form_validation as fv
from app.qt_ui.invoice_style import build_invoice_page_qss


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    from app.qt_ui.theme import apply_theme

    apply_theme(app)
    return app


class Form:
    """A tiny stand-in for the invoice form: a card with a grid of fields."""

    def __init__(self, qapp):
        self.page = QFrame()
        self.page.setObjectName("invoicePage")
        self.page.setStyleSheet(build_invoice_page_qss())
        self.card = QFrame(self.page)
        self.card.setObjectName("formGroup")
        grid = QGridLayout(self.card)
        grid.setVerticalSpacing(18)
        self.cnic, self.name, self.phone = QLineEdit(), QLineEdit(), QLineEdit()
        self.model, self.amount = QComboBox(), QDoubleSpinBox()
        self.amount.setRange(0, 99999999)
        self.model.addItems(["", "CD70", "CG125"])
        for row, w in enumerate((self.cnic, self.name, self.phone, self.model, self.amount)):
            grid.addWidget(QLabel(f"f{row}"), row, 0)
            grid.addWidget(w, row, 1)
        self.banner = fv.ValidationBanner(self.page)
        self.v = fv.FormValidator(self.page, banner=self.banner)
        self.v.add_line_edit(self.cnic, "CNIC", fv.cnic_rule)
        self.v.add_line_edit(self.name, "Buyer Name", fv.required("Buyer name is required."))
        self.v.add_line_edit(self.phone, "Cell (Phone)", fv.phone_rule)
        self.v.add_combo(self.model, "Model", fv.required("Model is required."))
        self.v.add_spin(self.amount, "Amount", fv.amount_rule)
        self.page.resize(500, 420)
        self.card.resize(480, 400)
        self.page.show()
        qapp.processEvents()
        self.qapp = qapp

    def blur(self, widget):
        QApplication.sendEvent(widget, QFocusEvent(QEvent.Type.FocusOut))
        self.qapp.processEvents()

    def state(self, widget):
        return widget.property("vstate")


@pytest.fixture()
def form(qapp):
    return Form(qapp)


# ---- the rules are the ones the form already enforced -------------------------------
@pytest.mark.parametrize("text,ok", [
    ("33302-0085847-5", True), ("12345-1234567-1", True),
    ("3330200858475", False), ("33302-0085847", False), ("33302-00858475-5", False),
    ("abcde-1234567-1", False), ("", False),
])
def test_cnic_rule_matches_the_form_regex(text, ok):
    assert (fv.cnic_rule(text) is None) is ok
    assert bool(re.match(r"^\d{5}-\d{7}-\d$", text)) is ok


@pytest.mark.parametrize("text,ok", [
    ("03021425133", True), ("03001234567", True),
    ("3021425133", False), ("0302142513", False), ("030214251334", False),
    ("04021425133", False), ("", False),
])
def test_phone_rule_matches_the_form_regex(text, ok):
    assert (fv.phone_rule(text) is None) is ok
    assert bool(re.match(r"^03\d{9}$", text)) is ok


def test_rules_have_not_drifted_from_the_forms_own_patterns():
    src = (Path(__file__).resolve().parents[1] / "app" / "qt_ui" / "main_window.py").read_text(encoding="utf-8")
    assert 'r"^\\d{5}-\\d{7}-\\d$"' in src       # the CNIC pattern the form itself uses
    assert 'r"^03\\d{9}$"' in src                # the phone pattern the form itself uses
    assert fv._CNIC_RE.pattern == r"^\d{5}-\d{7}-\d$"
    assert fv._PHONE_RE.pattern == r"^03\d{9}$"


def test_messages_match_the_existing_dialog_wording():
    assert fv.cnic_rule("") == "CNIC is required."
    assert fv.phone_rule("") == "Cell number is required."
    assert fv.required("Buyer name is required.")("") == "Buyer name is required."
    assert fv.amount_rule(0) and fv.amount_rule(0.01) is None


# ---- timing: reward early, punish late ------------------------------------------------
def test_a_pristine_form_shows_no_errors(form):
    assert form.v.visible_errors() == []
    assert not form.banner.isVisible()
    for w in (form.cnic, form.name, form.phone, form.model, form.amount):
        assert form.state(w) in (None, "neutral")


def test_typing_does_not_shout_before_the_user_leaves_the_field(form):
    form.cnic.setText("333")                     # partial, still typing
    assert form.state(form.cnic) == "neutral"
    assert form.v.visible_errors() == []
    form.blur(form.cnic)                         # now they have left it
    assert form.state(form.cnic) == "invalid"
    assert ("CNIC", "Format must be 12345-1234567-1.") in form.v.visible_errors()


def test_an_error_clears_the_moment_the_value_becomes_valid(form):
    form.cnic.setText("333")
    form.blur(form.cnic)
    assert form.state(form.cnic) == "invalid"
    form.cnic.setText("33302-0085847-5")         # fixed while still focused: no blur needed
    assert form.state(form.cnic) == "valid"
    assert form.v.visible_errors() == []
    assert not form.banner.isVisible()


def test_valid_input_is_confirmed_even_before_blur(form):
    form.name.setText("MUHAMMAD ALI")
    assert form.state(form.name) == "valid"


def test_error_message_label_and_icon_follow_the_state(form):
    f = form.v._fields[0]
    form.cnic.setText("12")
    form.blur(form.cnic)
    assert f.label.isVisible() and "12345-1234567-1" in f.label.text()
    assert f.action is not None and f.action.isVisible()
    form.cnic.setText("33302-0085847-5")
    assert not f.label.isVisible()


# ---- failed submit ---------------------------------------------------------------------
def test_reveal_all_shows_every_problem_and_the_banner(form):
    n = form.v.reveal_all(focus_first=False)
    assert n == 5
    assert form.banner.isVisible()
    assert "Please fix 5 items" in form.banner._title.text()
    for name in ("CNIC", "Buyer Name", "Cell (Phone)", "Model", "Amount"):
        assert name in form.banner._body.text()


def test_banner_is_compact_and_gives_long_messages_a_full_line(form):
    form.v.reveal_all(focus_first=False)
    body = form.banner._body.text()
    assert "is required" not in body                      # short ones: names only (field already has the message)
    long_msg = "Duplicate Chassis: HB473270 has already been uploaded to FBR. (FBR Invoice: 123456789012345)"
    form.v.show_error(form.name, long_msg)
    assert long_msg in form.banner._body.text()           # long ones: full text on their own line


def test_an_injected_post_submit_error_ends_when_the_value_changes(form):
    form.name.setText("ALI")
    assert form.v.show_error(form.name, "Duplicate Chassis: X is already uploaded.")
    assert form.state(form.name) == "invalid"
    form.name.setText("ALI K")                            # user edits the field
    assert form.state(form.name) == "valid"


def test_show_error_ignores_widgets_it_does_not_know(form):
    assert form.v.show_error(QLineEdit(), "x") is False


def test_combo_and_spin_validate_too(form):
    form.v.reveal_all(focus_first=False)
    assert form.state(form.model) == "invalid" and form.state(form.amount) == "invalid"
    form.model.setCurrentIndex(1)
    form.amount.setValue(650)
    assert form.state(form.model) == "valid" and form.state(form.amount) == "valid"


def test_reset_returns_to_a_pristine_form(form):
    form.v.reveal_all(focus_first=False)
    form.v.reset()
    assert form.v.visible_errors() == []
    assert not form.banner.isVisible()
    assert form.state(form.cnic) == "neutral"


def test_reset_keeps_confirming_what_is_still_filled_in(form):
    form.name.setText("ALI")
    form.v.reveal_all(focus_first=False)
    form.v.reset()                                        # e.g. the "preserve customer info" reset
    assert form.state(form.name) == "valid" and form.state(form.phone) == "neutral"


def test_submit_tooltip_lists_what_is_still_needed(form):
    tip = form.v.summary_tooltip()
    assert tip.startswith("Still needed:") and "CNIC" in tip and "Amount" in tip
    form.cnic.setText("33302-0085847-5")
    form.name.setText("ALI")
    form.phone.setText("03021425133")
    form.model.setCurrentIndex(1)
    form.amount.setValue(650)
    assert form.v.summary_tooltip() == ""


# ---- it must not disturb the layout -----------------------------------------------------
def test_showing_errors_does_not_move_or_resize_any_field(form):
    widgets = (form.cnic, form.name, form.phone, form.model, form.amount)
    before = [w.geometry() for w in widgets]
    form.v.reveal_all(focus_first=False)
    form.qapp.processEvents()
    assert [w.geometry() for w in widgets] == before


def test_message_sits_in_the_gap_below_its_field(form):
    form.cnic.setText("1")
    form.blur(form.cnic)
    label = form.v._fields[0].label
    assert label.geometry().top() >= form.cnic.geometry().bottom()
    assert label.geometry().bottom() < form.name.geometry().top()      # never overlaps the next row


# ---- the stylesheet understands the states ------------------------------------------------
def test_stylesheet_has_invalid_and_valid_states():
    css = build_invoice_page_qss()
    assert '[vstate="invalid"]' in css and '[vstate="valid"]' in css
    assert "#d64545" in css


def test_invalid_field_is_actually_painted_red(form):
    form.cnic.setText("1")
    form.blur(form.cnic)
    form.qapp.processEvents()
    img = form.cnic.grab().toImage()
    c = img.pixelColor(img.width() // 2, 0)                   # top edge of the field = its border
    assert c.red() > 170 and c.green() < 90 and c.blue() < 90, c.name()   # red (#d64545, or #c0392b when focused)


# ---- regression: a value set while signals are blocked must not leave a stale error ----------
# (Reported: the Color combo showed "RED" but still said "Color is required." because the
#  app fills it with blockSignals(True), so no change signal ever reached the validator.)
from PyQt6.QtTest import QTest


def _fill_combo_with_signals_blocked(combo, items):
    combo.blockSignals(True)
    combo.clear()
    for item in items:
        combo.addItem(item)
    combo.setCurrentIndex(0)
    combo.blockSignals(False)


def test_combo_filled_with_signals_blocked_clears_its_stale_error_on_refresh(form):
    form.v.reveal_all(focus_first=False)
    assert form.state(form.model) == "invalid"
    _fill_combo_with_signals_blocked(form.model, ["RED", "BLACK"])
    assert form.state(form.model) == "invalid"            # nothing has told the validator yet (that is the bug's cause)
    form.v.refresh()                                      # what the app now does right after such a fill
    assert form.state(form.model) == "valid"
    assert ("Model", "Model is required.") not in form.v.visible_errors()
    assert not form.v._fields[3].label.isVisible()        # the red message under the field is gone


def test_the_safety_net_poll_also_catches_it_without_any_explicit_call(form):
    form.v.reveal_all(focus_first=False)
    _fill_combo_with_signals_blocked(form.model, ["RED"])
    assert form.state(form.model) == "invalid"
    QTest.qWait(450)                                      # a couple of poll ticks (250 ms each)
    assert form.state(form.model) == "valid"
    assert not form.v._fields[3].label.isVisible()


def test_line_edit_and_spin_set_with_signals_blocked_are_caught_too(form):
    form.v.reveal_all(focus_first=False)
    for w, value in ((form.name, "MUHAMMAD ALI"), (form.cnic, "33302-0085847-5")):
        w.blockSignals(True)
        w.setText(value)
        w.blockSignals(False)
    form.amount.blockSignals(True)
    form.amount.setValue(650)
    form.amount.blockSignals(False)
    form.v.refresh()
    assert form.state(form.name) == "valid" and form.state(form.cnic) == "valid"
    assert form.state(form.amount) == "valid"
    assert all(k not in ("Buyer Name", "CNIC", "Amount") for k, _ in form.v.visible_errors())


def test_a_value_changed_silently_into_something_invalid_shows_the_error(form):
    form.name.setText("ALI")
    form.blur(form.name)
    assert form.state(form.name) == "valid"
    form.name.blockSignals(True)
    form.name.setText("")                                 # cleared behind the validator's back
    form.name.blockSignals(False)
    form.v.refresh()
    assert form.state(form.name) == "invalid"


def test_refresh_is_quiet_when_nothing_changed(form):
    form.v.refresh()                                      # settle
    seen = []
    form.v.changed.connect(lambda: seen.append(1))
    assert form.v.refresh() is False
    assert seen == []                                     # no needless signal / repaint churn


def test_refresh_force_reevaluates_everything(form):
    assert form.v.refresh(force=True) is True


def test_a_silent_change_also_ends_an_injected_post_submit_error(form):
    form.name.setText("ALI")
    form.v.show_error(form.name, "Duplicate Chassis: X is already uploaded.")
    assert form.state(form.name) == "invalid"
    form.name.blockSignals(True)
    form.name.setText("ALI K")
    form.name.blockSignals(False)
    form.v.refresh()
    assert form.state(form.name) == "valid"


def test_stop_halts_the_poll(form):
    form.v.stop()
    assert not form.v._poll.isActive()
