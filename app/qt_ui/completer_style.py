"""Look of the auto-complete suggestion list (the dropdown under the Chassis
Number and Buyer Name fields on the invoice form).

Presentation only: it changes how the existing QCompleter popup is DRAWN. The
model, the filtering, the keyboard handling and what happens on selection are all
untouched.

What it adds over Qt's plain default list:
  * a soft rounded frame and generous, evenly spaced rows;
  * a small leading icon (motorcycle / building);
  * the part you typed is shown bold in the accent colour inside each suggestion,
    so you can see at a glance why it matched;
  * a hover tint and a deep-blue gradient on the active (keyboard / mouse) row.
"""
from __future__ import annotations

import html
import re

from PyQt6.QtCore import QEvent, QObject, QRectF, QSize, Qt
from PyQt6.QtGui import QIcon, QPainterPath, QPixmap, QRegion, QTextDocument
from PyQt6.QtWidgets import QApplication, QCompleter, QStyle, QStyledItemDelegate, QStyleOptionViewItem

from app.qt_ui.theme import _qta

ROW_HEIGHT = 38
_ICON_SIZE = 16
_ICON_LEFT = 16
_TEXT_LEFT = 44          # where the text starts (after the icon)
_TEXT_COLOUR = "#263445"
_MATCH_COLOUR = "#2f6fb0"
_MATCH_ON_ACTIVE = "#ffe29a"   # soft gold on the blue gradient: stands out without shouting
_ICON_COLOUR = "#3474b0"

# NOTE on spacing: Qt sizes the popup to (rows x row-height + 3px). Any padding on
# the list itself would eat into that and force a scrollbar for a handful of rows,
# so the breathing room is on the ITEMS (margin), not on the list (padding).
POPUP_QSS = """
    QListView {
        background-color: #ffffff;
        border: 1px solid #b9cde6;
        border-radius: 12px;
        padding: 0px;
        outline: 0;
        font-size: 14px;
        color: #263445;
    }
    QListView::item {
        margin: 2px 6px;
        border-radius: 8px;
        padding-left: 4px;
    }
    QListView::item:hover {
        background-color: #e8f1fb;
    }
    QListView::item:selected {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1f4068, stop:1 #3474b0);
        color: #ffffff;
    }
    QScrollBar:vertical { background: transparent; width: 8px; margin: 4px 0px; }
    QScrollBar::handle:vertical { background: #c3cfdc; border-radius: 4px; min-height: 24px; }
    QScrollBar::handle:vertical:hover { background: #9fb0c1; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
"""


def highlight_html(text: str, query: str, match_colour: str) -> str:
    """HTML for `text` with every (case-insensitive) occurrence of `query` shown
    bold in `match_colour`. Everything is HTML-escaped."""
    query = (query or "").strip()
    if not query:
        return html.escape(text)
    parts = re.split(f"({re.escape(query)})", text, flags=re.IGNORECASE)
    out = []
    for part in parts:
        if not part:
            continue
        if part.lower() == query.lower():
            out.append(f'<span style="font-weight:700; color:{match_colour};">{html.escape(part)}</span>')
        else:
            out.append(html.escape(part))
    return "".join(out)


class SuggestionDelegate(QStyledItemDelegate):
    """Draws one suggestion row: stylesheet background (hover / gradient when
    active), a leading icon, and the text with the typed part highlighted."""

    def __init__(self, completer: QCompleter, icon_name: str | None = None, parent=None):
        super().__init__(parent)
        self._completer = completer
        self._icon_name = icon_name
        self._icon_cache: dict[str, QPixmap] = {}

    # -- helpers -------------------------------------------------------------
    def _query(self) -> str:
        prefix = self._completer.completionPrefix() or ""
        if not prefix:
            widget = self._completer.widget()
            prefix = widget.text() if widget is not None and hasattr(widget, "text") else ""
        return prefix

    def _icon_pixmap(self, colour: str) -> QPixmap | None:
        if _qta is None or not self._icon_name:
            return None
        if colour not in self._icon_cache:
            try:
                self._icon_cache[colour] = _qta.icon(self._icon_name, color=colour).pixmap(_ICON_SIZE, _ICON_SIZE)
            except Exception:
                return None
        return self._icon_cache[colour]

    # -- QStyledItemDelegate --------------------------------------------------
    def sizeHint(self, option, index):  # noqa: N802
        base = super().sizeHint(option, index)
        return QSize(base.width() + _TEXT_LEFT + 16, max(ROW_HEIGHT, base.height()))

    def paint(self, painter, option, index):  # noqa: N802
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""
        opt.icon = QIcon()

        widget = opt.widget
        style = widget.style() if widget is not None else QApplication.style()
        # Background (hover tint / gradient on the active row) comes from the stylesheet.
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)

        rect = opt.rect
        active = bool(opt.state & QStyle.StateFlag.State_Selected)

        pix = self._icon_pixmap("#ffffff" if active else _ICON_COLOUR)
        if pix is not None:
            painter.drawPixmap(rect.left() + _ICON_LEFT, rect.top() + (rect.height() - _ICON_SIZE) // 2, pix)

        doc = QTextDocument()
        doc.setDefaultFont(opt.font)
        colour = "#ffffff" if active else _TEXT_COLOUR
        match = _MATCH_ON_ACTIVE if active else _MATCH_COLOUR
        doc.setHtml(f'<span style="color:{colour};">{highlight_html(text, self._query(), match)}</span>')
        doc.setTextWidth(max(10, rect.width() - _TEXT_LEFT - 10))

        painter.save()
        painter.translate(rect.left() + _TEXT_LEFT, rect.top() + (rect.height() - doc.size().height()) / 2)
        doc.drawContents(painter)
        painter.restore()


class _RoundedMask(QObject):
    """Keeps the popup's window mask a rounded rectangle as it shows / resizes."""

    RADIUS = 12

    def eventFilter(self, obj, event):  # noqa: N802
        if event.type() in (QEvent.Type.Show, QEvent.Type.Resize):
            try:
                path = QPainterPath()
                path.addRoundedRect(QRectF(obj.rect()), self.RADIUS, self.RADIUS)
                obj.setMask(QRegion(path.toFillPolygon().toPolygon()))
            except Exception:
                pass
        return False


def style_completer(completer: QCompleter, icon_name: str | None = None) -> None:
    """Give an existing QCompleter's popup the new look. Safe to call once, right
    after the completer is created."""
    popup = completer.popup()
    if popup is None:
        return
    popup.setStyleSheet(POPUP_QSS)
    # Real rounded corners: clip the popup window itself to a rounded shape (a
    # translucent window would lose the list's own frame and background).
    round_mask = _RoundedMask(popup)
    popup.installEventFilter(round_mask)
    completer._popup_round_mask = round_mask
    delegate = SuggestionDelegate(completer, icon_name, popup)
    popup.setItemDelegate(delegate)
    # Keep the Python object alive: without a reference PyQt drops the subclass
    # wrapper and Qt silently falls back to its plain default row painting.
    completer._suggestion_delegate = delegate
    popup.setUniformItemSizes(True)
    popup.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    popup.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
