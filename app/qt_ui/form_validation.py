"""Inline form validation for the desktop invoice form.

PRESENTATION ONLY. The rules below are the same rules (same regexes, same
messages) the form already enforced in _validate_invoice_form /
_check_invoice_form_completeness - what is accepted and what is rejected has not
changed. What this adds is how problems are SHOWN:

  * a red border + short message right under the offending field, and a green
    tick / red warning icon inside text fields;
  * "reward early, punish late": a problem is only shown once you have left the
    field (or tried to submit); once shown it clears the moment the value is OK;
  * one summary banner listing the problems, each item clickable to jump there;
  * a failed submit highlights everything, scrolls to and focuses the first
    problem (no pop-up dialog for ordinary field errors);
  * a tooltip on the disabled Submit button saying what is still needed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from PyQt6.QtCore import QEvent, QObject, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QFontMetrics, QIcon
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.qt_ui.theme import _qta

# ---- the rules (identical to the ones the form already used) --------------------
_CNIC_RE = re.compile(r"^\d{5}-\d{7}-\d$")
_PHONE_RE = re.compile(r"^03\d{9}$")


def required(message: str) -> Callable[[str], Optional[str]]:
    return lambda text: None if (text or "").strip() else message


def cnic_rule(text: str) -> Optional[str]:
    text = (text or "").strip()
    if not text:
        return "CNIC is required."
    if not _CNIC_RE.match(text):
        return "Format must be 12345-1234567-1."
    return None


def phone_rule(text: str) -> Optional[str]:
    text = (text or "").strip()
    if not text:
        return "Cell number is required."
    if not _PHONE_RE.match(text):
        return "Format must be 03XXXXXXXXX."
    return None


def amount_rule(value: float) -> Optional[str]:
    return None if value > 0 else "Amount (Excl. Tax) must be greater than zero."


# ---- colours ------------------------------------------------------------------------
_ERROR = "#c0392b"
_VALID = "#2e9e6b"

_MESSAGE_QSS = f"QLabel {{ color: {_ERROR}; font-size: 11px; font-weight: 600; background: transparent; border: none; padding: 0px; }}"

_BANNER_QSS = f"""
    QFrame#validationBanner {{
        background-color: #fdeeed;
        border: 1px solid #f3c4c0;
        border-left: 5px solid {_ERROR};
        border-radius: 12px;
    }}
    QFrame#validationBanner QLabel {{ background: transparent; border: none; }}
    QLabel#validationTitle {{ color: #8f2a20; font-size: 14px; font-weight: 800; }}
    QLabel#validationBody {{ color: #7a2d25; font-size: 13px; }}
"""


def _icon(name: str, colour: str) -> QIcon:
    if _qta is None:
        return QIcon()
    try:
        return _qta.icon(name, color=colour)
    except Exception:
        return QIcon()


# ---- per-field bookkeeping ------------------------------------------------------------
@dataclass
class _Field:
    widget: QWidget
    key: str                                     # human name, used in the banner / tooltip
    check: Callable[[QWidget], Optional[str]]    # -> error message or None
    touched: bool = False
    external: Optional[str] = None               # an error injected after a submit attempt (e.g. duplicate chassis)
    state: str = "neutral"
    message: str = ""
    signature: object = None                     # the value this field was last checked against
    label: Optional[QLabel] = field(default=None, repr=False)
    action: Optional[QAction] = field(default=None, repr=False)


def _signature(widget: QWidget):
    """What the field currently holds - used to notice a change that arrived
    WITHOUT a signal (the app fills many fields with signals blocked)."""
    if isinstance(widget, QLineEdit):
        return widget.text()
    if isinstance(widget, QComboBox):
        return widget.currentText()
    if isinstance(widget, QAbstractSpinBox):
        try:
            return widget.value()
        except Exception:
            return None
    return None


def _is_blank(widget: QWidget) -> bool:
    if isinstance(widget, QLineEdit):
        return not widget.text().strip()
    if isinstance(widget, QComboBox):
        return not widget.currentText().strip()
    if isinstance(widget, QAbstractSpinBox):
        try:
            return widget.value() <= 0
        except Exception:
            return False
    return False


class ValidationBanner(QFrame):
    """Summary of the problems on the form. Hidden when there are none."""

    link_clicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("validationBanner")
        self.setStyleSheet(_BANNER_QSS)
        row = QHBoxLayout(self)
        row.setContentsMargins(18, 14, 18, 14)
        row.setSpacing(14)

        self._icon = QLabel()
        self._icon.setFixedSize(26, 26)
        self._icon.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        if _qta is not None:
            try:
                self._icon.setPixmap(_qta.icon("fa5s.exclamation-triangle", color=_ERROR).pixmap(22, 22))
            except Exception:
                pass
        row.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignTop)

        col = QVBoxLayout()
        col.setSpacing(4)
        self._title = QLabel("")
        self._title.setObjectName("validationTitle")
        self._body = QLabel("")
        self._body.setObjectName("validationBody")
        self._body.setTextFormat(Qt.TextFormat.RichText)
        self._body.setWordWrap(True)
        self._body.linkActivated.connect(self.link_clicked.emit)
        col.addWidget(self._title)
        col.addWidget(self._body)
        row.addLayout(col, 1)
        self.hide()

    LONG_MESSAGE = 48

    def set_errors(self, items: list[tuple[int, str, str]]) -> None:
        """items: (field index, field name, message). Short problems are shown as
        a compact row of clickable field names (each field already carries its own
        message); long ones - e.g. a duplicate-chassis warning - get a full line."""
        if not items:
            self.hide()
            return
        n = len(items)
        self._title.setText(f"Please fix {n} item{'s' if n != 1 else ''} before submitting")
        link = 'style="color:#8f2a20; font-weight:700;"'
        short = [f'<a href="{i}" {link}>{_esc(name)}</a>' for i, name, msg in items if len(msg) <= self.LONG_MESSAGE]
        long_ = [
            f'<a href="{i}" {link}>{_esc(name)}</a> &mdash; {_esc(msg)}'
            for i, name, msg in items if len(msg) > self.LONG_MESSAGE
        ]
        lines = []
        if short:
            lines.append("&nbsp;&nbsp;&middot;&nbsp;&nbsp;".join(short))
        lines.extend(long_)
        self._body.setText("<br>".join(lines))
        self.show()


def _esc(text: str) -> str:
    import html

    return html.escape(text or "")


class _MessageLabel(QLabel):
    """The short red message under a field. It is NOT part of any layout: it sits
    in the gap between form rows and follows its field (Move / Resize / Show /
    Hide), so adding it never shifts the form."""

    HEIGHT = 15

    def __init__(self, field_widget: QWidget):
        super().__init__(field_widget.parentWidget())
        self._field = field_widget
        self.setStyleSheet(_MESSAGE_QSS)
        self._full = ""
        self.hide()
        field_widget.installEventFilter(self)

    def set_message(self, text: str) -> None:
        self._full = text
        self.setToolTip(text)
        self._reposition()
        self.setVisible(bool(text) and self._field.isVisible())

    def _reposition(self) -> None:
        geo = self._field.geometry()
        width = max(20, geo.width() - 6)
        self.setGeometry(geo.left() + 3, geo.bottom() + 2, width, self.HEIGHT)
        self.setText(QFontMetrics(self.font()).elidedText(self._full, Qt.TextElideMode.ElideRight, width))
        self.raise_()

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self._field:
            t = event.type()
            if t in (QEvent.Type.Move, QEvent.Type.Resize):
                self._reposition()
            elif t in (QEvent.Type.Show, QEvent.Type.Hide):
                self._reposition()
                self.setVisible(bool(self._full) and self._field.isVisible())
        return False


class FormValidator(QObject):
    """Owns the per-field validation state for one form."""

    changed = pyqtSignal()

    def __init__(self, parent: QObject | None = None, scroll_area: QScrollArea | None = None,
                 banner: ValidationBanner | None = None):
        super().__init__(parent)
        self._fields: list[_Field] = []
        self._scroll = scroll_area
        self._banner = banner
        if banner is not None:
            banner.link_clicked.connect(self._on_banner_link)
        self._icon_error = _icon("fa5s.exclamation-circle", _ERROR)
        self._icon_valid = _icon("fa5s.check-circle", _VALID)
        # Safety net: the app sets many fields programmatically with signals blocked
        # (customer autofill, chassis selection, the colour list, price lookup...), so
        # no change signal reaches us. This cheap check notices any field whose value
        # changed behind our back and re-validates it, so a stale error can never stay
        # on a field that already holds a valid value.
        self._poll = QTimer(self)
        self._poll.setInterval(250)
        self._poll.timeout.connect(self.refresh)
        self._poll.start()

    # ---- registration ----------------------------------------------------------------
    def add_line_edit(self, widget: QLineEdit, key: str, rule: Callable[[str], Optional[str]]) -> None:
        self._add(widget, key, lambda w: rule(w.text()), widget.textChanged)

    def add_combo(self, widget: QComboBox, key: str, rule: Callable[[str], Optional[str]]) -> None:
        self._add(widget, key, lambda w: rule(w.currentText()), widget.currentTextChanged)

    def add_spin(self, widget: QAbstractSpinBox, key: str, rule: Callable[[float], Optional[str]]) -> None:
        self._add(widget, key, lambda w: rule(w.value()), widget.valueChanged)

    def _add(self, widget: QWidget, key: str, check, signal) -> None:
        f = _Field(widget=widget, key=key, check=check)
        f.label = _MessageLabel(widget)
        if isinstance(widget, QLineEdit):
            f.action = QAction(widget)
            f.action.setVisible(False)
            widget.addAction(f.action, QLineEdit.ActionPosition.TrailingPosition)
        idx = len(self._fields)
        self._fields.append(f)
        signal.connect(lambda *_a, i=idx: self._on_changed(i))
        # "touched" = the user has left the field once
        widget.installEventFilter(self)
        if isinstance(widget, QAbstractSpinBox) and widget.lineEdit() is not None:
            widget.lineEdit().installEventFilter(self)
        self._evaluate(f)

    # ---- events ----------------------------------------------------------------------
    def eventFilter(self, obj, event):  # noqa: N802
        if event.type() == QEvent.Type.FocusOut:
            for f in self._fields:
                w = f.widget
                spin_edit = w.lineEdit() if isinstance(w, QAbstractSpinBox) else None
                if obj is w or (spin_edit is not None and obj is spin_edit):
                    if not f.touched:
                        f.touched = True
                        self._evaluate(f)
                        self._refresh_banner()
                        self.changed.emit()
                    break
        return False

    def _on_changed(self, index: int) -> None:
        f = self._fields[index]
        f.external = None            # an injected (post-submit) error ends as soon as the value changes
        self._evaluate(f)
        self._refresh_banner()
        self.changed.emit()

    def _on_banner_link(self, href: str) -> None:
        try:
            self._focus(self._fields[int(href)])
        except (ValueError, IndexError):
            pass

    # ---- evaluation ------------------------------------------------------------------
    def _message_for(self, f: _Field) -> Optional[str]:
        return f.external or f.check(f.widget)

    def _evaluate(self, f: _Field) -> None:
        f.signature = _signature(f.widget)
        msg = self._message_for(f)
        if msg is None:
            state, text = ("neutral", "") if _is_blank(f.widget) else ("valid", "")
        elif f.touched:
            state, text = "invalid", msg
        else:
            state, text = "neutral", ""
        self._apply(f, state, text)

    def _apply(self, f: _Field, state: str, text: str) -> None:
        f.state, f.message = state, text
        w = f.widget
        if w.property("vstate") != state:
            w.setProperty("vstate", state)
            style = w.style()
            style.unpolish(w)
            style.polish(w)
            w.update()
        if f.label is not None:
            f.label.set_message(text if state == "invalid" else "")
        if f.action is not None:
            if state == "invalid":
                f.action.setIcon(self._icon_error)
                f.action.setToolTip(text)
                f.action.setVisible(not self._icon_error.isNull())
            elif state == "valid":
                f.action.setIcon(self._icon_valid)
                f.action.setToolTip("")
                f.action.setVisible(not self._icon_valid.isNull())
            else:
                f.action.setVisible(False)

    def _refresh_banner(self) -> None:
        if self._banner is not None:
            self._banner.set_errors(
                [(i, f.key, f.message) for i, f in enumerate(self._fields) if f.state == "invalid"]
            )

    def _focus(self, f: _Field) -> None:
        if self._scroll is not None:
            try:
                self._scroll.ensureWidgetVisible(f.widget, 60, 120)
            except Exception:
                pass
        f.widget.setFocus()

    # ---- public API ------------------------------------------------------------------
    def refresh(self, force: bool = False) -> bool:
        """Re-validate any field whose value changed without us being told (or all of
        them with force=True). Returns True if anything was re-evaluated."""
        touched_any = False
        for f in self._fields:
            sig = _signature(f.widget)
            if force or sig != f.signature:
                if sig != f.signature:
                    f.external = None        # a value change ends an injected (post-submit) error, as in _on_changed
                self._evaluate(f)
                touched_any = True
        if touched_any:
            self._refresh_banner()
            self.changed.emit()
        return touched_any

    def stop(self) -> None:
        """Stop the safety-net poll (tests / teardown)."""
        self._poll.stop()

    def errors(self) -> list[tuple[str, str]]:
        """Every current rule violation, shown or not: [(field name, message)]."""
        out = []
        for f in self._fields:
            msg = self._message_for(f)
            if msg:
                out.append((f.key, msg))
        return out

    def visible_errors(self) -> list[tuple[str, str]]:
        return [(f.key, f.message) for f in self._fields if f.state == "invalid"]

    def summary_tooltip(self) -> str:
        names = [k for k, _ in self.errors()]
        return f"Still needed: {', '.join(names)}" if names else ""

    def reveal_all(self, focus_first: bool = True) -> int:
        """Show every problem now (used when a submit is attempted)."""
        first: Optional[_Field] = None
        for f in self._fields:
            f.touched = True
            self._evaluate(f)
            if first is None and f.state == "invalid":
                first = f
        self._refresh_banner()
        self.changed.emit()
        if focus_first and first is not None:
            self._focus(first)
        return sum(1 for f in self._fields if f.state == "invalid")

    def show_error(self, widget: QWidget, message: str) -> bool:
        """Attach an error to a field from outside the normal rules (e.g. the
        duplicate-chassis check done against the database at submit time)."""
        for f in self._fields:
            if f.widget is widget:
                f.external = message
                f.touched = True
                self._evaluate(f)
                self._refresh_banner()
                self.changed.emit()
                return True
        return False

    def focus_first_invalid(self) -> None:
        for f in self._fields:
            if f.state == "invalid":
                self._focus(f)
                return

    def reset(self) -> None:
        """Back to a pristine form (after Reset / a successful submit)."""
        for f in self._fields:
            f.touched = False
            f.external = None
            self._evaluate(f)
        self._refresh_banner()
        self.changed.emit()
