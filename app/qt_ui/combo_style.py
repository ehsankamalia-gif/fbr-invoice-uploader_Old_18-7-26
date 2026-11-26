"""Look of a combo box's DROP-DOWN LIST (e.g. Motorcycle Model / Color on Advance Booking).

Presentation only: it changes how the existing QComboBox popup is DRAWN. The items, the
current index, the signals and the keyboard handling are untouched.

Same family as the chassis auto-complete list (completer_style.py):
  * a soft rounded frame, generous evenly spaced rows;
  * a small leading icon;
  * the hovered / keyboard-active row gets a deep-blue gradient;
  * the CURRENT choice is bold with a check mark on the right;
  * a blank first item (used as "nothing chosen") is shown as a muted placeholder.
"""
from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtWidgets import QApplication, QComboBox, QListView, QStyle, QStyledItemDelegate, QStyleOptionViewItem

from app.qt_ui.completer_style import POPUP_QSS, ROW_HEIGHT, _RoundedMask
from app.qt_ui.theme import _qta

_ICON_SIZE = 16
_ICON_LEFT = 16
_TEXT_LEFT = 44
_TEXT_COLOUR = "#263445"
_MUTED = "#8a97a6"
_ICON_COLOUR = "#3474b0"
_CHECK_COLOUR = "#2f6fb0"


class ComboItemDelegate(QStyledItemDelegate):
    def __init__(self, combo: QComboBox, icon_name: str | None, placeholder: str, parent=None):
        super().__init__(parent)
        self._combo = combo
        self._icon_name = icon_name
        self._placeholder = placeholder
        self._cache: dict[tuple[str, str], QPixmap] = {}
        self._text_left = _TEXT_LEFT if icon_name else 18      # no icon -> no icon-sized gap

    def _pixmap(self, name: str | None, colour: str) -> QPixmap | None:
        if _qta is None or not name:
            return None
        key = (name, colour)
        if key not in self._cache:
            try:
                self._cache[key] = _qta.icon(name, color=colour).pixmap(_ICON_SIZE, _ICON_SIZE)
            except Exception:
                return None
        return self._cache[key]

    def sizeHint(self, option, index):  # noqa: N802
        base = super().sizeHint(option, index)
        return QSize(base.width() + self._text_left + 40, max(ROW_HEIGHT, base.height()))

    def paint(self, painter, option, index):  # noqa: N802
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""
        opt.icon = QIcon()
        widget = opt.widget
        style = widget.style() if widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)   # hover gradient from QSS

        rect = opt.rect
        active = bool(opt.state & (QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_MouseOver))
        current = index.row() == self._combo.currentIndex()
        blank = not text.strip()

        icon = self._pixmap(self._icon_name, "#ffffff" if active else (_MUTED if blank else _ICON_COLOUR))
        if icon is not None:
            painter.drawPixmap(rect.left() + _ICON_LEFT, rect.top() + (rect.height() - _ICON_SIZE) // 2, icon)

        font = opt.font
        font.setBold(current and not blank)
        font.setItalic(blank)
        painter.save()
        painter.setFont(font)
        painter.setPen(QColor("#ffffff" if active else (_MUTED if blank else _TEXT_COLOUR)))
        text_rect = rect.adjusted(self._text_left, 0, -40, 0)
        painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                         self._placeholder if blank else text)
        painter.restore()

        if current and not blank:
            tick = self._pixmap("fa5s.check", "#ffffff" if active else _CHECK_COLOUR)
            if tick is not None:
                painter.drawPixmap(rect.right() - 16 - _ICON_SIZE, rect.top() + (rect.height() - _ICON_SIZE) // 2, tick)


def style_combo(combo: QComboBox, icon_name: str | None = None, placeholder: str = "Select…") -> None:
    """Give a QComboBox's drop-down list the new look. Call once, right after creating the
    combo (before it is first shown)."""
    view = QListView(combo)
    view.setUniformItemSizes(True)
    combo.setView(view)
    view.setStyleSheet(POPUP_QSS)
    view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    delegate = ComboItemDelegate(combo, icon_name, placeholder, view)
    view.setItemDelegate(delegate)
    combo._item_delegate = delegate            # keep the Python object alive (PyQt would drop it)
    combo.setMaxVisibleItems(8)
    # open BELOW the field like a normal dropdown (not over it), and round the popup window
    combo.setStyleSheet("QComboBox { combobox-popup: 0; }")
    container = view.parentWidget()
    if container is not None and container is not combo:
        container.setStyleSheet("QFrame { border: none; background: transparent; }")
        mask = _RoundedMask(container)
        container.installEventFilter(mask)
        combo._popup_round_mask = mask
