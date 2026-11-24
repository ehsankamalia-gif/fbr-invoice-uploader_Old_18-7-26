"""Desktop invoice page styling: scoped to the invoice page, valid QSS, no leaks."""
import os
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtCore import qInstallMessageHandler
from PyQt6.QtWidgets import QApplication, QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from app.qt_ui import invoice_style


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _selectors(qss: str):
    """Selector lists of every rule (text before each '{'), comments removed."""
    qss = re.sub(r"/\*.*?\*/", "", qss, flags=re.S)
    return [chunk.split("{")[0].strip() for chunk in qss.split("}") if "{" in chunk]


def test_every_page_rule_is_scoped_to_the_invoice_page():
    for selector_list in _selectors(invoice_style.build_invoice_page_qss()):
        for sel in (s.strip() for s in selector_list.split(",")):
            assert sel.startswith("#invoicePage"), f"unscoped selector would leak: {sel!r}"


def _parse_warnings(qapp, stylesheet: str):
    seen = []
    previous = qInstallMessageHandler(lambda mode, ctx, msg: seen.append(msg))
    try:
        w = QWidget()
        w.setObjectName("invoicePage")
        w.setStyleSheet(stylesheet)
        w.show()
        qapp.processEvents()
    finally:
        qInstallMessageHandler(previous)
    return [m for m in seen if "parse" in m.lower() and "stylesheet" in m.lower()]


def test_qt_parses_the_page_stylesheet_without_errors(qapp):
    assert _parse_warnings(qapp, invoice_style.build_invoice_page_qss()) == []


def test_helper_stylesheets_parse_without_errors(qapp):
    for css in (
        invoice_style.stat_card_qss("fbrStatBox"),
        invoice_style.env_badge_qss("#27ae60"),
        invoice_style.joined_button_qss(18),
        invoice_style.STANDALONE_ICON_BUTTON_QSS,
        invoice_style.FBR_NUMBER_DISPLAY_QSS,
        invoice_style.ADVANCED_TOGGLE_QSS,
    ):
        assert _parse_warnings(qapp, css) == [], css[:60]


def test_env_badge_style_does_not_leak_onto_its_labels(qapp):
    """The old unscoped 'QFrame {border...}' drew a border around the badge's
    own labels (QLabel is a QFrame). The new one is object-name scoped."""
    css = invoice_style.env_badge_qss("#e67e22")
    assert "QFrame#envBadge" in css and "#e67e22" in css
    assert not re.search(r"(^|\})\s*QFrame\s*\{", css)

    badge = QFrame()
    badge.setObjectName("envBadge")
    badge.setStyleSheet(css)
    lay = QVBoxLayout(badge)
    label = QLabel("SANDBOX")
    label.setStyleSheet(invoice_style.ENV_VALUE_QSS)
    lay.addWidget(label)
    badge.show()
    qapp.processEvents()
    assert "border: none" in invoice_style.ENV_VALUE_QSS


def test_runtime_environment_colours_still_apply():
    sandbox = invoice_style.env_badge_qss("#e67e22")
    production = invoice_style.env_badge_qss("#27ae60")
    assert "#e67e22" in sandbox and "#27ae60" not in sandbox
    assert "#27ae60" in production and "#e67e22" not in production


def test_total_spin_style_stands_out():
    assert "font-size: 17px" in invoice_style.TOTAL_SPIN_QSS


def test_stat_cards_expose_a_settable_value_label(qapp):
    """Other code only ever calls .setText() on these labels (counts refresh)."""
    parent = QWidget()
    card, value = invoice_style.build_stat_card(parent, "todayStatBox", "SUBMITTED TODAY", "fa5s.calendar-day", "#2980b9")
    assert card.objectName() == "todayStatBox"
    assert value.text() == "0"
    value.setText("42")
    assert value.text() == "42"


def test_cards_in_the_row_get_the_same_width_and_none_is_clipped(qapp):
    parent = QWidget()
    a, _ = invoice_style.build_stat_card(parent, "fbrStatBox", "FBR SUBMITTED", "fa5s.cloud-upload-alt", "#27ae60")
    b, _ = invoice_style.build_stat_card(parent, "monthStatBox", "SUBMITTED THIS MONTH", "fa5s.calendar-alt", "#8e44ad")
    env, env_value = invoice_style.build_env_card(parent)
    invoice_style.equalize_cards(a, b, env)
    assert a.minimumWidth() == b.minimumWidth() == env.minimumWidth()
    # the widest label ("SUBMITTED THIS MONTH") decides the width, so it always fits
    assert a.minimumWidth() >= b.sizeHint().width()
    assert env_value.text() == "UNKNOWN"
    assert env.objectName() == "envBadge"


def test_environment_dot_colour_follows_the_runtime_restyle(qapp):
    parent = QWidget()
    env, _ = invoice_style.build_env_card(parent)
    env.setStyleSheet(invoice_style.env_badge_qss("#e67e22"))      # what main_window does for SANDBOX
    assert "QLabel#envDot" in env.styleSheet() and "#e67e22" in env.styleSheet()
    dot = env.findChild(QLabel, "envDot")
    assert dot is not None and dot.width() == 12


# ---- eye-comfort pass: shared grid + soft palette ---------------------------------
def test_polish_form_layouts_gives_every_card_the_same_grid(qapp):
    from PyQt6.QtWidgets import QGridLayout

    host_a, host_b = QWidget(), QWidget()           # keep parents alive (they own the layouts)
    with_hint = QGridLayout(host_a)
    with_hint.addWidget(QLabel("a"), 0, 0)
    with_hint.addWidget(QLabel("hint"), 0, 4)      # like the CNIC / stock hint labels
    without_hint = QGridLayout(host_b)
    without_hint.addWidget(QLabel("a"), 0, 0)
    without_hint.setContentsMargins(28, 26, 28, 24)

    invoice_style.polish_form_layouts(with_hint, without_hint)

    for grid in (with_hint, without_hint):
        assert grid.columnMinimumWidth(0) == grid.columnMinimumWidth(2) == 166
        assert [grid.columnStretch(c) for c in range(5)] == [0, 1, 0, 1, 0]
        assert grid.horizontalSpacing() == 22 and grid.verticalSpacing() == 18
    # the card with no hint column reserves the same right gutter instead
    assert without_hint.contentsMargins().right() == 28 + 22


def test_polish_applies_explicit_card_margins(qapp):
    from PyQt6.QtWidgets import QGridLayout

    host = QWidget()
    grid = QGridLayout(host)
    grid.addWidget(QLabel("x"), 0, 4)
    invoice_style.polish_form_layouts(grid, card_margins={grid: (28, 26, 28, 24)})
    m = grid.contentsMargins()
    assert (m.left(), m.top(), m.right(), m.bottom()) == (28, 26, 28, 24)


def test_inputs_use_a_soft_background_not_pure_white():
    css = invoice_style.build_invoice_page_qss()
    assert invoice_style._FIELD_BG in css and invoice_style._FIELD_BG != "#ffffff"
    assert "color: #000000" not in css and "color: black" not in css   # no harsh pure black text
    assert "font-size: 14px" in css and "font-size: 13px" in css       # larger, readable text
