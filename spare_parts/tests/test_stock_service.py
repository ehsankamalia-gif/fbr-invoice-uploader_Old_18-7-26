"""Unit tests for spare_parts.services.stock_service - the core
stock-ledger primitive every other service (purchases now, sales/returns/
adjustments later) builds on.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from spare_parts.db.base import SpareBase
from spare_parts.db import models  # noqa: F401
from spare_parts.errors import SparePartsValidationError
from spare_parts.services import parts_service, stock_service
from spare_parts.services.settings_service import update_settings
from spare_parts.services.stock_service import StockError


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SpareBase.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def part(db_session):
    return parts_service.create_part(db_session, part_no="HD-1", name="Brake Pad")


def test_current_stock_starts_at_zero(db_session, part):
    assert stock_service.get_current_stock(db_session, part.id) == 0


def test_add_ledger_entry_in_and_out_tracks_balance(db_session, part):
    e1 = stock_service.add_ledger_entry(
        db_session, part_id=part.id, qty_in=10, reference_type="PURCHASE", reference_id=1
    )
    assert e1.balance == 10
    db_session.commit()

    e2 = stock_service.add_ledger_entry(
        db_session, part_id=part.id, qty_out=4, reference_type="SALE", reference_id=1
    )
    assert e2.balance == 6
    db_session.commit()

    assert stock_service.get_current_stock(db_session, part.id) == 6


def test_multiple_entries_in_same_uncommitted_transaction_see_each_other(db_session, part):
    """A single purchase with two lines of the same part must see the
    first line's effect before computing the second line's balance,
    without needing an intermediate commit."""
    stock_service.add_ledger_entry(
        db_session, part_id=part.id, qty_in=5, reference_type="PURCHASE", reference_id=1
    )
    e2 = stock_service.add_ledger_entry(
        db_session, part_id=part.id, qty_in=3, reference_type="PURCHASE", reference_id=1
    )
    assert e2.balance == 8


def test_negative_stock_blocked_by_default(db_session, part):
    with pytest.raises(StockError):
        stock_service.add_ledger_entry(
            db_session, part_id=part.id, qty_out=1, reference_type="SALE", reference_id=1
        )


def test_negative_stock_allowed_when_setting_enabled(db_session, part):
    update_settings(db_session, allow_negative_stock=True)
    entry = stock_service.add_ledger_entry(
        db_session, part_id=part.id, qty_out=1, reference_type="SALE", reference_id=1
    )
    assert entry.balance == -1


def test_add_ledger_entry_requires_nonzero_movement(db_session, part):
    with pytest.raises(ValueError):
        stock_service.add_ledger_entry(db_session, part_id=part.id, reference_type="ADJUSTMENT")


def test_get_current_stock_bulk(db_session):
    p1 = parts_service.create_part(db_session, part_no="HD-1", name="Brake Pad")
    p2 = parts_service.create_part(db_session, part_no="HD-2", name="Clutch Plate")
    stock_service.add_ledger_entry(db_session, part_id=p1.id, qty_in=10, reference_type="PURCHASE")
    stock_service.add_ledger_entry(db_session, part_id=p2.id, qty_in=4, reference_type="PURCHASE")
    db_session.commit()

    balances = stock_service.get_current_stock_bulk(db_session, [p1.id, p2.id])
    assert balances[p1.id] == 10
    assert balances[p2.id] == 4


def test_get_current_stock_bulk_includes_zero_for_untouched_parts(db_session):
    p1 = parts_service.create_part(db_session, part_no="HD-1", name="Brake Pad")
    balances = stock_service.get_current_stock_bulk(db_session, [p1.id])
    assert balances[p1.id] == 0


def test_get_ledger_entries_returns_full_history_oldest_first(db_session, part):
    stock_service.add_ledger_entry(db_session, part_id=part.id, qty_in=10, reference_type="OPENING")
    db_session.commit()
    stock_service.add_ledger_entry(db_session, part_id=part.id, qty_out=3, reference_type="SALE", reference_id=1)
    db_session.commit()
    stock_service.add_ledger_entry(db_session, part_id=part.id, qty_in=5, reference_type="PURCHASE", reference_id=2)
    db_session.commit()

    entries = stock_service.get_ledger_entries(db_session, part.id)
    assert [e.reference_type for e in entries] == ["OPENING", "SALE", "PURCHASE"]
    assert [e.balance for e in entries] == [10, 7, 12]


def test_get_ledger_entries_empty_for_untouched_part(db_session, part):
    assert stock_service.get_ledger_entries(db_session, part.id) == []


def test_get_ledger_entries_only_includes_the_requested_part(db_session):
    p1 = parts_service.create_part(db_session, part_no="HD-1", name="Brake Pad")
    p2 = parts_service.create_part(db_session, part_no="HD-2", name="Clutch Plate")
    stock_service.add_ledger_entry(db_session, part_id=p1.id, qty_in=10, reference_type="OPENING")
    stock_service.add_ledger_entry(db_session, part_id=p2.id, qty_in=4, reference_type="OPENING")
    db_session.commit()

    entries = stock_service.get_ledger_entries(db_session, p1.id)
    assert len(entries) == 1
    assert entries[0].part_id == p1.id


# --- create_adjustment ---------------------------------------------------

def test_create_adjustment_in_increases_stock(db_session, part):
    entry = stock_service.create_adjustment(
        db_session, part_id=part.id, direction="IN", qty=15, reason="Opening stock count",
    )
    assert entry.reference_type == "ADJUSTMENT"
    assert entry.qty_in == 15
    assert entry.note == "Opening stock count"
    assert stock_service.get_current_stock(db_session, part.id) == 15


def test_create_adjustment_out_decreases_stock(db_session, part):
    stock_service.create_adjustment(db_session, part_id=part.id, direction="IN", qty=20, reason="Initial")
    entry = stock_service.create_adjustment(
        db_session, part_id=part.id, direction="OUT", qty=5, reason="Damaged in storage",
    )
    assert entry.qty_out == 5
    assert stock_service.get_current_stock(db_session, part.id) == 15


def test_create_adjustment_out_blocked_when_it_would_go_negative(db_session, part):
    with pytest.raises(StockError):
        stock_service.create_adjustment(db_session, part_id=part.id, direction="OUT", qty=5, reason="Count correction")
    assert stock_service.get_current_stock(db_session, part.id) == 0


def test_create_adjustment_requires_a_reason(db_session, part):
    with pytest.raises(SparePartsValidationError):
        stock_service.create_adjustment(db_session, part_id=part.id, direction="IN", qty=5, reason="")
    with pytest.raises(SparePartsValidationError):
        stock_service.create_adjustment(db_session, part_id=part.id, direction="IN", qty=5, reason="   ")


def test_create_adjustment_requires_positive_qty(db_session, part):
    with pytest.raises(SparePartsValidationError):
        stock_service.create_adjustment(db_session, part_id=part.id, direction="IN", qty=0, reason="x")


def test_create_adjustment_rejects_invalid_direction(db_session, part):
    with pytest.raises(SparePartsValidationError):
        stock_service.create_adjustment(db_session, part_id=part.id, direction="SIDEWAYS", qty=5, reason="x")


def test_create_adjustment_shows_up_in_ledger_history(db_session, part):
    stock_service.create_adjustment(db_session, part_id=part.id, direction="IN", qty=8, reason="Initial count")
    entries = stock_service.get_ledger_entries(db_session, part.id)
    assert len(entries) == 1
    assert entries[0].reference_type == "ADJUSTMENT"
    assert entries[0].note == "Initial count"
