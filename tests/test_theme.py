"""The shared desktop theme: stylesheet, emoji -> font-icon swap, and the
small-button padding fix. Runs on Qt's offscreen platform (no display needed)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QApplication, QPushButton

from app.qt_ui import theme


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    return app


def test_stylesheet_builds_from_tokens_and_overrides():
    css = theme.build_stylesheet({"primary": "#123456"})
    assert "#123456" in css            # a token override flows into the sheet
    assert "QHeaderView::section" in css and "QScrollBar" in css and "QPushButton" in css


def test_apply_theme_sets_palette_and_stylesheet(qapp):
    # (With a stylesheet active Qt wraps the style, so its name isn't readable.)
    assert qapp.palette().color(QPalette.ColorRole.Highlight).name() == theme.TOKENS["primary"]
    assert "QLineEdit" in qapp.styleSheet()


def test_emoji_button_becomes_icon_button(qapp):
    pytest.importorskip("qtawesome")
    b = QPushButton("\U0001f5d1️ Delete Dealer")      # 🗑️ Delete Dealer (via constructor)
    b.show()
    qapp.processEvents()
    assert b.text() == "Delete Dealer"
    assert not b.icon().isNull()
    assert b.iconSize() == QSize(16, 16)


def test_set_text_later_keeps_using_the_icon(qapp):
    pytest.importorskip("qtawesome")
    b = QPushButton("Convert")
    b.setText("⇄ Convert to Customer")                   # ⇄ ...
    assert b.text() == "Convert to Customer" and not b.icon().isNull()
    b.setText("⇄ Convert to Customer")                   # reset after a "busy" label
    assert b.text() == "Convert to Customer"


def test_icon_only_button_keeps_empty_text(qapp):
    pytest.importorskip("qtawesome")
    b = QPushButton("↻")                                  # ↻ refresh
    b.show()
    qapp.processEvents()
    assert b.text() == "" and not b.icon().isNull()


def test_unmapped_and_plain_text_untouched(qapp):
    b = QPushButton("Save")
    b.show()
    qapp.processEvents()
    assert b.text() == "Save" and b.icon().isNull()
    b.setText("⌛ Sending...")                            # ⌛ not mapped -> unchanged
    assert b.text() == "⌛ Sending..."


def test_icon_colour_follows_inline_stylesheet(qapp):
    b = QPushButton("x")
    b.setStyleSheet("background-color: #3498db; color: white; border: none;")
    assert theme._icon_colour(b) == "#ffffff"
    b.setStyleSheet("QPushButton { color: #e74c3c; }")
    assert theme._icon_colour(b) == "#e74c3c"
    assert theme._icon_colour(QPushButton("y")) == theme.TOKENS["text"]


def test_small_fixed_width_button_gets_zero_padding(qapp):
    b = QPushButton("+")
    b.setFixedWidth(28)
    b.show()
    qapp.processEvents()
    assert "padding: 0px" in b.styleSheet()
    wide = QPushButton("Wide button")
    wide.show()
    qapp.processEvents()
    assert wide.styleSheet() == ""


def test_disable_switch(monkeypatch):
    monkeypatch.setenv("APP_DISABLE_THEME", "1")
    app = QApplication.instance()
    before = app.styleSheet()
    theme.apply_theme(app)
    assert app.styleSheet() == before     # untouched when disabled
