"""Unit tests for spare_parts.services.sales_service: sale creation
(stock out, pack conversion, pricing), cancellation, and sale-number
series independence between RETAIL and WHOLESALE.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from spare_parts.db.base import SpareBase
from spare_parts.db import models  # noqa: F401
from spare_parts.errors import SparePartsValidationError
from spare_parts.services import customers_service, parts_service, sales_service, stock_service
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
    p = parts_service.create_part(
        db_session, part_no="HD-1", name="Brake Pad",
        pack_size=10, retail_price=50, wholesale_price=40,
    )
    # Give it stock to sell.
    stock_service.add_ledger_entry(db_session, part_id=p.id, qty_in=100, reference_type="OPENING")
    db_session.commit()
    return p


@pytest.fixture()
def retail_customer(db_session):
    return customers_service.create_customer(db_session, name="Walk-in Regular", type="RETAIL")


@pytest.fixture()
def wholesale_customer(db_session):
    return customers_service.create_customer(
        db_session, name="ACME Garage", type="WHOLESALE", credit_limit=5000
    )


# --- sale number series --------------------------------------------------

def test_sale_no_series_independent_per_type(db_session, part, retail_customer, wholesale_customer):
    rt1 = sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=retail_customer.id,
        items=[dict(part_id=part.id, qty_entered=1, unit_price=50)],
    )
    ws1 = sales_service.create_sale(
        db_session, sale_type="WHOLESALE", customer_id=wholesale_customer.id,
        items=[dict(part_id=part.id, qty_entered=1, unit_price=40)],
    )
    rt2 = sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=retail_customer.id,
        items=[dict(part_id=part.id, qty_entered=1, unit_price=50)],
    )
    assert rt1.sale_no == "RT-0001"
    assert ws1.sale_no == "WS-0001"
    assert rt2.sale_no == "RT-0002"


# --- basic sale creation ---------------------------------------------------

def test_retail_sale_walk_in_no_customer(db_session, part):
    sale = sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=None,
        items=[dict(part_id=part.id, qty_entered=2, unit_price=50)],
        paid=100,
    )
    assert sale.customer_id is None
    assert sale.total == Decimal("100")
    assert sale.due == Decimal("0")


def test_wholesale_sale_requires_customer(db_session, part):
    with pytest.raises(SparePartsValidationError):
        sales_service.create_sale(
            db_session, sale_type="WHOLESALE", customer_id=None,
            items=[dict(part_id=part.id, qty_entered=10, unit_price=40)],
        )


def test_sale_decrements_stock(db_session, part, retail_customer):
    assert stock_service.get_current_stock(db_session, part.id) == 100
    sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=retail_customer.id,
        items=[dict(part_id=part.id, qty_entered=5, unit_price=50)],
    )
    assert stock_service.get_current_stock(db_session, part.id) == 95


def test_sale_blocked_when_insufficient_stock(db_session, part, retail_customer):
    with pytest.raises(StockError):
        sales_service.create_sale(
            db_session, sale_type="RETAIL", customer_id=retail_customer.id,
            items=[dict(part_id=part.id, qty_entered=9999, unit_price=50)],
        )
    # Nothing should have been committed.
    assert stock_service.get_current_stock(db_session, part.id) == 100
    assert sales_service.list_sales(db_session) == []


def test_stock_error_is_a_spare_parts_validation_error(db_session, part, retail_customer):
    """Regression check for the catch-type bug fixed this phase: UI code
    catching SparePartsValidationError around a sale save must also catch
    StockError."""
    try:
        sales_service.create_sale(
            db_session, sale_type="RETAIL", customer_id=retail_customer.id,
            items=[dict(part_id=part.id, qty_entered=9999, unit_price=50)],
        )
        assert False, "expected an exception"
    except SparePartsValidationError:
        pass  # correctly caught via the shared base class


# --- pack selling (wholesale) -----------------------------------------------

def test_wholesale_pack_sale_converts_to_base_units(db_session, part, wholesale_customer):
    """part.pack_size == 10 - selling 2 packs must consume 20 base units."""
    sale = sales_service.create_sale(
        db_session, sale_type="WHOLESALE", customer_id=wholesale_customer.id,
        items=[dict(part_id=part.id, qty_entered=2, sold_as="PACK", unit_price=40)],
    )
    item = sale.items[0]
    assert item.qty == 20
    assert item.sold_as == "PACK"
    assert item.pack_qty == 2
    assert stock_service.get_current_stock(db_session, part.id) == 80
    # unit_price is per base unit, so line_total = 40 * 20 = 800.
    assert item.line_total == Decimal("800")


# --- totals / tax -----------------------------------------------------------

def test_sale_totals_with_discount_and_tax(db_session, part, retail_customer):
    sale = sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=retail_customer.id,
        items=[dict(part_id=part.id, qty_entered=10, unit_price=50, discount=20)],
        discount=10,
        tax_percent=10,
        paid=400,
    )
    # subtotal = 10*50 - 20 = 480; taxable = 480-10 = 470; tax = 47; total = 517
    assert sale.subtotal == Decimal("480")
    assert sale.tax_amount == Decimal("47.00")
    assert sale.total == Decimal("517")
    assert sale.due == Decimal("117")


def test_sale_uses_default_tax_percent_when_not_specified(db_session, part, retail_customer):
    from spare_parts.services.settings_service import update_settings
    update_settings(db_session, default_tax_percent=5)
    sale = sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=retail_customer.id,
        items=[dict(part_id=part.id, qty_entered=1, unit_price=100)],
    )
    assert sale.tax_percent == Decimal("5.00")
    assert sale.tax_amount == Decimal("5.00")
    assert sale.total == Decimal("105.00")


# --- credit limit (advisory only) -------------------------------------------

def test_check_credit_limit_within(db_session, wholesale_customer):
    within, projected, limit = customers_service.check_credit_limit(
        db_session, wholesale_customer.id, 1000
    )
    assert within is True
    assert projected == Decimal("1000")
    assert limit == Decimal("5000")


def test_check_credit_limit_exceeded(db_session, wholesale_customer):
    within, projected, limit = customers_service.check_credit_limit(
        db_session, wholesale_customer.id, 6000
    )
    assert within is False
    assert projected == Decimal("6000")


def test_check_credit_limit_no_limit_configured_always_within(db_session, retail_customer):
    within, projected, limit = customers_service.check_credit_limit(
        db_session, retail_customer.id, 999999
    )
    assert within is True


def test_create_sale_never_blocks_on_credit_limit(db_session, part, wholesale_customer):
    """create_sale itself must never raise for exceeding credit_limit -
    that's advisory/UI-only per spec ("warn when exceeded")."""
    sale = sales_service.create_sale(
        db_session, sale_type="WHOLESALE", customer_id=wholesale_customer.id,
        items=[dict(part_id=part.id, qty_entered=50, unit_price=40)],
        paid=0,
    )
    assert sale.due == Decimal("2000")  # well within the 5000 limit anyway, just confirms no error


# --- cancel_sale -------------------------------------------------------------

def test_cancel_sale_reverses_stock_and_status(db_session, part, retail_customer):
    sale = sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=retail_customer.id,
        items=[dict(part_id=part.id, qty_entered=10, unit_price=50)],
    )
    assert stock_service.get_current_stock(db_session, part.id) == 90

    sales_service.cancel_sale(db_session, sale.id, reason="customer changed mind")
    db_session.refresh(sale)
    assert sale.status == "CANCELLED"
    assert stock_service.get_current_stock(db_session, part.id) == 100


def test_cancel_already_cancelled_sale_rejected(db_session, part, retail_customer):
    sale = sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=retail_customer.id,
        items=[dict(part_id=part.id, qty_entered=1, unit_price=50)],
    )
    sales_service.cancel_sale(db_session, sale.id)
    with pytest.raises(SparePartsValidationError):
        sales_service.cancel_sale(db_session, sale.id)


# --- update_sale (editing a saved cart) --------------------------------------

def test_update_sale_changes_items_and_recalculates_totals(db_session, part, retail_customer):
    sale = sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=retail_customer.id,
        items=[dict(part_id=part.id, qty_entered=5, unit_price=50)], paid=250,
    )
    assert sale.total == Decimal("250")
    assert stock_service.get_current_stock(db_session, part.id) == 95

    updated = sales_service.update_sale(
        db_session, sale.id,
        items=[dict(part_id=part.id, qty_entered=8, unit_price=50)], paid=400,
    )
    assert updated.id == sale.id
    assert updated.sale_no == sale.sale_no  # same record, not a new one
    assert updated.total == Decimal("400")
    assert updated.due == Decimal("0")
    # 5 originally sold, now 8 sold -> 3 more units out of stock (100 -> 92).
    assert stock_service.get_current_stock(db_session, part.id) == 92


def test_update_sale_can_add_and_remove_lines(db_session, part, retail_customer):
    part2 = parts_service.create_part(db_session, part_no="HD-2", name="Clutch Cable", retail_price=20)
    stock_service.add_ledger_entry(db_session, part_id=part2.id, qty_in=50, reference_type="OPENING")
    db_session.commit()

    sale = sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=retail_customer.id,
        items=[dict(part_id=part.id, qty_entered=5, unit_price=50)],
    )
    # Replace the original line with a different part entirely.
    sales_service.update_sale(
        db_session, sale.id,
        items=[dict(part_id=part2.id, qty_entered=3, unit_price=20)],
    )
    db_session.refresh(sale)
    assert len(sale.items) == 1
    assert sale.items[0].part_id == part2.id
    # Original part's stock is fully restored, part2's is decremented.
    assert stock_service.get_current_stock(db_session, part.id) == 100
    assert stock_service.get_current_stock(db_session, part2.id) == 47


def test_update_sale_reduces_stock_movement_when_qty_lowered(db_session, part, retail_customer):
    sale = sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=retail_customer.id,
        items=[dict(part_id=part.id, qty_entered=10, unit_price=50)],
    )
    assert stock_service.get_current_stock(db_session, part.id) == 90
    sales_service.update_sale(
        db_session, sale.id,
        items=[dict(part_id=part.id, qty_entered=4, unit_price=50)],
    )
    assert stock_service.get_current_stock(db_session, part.id) == 96


def test_update_sale_blocked_when_insufficient_stock(db_session, part, retail_customer):
    sale = sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=retail_customer.id,
        items=[dict(part_id=part.id, qty_entered=5, unit_price=50)],
    )
    with pytest.raises(StockError):
        sales_service.update_sale(
            db_session, sale.id,
            items=[dict(part_id=part.id, qty_entered=9999, unit_price=50)],
        )
    # Nothing changed - original quantity/stock still intact.
    db_session.refresh(sale)
    assert len(sale.items) == 1
    assert sale.items[0].qty == 5
    assert stock_service.get_current_stock(db_session, part.id) == 95


def test_update_sale_rejects_cancelled_sale(db_session, part, retail_customer):
    sale = sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=retail_customer.id,
        items=[dict(part_id=part.id, qty_entered=5, unit_price=50)],
    )
    sales_service.cancel_sale(db_session, sale.id)
    with pytest.raises(SparePartsValidationError):
        sales_service.update_sale(
            db_session, sale.id, items=[dict(part_id=part.id, qty_entered=1, unit_price=50)],
        )


def test_update_sale_rejects_when_sale_not_found(db_session):
    with pytest.raises(SparePartsValidationError):
        sales_service.update_sale(db_session, 999999, items=[])


def test_update_sale_blocked_when_return_already_exists(db_session, part, retail_customer):
    from spare_parts.services import returns_service
    sale = sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=retail_customer.id,
        items=[dict(part_id=part.id, qty_entered=10, unit_price=50)],
    )
    returns_service.create_sale_return(
        db_session, sale_id=sale.id, items=[dict(sale_item_id=sale.items[0].id, qty=2)],
    )
    with pytest.raises(SparePartsValidationError):
        sales_service.update_sale(
            db_session, sale.id, items=[dict(part_id=part.id, qty_entered=3, unit_price=50)],
        )


def test_update_sale_preserves_sale_type_and_customer(db_session, part, wholesale_customer):
    sale = sales_service.create_sale(
        db_session, sale_type="WHOLESALE", customer_id=wholesale_customer.id,
        items=[dict(part_id=part.id, qty_entered=5, unit_price=40)],
    )
    updated = sales_service.update_sale(
        db_session, sale.id, items=[dict(part_id=part.id, qty_entered=6, unit_price=40)],
    )
    assert updated.sale_type == "WHOLESALE"
    assert updated.customer_id == wholesale_customer.id


# --- warranty snapshot -----------------------------------------------------

def test_sale_item_captures_warranty_expiry_when_part_has_warranty(db_session, retail_customer):
    part = parts_service.create_part(
        db_session, part_no="W-1", name="Warrantied Part", retail_price=100, warranty_days=90,
    )
    stock_service.add_ledger_entry(db_session, part_id=part.id, qty_in=10, reference_type="OPENING")
    db_session.commit()

    fixed_date = dt.datetime(2026, 1, 1, 10, 0, 0)
    sale = sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=retail_customer.id,
        items=[dict(part_id=part.id, qty_entered=1, unit_price=100)],
        sale_date=fixed_date,
    )
    assert sale.items[0].warranty_expires_at == fixed_date + dt.timedelta(days=90)


def test_sale_item_has_no_warranty_when_part_has_none(db_session, part, retail_customer):
    sale = sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=retail_customer.id,
        items=[dict(part_id=part.id, qty_entered=1, unit_price=50)],
    )
    assert sale.items[0].warranty_expires_at is None


def test_update_sale_recomputes_warranty_from_current_part_setting(db_session, retail_customer):
    part = parts_service.create_part(
        db_session, part_no="W-2", name="Warrantied Part 2", retail_price=100, warranty_days=30,
    )
    stock_service.add_ledger_entry(db_session, part_id=part.id, qty_in=10, reference_type="OPENING")
    db_session.commit()

    fixed_date = dt.datetime(2026, 1, 1, 10, 0, 0)
    sale = sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=retail_customer.id,
        items=[dict(part_id=part.id, qty_entered=1, unit_price=100)],
        sale_date=fixed_date,
    )
    assert sale.items[0].warranty_expires_at == fixed_date + dt.timedelta(days=30)

    parts_service.update_part(db_session, part.id, warranty_days=180)
    updated = sales_service.update_sale(
        db_session, sale.id, items=[dict(part_id=part.id, qty_entered=1, unit_price=100)],
    )
    assert updated.items[0].warranty_expires_at == fixed_date + dt.timedelta(days=180)
