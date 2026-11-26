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
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainterPath, QPixmap, QRegion, QTextDocument
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
        # Moving through the list with the arrow keys can blank the search box (a completer that
        # returns "" from pathFromIndex does that), so keep what was typed for the highlight.
        if prefix:
            self._last_query = prefix
        return prefix or getattr(self, "_last_query", "")

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


COLUMN_SEPARATOR = " | "
_PILL_BG, _PILL_TEXT = "#eaf0f7", "#4a5d73"
_SECONDARY = "#5b6b7c"


class ColumnSuggestionDelegate(SuggestionDelegate):
    """For suggestions shaped "PRIMARY | secondary | tag" (e.g. "HB479029 | CD70 | BLK"):

        icon  HB479029   CD70 ............................................ [ BLK ]

    The first column is the bold main value (with the typed part highlighted), the middle
    column(s) are normal secondary text, and the LAST column is a small rounded tag on the
    right. A suggestion without the separator is drawn exactly like SuggestionDelegate."""

    def paint(self, painter, option, index):  # noqa: N802
        # PyQt aborts the whole program if a virtual raises, so never let one escape.
        try:
            if COLUMN_SEPARATOR not in (index.data() or ""):
                super().paint(painter, option, index)
            else:
                self._paint_columns(painter, option, index)
        except Exception:
            try:
                super().paint(painter, option, index)
            except Exception:
                pass

    def _paint_columns(self, painter, option, index) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""
        opt.icon = QIcon()
        widget = opt.widget
        style = widget.style() if widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)    # hover / gradient

        rect = opt.rect
        active = bool(opt.state & QStyle.StateFlag.State_Selected)
        cy = rect.top() + rect.height() / 2
        parts = [p.strip() for p in text.split(COLUMN_SEPARATOR)]
        primary, rest = parts[0], parts[1:]
        tag = rest.pop() if len(rest) >= 1 and len(parts) >= 3 else ""
        secondary = "  \u00b7  ".join(r for r in rest if r)

        pix = self._icon_pixmap("#ffffff" if active else _ICON_COLOUR)
        if pix is not None:
            painter.drawPixmap(rect.left() + _ICON_LEFT, rect.top() + (rect.height() - _ICON_SIZE) // 2, pix)

        right = rect.right() - 14
        # tag pill (right)
        if tag:
            small = QFont(opt.font)
            small.setBold(True)
            small.setPixelSize(11)
            fm = QFontMetrics(small)
            pill_w = fm.horizontalAdvance(tag) + 18
            pill = QRectF(right - pill_w, cy - 11, pill_w, 22)
            painter.save()
            painter.setRenderHint(painter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 60) if active else QColor(_PILL_BG))
            painter.drawRoundedRect(pill, 11, 11)
            painter.setFont(small)
            painter.setPen(QColor("#ffffff" if active else _PILL_TEXT))
            painter.drawText(pill, int(Qt.AlignmentFlag.AlignCenter), tag)
            painter.restore()
            right = pill.left() - 12

        # primary (bold, highlighted) then secondary
        query = self._query()
        match = _MATCH_ON_ACTIVE if active else _MATCH_COLOUR
        main_font = QFont(opt.font)
        main_font.setBold(True)
        left = rect.left() + _TEXT_LEFT
        main_w = QFontMetrics(main_font).horizontalAdvance(primary) + 4
        doc = QTextDocument()
        doc.setDefaultFont(main_font)
        doc.setDocumentMargin(0)
        doc.setHtml(f'<span style="color:{"#ffffff" if active else _TEXT_COLOUR};">'
                    f'{highlight_html(primary, query, match)}</span>')
        doc.setTextWidth(max(10, main_w + 20))
        painter.save()
        painter.translate(left, cy - doc.size().height() / 2)
        doc.drawContents(painter)
        painter.restore()

        if secondary:
            sec_left = left + main_w + 18
            sec_w = right - sec_left
            if sec_w > 20:
                elided = QFontMetrics(opt.font).elidedText(secondary, Qt.TextElideMode.ElideRight, int(sec_w))
                painter.save()
                painter.setFont(opt.font)
                painter.setPen(QColor("#e3ecf7" if active else _SECONDARY))
                painter.drawText(QRectF(sec_left, rect.top(), sec_w, rect.height()),
                                 int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), elided)
                painter.restore()


BUYER_ROW_HEIGHT = 56
_BUYER_TYPES = {
    # type text -> (badge bg, badge text, avatar bg, avatar icon colour, icon name)
    "dealer": ("#fff1d6", "#8a5200", "#fff1d6", "#b36b00", "fa5s.building"),
    "customer": ("#e3eefb", "#2f6fb0", "#e3eefb", "#3474b0", "fa5s.user"),
}


class BuyerSuggestionDelegate(SuggestionDelegate):
    """For buyer suggestions shaped "Name | Dealer/Customer | Phone | CNIC":

        (avatar)  MUHAMMAD AKRAM                                     [ Customer ]
                  0300-1234567   \u00b7   33302-9056747-5

    A round avatar (blue person for a customer, amber building for a dealer), the name in
    bold with what you typed highlighted, a Dealer / Customer badge on the right and the
    phone and CNIC on a quieter second line. A row that is not in that shape is drawn like
    SuggestionDelegate."""

    def sizeHint(self, option, index):  # noqa: N802
        base = super().sizeHint(option, index)
        if len((index.data() or "").split(COLUMN_SEPARATOR)) == 4:
            return QSize(base.width(), BUYER_ROW_HEIGHT)
        return base

    def paint(self, painter, option, index):  # noqa: N802
        # PyQt aborts the whole program if a virtual raises, so never let one escape.
        try:
            if len((index.data() or "").split(COLUMN_SEPARATOR)) == 4:
                self._paint_buyer(painter, option, index)
            else:
                super().paint(painter, option, index)
        except Exception:
            try:
                super().paint(painter, option, index)
            except Exception:
                pass

    def _pix(self, name: str, colour: str, size: int = 15):
        if _qta is None:
            return None
        key = f"{name}|{colour}|{size}"
        if key not in self._icon_cache:
            try:
                self._icon_cache[key] = _qta.icon(name, color=colour).pixmap(size, size)
            except Exception:
                return None
        return self._icon_cache[key]

    def _paint_buyer(self, painter, option, index) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""
        opt.icon = QIcon()
        widget = opt.widget
        style = widget.style() if widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)    # hover / gradient

        rect = opt.rect
        active = bool(opt.state & QStyle.StateFlag.State_Selected)
        name, kind, phone, cnic = [p.strip() for p in text.split(COLUMN_SEPARATOR)]
        key = "dealer" if kind.lower().startswith("dealer") else "customer"
        badge_bg, badge_fg, av_bg, av_fg, icon_name = _BUYER_TYPES[key]
        query = self._query()
        match = _MATCH_ON_ACTIVE if active else _MATCH_COLOUR
        top_line_y = rect.top() + rect.height() * 0.36
        sub_line_y = rect.top() + rect.height() * 0.72

        # avatar circle
        d = 34
        avatar = QRectF(rect.left() + 14, rect.top() + (rect.height() - d) / 2, d, d)
        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 56) if active else QColor(av_bg))
        painter.drawEllipse(avatar)
        painter.restore()
        pix = self._pix(icon_name, "#ffffff" if active else av_fg)
        if pix is not None:
            painter.drawPixmap(int(avatar.center().x() - 7.5), int(avatar.center().y() - 7.5), pix)

        right = rect.right() - 14
        # type badge (right, on the name line)
        small = QFont(opt.font)
        small.setBold(True)
        small.setPixelSize(11)
        fm = QFontMetrics(small)
        label = "Dealer" if key == "dealer" else "Customer"
        bw = fm.horizontalAdvance(label) + 20
        badge = QRectF(right - bw, top_line_y - 11, bw, 22)
        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 60) if active else QColor(badge_bg))
        painter.drawRoundedRect(badge, 11, 11)
        painter.setFont(small)
        painter.setPen(QColor("#ffffff" if active else badge_fg))
        painter.drawText(badge, int(Qt.AlignmentFlag.AlignCenter), label)
        painter.restore()

        text_left = avatar.right() + 12
        # name (bold, highlighted, elided before the badge)
        name_font = QFont(opt.font)
        name_font.setBold(True)
        name_w = badge.left() - 12 - text_left
        shown = QFontMetrics(name_font).elidedText(name, Qt.TextElideMode.ElideRight, int(max(20, name_w)))
        doc = QTextDocument()
        doc.setDefaultFont(name_font)
        doc.setDocumentMargin(0)
        doc.setHtml(f'<span style="color:{"#ffffff" if active else _TEXT_COLOUR};">'
                    f'{highlight_html(shown, query, match)}</span>')
        doc.setTextWidth(max(20, name_w))
        painter.save()
        painter.translate(text_left, top_line_y - doc.size().height() / 2)
        doc.drawContents(painter)
        painter.restore()

        # phone / CNIC (quiet second line)
        sub_font = QFont(opt.font)
        sub_font.setPixelSize(12)
        bits = [phone or "No phone", cnic or "No CNIC"]
        painter.save()
        painter.setFont(sub_font)
        painter.setPen(QColor("#dbe7f5" if active else _SECONDARY))
        painter.drawText(QRectF(text_left, sub_line_y - 10, right - text_left, 20),
                         int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                         QFontMetrics(sub_font).elidedText("   \u00b7   ".join(bits), Qt.TextElideMode.ElideRight,
                                                           int(right - text_left)))
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


def style_completer(completer: QCompleter, icon_name: str | None = None, delegate_class=None) -> None:
    """Give an existing QCompleter's popup the new look. Safe to call once, right
    after the completer is created. `delegate_class` (default SuggestionDelegate) lets a
    list with columns use ColumnSuggestionDelegate."""
    popup = completer.popup()
    if popup is None:
        return
    popup.setStyleSheet(POPUP_QSS)
    # Real rounded corners: clip the popup window itself to a rounded shape (a
    # translucent window would lose the list's own frame and background).
    round_mask = _RoundedMask(popup)
    popup.installEventFilter(round_mask)
    completer._popup_round_mask = round_mask
    delegate = (delegate_class or SuggestionDelegate)(completer, icon_name, popup)
    popup.setItemDelegate(delegate)
    # Keep the Python object alive: without a reference PyQt drops the subclass
    # wrapper and Qt silently falls back to its plain default row painting.
    completer._suggestion_delegate = delegate
    popup.setUniformItemSizes(True)
    popup.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    popup.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
