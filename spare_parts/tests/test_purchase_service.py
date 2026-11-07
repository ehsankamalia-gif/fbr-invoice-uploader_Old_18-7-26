"""Unit tests for spare_parts.services.purchase_service - purchase
creation (stock + moving-average cost), cancellation (stock reversal),
and purchase-number generation.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from spare_parts.db.base import SpareBase
from spare_parts.db import models  # noqa: F401
from spare_parts.errors import SparePartsValidationError
from spare_parts.services import parts_service, purchase_service, stock_service, suppliers_service


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
def supplier(db_session):
    return suppliers_service.create_supplier(db_session, name="ACME Spares")


@pytest.fixture()
def part(db_session):
    return parts_service.create_part(db_session, part_no="HD-1", name="Brake Pad")


# --- purchase number generation ------------------------------------------

def test_generate_purchase_no_sequence(db_session, supplier, part):
    p1 = purchase_service.create_purchase(
        db_session, supplier_id=supplier.id,
        items=[dict(part_id=part.id, qty=1, unit_cost=10)],
    )
    p2 = purchase_service.create_purchase(
        db_session, supplier_id=supplier.id,
        items=[dict(part_id=part.id, qty=1, unit_cost=10)],
    )
    assert p1.purchase_no == "PO-0001"
    assert p2.purchase_no == "PO-0002"


# --- create_purchase: stock + totals --------------------------------------

def test_create_purchase_updates_stock_ledger(db_session, supplier, part):
    purchase_service.create_purchase(
        db_session, supplier_id=supplier.id,
        items=[dict(part_id=part.id, qty=20, unit_cost=100)],
    )
    assert stock_service.get_current_stock(db_session, part.id) == 20


def test_create_purchase_computes_totals(db_session, supplier, part):
    purchase = purchase_service.create_purchase(
        db_session, supplier_id=supplier.id,
        items=[
            dict(part_id=part.id, qty=10, unit_cost=100, discount=50),
        ],
        discount=20,
        paid=500,
    )
    # subtotal = 10*100 - 50 = 950; total = 950 - 20 = 930; due = 930-500
    assert purchase.subtotal == Decimal("950")
    assert purchase.total == Decimal("930")
    assert purchase.due == Decimal("430")


def test_create_purchase_rejects_empty_items(db_session, supplier):
    with pytest.raises(SparePartsValidationError):
        purchase_service.create_purchase(db_session, supplier_id=supplier.id, items=[])


def test_create_purchase_rejects_invalid_supplier(db_session, part):
    with pytest.raises(SparePartsValidationError):
        purchase_service.create_purchase(
            db_session, supplier_id=999, items=[dict(part_id=part.id, qty=1, unit_cost=10)]
        )


def test_create_purchase_rejects_zero_qty(db_session, supplier, part):
    with pytest.raises(SparePartsValidationError):
        purchase_service.create_purchase(
            db_session, supplier_id=supplier.id,
            items=[dict(part_id=part.id, qty=0, unit_cost=10)],
        )


def test_create_purchase_rejects_negative_unit_cost(db_session, supplier, part):
    with pytest.raises(SparePartsValidationError):
        purchase_service.create_purchase(
            db_session, supplier_id=supplier.id,
            items=[dict(part_id=part.id, qty=1, unit_cost=-5)],
        )


def test_create_purchase_rejects_discount_exceeding_line(db_session, supplier, part):
    with pytest.raises(SparePartsValidationError):
        purchase_service.create_purchase(
            db_session, supplier_id=supplier.id,
            items=[dict(part_id=part.id, qty=1, unit_cost=10, discount=50)],
        )


def test_create_purchase_rolls_back_fully_on_error(db_session, supplier, part):
    """A second, invalid line must leave the first line's stock/ledger
    effect fully undone too - header+items+ledger is one transaction."""
    bad_part_id = 999
    with pytest.raises(SparePartsValidationError):
        purchase_service.create_purchase(
            db_session, supplier_id=supplier.id,
            items=[
                dict(part_id=part.id, qty=10, unit_cost=100),
                dict(part_id=bad_part_id, qty=1, unit_cost=10),
            ],
        )
    assert stock_service.get_current_stock(db_session, part.id) == 0
    assert purchase_service.list_purchases(db_session) == []


# --- moving average cost ---------------------------------------------------

def test_moving_average_cost_first_purchase_sets_cost(db_session, supplier, part):
    purchase_service.create_purchase(
        db_session, supplier_id=supplier.id,
        items=[dict(part_id=part.id, qty=10, unit_cost=100)],
    )
    db_session.refresh(part)
    assert part.cost_price == Decimal("100")


def test_moving_average_cost_second_purchase_blends(db_session, supplier, part):
    # 10 units @ 100 = 1000 value
    purchase_service.create_purchase(
        db_session, supplier_id=supplier.id,
        items=[dict(part_id=part.id, qty=10, unit_cost=100)],
    )
    # + 10 units @ 200 = 2000 value -> total 3000 value / 20 units = 150 avg
    purchase_service.create_purchase(
        db_session, supplier_id=supplier.id,
        items=[dict(part_id=part.id, qty=10, unit_cost=200)],
    )
    db_session.refresh(part)
    assert part.cost_price == Decimal("150.00")


# --- cancel_purchase --------------------------------------------------------

def test_cancel_purchase_reverses_stock_and_status(db_session, supplier, part):
    purchase = purchase_service.create_purchase(
        db_session, supplier_id=supplier.id,
        items=[dict(part_id=part.id, qty=10, unit_cost=100)],
    )
    assert stock_service.get_current_stock(db_session, part.id) == 10

    purchase_service.cancel_purchase(db_session, purchase.id, reason="wrong entry")
    db_session.refresh(purchase)
    assert purchase.status == "CANCELLED"
    assert stock_service.get_current_stock(db_session, part.id) == 0


def test_cancel_already_cancelled_purchase_rejected(db_session, supplier, part):
    purchase = purchase_service.create_purchase(
        db_session, supplier_id=supplier.id,
        items=[dict(part_id=part.id, qty=5, unit_cost=50)],
    )
    purchase_service.cancel_purchase(db_session, purchase.id)
    with pytest.raises(SparePartsValidationError):
        purchase_service.cancel_purchase(db_session, purchase.id)


def test_cancel_purchase_blocked_if_would_go_negative(db_session, supplier, part):
    purchase = purchase_service.create_purchase(
        db_session, supplier_id=supplier.id,
        items=[dict(part_id=part.id, qty=10, unit_cost=100)],
    )
    # Simulate something else having consumed most of the stock since
    # (sales don't exist until Phase 3, so this uses the generic ledger
    # primitive directly, exactly as a future sale would).
    stock_service.add_ledger_entry(
        db_session, part_id=part.id, qty_out=8, reference_type="TEST_CONSUME", reference_id=0
    )
    db_session.commit()
    assert stock_service.get_current_stock(db_session, part.id) == 2

    with pytest.raises(SparePartsValidationError):
        purchase_service.cancel_purchase(db_session, purchase.id)

    # Nothing should have changed - still POSTED, stock still 2.
    db_session.refresh(purchase)
    assert purchase.status == "POSTED"
    assert stock_service.get_current_stock(db_session, part.id) == 2
