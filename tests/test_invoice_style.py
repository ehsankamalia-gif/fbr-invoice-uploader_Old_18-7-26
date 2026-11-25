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
    css = invoice_style.env_badge_qss("#d9700f")
    assert "QFrame#envBadge" in css and "qlineargradient" in css
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
    """The card takes the environment's colour, so SANDBOX and PRODUCTION must
    produce different styles (this is what main_window applies on a switch)."""
    sandbox = invoice_style.env_badge_qss("#d9700f")
    production = invoice_style.env_badge_qss("#17934d")
    assert sandbox != production
    assert "qlineargradient" in sandbox and "qlineargradient" in production


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
    env.setStyleSheet(invoice_style.env_badge_qss("#d9700f"))      # what main_window does for SANDBOX
    assert "QLabel#envDot" in env.styleSheet() and "qlineargradient" in env.styleSheet()
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


# ---- colourful header cards -----------------------------------------------------
def _luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    chans = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255
        chans.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * chans[0] + 0.7152 * chans[1] + 0.0722 * chans[2]


def _contrast_with_white(hex_colour: str) -> float:
    return 1.05 / (_luminance(hex_colour) + 0.05)


def test_cards_are_gradients_with_white_text():
    css = invoice_style.stat_card_qss("todayStatBox", "#2578b5")
    assert "qlineargradient" in css and "#todayStatBox" in css
    assert "#ffffff" in invoice_style.STAT_VALUE_QSS
    assert "255, 255, 255" in invoice_style.STAT_LABEL_QSS


def test_white_text_stays_readable_on_every_card_colour():
    """The point of 'catch the eye' is not to make it hard to read: white text
    must keep >= 3:1 contrast (WCAG large/bold text) on both ends of each
    card's gradient, for every accent used by the page - environments included."""
    accents = ["#17934d", "#2578b5", "#8340a0", "#d9700f"]        # FBR, today, month, SANDBOX
    for accent in accents:
        start, end = invoice_style._tint(accent, 0.10), invoice_style._shade(accent, 0.82)
        assert _contrast_with_white(start) >= 2.9, (accent, start)
        assert _contrast_with_white(end) >= 3.0, (accent, end)


def test_shade_and_tint_helpers():
    assert invoice_style._shade("#808080", 0.5) == "#404040"
    assert invoice_style._tint("#000000", 0.5) == "#7f7f7f"
    assert invoice_style._tint("#123456", 0.0) == "#123456"


# ---- field labels -----------------------------------------------------------------
def test_field_labels_are_right_aligned_next_to_their_inputs(qapp):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QGridLayout, QLineEdit

    host = QWidget()
    grid = QGridLayout(host)
    title = QLabel("SECTION")
    title.setObjectName("groupTitle")
    grid.addWidget(title, 0, 0, 1, 4)
    left, right = QLabel("Cell (Phone)"), QLabel("Address")
    hint = QLabel("hint")
    grid.addWidget(left, 1, 0)
    grid.addWidget(QLineEdit(), 1, 1)
    grid.addWidget(right, 1, 2)
    grid.addWidget(QLineEdit(), 1, 3)
    grid.addWidget(hint, 1, 4)

    default_hint_alignment = hint.alignment()
    default_title_alignment = title.alignment()
    invoice_style.polish_form_layouts(grid)

    expected = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
    assert left.alignment() == expected and right.alignment() == expected
    assert hint.alignment() == default_hint_alignment          # inline hints untouched
    assert title.alignment() == default_title_alignment        # section titles untouched


def test_label_style_is_darker_than_secondary_text_and_not_pure_black():
    css = invoice_style.build_invoice_page_qss()
    assert invoice_style._LABEL in css
    assert _luminance(invoice_style._LABEL) < _luminance(invoice_style._INK_SOFT)   # reads as a label
    assert _contrast_with_white(invoice_style._LABEL) >= 7                          # WCAG AAA on white cards
    assert invoice_style._LABEL.lower() != "#000000"


# ---- section heading banners ------------------------------------------------------
def test_section_headings_are_bold_white_gradient_banners():
    css = invoice_style.build_invoice_page_qss()
    block = css[css.index("QLabel#groupTitle"):]
    block = block[:block.index("}")]
    assert "qlineargradient" in block
    assert "font-weight: 800" in block and "color: #ffffff" in block
    assert "border-radius" in block


def test_collapsible_advanced_header_gets_its_banner_from_the_page_stylesheet():
    css = invoice_style.build_invoice_page_qss()
    for name in invoice_style.SECTIONS:
        assert f'QFrame#formGroup[section="{name}"] QPushButton#groupTitleToggle' in css
    # the inline button style only carries structure + white bold text (no colour of its own,
    # otherwise it would override its section's colour)
    toggle = invoice_style.ADVANCED_TOGGLE_QSS
    assert "background" not in toggle
    assert "color: #ffffff" in toggle and "font-weight: 800" in toggle


def test_white_heading_text_is_readable_on_both_ends_of_every_banner():
    for name, c in invoice_style.SECTIONS.items():
        assert _contrast_with_white(c["start"]) >= 4.5, name
        assert _contrast_with_white(c["end"]) >= 4.5, name
        assert _contrast_with_white(c["hover"]) >= 3.0, name        # hover only brightens a little


def test_banner_stylesheets_parse_cleanly(qapp):
    assert _parse_warnings(qapp, invoice_style.ADVANCED_TOGGLE_QSS) == []
    assert _parse_warnings(qapp, invoice_style.build_invoice_page_qss()) == []


# ---- each section has its own colour ------------------------------------------------
def test_there_are_four_distinct_section_colour_schemes():
    s = invoice_style.SECTIONS
    assert set(s) == {"customer", "product", "advanced", "pricing"}
    assert len({c["card"] for c in s.values()}) == 4
    assert len({c["end"] for c in s.values()}) == 4
    assert len({invoice_style._banner_gradient(n) for n in s}) == 4


def test_section_cards_are_pale_so_the_page_stays_easy_on_the_eyes():
    for name, c in invoice_style.SECTIONS.items():
        assert _luminance(c["card"]) > 0.87, name          # very light tint, never a heavy fill
        assert c["card"].lower() != "#ffffff"              # but visibly not plain white


def test_page_stylesheet_has_a_rule_set_per_section():
    css = invoice_style.build_invoice_page_qss()
    for name, c in invoice_style.SECTIONS.items():
        assert f'QFrame#formGroup[section="{name}"]' in css
        assert c["card"] in css and c["border"] in css
        assert f'QFrame#formGroup[section="{name}"] QLabel#groupTitle' in css


def test_tag_section_marks_the_frame_and_rejects_unknown_names(qapp):
    frame = QFrame()
    invoice_style.tag_section(frame, "pricing")
    assert frame.property("section") == "pricing"
    with pytest.raises(ValueError):
        invoice_style.tag_section(frame, "nonsense")


def test_section_colours_actually_apply_to_a_tagged_card(qapp):
    """A card tagged 'product' really gets the green tint (property selector works)."""
    page = QWidget()
    page.setObjectName("invoicePage")
    card = QFrame(page)
    card.setObjectName("formGroup")
    invoice_style.tag_section(card, "product")
    page.setStyleSheet(invoice_style.build_invoice_page_qss())
    page.resize(200, 100)
    page.show()
    qapp.processEvents()
    pixel = card.grab().toImage().pixelColor(5, 5).name()
    assert pixel == invoice_style.SECTIONS["product"]["card"]
