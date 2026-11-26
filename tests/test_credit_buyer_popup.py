"""Credit Sale / Payments / Ledger: the Buyer Name drop-down (avatar, name, Dealer/Customer badge, phone, CNIC)."""
import gc
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import QApplication, QStyleOptionViewItem
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.qt_ui import completer_style
from app.qt_ui.completer_style import BuyerSuggestionDelegate, SuggestionDelegate

ROWS = [
    "MUHAMMAD AKRAM | Customer | 03001234567 | 33302-9056747-5",
    "AKRAM MOTORS LAHORE | Dealer | 03217654321 | 35202-1112223-4",
    "ABDUL AKRAM KHAN SON OF HAQ NAWAZ KAMALIA TOBA TEK SINGH AND SONS | Customer | 03331112223 | 33302-1234567-8",
    "AKRAM | Customer |  | ",                      # no phone / no CNIC recorded
    "not a buyer row at all",
    "A | B",
]


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    from app.qt_ui.theme import apply_theme

    apply_theme(app)
    return app


def _setup(qapp):
    from app.qt_ui.credit_ledger_system_page import BuyerCompleter, SharedLineEdit

    edit = SharedLineEdit()
    comp = BuyerCompleter(edit)
    edit.setCompleter(comp)
    completer_style.style_completer(comp, None, BuyerSuggestionDelegate)
    model = QStandardItemModel(comp)
    for text in ROWS:
        item = QStandardItem(text)
        item.setData(text.split(" | ")[0], Qt.ItemDataRole.UserRole)       # metadata the page relies on
        item.setData(7, Qt.ItemDataRole.UserRole + 1)
        model.appendRow(item)
    comp.setModel(model)
    edit.show()
    return edit, comp


def test_the_buyer_delegate_is_installed_and_survives_gc(qapp):
    edit, comp = _setup(qapp)
    gc.collect()
    delegate = comp.popup().itemDelegate()
    assert isinstance(delegate, BuyerSuggestionDelegate) and isinstance(delegate, SuggestionDelegate)
    assert delegate is comp._suggestion_delegate
    edit.deleteLater()


def test_every_kind_of_row_paints_without_error(qapp):
    """PyQt aborts the program if paint() raises: customer, dealer, very long name, empty phone/CNIC,
    non-buyer rows, hovered and not."""
    edit, comp = _setup(qapp)
    edit.setText("AKRAM")
    comp.setCompletionPrefix("")
    comp.complete()
    qapp.processEvents()
    popup = comp.popup()
    popup.setCurrentIndex(comp.completionModel().index(1, 0))
    qapp.processEvents()
    pix = popup.grab()
    assert not pix.isNull() and pix.width() >= 500 and pix.height() > 150
    popup.hide()
    edit.deleteLater()


def test_buyer_rows_are_taller_and_other_rows_keep_the_normal_height(qapp):
    edit, comp = _setup(qapp)
    delegate = comp.popup().itemDelegate()
    option = QStyleOptionViewItem()
    assert delegate.sizeHint(option, comp.model().index(0, 0)).height() == completer_style.BUYER_ROW_HEIGHT
    assert delegate.sizeHint(option, comp.model().index(4, 0)).height() == completer_style.ROW_HEIGHT
    edit.deleteLater()


def test_row_text_and_selection_metadata_are_untouched(qapp):
    edit, comp = _setup(qapp)
    index = comp.model().index(1, 0)
    assert index.data() == "AKRAM MOTORS LAHORE | Dealer | 03217654321 | 35202-1112223-4"
    assert index.data(Qt.ItemDataRole.UserRole) == "AKRAM MOTORS LAHORE"
    assert index.data(Qt.ItemDataRole.UserRole + 1) == 7
    edit.deleteLater()


def test_the_highlight_survives_arrow_navigation_blanking_the_search_box(qapp):
    """Qt blanks the field when a row is highlighted (pathFromIndex returns ''), but the typed
    text must still be highlighted in the rows."""
    edit, comp = _setup(qapp)
    delegate = comp.popup().itemDelegate()
    edit.setText("AKRAM")
    assert delegate._query() == "AKRAM"
    edit.clear()
    comp.setCompletionPrefix("")
    assert delegate._query() == "AKRAM"          # remembered
    edit.deleteLater()


def test_the_chassis_and_default_lists_are_unchanged(qapp):
    from PyQt6.QtWidgets import QCompleter, QLineEdit

    edit = QLineEdit()
    comp = QCompleter(["HB1"], edit)
    edit.setCompleter(comp)
    completer_style.style_completer(comp, "fa5s.motorcycle")
    assert type(comp.popup().itemDelegate()) is SuggestionDelegate
    edit.deleteLater()


def test_all_three_buyer_boxes_on_the_credit_page_use_it(qapp):
    import app.db.session as dbs
    from app.db.models import Base

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    original = dbs.SessionLocal.kw.get("bind")
    dbs.SessionLocal.configure(bind=engine)
    try:
        from app.qt_ui.credit_ledger_system_page import CreditLedgerSystemPage

        page = CreditLedgerSystemPage()
        for completer in (page.sale_buyer_completer, page.pay_buyer_completer, page.ledger_buyer_completer):
            popup = completer.popup()
            assert isinstance(popup.itemDelegate(), BuyerSuggestionDelegate)
            assert "border-radius" in popup.styleSheet()
        page.hide()
        page.deleteLater()
    finally:
        dbs.SessionLocal.configure(bind=original)


def test_the_icons_the_buyer_rows_use_are_committed():
    from app.qt_ui import icons

    for name in ("fa5s.user", "fa5s.building"):
        assert icons.icon_file(name) is not None, name
