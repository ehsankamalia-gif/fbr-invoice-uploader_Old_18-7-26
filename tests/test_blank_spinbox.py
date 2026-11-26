"""Money spin box that shows only "Rs. " until a number is typed (New Ledger Transaction amount)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDoubleSpinBox, QLineEdit

from app.qt_ui.blank_spinbox import BlankZeroDoubleSpinBox


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _spin(qapp):
    s = BlankZeroDoubleSpinBox()
    s.setRange(0, 99999999)
    s.setDecimals(2)
    s.setPrefix("Rs. ")
    other = QLineEdit()
    s.show()
    other.show()
    s.setFocus()
    qapp.processEvents()
    return s, other


def test_starts_blank_after_the_prefix_with_value_zero(qapp):
    s, other = _spin(qapp)
    assert s.lineEdit().text() == "Rs. " and s.value() == 0.0
    assert "0.00" not in s.lineEdit().text()
    s.deleteLater(); other.deleteLater()


def test_typing_a_number_gives_that_value(qapp):
    s, other = _spin(qapp)
    s.selectAll()
    QTest.keyClicks(s, "2500")
    assert s.value() == 2500.0 and s.lineEdit().text() == "Rs. 2500"
    other.setFocus(); qapp.processEvents()
    assert s.lineEdit().text() == "Rs. 2,500.00" or s.lineEdit().text().startswith("Rs. 2")
    assert s.value() == 2500.0
    s.deleteLater(); other.deleteLater()


def test_decimals_can_be_typed(qapp):
    s, other = _spin(qapp)
    QTest.keyClicks(s, "75.5")
    other.setFocus(); qapp.processEvents()
    assert s.value() == 75.5
    s.deleteLater(); other.deleteLater()


def test_deleting_the_digits_really_resets_the_value_to_zero(qapp):
    """The dangerous case: a blank-looking box must never keep (and save) a stale amount."""
    s, other = _spin(qapp)
    s.selectAll()
    QTest.keyClicks(s, "2500")
    for _ in range(4):
        QTest.keyClick(s, Qt.Key.Key_Backspace)
    assert s.value() == 0.0
    other.setFocus(); qapp.processEvents()
    assert s.value() == 0.0 and s.lineEdit().text() == "Rs. "
    s.deleteLater(); other.deleteLater()


def test_set_value_zero_blanks_it_and_other_values_show_normally(qapp):
    s, other = _spin(qapp)
    s.setValue(12.5)
    assert s.lineEdit().text() == "Rs. 12.50"
    s.setValue(0)
    assert s.lineEdit().text() == "Rs. "
    s.deleteLater(); other.deleteLater()


def test_arrows_range_and_decimals_still_work_like_a_normal_spin_box(qapp):
    s, other = _spin(qapp)
    QTest.keyClick(s, Qt.Key.Key_Up)
    assert s.value() == 1.0
    s.setValue(5)
    QTest.keyClick(s, Qt.Key.Key_Down)
    QTest.keyClick(s, Qt.Key.Key_Down)
    QTest.keyClick(s, Qt.Key.Key_Down)
    QTest.keyClick(s, Qt.Key.Key_Down)
    QTest.keyClick(s, Qt.Key.Key_Down)
    QTest.keyClick(s, Qt.Key.Key_Down)
    assert s.value() == 0.0                       # clamped at the minimum, never negative
    assert s.decimals() == 2 and s.maximum() == 99999999
    assert isinstance(s, QDoubleSpinBox)
    s.deleteLater(); other.deleteLater()
