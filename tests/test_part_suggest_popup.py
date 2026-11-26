"""Sales Counter part-search dropdown: stock-aware professional suggestion list."""
import gc
import os
import pathlib

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QCompleter, QLineEdit

from spare_parts.ui import part_suggest_popup as psp

LABELS = [
    "HD-1001 - Brake Pad Set   (Stock: 93)",
    "F-85933 - Front Wheel   (Stock: 968)",
    "HD-3300 - Spark Plug   (Stock: 0)",
    "HD-2210 - Chain Sprocket Kit Heavy Duty Very Long Name Item   (Stock: 4)",
    "Plain suggestion without stock",
]


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    from app.qt_ui.theme import apply_theme

    apply_theme(app)
    return app


def _setup(qapp, labels=LABELS):
    edit = QLineEdit()
    comp = QCompleter(list(labels), edit)
    comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    comp.setFilterMode(Qt.MatchFlag.MatchContains)
    edit.setCompleter(comp)
    psp.style_part_completer(comp)
    edit.show()
    return edit, comp


def test_label_parsing():
    assert psp.parse_label("HD-1001 - Brake Pad Set   (Stock: 93)") == ("HD-1001", "Brake Pad Set", 93)
    assert psp.parse_label("A-1 - Front - Left Wheel   (Stock: 0)") == ("A-1", "Front - Left Wheel", 0)
    assert psp.parse_label("X - Negative   (Stock: -2)") == ("X", "Negative", -2)
    assert psp.parse_label("just text") is None
    assert psp.parse_label("") is None


def test_stock_badges_by_quantity():
    assert psp.stock_badge(0)[0] == "Out of stock" and psp.stock_badge(-3)[0] == "Out of stock"
    assert psp.stock_badge(1)[0] == "Low · 1" and psp.stock_badge(5)[0] == "Low · 5"
    assert psp.stock_badge(6)[0] == "6 in stock" and psp.stock_badge(968)[0] == "968 in stock"
    # three distinct colour families
    assert len({psp.stock_badge(q)[1] for q in (0, 3, 50)}) == 3


def test_highlight_escapes_and_wraps_matches():
    assert "font-weight:700" in psp.highlight_html("Brake Pad", "pad", "#123")
    assert psp.highlight_html("<b>x</b>", "x", "#123").count("<b>") == 0
    assert psp.highlight_html("abc", "", "#123") == "abc"


def test_the_delegate_is_installed_and_survives_gc(qapp):
    edit, comp = _setup(qapp)
    gc.collect()
    assert isinstance(comp.popup().itemDelegate(), psp.PartSuggestionDelegate)
    assert comp.popup().itemDelegate() is comp._suggestion_delegate
    assert "border-radius" in comp.popup().styleSheet()
    edit.deleteLater()


def test_the_popup_really_paints_every_kind_of_row(qapp):
    """PyQt aborts the program if a delegate's paint() raises, so draw it for real:
    in stock, low, out, a very long name, a plain row, hovered and not."""
    edit, comp = _setup(qapp)
    edit.setText("h")
    comp.setCompletionPrefix("h")
    comp.complete()
    qapp.processEvents()
    popup = comp.popup()
    popup.setCurrentIndex(popup.model().index(1, 0))        # an "active" (gradient) row
    qapp.processEvents()
    pix = popup.grab()
    assert not pix.isNull() and pix.width() > 100 and pix.height() > 80
    popup.hide()
    edit.deleteLater()


def test_rows_are_comfortably_tall(qapp):
    from PyQt6.QtWidgets import QStyleOptionViewItem

    edit, comp = _setup(qapp)
    hint = comp.popup().itemDelegate().sizeHint(QStyleOptionViewItem(), comp.popup().model().index(0, 0))
    assert hint.height() >= psp.ROW_HEIGHT
    edit.deleteLater()


def test_selection_still_activates_the_full_label_unchanged(qapp):
    edit, comp = _setup(qapp)
    got = []
    comp.activated[str].connect(got.append)
    edit.setText("brake")
    comp.setCompletionPrefix("brake")
    comp.complete()
    qapp.processEvents()
    popup = comp.popup()
    assert popup.model().rowCount() == 1
    comp.activated[str].emit(popup.model().index(0, 0).data())      # what a click / Enter emits
    assert got == ["HD-1001 - Brake Pad Set   (Stock: 93)"]          # stock text still part of it
    popup.hide()
    edit.deleteLater()


def test_the_spare_parts_package_stays_free_of_app_imports():
    """spare_parts is PyQt6-only by design (see spare_parts/__init__.py)."""
    src = pathlib.Path(psp.__file__).read_text(encoding="utf-8")
    import re

    imports = re.findall(r"^\s*(?:from|import)\s+([\w\.]+)", src, flags=re.MULTILINE)
    assert imports, "no import lines found"
    assert not [m for m in imports if m == "app" or m.startswith("app.")], imports


def test_sale_card_uses_the_new_popup():
    src = (pathlib.Path(psp.__file__).parent / "sale_card_widget.py").read_text(encoding="utf-8")
    assert "style_part_completer(completer)" in src
    assert "_PART_SEARCH_POPUP_QSS" not in src
