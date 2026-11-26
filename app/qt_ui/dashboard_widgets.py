"""Building blocks of the redesigned Dashboard (presentation only).

  build_kpi_card()    big gradient status card (Total / Synced / Pending / Failed); keeps .value_label / .subtitle_label
  GlanceTile          "Today at a glance": a value with a coloured trend chip (up / down / new / flat)
  TrendCard           sales-trend chart with a 7 / 30 day switch (TrendChart is the painted bar chart)
  AttentionPanel      failed + pending uploads with a Retry button per row
  QuickActions        four large shortcut tiles

Everything is driven by plain data (app/services/dashboard_insights.py) through set_* methods, so the
window decides what to show and these widgets never touch the database or an invoice. Virtual methods
(paint / mouse events) are wrapped so nothing in here can abort the application.
"""
from __future__ import annotations

import math
from typing import Callable, Optional

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from app.qt_ui.invoice_style import _gradient
from app.qt_ui.theme import _qta

INK = "#263445"
MUTED = "#6b7a8b"
LINE = "#e3e9f0"
CARD_BG = "#ffffff"
GOOD, BAD, NEUTRAL = "#1c6b3f", "#b42318", "#5b6b7c"
GOOD_BG, BAD_BG, NEUTRAL_BG, NEW_BG = "#e1f4e8", "#fde7e7", "#eef2f7", "#e3eefb"


# ---- small helpers ---------------------------------------------------------------------------------
def format_money(value: float) -> str:
    return f"Rs. {value:,.0f}"


def format_short(value: float) -> str:
    """Axis label: 1,500 -> 1.5K, 2,000,000 -> 2M."""
    value = float(value)
    for limit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= limit:
            text = f"{value / limit:.1f}".rstrip("0").rstrip(".")
            return f"{text}{suffix}"
    return f"{value:.0f}"


def nice_ceiling(value: float) -> float:
    """The smallest 'round' number >= value (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10 x a power of ten)."""
    if value <= 0:
        return 1.0
    magnitude = 10 ** math.floor(math.log10(value))
    for m in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if value <= m * magnitude + 1e-9:
            return m * magnitude
    return 10 * magnitude


def trend_chip(trend) -> tuple[str, str, str]:
    """(text, text colour, background) for a dashboard_insights.Trend."""
    if trend is None or trend.direction == "flat":
        return "– no change", NEUTRAL, NEUTRAL_BG
    if trend.direction == "new":
        return "▲ new", "#2f6fb0", NEW_BG
    pct = f"{abs(trend.pct):.0f}%" if abs(trend.pct) >= 10 else f"{abs(trend.pct):.1f}%"
    if trend.direction == "up":
        return f"▲ {pct}", GOOD, GOOD_BG
    return f"▼ {pct}", BAD, BAD_BG


def _shadow(widget, blur: int = 22, alpha: int = 38) -> None:
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, 4)
    effect.setColor(QColor(30, 50, 80, alpha))
    widget.setGraphicsEffect(effect)


def _icon_label(name: str, colour: str, size: int, box: int, bg: str, radius: int) -> QLabel:
    label = QLabel()
    label.setFixedSize(box, box)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setStyleSheet(f"background-color: {bg}; border: none; border-radius: {radius}px;")
    try:
        if _qta is not None:
            label.setPixmap(_qta.icon(name, color=colour).pixmap(size, size))
    except Exception:
        pass
    return label


# ---- KPI cards (Total / Synced / Pending / Failed) -----------------------------------------------------
def build_kpi_card(title: str, icon_name: str, accent: str, clickable: bool = False) -> QFrame:
    """A gradient status card. `card.value_label` and `card.subtitle_label` are the labels to update."""
    card = QFrame()
    card.setObjectName("dashKpi")
    card.setMinimumHeight(112)
    card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    hover = (
        f"#dashKpi:hover, #dashKpi:focus {{ background: {_gradient(accent, lift=True)}; }}" if clickable else ""
    )
    card.setStyleSheet(
        f"#dashKpi {{ background: {_gradient(accent)}; border: none; border-radius: 16px; }} {hover}"
    )
    _shadow(card)

    row = QHBoxLayout(card)
    row.setContentsMargins(20, 14, 20, 14)
    row.setSpacing(16)
    row.addWidget(_icon_label(icon_name, "#ffffff", 22, 52, "rgba(255,255,255,0.22)", 14))

    col = QVBoxLayout()
    col.setSpacing(1)
    heading = QLabel(title)
    heading.setStyleSheet(
        "color: rgba(255,255,255,0.88); font-size: 11px; font-weight: 700; letter-spacing: 1px; "
        "background: transparent;"
    )
    value = QLabel("0")
    value.setStyleSheet("color: #ffffff; font-size: 32px; font-weight: 800; background: transparent;")
    subtitle = QLabel("")
    subtitle.setStyleSheet("color: rgba(255,255,255,0.82); font-size: 11px; background: transparent;")
    col.addStretch(1)
    col.addWidget(heading)
    col.addWidget(value)
    col.addWidget(subtitle)
    col.addStretch(1)
    row.addLayout(col, 1)
    card.value_label = value
    card.subtitle_label = subtitle
    return card


# ---- "Today at a glance" tiles ---------------------------------------------------------------------------
class GlanceTile(QFrame):
    def __init__(self, title: str, icon_name: str, accent: str, parent=None):
        super().__init__(parent)
        self.setObjectName("glanceTile")
        self.setMinimumHeight(104)
        self.setStyleSheet(
            f"#glanceTile {{ background: {CARD_BG}; border: 1px solid {LINE}; border-radius: 14px; }}"
        )
        _shadow(self, 16, 22)
        row = QHBoxLayout(self)
        row.setContentsMargins(18, 14, 18, 14)
        row.setSpacing(14)
        row.addWidget(_icon_label(icon_name, accent, 20, 46, _tint_bg(accent), 12), 0, Qt.AlignmentFlag.AlignTop)

        col = QVBoxLayout()
        col.setSpacing(2)
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(
            f"color: {MUTED}; font-size: 11px; font-weight: 700; letter-spacing: 0.8px; background: transparent;"
        )
        self.value_label = QLabel("–")
        self.value_label.setStyleSheet(f"color: {INK}; font-size: 24px; font-weight: 800; background: transparent;")
        foot = QHBoxLayout()
        foot.setSpacing(8)
        self.trend_label = QLabel("")
        self.compare_label = QLabel("")
        self.compare_label.setStyleSheet(f"color: {MUTED}; font-size: 11px; background: transparent;")
        foot.addWidget(self.trend_label)
        foot.addWidget(self.compare_label)
        foot.addStretch(1)
        col.addWidget(self.title_label)
        col.addWidget(self.value_label)
        col.addLayout(foot)
        row.addLayout(col, 1)
        self.set_trend(None, "")

    def set_value(self, text: str) -> None:
        self.value_label.setText(text)

    def set_trend(self, trend, compared_with: str) -> None:
        text, colour, bg = trend_chip(trend)
        self.trend_label.setText(text)
        self.trend_label.setStyleSheet(
            f"color: {colour}; background-color: {bg}; border-radius: 9px; padding: 2px 9px; "
            f"font-size: 11px; font-weight: 700;"
        )
        self.compare_label.setText(compared_with)
        self.trend_label.setVisible(bool(compared_with))
        self.compare_label.setVisible(bool(compared_with))


def _tint_bg(accent: str) -> str:
    c = QColor(accent)
    return f"rgba({c.red()},{c.green()},{c.blue()},0.13)"


# ---- the painted bar chart -----------------------------------------------------------------------------------
class TrendChart(QWidget):
    """Daily sales bars with gridlines, short axis labels, a highlighted latest day and a hover tooltip."""

    LEFT, RIGHT, TOP, BOTTOM = 52, 10, 14, 34

    def __init__(self, parent=None):
        super().__init__(parent)
        self._points: list = []
        self._hover = -1
        self.setMouseTracking(True)
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    # -- data
    def set_points(self, points) -> None:
        self._points = list(points)
        self._hover = -1
        self.update()

    def points(self) -> list:
        return list(self._points)

    def axis_max(self) -> float:
        peak = max((p.amount for p in self._points), default=0.0)
        return nice_ceiling(peak)

    def has_sales(self) -> bool:
        return any(p.amount > 0 or p.count > 0 for p in self._points)

    # -- geometry
    def _plot(self) -> QRectF:
        return QRectF(self.LEFT, self.TOP, max(10, self.width() - self.LEFT - self.RIGHT),
                      max(10, self.height() - self.TOP - self.BOTTOM))

    def bar_rect(self, index: int) -> QRectF:
        plot = self._plot()
        n = max(1, len(self._points))
        slot = plot.width() / n
        width = min(slot * 0.62, 40.0)
        height = plot.height() * (self._points[index].amount / self.axis_max()) if self.axis_max() else 0
        height = max(height, 3.0 if self._points[index].amount > 0 else 0.0)
        return QRectF(plot.left() + slot * index + (slot - width) / 2, plot.bottom() - height, width, height)

    def index_at(self, x: float) -> int:
        plot = self._plot()
        n = len(self._points)
        if n == 0 or x < plot.left() or x > plot.right():
            return -1
        return min(n - 1, int((x - plot.left()) / (plot.width() / n)))

    def label_for(self, index: int) -> str:
        p = self._points[index]
        return f"{p.day.strftime('%a %d %b %Y')}\n{p.count} invoice{'s' if p.count != 1 else ''}  ·  {format_money(p.amount)}"

    def _x_label(self, index: int, n: int) -> Optional[str]:
        day = self._points[index].day
        if n <= 8:
            return day.strftime("%a\n%d")
        step = 2 if n <= 16 else 5
        if (n - 1 - index) % step != 0:
            return None
        return day.strftime("%d\n%b") if (day.day <= step or index == 0) else day.strftime("%d")

    # -- events
    def mouseMoveEvent(self, event):  # noqa: N802
        try:
            index = self.index_at(event.position().x())
            if index != self._hover:
                self._hover = index
                self.update()
            if index >= 0:
                QToolTip.showText(event.globalPosition().toPoint(), self.label_for(index), self)
            else:
                QToolTip.hideText()
        except Exception:
            pass

    def leaveEvent(self, event):  # noqa: N802
        self._hover = -1
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):  # noqa: N802
        try:
            self._paint()
        except Exception:
            pass

    def _paint(self) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        plot = self._plot()
        small = QFont(self.font())
        small.setPixelSize(10)
        p.setFont(small)

        if not self._points or not self.has_sales():
            p.setPen(QColor(MUTED))
            big = QFont(self.font())
            big.setPixelSize(13)
            p.setFont(big)
            p.drawText(QRectF(0, 0, self.width(), self.height()), int(Qt.AlignmentFlag.AlignCenter),
                       "No invoices in this period yet")
            p.end()
            return

        top_value = self.axis_max()
        steps = 4
        for i in range(steps + 1):
            y = plot.bottom() - plot.height() * i / steps
            pen = QPen(QColor(LINE), 1, Qt.PenStyle.SolidLine if i == 0 else Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(QColor("#8795a5"))
            p.drawText(QRectF(0, y - 8, self.LEFT - 8, 16),
                       int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                       format_short(top_value * i / steps))

        n = len(self._points)
        last = n - 1
        for i, point in enumerate(self._points):
            rect = self.bar_rect(i)
            if rect.height() > 0:
                hovered = i == self._hover
                if i == last:
                    top, bottom = ("#5fd3a0", "#17934d") if not hovered else ("#7fe0b5", "#1c9f55")
                else:
                    top, bottom = ("#6fb0e8", "#2f6fb0") if not hovered else ("#3f86cd", "#1f4068")
                grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
                grad.setColorAt(0.0, QColor(top))
                grad.setColorAt(1.0, QColor(bottom))
                path = QPainterPath()
                r = min(6.0, rect.width() / 2, rect.height())
                path.addRoundedRect(rect, r, r)
                p.fillPath(path, grad)
                if hovered:                                   # value above the hovered bar
                    p.setPen(QColor(INK))
                    p.drawText(QRectF(rect.center().x() - 50, rect.top() - 18, 100, 16),
                               int(Qt.AlignmentFlag.AlignCenter), format_short(point.amount))
            label = self._x_label(i, n)
            if label:
                slot = plot.width() / n
                p.setPen(QColor("#8795a5" if i != last else INK))
                p.drawText(QRectF(plot.left() + slot * i - 4, plot.bottom() + 5, slot + 8, 28),
                           int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop), label)
        p.end()


_SEGMENT_QSS = f"""
    QPushButton#dashSegment {{
        background: transparent; color: {MUTED}; border: none; border-radius: 9px;
        padding: 6px 16px; font-size: 12px; font-weight: 700;
    }}
    QPushButton#dashSegment:hover {{ color: {INK}; }}
    QPushButton#dashSegment:checked {{ background: #ffffff; color: #1f4068; }}
"""


class TrendCard(QFrame):
    """Card = title + totals line + 7 / 30 day switch + chart."""

    days_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("trendCard")
        self.setStyleSheet(f"#trendCard {{ background: {CARD_BG}; border: 1px solid {LINE}; border-radius: 16px; }}")
        _shadow(self, 18, 26)
        self._days = 7
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 14)
        root.setSpacing(8)

        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(1)
        self.title_label = QLabel("Sales trend")
        self.title_label.setStyleSheet(f"color: {INK}; font-size: 16px; font-weight: 800; background: transparent;")
        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet(f"color: {MUTED}; font-size: 12px; background: transparent;")
        titles.addWidget(self.title_label)
        titles.addWidget(self.summary_label)
        head.addLayout(titles, 1)

        switch = QFrame()
        switch.setStyleSheet(f"QFrame {{ background: {NEUTRAL_BG}; border-radius: 12px; }} {_SEGMENT_QSS}")
        sl = QHBoxLayout(switch)
        sl.setContentsMargins(4, 4, 4, 4)
        sl.setSpacing(2)
        self.btn_7 = self._segment("7 days", 7)
        self.btn_30 = self._segment("30 days", 30)
        self.btn_7.setChecked(True)
        group = QButtonGroup(self)
        group.setExclusive(True)
        for b in (self.btn_7, self.btn_30):
            group.addButton(b)
            sl.addWidget(b)
        self._group = group
        head.addWidget(switch, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(head)

        self.chart = TrendChart()
        root.addWidget(self.chart, 1)

    def _segment(self, text: str, days: int) -> QPushButton:
        b = QPushButton(text)
        b.setObjectName("dashSegment")
        b.setCheckable(True)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setAutoDefault(False)
        b.clicked.connect(lambda _checked=False, d=days: self._choose(d))
        return b

    def _choose(self, days: int) -> None:
        if days != self._days:
            self._days = days
            self.days_changed.emit(days)

    def days(self) -> int:
        return self._days

    def set_series(self, points) -> None:
        points = list(points)
        self.chart.set_points(points)
        total = sum(p.amount for p in points)
        count = sum(p.count for p in points)
        self.summary_label.setText(
            f"{format_money(total)}  ·  {count} invoice{'s' if count != 1 else ''} in the last {len(points)} days"
        )


class ElidedLabel(QLabel):
    """One-line label that ends with an ellipsis instead of widening its parent or cutting a letter in half."""

    def __init__(self, text: str = "", colour: str = MUTED, pixel_size: int = 11, parent=None):
        super().__init__(parent)
        self._full = text
        self._colour = colour
        self.setStyleSheet(f"color: {colour}; font-size: {pixel_size}px; background: transparent;")
        self.setMinimumWidth(10)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def full_text(self) -> str:
        return self._full

    def elided_text(self) -> str:
        return self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideRight, max(0, self.width()))

    def minimumSizeHint(self):  # noqa: N802
        hint = super().minimumSizeHint()
        hint.setWidth(10)
        return hint

    def paintEvent(self, event):  # noqa: N802
        try:
            painter = QPainter(self)
            painter.setPen(QColor(self._colour))
            painter.setFont(self.font())
            painter.drawText(self.rect(), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                             self.elided_text())
            painter.end()
        except Exception:
            pass


# ---- needs-attention panel -----------------------------------------------------------------------------------
class AttentionPanel(QFrame):
    retry_requested = pyqtSignal(int)
    view_pending_requested = pyqtSignal()
    view_failed_requested = pyqtSignal()

    MAX_ROWS = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("attentionPanel")
        self.setStyleSheet(
            f"#attentionPanel {{ background: {CARD_BG}; border: 1px solid {LINE}; border-radius: 16px; }}"
        )
        _shadow(self, 18, 26)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 14)
        root.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("Needs attention")
        title.setStyleSheet(f"color: {INK}; font-size: 16px; font-weight: 800; background: transparent;")
        head.addWidget(title, 1)
        self.failed_badge = self._badge()
        self.pending_badge = self._badge()
        head.addWidget(self.failed_badge)
        head.addWidget(self.pending_badge)
        root.addLayout(head)

        self.rows_host = QVBoxLayout()
        self.rows_host.setSpacing(6)
        root.addLayout(self.rows_host)
        root.addStretch(1)

        foot = QHBoxLayout()
        foot.setSpacing(8)
        self.pending_btn = self._link_button("View pending list")
        self.pending_btn.clicked.connect(self.view_pending_requested.emit)
        self.failed_btn = self._link_button("View failed list")
        self.failed_btn.clicked.connect(self.view_failed_requested.emit)
        foot.addWidget(self.pending_btn)
        foot.addWidget(self.failed_btn)
        foot.addStretch(1)
        root.addLayout(foot)
        self.set_attention(0, 0, [])

    @staticmethod
    def _badge() -> QLabel:
        label = QLabel("")
        label.setVisible(False)
        return label

    @staticmethod
    def _link_button(text: str) -> QPushButton:
        b = QPushButton(text)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setAutoDefault(False)
        b.setStyleSheet(
            "QPushButton { background: transparent; color: #2f6fb0; border: none; font-size: 12px; font-weight: 700; "
            "padding: 4px 2px; } QPushButton:hover { color: #1f4068; text-decoration: underline; }"
        )
        return b

    def _set_badge(self, label: QLabel, count: int, word: str, fg: str, bg: str) -> None:
        label.setVisible(count > 0)
        label.setText(f"{count} {word}")
        label.setStyleSheet(
            f"color: {fg}; background-color: {bg}; border-radius: 10px; padding: 3px 10px; "
            f"font-size: 11px; font-weight: 700;"
        )

    def _clear_rows(self) -> None:
        while self.rows_host.count():
            item = self.rows_host.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def set_attention(self, failed: int, pending: int, rows) -> None:
        self._set_badge(self.failed_badge, failed, "failed", BAD, BAD_BG)
        self._set_badge(self.pending_badge, pending, "pending", "#8a5200", "#fff1d6")
        self.failed_btn.setVisible(failed > 0)
        self.pending_btn.setVisible(pending > 0)
        self._clear_rows()
        rows = list(rows)[: self.MAX_ROWS]
        if not rows and failed + pending == 0:
            self.rows_host.addWidget(self._all_clear())
            return
        for row in rows:
            self.rows_host.addWidget(self._row_widget(row))
        hidden = failed + pending - len(rows)
        if hidden > 0:
            more = QLabel(f"+ {hidden} more")
            more.setStyleSheet(f"color: {MUTED}; font-size: 12px; background: transparent; padding-left: 4px;")
            self.rows_host.addWidget(more)

    def _all_clear(self) -> QWidget:
        box = QFrame()
        box.setObjectName("allClear")
        box.setStyleSheet(f"#allClear {{ background: {GOOD_BG}; border-radius: 12px; }}")
        lay = QHBoxLayout(box)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)
        lay.addWidget(_icon_label("fa5s.check-circle", GOOD, 22, 40, "transparent", 20))
        text = QLabel("All invoices are uploaded to FBR.\nNothing needs attention.")
        text.setStyleSheet(f"color: {GOOD}; font-size: 13px; font-weight: 700; background: transparent;")
        lay.addWidget(text, 1)
        return box

    def _row_widget(self, row) -> QWidget:
        failed = row.status == "FAILED"
        accent, soft = (BAD, BAD_BG) if failed else ("#8a5200", "#fff1d6")
        frame = QFrame()
        frame.setObjectName("attentionRow")
        frame.setStyleSheet(
            f"#attentionRow {{ background: #f8fafc; border: 1px solid {LINE}; border-radius: 10px; }}"
        )
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(10, 8, 8, 8)
        lay.setSpacing(10)
        lay.addWidget(_icon_label("fa5s.exclamation-triangle" if failed else "fa5s.clock", accent, 13, 30, soft, 15))

        col = QVBoxLayout()
        col.setSpacing(0)
        first = QLabel(f"{row.invoice_number}  ·  Rs. {row.amount:,.0f}")
        first.setStyleSheet(f"color: {INK}; font-size: 13px; font-weight: 700; background: transparent;")
        who = row.buyer or "No buyer"
        detail = (row.message or ("Upload failed" if failed else "Waiting to upload")).replace("\n", " ")
        second = ElidedLabel(f"{who}  ·  {detail}")          # long text ends with "...", never widens the panel
        second.setToolTip(row.message or "")
        col.addWidget(first)
        col.addWidget(second)
        lay.addLayout(col, 1)

        retry = QPushButton("Retry")
        retry.setCursor(Qt.CursorShape.PointingHandCursor)
        retry.setAutoDefault(False)
        retry.setFixedHeight(28)
        retry.setToolTip(f"Re-queue {row.invoice_number} for FBR upload")
        retry.setStyleSheet(
            "QPushButton { background-color: #fff4d0; color: #6b4200; border: 1px solid #e0a200; border-radius: 8px; "
            "padding: 0 14px; font-size: 12px; font-weight: 700; } QPushButton:hover { background-color: #ffe27a; }"
        )
        retry.clicked.connect(lambda _checked=False, iid=row.invoice_id: self.retry_requested.emit(iid))
        lay.addWidget(retry)
        frame.retry_button = retry
        return frame

    def row_count(self) -> int:
        return sum(1 for i in range(self.rows_host.count())
                   if getattr(self.rows_host.itemAt(i).widget(), "retry_button", None) is not None)


# ---- quick actions ----------------------------------------------------------------------------------------------
class ActionTile(QFrame):
    clicked = pyqtSignal()

    def __init__(self, title: str, subtitle: str, icon_name: str, accent: str, parent=None):
        super().__init__(parent)
        self.setObjectName("actionTile")
        self.setMinimumHeight(84)
        self.setStyleSheet(
            f"#actionTile {{ background: {CARD_BG}; border: 1px solid {LINE}; border-radius: 14px; }}"
            f"#actionTile:hover, #actionTile:focus {{ border: 1px solid {accent}; background: {_tint_solid(accent)}; }}"
        )
        _shadow(self, 14, 20)
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 12, 16, 12)
        row.setSpacing(14)
        tile = QLabel()
        tile.setFixedSize(48, 48)
        tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tile.setStyleSheet(f"background: {_gradient(accent)}; border-radius: 13px;")
        try:
            if _qta is not None:
                tile.setPixmap(_qta.icon(icon_name, color="#ffffff").pixmap(21, 21))
        except Exception:
            pass
        row.addWidget(tile)
        col = QVBoxLayout()
        col.setSpacing(1)
        t = QLabel(title)
        t.setStyleSheet(f"color: {INK}; font-size: 14px; font-weight: 800; background: transparent;")
        s = QLabel(subtitle)
        s.setStyleSheet(f"color: {MUTED}; font-size: 11px; background: transparent;")
        col.addStretch(1)
        col.addWidget(t)
        col.addWidget(s)
        col.addStretch(1)
        row.addLayout(col, 1)
        for child in (tile, t, s):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.title_text = title

    def mouseReleaseEvent(self, event):  # noqa: N802
        try:
            if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
                self.clicked.emit()
        except Exception:
            pass
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):  # noqa: N802
        try:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
                self.clicked.emit()
                return
        except Exception:
            pass
        super().keyPressEvent(event)


def _tint_solid(accent: str) -> str:
    c = QColor(accent)
    return f"rgb({int(c.red() * 0.08 + 255 * 0.92)},{int(c.green() * 0.08 + 255 * 0.92)},{int(c.blue() * 0.08 + 255 * 0.92)})"


class QuickActions(QWidget):
    """Row of shortcut tiles. `triggered(key)` carries the page key the window should open."""

    triggered = pyqtSignal(str)

    ACTIONS = (
        ("invoice", "New Invoice", "Create a motorcycle invoice", "fa5s.plus", "#2578b5"),
        ("print_document", "Print Documents", "Search by chassis and print", "fa5s.print", "#8340a0"),
        ("credit_ledger", "Credit Sale", "Installments and ledgers", "fa5s.exchange-alt", "#17934d"),
        ("spare_parts", "Spare Parts", "Sales counter and stock", "fa5s.cog", "#b4540a"),
    )

    def __init__(self, allowed: Optional[Callable[[str], bool]] = None, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(18)
        self.tiles: dict[str, ActionTile] = {}
        for key, title, subtitle, icon, accent in self.ACTIONS:
            if allowed is not None and not allowed(key):
                continue                                   # staff without access never see the shortcut
            tile = ActionTile(title, subtitle, icon, accent)
            tile.clicked.connect(lambda k=key: self.triggered.emit(k))
            lay.addWidget(tile, 1)
            self.tiles[key] = tile


def section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(
        f"color: {INK}; font-size: 12px; font-weight: 800; letter-spacing: 1.2px; background: transparent;"
    )
    return label
