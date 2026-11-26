"""A money spin box that shows NOTHING after its prefix while the value is 0.

A plain QDoubleSpinBox always shows a number, so an untouched amount field reads "Rs. 0.00" and
the cashier has to delete it first. This one reads just "Rs. " until a number is typed.

The value is still a normal float: empty text means exactly 0.0 (also when digits are deleted
again and the field is left), so a blank-looking box can never save a stale amount. Typing,
arrow keys, the mouse wheel, ranges, decimals and signals all behave as in QDoubleSpinBox.
"""
from __future__ import annotations

from PyQt6.QtGui import QValidator
from PyQt6.QtWidgets import QDoubleSpinBox


class BlankZeroDoubleSpinBox(QDoubleSpinBox):
    def _is_blank(self, text: str) -> bool:
        stripped = (text or "")
        prefix, suffix = self.prefix(), self.suffix()
        if prefix and stripped.startswith(prefix):
            stripped = stripped[len(prefix):]
        if suffix and stripped.endswith(suffix):
            stripped = stripped[: len(stripped) - len(suffix)]
        return not stripped.strip()

    def textFromValue(self, value: float) -> str:  # noqa: N802
        if value == 0:
            return ""
        return super().textFromValue(value)

    def valueFromText(self, text: str) -> float:  # noqa: N802
        if self._is_blank(text):
            return 0.0
        return super().valueFromText(text)

    def validate(self, text: str, pos: int):
        if self._is_blank(text):
            return QValidator.State.Acceptable, text, pos
        return super().validate(text, pos)
