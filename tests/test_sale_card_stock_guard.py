"""Sales Counter: a quantity above the available stock is flagged, warned about, and blocks the sale."""
import inspect
import os
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication, QMessageBox
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from spare_parts.db import models  # noqa: F401
from spare_parts.db.base import SpareBase
from spare_parts.services import parts_service, settings_service, stock_service
from spare_parts.ui import sale_card_widget as scw
from spare_parts.ui.sale_card_widget import SaleCardWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    from app.qt_ui.theme import apply_theme

    apply_theme(app)
    return app


@pytest.fixture()
def env(qapp, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SpareBase.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(scw, "get_spare_session", lambda: Session())

    db = Session()
    parts = {}
    for key, part_no, name, stock in (("few", "HD-1", "Brake Pad", 4), ("many", "F-2", "Oil Filter", 100),
                                      ("none", "Z-9", "Spark Plug", 0)):
        p = parts_service.create_part(db, part_no=part_no, name=name, retail_price=100)
        if stock:
            stock_service.add_ledger_entry(db, part_id=p.id, qty_in=stock, reference_type="OPENING")
        parts[key] = p
    db.commit()
    db.close()

    popups = []

    def fake_warning(parent, title, text, *a, **k):
        popups.append((title, text))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "warning", staticmethod(fake_warning))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok))

    card = SaleCardWidget(reserved_qty_fn=lambda part_id, held_id: 0)
    card.show()
    qapp.processEvents()
    yield types.SimpleNamespace(card=card, parts=parts, popups=popups, Session=Session)
    card.hide()
    card.deleteLater()
    qapp.processEvents()


def _qty(card, row=0):
    return card.items_table.cellWidget(row, scw._COL_QTY)


def test_a_quantity_within_stock_is_fine(env):
    env.card._add_line_item(env.parts["few"])
    _qty(env.card).setValue(4)
    assert not _qty(env.card).property("overStock")
    assert env.card._stock_problems() == []
    assert env.popups == []


def test_a_quantity_above_stock_turns_the_box_red_with_a_tooltip(env):
    env.card._add_line_item(env.parts["few"])
    _qty(env.card).setValue(10)
    assert _qty(env.card).property("overStock") is True
    assert "4" in _qty(env.card).toolTip() and "in stock" in _qty(env.card).toolTip()
    _qty(env.card).setValue(3)
    assert not _qty(env.card).property("overStock") and _qty(env.card).toolTip() == ""


def test_finishing_the_quantity_shows_the_warning_with_the_numbers(env):
    env.card._add_line_item(env.parts["few"])
    env.popups.clear()
    _qty(env.card).setValue(10)
    _qty(env.card).editingFinished.emit()
    title, text = env.popups[-1]
    assert title == "Quantity Exceeds Stock"
    assert "you entered 10" in text and "only 4 in stock" in text and "Brake Pad" in text
    assert "cannot be completed" in text


def test_the_warning_is_not_repeated_for_every_keystroke(env):
    env.card._add_line_item(env.parts["few"])
    env.popups.clear()
    for value in (1, 12, 120, 1200):               # typing "1200" digit by digit
        _qty(env.card).setValue(value)
    assert env.popups == []                         # only the red box until the cashier finishes


def test_complete_sale_is_blocked_while_a_quantity_is_over_stock(env, monkeypatch):
    calls = []
    monkeypatch.setattr(scw.sales_service, "create_sale", lambda *a, **k: calls.append(1))
    env.card._add_line_item(env.parts["few"])
    _qty(env.card).setValue(10)
    env.popups.clear()
    assert env.card.complete_sale() is None
    assert calls == []                              # nothing was saved, no stock moved
    title, text = env.popups[-1]
    assert title == "Cannot Complete Sale" and "only 4 in stock" in text
    assert "Cannot complete the sale" in env.card.error_label.text()
    assert env.card._saving is False                # the card is usable again straight away


def test_complete_sale_goes_through_once_the_quantity_is_fixed(env, monkeypatch):
    calls = []
    fake_sale = types.SimpleNamespace(id=1, sale_no="S-1", sale_type="RETAIL")
    monkeypatch.setattr(scw.sales_service, "create_sale", lambda *a, **k: calls.append(1) or fake_sale)
    env.card._add_line_item(env.parts["few"])
    _qty(env.card).setValue(10)
    assert env.card.complete_sale() is None
    _qty(env.card).setValue(4)
    assert env.card.complete_sale() is fake_sale and calls == [1]


def test_an_out_of_stock_part_says_so(env):
    env.card._add_line_item(env.parts["none"])
    problems = env.card._stock_problems()
    assert len(problems) == 1 and problems[0]["in_stock"] == 0
    assert "out of stock" in env.card._over_stock_text(problems[0])
    assert any(t == "Quantity Exceeds Stock" and "out of stock" in m for t, m in env.popups)   # warned on add


def test_adding_the_same_part_again_warns_when_it_passes_the_stock(env):
    env.card._add_line_item(env.parts["few"])
    _qty(env.card).setValue(4)
    env.popups.clear()
    env.card._add_line_item(env.parts["few"])       # bumps the existing line to 5
    assert _qty(env.card).value() == 5
    assert env.popups and env.popups[-1][0] == "Quantity Exceeds Stock"


def test_all_lines_of_one_part_count_together(env):
    card, part = env.card, env.parts["few"]
    card._add_line_item(part)
    sell_as = card.items_table.cellWidget(0, scw._COL_SELL_AS)
    sell_as.setProperty("pack_size", 2)
    sell_as.setCurrentIndex(sell_as.findData("PACK"))         # line 1: 1 pack = 2 pieces
    _qty(card, 0).setValue(1)
    card._add_line_item(part)                                  # line 2: a separate PIECE line
    assert card.items_table.rowCount() == 2
    _qty(card, 1).setValue(1)                                  # 2 + 1 = 3 <= 4 -> fine
    assert card._stock_problems() == []
    _qty(card, 1).setValue(3)                                  # 2 + 3 = 5 > 4 -> both lines flagged
    problems = card._stock_problems()
    assert len(problems) == 1 and problems[0]["requested"] == 5
    assert _qty(card, 0).property("overStock") is True and _qty(card, 1).property("overStock") is True


def test_packs_are_counted_in_base_units(env):
    env.card._add_line_item(env.parts["few"])
    sell_as = env.card.items_table.cellWidget(0, scw._COL_SELL_AS)
    sell_as.setProperty("pack_size", 5)
    sell_as.setCurrentIndex(sell_as.findData("PACK"))
    _qty(env.card).setValue(1)                      # 1 pack = 5 pieces > 4 in stock
    problems = env.card._stock_problems()
    assert problems and problems[0]["requested"] == 5 and problems[0]["in_stock"] == 4
    assert _qty(env.card).property("overStock") is True


def test_other_parts_are_not_flagged_by_one_bad_line(env):
    env.card._add_line_item(env.parts["few"])
    env.card._add_line_item(env.parts["many"])
    _qty(env.card, 0).setValue(10)
    _qty(env.card, 1).setValue(10)
    assert _qty(env.card, 0).property("overStock") is True
    assert not _qty(env.card, 1).property("overStock")


def test_allow_negative_stock_setting_switches_the_guard_off(env, monkeypatch):
    db = env.Session()
    settings_service.update_settings(db, allow_negative_stock=True)
    db.commit()
    db.close()
    calls = []
    fake_sale = types.SimpleNamespace(id=1, sale_no="S-1", sale_type="RETAIL")
    monkeypatch.setattr(scw.sales_service, "create_sale", lambda *a, **k: calls.append(1) or fake_sale)
    env.card._add_line_item(env.parts["few"])
    _qty(env.card).setValue(10)
    assert env.card._stock_problems() == [] and not _qty(env.card).property("overStock")
    assert env.card.complete_sale() is fake_sale and calls == [1]


def test_holding_a_sale_is_not_blocked_by_the_stock_guard():
    """Hold saves a draft with no stock effect, so it must not use the guard."""
    assert "_stock_problems" not in inspect.getsource(SaleCardWidget.hold_sale)
