"""Credit Sale table: the chassis drop-down shows chassis | model | colour as a clean 3-part row."""
import gc
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import QApplication, QLineEdit, QStyleOptionViewItem
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.qt_ui import completer_style
from app.qt_ui.completer_style import ColumnSuggestionDelegate, SuggestionDelegate

ROWS = ["HB479029 | CD70 | BLK", "HB479030 | CD70 | RED", "HB484087 | CG125S GOLD | SILVER",
        "BH597159 | A very long model name that must be cut before it reaches the colour tag | BLUE",
        "NO-SEPARATOR-ROW", "HB000001 | ONLY-TWO"]


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    from app.qt_ui.theme import apply_theme

    apply_theme(app)
    return app


def _setup(qapp):
    from app.qt_ui.credit_ledger_system_page import ChassisCompleter, SharedLineEdit

    edit = SharedLineEdit()
    comp = ChassisCompleter(edit)
    edit.setCompleter(comp)
    completer_style.style_completer(comp, "fa5s.motorcycle", ColumnSuggestionDelegate)
    model = QStandardItemModel(comp)
    for text in ROWS:
        item = QStandardItem(text)
        item.setData(text.split(" | ")[0], Qt.ItemDataRole.UserRole)       # metadata the page relies on
        model.appendRow(item)
    comp.setModel(model)
    edit.show()
    return edit, comp


def test_the_column_delegate_is_installed_and_survives_gc(qapp):
    edit, comp = _setup(qapp)
    gc.collect()
    delegate = comp.popup().itemDelegate()
    assert isinstance(delegate, ColumnSuggestionDelegate) and isinstance(delegate, SuggestionDelegate)
    assert delegate is comp._suggestion_delegate
    edit.deleteLater()


def test_every_kind_of_row_paints_without_error(qapp):
    """PyQt aborts the program if a delegate's paint() raises - draw 3-part, 2-part, plain, long,
    hovered and not."""
    edit, comp = _setup(qapp)
    edit.setText("HB")
    comp.setCompletionPrefix("")
    comp.complete()
    qapp.processEvents()
    popup = comp.popup()
    popup.setCurrentIndex(comp.completionModel().index(1, 0))
    qapp.processEvents()
    pix = popup.grab()
    assert not pix.isNull() and pix.width() >= 400 and pix.height() > 100
    popup.hide()
    edit.deleteLater()


def test_the_default_style_completer_call_is_unchanged(qapp):
    """Other screens call style_completer(completer, icon) with no delegate class."""
    edit = QLineEdit()
    from PyQt6.QtWidgets import QCompleter

    comp = QCompleter(["HB1", "HB2"], edit)
    edit.setCompleter(comp)
    completer_style.style_completer(comp, "fa5s.motorcycle")
    assert type(comp.popup().itemDelegate()) is SuggestionDelegate
    edit.deleteLater()


def test_row_text_and_selection_metadata_are_untouched(qapp):
    edit, comp = _setup(qapp)
    index = comp.model().index(0, 0)
    assert index.data() == "HB479029 | CD70 | BLK"
    assert index.data(Qt.ItemDataRole.UserRole) == "HB479029"       # what _on_chassis_selected reads
    edit.deleteLater()


def test_rows_are_comfortably_tall(qapp):
    edit, comp = _setup(qapp)
    hint = comp.popup().itemDelegate().sizeHint(QStyleOptionViewItem(), comp.model().index(0, 0))
    assert hint.height() >= completer_style.ROW_HEIGHT
    edit.deleteLater()


def test_the_credit_sale_page_chassis_cell_uses_it(qapp):
    """The real Credit Sale page: a new row's chassis cell gets the styled column popup."""
    import app.db.session as dbs
    from app.db.models import Base

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    original = dbs.SessionLocal.kw.get("bind")
    dbs.SessionLocal.configure(bind=engine)
    try:
        from app.qt_ui.credit_ledger_system_page import CreditLedgerSystemPage

        page = CreditLedgerSystemPage()
        page._add_sale_item_row()
        chassis = page.sale_items_table.cellWidget(page.sale_items_table.rowCount() - 1, 0)
        popup = chassis.completer().popup()
        assert isinstance(popup.itemDelegate(), ColumnSuggestionDelegate)
        assert "border-radius" in popup.styleSheet()
        page.hide()
        page.deleteLater()
    finally:
        dbs.SessionLocal.configure(bind=original)
