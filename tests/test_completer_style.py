"""Chassis / buyer-name suggestion popup: look only - behaviour must not change."""
import gc
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtCore import Qt, QStringListModel, qInstallMessageHandler
from PyQt6.QtWidgets import QApplication, QCompleter, QLineEdit, QStyleOptionViewItem

from app.qt_ui import completer_style


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    from app.qt_ui.theme import apply_theme

    apply_theme(app)
    return app


def _make(qapp, items, text="HB46", icon="fa5s.motorcycle"):
    edit = QLineEdit(text)
    model = QStringListModel(items, edit)          # parented: a bare temporary would be garbage-collected
    comp = QCompleter(model, edit)
    comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    comp.setFilterMode(Qt.MatchFlag.MatchContains)
    comp.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
    comp.setMaxVisibleItems(10)
    edit.setCompleter(comp)
    completer_style.style_completer(comp, icon)
    edit.show()
    edit.activateWindow()
    edit.setFocus()
    qapp.processEvents()
    return edit, comp


# ---- highlight --------------------------------------------------------------------
def test_highlight_wraps_every_match_case_insensitively():
    out = completer_style.highlight_html("AB Cycles - abbas", "ab", "#2f6fb0")
    assert out.count("font-weight:700") == 2
    assert ">AB<" in out and ">ab<" in out          # original casing is kept


def test_highlight_with_no_query_is_just_escaped_text():
    assert completer_style.highlight_html("HB4<b>x", "", "#000") == "HB4&lt;b&gt;x"
    assert completer_style.highlight_html("plain", "   ", "#000") == "plain"


def test_highlight_escapes_html_in_text_and_query():
    out = completer_style.highlight_html("A&B <i>x</i>", "<i>", "#000")
    assert "<i>x" not in out.replace('<span style="font-weight:700; color:#000;">&lt;i&gt;</span>', "")
    assert "&amp;" in out and "&lt;" in out


def test_highlight_treats_regex_characters_literally():
    assert "font-weight" in completer_style.highlight_html("a.b (1)", ".", "#000")
    assert completer_style.highlight_html("axb", ".", "#000") == "axb"     # '.' is not a wildcard


# ---- the popup --------------------------------------------------------------------
def test_popup_uses_the_custom_delegate_and_it_survives_garbage_collection(qapp):
    """Regression: without a Python reference PyQt drops the subclass and Qt
    silently reverts to plain rows."""
    edit, comp = _make(qapp, ["HB469681", "HB465385"])
    gc.collect()
    comp.setCompletionPrefix("HB46")
    comp.complete()
    qapp.processEvents()
    assert type(comp.popup().itemDelegate()).__name__ == "SuggestionDelegate"


def test_rows_are_comfortably_tall(qapp):
    edit, comp = _make(qapp, ["HB469681"])
    hint = comp.popup().itemDelegate().sizeHint(
        QStyleOptionViewItem(), comp.popup().model().index(0, 0)
    )
    assert hint.height() >= completer_style.ROW_HEIGHT


def test_short_lists_show_without_a_scrollbar(qapp):
    items = ["HB469681", "HB465385", "HB465367", "HB465376", "HB465349", "HB465374"]
    edit, comp = _make(qapp, items)
    comp.setCompletionPrefix("HB46")
    comp.popup().setMinimumWidth(edit.width())
    comp.complete()
    qapp.processEvents()
    assert comp.popup().isVisible()
    assert not comp.popup().verticalScrollBar().isVisible()


def test_popup_gets_rounded_corners_via_a_window_mask(qapp):
    edit, comp = _make(qapp, ["HB469681", "HB465385"])
    comp.setCompletionPrefix("HB46")
    comp.complete()
    qapp.processEvents()
    mask = comp.popup().mask()
    assert not mask.isEmpty()
    assert not mask.contains(__import__("PyQt6.QtCore", fromlist=["QPoint"]).QPoint(0, 0))   # top-left corner is cut off


def test_popup_stylesheet_parses_cleanly(qapp):
    seen = []
    previous = qInstallMessageHandler(lambda mode, ctx, msg: seen.append(msg))
    try:
        edit, comp = _make(qapp, ["HB469681"])
        comp.setCompletionPrefix("HB46")
        comp.complete()
        qapp.processEvents()
    finally:
        qInstallMessageHandler(previous)
    assert [m for m in seen if "parse" in m.lower() and "stylesheet" in m.lower()] == []


def test_painting_works_with_and_without_icons(qapp, monkeypatch):
    edit, comp = _make(qapp, ["HB469681", "HB465385"])
    comp.setCompletionPrefix("HB46")
    comp.complete()
    qapp.processEvents()
    comp.popup().setCurrentIndex(comp.popup().model().index(1, 0))
    assert not comp.popup().grab().isNull()
    monkeypatch.setattr(completer_style, "_qta", None)            # QtAwesome missing -> text-only rows
    edit2, comp2 = _make(qapp, ["HB469681"])
    comp2.setCompletionPrefix("HB46")
    comp2.complete()
    qapp.processEvents()
    assert not comp2.popup().grab().isNull()


# ---- behaviour is unchanged -------------------------------------------------------
def test_selection_behaviour_is_untouched(qapp):
    """The styling must not change what the completer does: same model, same
    filtering, same activation signal."""
    edit, comp = _make(qapp, ["HB469681", "HB472034", "HB465385"])
    comp.setCompletionPrefix("HB46")
    assert comp.completionCount() == 2                        # MatchContains filter still in force
    chosen = []
    comp.activated.connect(chosen.append)
    comp.complete()
    qapp.processEvents()
    index = comp.popup().model().index(1, 0)
    comp.popup().setCurrentIndex(index)
    comp.popup().clicked.emit(index)
    qapp.processEvents()
    assert chosen and chosen[-1] == "HB465385"
