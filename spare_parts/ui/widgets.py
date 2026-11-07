"""Small reusable PyQt6 building blocks shared across every Spare Parts
screen, present from Phase 1 so later phases don't reinvent them.

PyQt6 only - no imports from app.qt_ui or any other app package (see
spare_parts/__init__.py).
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QComboBox, QDateEdit, QDoubleSpinBox, QSpinBox


class NoScrollMixin:
    """Mouse wheel scrolls the containing form (e.g. a QScrollArea), not
    this widget's value, unless the widget already has keyboard focus -
    required by the module's UI rules (see spare_parts/__init__.py)."""

    def wheelEvent(self, event):  # noqa: N802 - Qt override naming
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class NoScrollComboBox(NoScrollMixin, QComboBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)


class NoScrollSpinBox(NoScrollMixin, QSpinBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)


class NoScrollDoubleSpinBox(NoScrollMixin, QDoubleSpinBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)


class NoScrollDateEdit(NoScrollMixin, QDateEdit):
    """Used by Phase 5's report date-range filters."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)


def _draw_trash_pixmap(size: int, color: QColor) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(color)
    pen.setWidthF(max(1.2, size * 0.1))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    s = float(size)
    painter.drawLine(QPointF(s * 0.18, s * 0.32), QPointF(s * 0.82, s * 0.32))  # lid
    painter.drawRoundedRect(QRectF(s * 0.38, s * 0.16, s * 0.24, s * 0.14), s * 0.03, s * 0.03)  # handle
    painter.drawRoundedRect(QRectF(s * 0.26, s * 0.32, s * 0.48, s * 0.54), s * 0.06, s * 0.06)  # bin body
    for fx in (0.40, 0.50, 0.60):  # ridge lines
        painter.drawLine(QPointF(s * fx, s * 0.42), QPointF(s * fx, s * 0.76))
    painter.end()
    return pixmap


def trash_icon(size: int = 16, normal_color: str = "#e74c3c", hover_color: str = "#ffffff") -> QIcon:
    """A small flat trash-can glyph, painted at runtime so delete buttons
    get a proper icon without pulling in an icon-font package. Qt shows
    the hover_color pixmap automatically while the mouse is over the
    button (QIcon.Mode.Active) - no extra event wiring needed, it just
    has to line up with the button's own :hover background colour."""
    icon = QIcon()
    icon.addPixmap(_draw_trash_pixmap(size, QColor(normal_color)), QIcon.Mode.Normal)
    icon.addPixmap(_draw_trash_pixmap(size, QColor(hover_color)), QIcon.Mode.Active)
    return icon
