"""Look of the Sales Counter's part-search suggestion list.

PyQt6 only - no imports from app.qt_ui or any other app package (see spare_parts/__init__.py).

Presentation only: it changes how the existing QCompleter popup is DRAWN. The suggestions
(text), the filtering, the keyboard handling and what happens on selection are untouched -
the activated text is still the full "PART-NO - Name   (Stock: N)" label.

Each row shows:  [ PART-NO ]  Part name ......................  [ stock badge ]
  * the part number in a small blue chip, the name beside it;
  * what you typed is bold in the accent colour wherever it matches;
  * a stock badge on the right - green "93 in stock", amber "Low . 4", red "Out of stock";
  * a deep-blue gradient on the hovered / keyboard-active row, a rounded frame, a soft shadow.
A suggestion that doesn't look like that (no stock part) is drawn as plain highlighted text.
"""
from __future__ import annotations

import html
import re

from PyQt6.QtCore import QEvent, QObject, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainterPath, QRegion, QTextDocument
from PyQt6.QtWidgets import QApplication, QCompleter, QStyle, QStyledItemDelegate, QStyleOptionViewItem

ROW_HEIGHT = 40
LOW_STOCK_AT = 5
_LABEL_RE = re.compile(r"^(?P<part_no>.+?)\s+-\s+(?P<name>.*?)\s+\(Stock:\s*(?P<qty>-?\d+)\)\s*$")

_TEXT = "#263445"
_MATCH = "#2f6fb0"
_MATCH_ON_ACTIVE = "#ffe29a"
_CHIP_BG, _CHIP_TEXT = "#e6eef8", "#2f6fb0"

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
    QListView::item { margin: 2px 6px; border-radius: 8px; }
    QListView::item:hover { background-color: #e8f1fb; }
    QListView::item:selected {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1f4068, stop:1 #3474b0);
        color: #ffffff;
    }
    QScrollBar:vertical { background: transparent; width: 8px; margin: 4px 0px; }
    QScrollBar::handle:vertical { background: #c3cfdc; border-radius: 4px; min-height: 24px; }
    QScrollBar::handle:vertical:hover { background: #9fb0c1; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
"""


def parse_label(text: str):
    """(part_no, name, qty) from a suggestion label, or None if it isn't one."""
    m = _LABEL_RE.match(text or "")
    if not m:
        return None
    return m.group("part_no").strip(), m.group("name").strip(), int(m.group("qty"))


def stock_badge(qty: int) -> tuple[str, str, str]:
    """(text, background, text colour) of the stock badge for a quantity."""
    if qty <= 0:
        return "Out of stock", "#fde7e7", "#b42318"
    if qty <= LOW_STOCK_AT:
        return f"Low · {qty}", "#fff1d6", "#8a5200"
    return f"{qty} in stock", "#e1f4e8", "#1c6b3f"


def highlight_html(text: str, query: str, colour: str) -> str:
    query = (query or "").strip()
    if not query:
        return html.escape(text)
    out = []
    for part in re.split(f"({re.escape(query)})", text, flags=re.IGNORECASE):
        if not part:
            continue
        if part.lower() == query.lower():
            out.append(f'<span style="font-weight:700; color:{colour};">{html.escape(part)}</span>')
        else:
            out.append(html.escape(part))
    return "".join(out)


class PartSuggestionDelegate(QStyledItemDelegate):
    def __init__(self, completer: QCompleter, parent=None):
        super().__init__(parent)
        self._completer = completer

    def sizeHint(self, option, index):  # noqa: N802
        base = super().sizeHint(option, index)
        return QSize(base.width() + 60, max(ROW_HEIGHT, base.height()))

    def paint(self, painter, option, index):  # noqa: N802
        # PyQt aborts the whole program if a virtual raises, so never let one escape.
        try:
            self._paint(painter, option, index)
        except Exception:
            try:
                super().paint(painter, option, index)
            except Exception:
                pass

    # ---- drawing ------------------------------------------------------------------------
    def _query(self) -> str:
        prefix = self._completer.completionPrefix() or ""
        if not prefix:
            widget = self._completer.widget()
            prefix = widget.text() if widget is not None and hasattr(widget, "text") else ""
        return prefix

    @staticmethod
    def _draw_html(painter, markup: str, x: float, centre_y: float, width: float, font: QFont) -> None:
        doc = QTextDocument()
        doc.setDefaultFont(font)
        doc.setDocumentMargin(0)
        doc.setHtml(markup)
        doc.setTextWidth(max(10.0, width))
        painter.save()
        painter.translate(x, centre_y - doc.size().height() / 2)
        doc.drawContents(painter)
        painter.restore()

    def _paint(self, painter, option, index) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""
        opt.icon = QIcon()
        widget = opt.widget
        style = widget.style() if widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)   # hover / gradient from QSS

        rect = opt.rect
        active = bool(opt.state & QStyle.StateFlag.State_Selected)
        query = self._query()
        match_colour = _MATCH_ON_ACTIVE if active else _MATCH
        base_colour = "#ffffff" if active else _TEXT
        cy = rect.top() + rect.height() / 2
        font = opt.font

        parsed = parse_label(text)
        if parsed is None:                                     # plain suggestion
            markup = f'<span style="color:{base_colour};">{highlight_html(text, query, match_colour)}</span>'
            self._draw_html(painter, markup, rect.left() + 16, cy, rect.width() - 32, font)
            return

        part_no, name, qty = parsed
        left = rect.left() + 14
        right = rect.right() - 14

        # stock badge (right)
        badge_text, badge_bg, badge_fg = stock_badge(qty)
        small = QFont(font)
        small.setBold(True)
        small.setPixelSize(11)
        fm_small = QFontMetrics(small)
        badge_w = fm_small.horizontalAdvance(badge_text) + 20
        badge_rect = QRectF(right - badge_w, cy - 11, badge_w, 22)
        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 60) if active else QColor(badge_bg))
        painter.drawRoundedRect(badge_rect, 11, 11)
        painter.setFont(small)
        painter.setPen(QColor("#ffffff" if active else badge_fg))
        painter.drawText(badge_rect, int(Qt.AlignmentFlag.AlignCenter), badge_text)
        painter.restore()

        # part-number chip (left)
        chip_font = QFont(font)
        chip_font.setBold(True)
        chip_font.setPixelSize(12)
        fm_chip = QFontMetrics(chip_font)
        chip_text = fm_chip.elidedText(part_no, Qt.TextElideMode.ElideRight, 150)
        chip_w = fm_chip.horizontalAdvance(chip_text) + 18
        chip_rect = QRectF(left, cy - 11, chip_w, 22)
        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 50) if active else QColor(_CHIP_BG))
        painter.drawRoundedRect(chip_rect, 7, 7)
        painter.restore()
        chip_markup = (f'<span style="color:{"#ffffff" if active else _CHIP_TEXT};">'
                       f'{highlight_html(chip_text, query, match_colour)}</span>')
        self._draw_html(painter, f"<b>{chip_markup}</b>", chip_rect.left() + 9, cy, chip_w, chip_font)

        # part name (middle), elided so it never runs under the badge
        name_left = chip_rect.right() + 12
        name_width = badge_rect.left() - 12 - name_left
        if name_width > 20:
            name_text = QFontMetrics(font).elidedText(name, Qt.TextElideMode.ElideRight, int(name_width))
            markup = f'<span style="color:{base_colour};">{highlight_html(name_text, query, match_colour)}</span>'
            self._draw_html(painter, markup, name_left, cy, name_width, font)


class _RoundedMask(QObject):
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


def style_part_completer(completer: QCompleter) -> None:
    """Give an existing QCompleter's popup the new look. Call once, right after creating it."""
    popup = completer.popup()
    if popup is None:
        return
    popup.setStyleSheet(POPUP_QSS)
    mask = _RoundedMask(popup)
    popup.installEventFilter(mask)
    completer._popup_round_mask = mask
    delegate = PartSuggestionDelegate(completer, popup)
    popup.setItemDelegate(delegate)
    # keep the Python object alive: PyQt drops a subclass that only C++ references, and Qt
    # then silently falls back to its plain default painting
    completer._suggestion_delegate = delegate
    popup.setUniformItemSizes(True)
    popup.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    popup.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
