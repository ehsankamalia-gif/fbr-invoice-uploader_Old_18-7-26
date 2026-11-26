"""The professional drop-down list for combo boxes (Advance Booking: Motorcycle Model / Color)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication, QComboBox

from app.qt_ui import combo_style


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    from app.qt_ui.theme import apply_theme

    apply_theme(app)
    return app


def _combo(qapp, items=("", "CD70", "CG125", "PRIDOR"), icon="fa5s.motorcycle"):
    combo = QComboBox()
    combo_style.style_combo(combo, icon, "Select model")
    for item in items:
        combo.addItem(item)
    return combo


def test_popup_uses_the_custom_delegate_and_it_survives_gc(qapp):
    import gc

    combo = _combo(qapp)
    gc.collect()
    assert isinstance(combo.view().itemDelegate(), combo_style.ComboItemDelegate)
    assert combo.view().itemDelegate() is combo._item_delegate
    assert "border-radius" in combo.view().styleSheet()
    combo.deleteLater()


def test_the_popup_really_paints_without_error(qapp):
    """PyQt aborts the whole program if a delegate's paint() raises, so draw it for real."""
    combo = _combo(qapp)
    combo.setCurrentText("CG125")
    combo.show()
    combo.showPopup()
    qapp.processEvents()
    pix = combo.view().grab()
    assert not pix.isNull() and pix.width() > 50
    combo.hidePopup()
    combo.deleteLater()


def test_items_selection_and_signals_are_untouched(qapp):
    combo = _combo(qapp)
    seen = []
    combo.currentTextChanged.connect(seen.append)
    assert [combo.itemText(i) for i in range(combo.count())] == ["", "CD70", "CG125", "PRIDOR"]
    combo.setCurrentIndex(2)
    assert combo.currentText() == "CG125" and seen == ["CG125"]
    combo.deleteLater()


def test_a_blank_item_is_shown_as_the_placeholder_not_as_an_empty_row(qapp):
    combo = _combo(qapp)
    delegate = combo._item_delegate
    assert delegate._placeholder == "Select model"
    assert combo.itemText(0) == ""                 # data unchanged - only the drawing differs
    combo.deleteLater()


def test_rows_are_comfortably_tall_and_the_list_opens_below_the_field(qapp):
    from PyQt6.QtWidgets import QStyleOptionViewItem

    combo = _combo(qapp)
    hint = combo._item_delegate.sizeHint(QStyleOptionViewItem(), combo.model().index(1, 0))
    assert hint.height() >= 38
    assert "combobox-popup: 0" in combo.styleSheet()
    assert combo.maxVisibleItems() == 8
    combo.deleteLater()


def test_works_without_an_icon(qapp):
    combo = _combo(qapp, icon=None)
    combo.showPopup()
    qapp.processEvents()
    assert not combo.view().grab().isNull()
    combo.hidePopup()
    combo.deleteLater()
