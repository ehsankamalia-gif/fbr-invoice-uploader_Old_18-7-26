"""Unit tests for spare_parts.services.held_sales_service: the POS
multi-card screen's Hold/Resume drafts. No test here should ever touch
the stock ledger - holding/updating/deleting a draft must have zero
stock effect (that only happens when a card is finalized into a real
sale via sales_service.create_sale).
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from spare_parts.db.base import SpareBase
from spare_parts.db import models  # noqa: F401
from spare_parts.errors import SparePartsValidationError
from spare_parts.services import customers_service, held_sales_service, parts_service, stock_service


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
    p = parts_service.create_part(db_session, part_no="HD-1", name="Brake Pad", retail_price=50)
    stock_service.add_ledger_entry(db_session, part_id=p.id, qty_in=100, reference_type="OPENING")
    db_session.commit()
    return p


@pytest.fixture()
def customer(db_session):
    return customers_service.create_customer(db_session, name="Walk-in Regular", type="RETAIL")


def test_create_held_sale_has_no_stock_effect(db_session, part, customer):
    held_sales_service.create_held_sale(
        db_session, sale_type="RETAIL", customer_id=customer.id,
        items=[dict(part_id=part.id, qty=5, unit_price=50)],
    )
    assert stock_service.get_current_stock(db_session, part.id) == 100


def test_create_held_sale_generates_hold_no_series(db_session, part):
    h1 = held_sales_service.create_held_sale(
        db_session, sale_type="RETAIL", items=[dict(part_id=part.id, qty=1, unit_price=50)],
    )
    h2 = held_sales_service.create_held_sale(
        db_session, sale_type="RETAIL", items=[dict(part_id=part.id, qty=1, unit_price=50)],
    )
    assert h1.hold_no == "HOLD-0001"
    assert h2.hold_no == "HOLD-0002"


def test_create_held_sale_requires_items(db_session):
    with pytest.raises(SparePartsValidationError):
        held_sales_service.create_held_sale(db_session, sale_type="RETAIL", items=[])


def test_create_held_sale_stores_reference_and_label(db_session, part):
    held = held_sales_service.create_held_sale(
        db_session, sale_type="RETAIL", reference="John - 0300-1234567", card_label="Card 2",
        items=[dict(part_id=part.id, qty=2, unit_price=50)],
    )
    assert held.reference == "John - 0300-1234567"
    assert held.card_label == "Card 2"


def test_list_and_get_held_sale(db_session, part):
    held = held_sales_service.create_held_sale(
        db_session, sale_type="RETAIL", items=[dict(part_id=part.id, qty=1, unit_price=50)],
    )
    all_held = held_sales_service.list_held_sales(db_session)
    assert len(all_held) == 1
    assert held_sales_service.get_held_sale(db_session, held.id).id == held.id
    assert held_sales_service.get_held_sale(db_session, 999999) is None


def test_delete_held_sale_removes_it_and_its_items(db_session, part):
    held = held_sales_service.create_held_sale(
        db_session, sale_type="RETAIL", items=[dict(part_id=part.id, qty=1, unit_price=50)],
    )
    held_sales_service.delete_held_sale(db_session, held.id)
    assert held_sales_service.get_held_sale(db_session, held.id) is None
    assert stock_service.get_current_stock(db_session, part.id) == 100  # still untouched


def test_delete_held_sale_is_a_no_op_when_missing(db_session):
    held_sales_service.delete_held_sale(db_session, 999999)  # must not raise


def test_update_held_sale_replaces_items_and_recomputes(db_session, part):
    held = held_sales_service.create_held_sale(
        db_session, sale_type="RETAIL", items=[dict(part_id=part.id, qty=2, unit_price=50)],
    )
    part2 = parts_service.create_part(db_session, part_no="HD-2", name="Clutch Cable", retail_price=20)
    updated = held_sales_service.update_held_sale(
        db_session, held.id, items=[dict(part_id=part2.id, qty=3, unit_price=20)],
    )
    assert len(updated.items) == 1
    assert updated.items[0].part_id == part2.id
    assert updated.hold_no == held.hold_no  # same draft record, not a new one


def test_update_held_sale_can_change_customer_to_walk_in(db_session, part, customer):
    held = held_sales_service.create_held_sale(
        db_session, sale_type="RETAIL", customer_id=customer.id,
        items=[dict(part_id=part.id, qty=1, unit_price=50)],
    )
    updated = held_sales_service.update_held_sale(db_session, held.id, customer_id=None)
    assert updated.customer_id is None


def test_update_held_sale_missing_raises(db_session):
    with pytest.raises(SparePartsValidationError):
        held_sales_service.update_held_sale(db_session, 999999, items=[])


def test_held_sale_total_matches_items_discount_and_tax(db_session, part):
    held = held_sales_service.create_held_sale(
        db_session, sale_type="RETAIL",
        items=[dict(part_id=part.id, qty=10, unit_price=50, discount=20)],
        discount=10, tax_percent=10,
    )
    # subtotal = 10*50 - 20 = 480; taxable = 480-10 = 470; tax = 47; total = 517
    total = held_sales_service.held_sale_total(held)
    assert total == Decimal("517.00")


def test_get_reserved_qty_for_part_sums_across_drafts(db_session, part):
    held_sales_service.create_held_sale(
        db_session, sale_type="RETAIL", items=[dict(part_id=part.id, qty=5, unit_price=50)],
    )
    held_sales_service.create_held_sale(
        db_session, sale_type="RETAIL", items=[dict(part_id=part.id, qty=7, unit_price=50)],
    )
    assert held_sales_service.get_reserved_qty_for_part(db_session, part.id) == 12


def test_get_reserved_qty_for_part_excludes_given_held_sale(db_session, part):
    h1 = held_sales_service.create_held_sale(
        db_session, sale_type="RETAIL", items=[dict(part_id=part.id, qty=5, unit_price=50)],
    )
    held_sales_service.create_held_sale(
        db_session, sale_type="RETAIL", items=[dict(part_id=part.id, qty=7, unit_price=50)],
    )
    reserved = held_sales_service.get_reserved_qty_for_part(
        db_session, part.id, exclude_held_sale_id=h1.id
    )
    assert reserved == 7


def test_get_reserved_qty_for_part_zero_when_no_drafts(db_session, part):
    assert held_sales_service.get_reserved_qty_for_part(db_session, part.id) == 0


# --- per-line price_type (preserved through Hold/Resume) --------------------

def test_create_held_sale_stores_price_type_per_line(db_session, part):
    part2 = parts_service.create_part(db_session, part_no="HD-3", name="Oil Filter", retail_price=30)
    held = held_sales_service.create_held_sale(
        db_session, sale_type="WHOLESALE",
        items=[
            dict(part_id=part.id, qty=5, unit_price=50, price_type="WHOLESALE"),
            dict(part_id=part2.id, qty=2, unit_price=30, price_type="RETAIL"),
        ],
    )
    types_by_part = {i.part_id: i.price_type for i in held.items}
    assert types_by_part[part.id] == "WHOLESALE"
    assert types_by_part[part2.id] == "RETAIL"


def test_create_held_sale_defaults_price_type_to_retail(db_session, part):
    held = held_sales_service.create_held_sale(
        db_session, sale_type="RETAIL", items=[dict(part_id=part.id, qty=1, unit_price=50)],
    )
    assert held.items[0].price_type == "RETAIL"


def test_update_held_sale_preserves_per_line_price_type(db_session, part):
    part2 = parts_service.create_part(db_session, part_no="HD-4", name="Spark Plug", retail_price=15)
    held = held_sales_service.create_held_sale(
        db_session, sale_type="RETAIL", items=[dict(part_id=part.id, qty=1, unit_price=50)],
    )
    updated = held_sales_service.update_held_sale(
        db_session, held.id,
        items=[
            dict(part_id=part.id, qty=3, unit_price=40, price_type="WHOLESALE"),
            dict(part_id=part2.id, qty=1, unit_price=15, price_type="RETAIL"),
        ],
    )
    types_by_part = {i.part_id: i.price_type for i in updated.items}
    assert types_by_part[part.id] == "WHOLESALE"
    assert types_by_part[part2.id] == "RETAIL"


def test_held_sale_overall_type_mixed(db_session, part):
    part2 = parts_service.create_part(db_session, part_no="HD-5", name="Chain Lube", retail_price=10)
    held = held_sales_service.create_held_sale(
        db_session, sale_type="RETAIL",
        items=[
            dict(part_id=part.id, qty=5, unit_price=50, price_type="WHOLESALE"),
            dict(part_id=part2.id, qty=2, unit_price=10, price_type="RETAIL"),
        ],
    )
    overall, is_mixed = held_sales_service.held_sale_overall_type(held)
    assert overall == "WHOLESALE"
    assert is_mixed is True


def test_held_sale_overall_type_uniform(db_session, part):
    held = held_sales_service.create_held_sale(
        db_session, sale_type="RETAIL",
        items=[dict(part_id=part.id, qty=5, unit_price=50, price_type="RETAIL")],
    )
    overall, is_mixed = held_sales_service.held_sale_overall_type(held)
    assert overall == "RETAIL"
    assert is_mixed is False


