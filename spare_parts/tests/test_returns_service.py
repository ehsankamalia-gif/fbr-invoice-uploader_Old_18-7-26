"""Unit tests for spare_parts.services.returns_service: sale returns
(stock back in) and purchase returns (stock back out), including partial
returns and the over-return guard.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from spare_parts.db.base import SpareBase
from spare_parts.db import models  # noqa: F401
from spare_parts.errors import SparePartsValidationError
from spare_parts.services import (
    customers_service,
    parts_service,
    purchase_service,
    returns_service,
    sales_service,
    stock_service,
    suppliers_service,
)
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


@pytest.fixture()
def supplier(db_session):
    return suppliers_service.create_supplier(db_session, name="ACME Spares")


@pytest.fixture()
def customer(db_session):
    return customers_service.create_customer(db_session, name="Walk-in", type="RETAIL")


# --- sale returns ------------------------------------------------------

def test_sale_return_full_flow(db_session, part, customer):
    stock_service.add_ledger_entry(db_session, part_id=part.id, qty_in=50, reference_type="OPENING")
    db_session.commit()

    sale = sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=customer.id,
        items=[dict(part_id=part.id, qty_entered=10, unit_price=50)],
    )
    assert stock_service.get_current_stock(db_session, part.id) == 40

    sale_item_id = sale.items[0].id
    sale_return = returns_service.create_sale_return(
        db_session, sale_id=sale.id,
        items=[dict(sale_item_id=sale_item_id, qty=4)],
    )
    assert sale_return.return_no == "SR-0001"
    assert sale_return.total == Decimal("200")  # 4 * 50
    assert stock_service.get_current_stock(db_session, part.id) == 44


def test_sale_return_cannot_exceed_sold_qty(db_session, part, customer):
    stock_service.add_ledger_entry(db_session, part_id=part.id, qty_in=50, reference_type="OPENING")
    db_session.commit()
    sale = sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=customer.id,
        items=[dict(part_id=part.id, qty_entered=5, unit_price=50)],
    )
    with pytest.raises(SparePartsValidationError):
        returns_service.create_sale_return(
            db_session, sale_id=sale.id,
            items=[dict(sale_item_id=sale.items[0].id, qty=6)],
        )


def test_sale_return_cannot_exceed_remaining_after_partial_return(db_session, part, customer):
    stock_service.add_ledger_entry(db_session, part_id=part.id, qty_in=50, reference_type="OPENING")
    db_session.commit()
    sale = sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=customer.id,
        items=[dict(part_id=part.id, qty_entered=10, unit_price=50)],
    )
    sale_item_id = sale.items[0].id
    returns_service.create_sale_return(db_session, sale_id=sale.id, items=[dict(sale_item_id=sale_item_id, qty=6)])
    # Only 4 left returnable.
    with pytest.raises(SparePartsValidationError):
        returns_service.create_sale_return(db_session, sale_id=sale.id, items=[dict(sale_item_id=sale_item_id, qty=5)])
    # Exactly 4 should succeed.
    returns_service.create_sale_return(db_session, sale_id=sale.id, items=[dict(sale_item_id=sale_item_id, qty=4)])


def test_sale_return_requires_posted_sale(db_session, part, customer):
    stock_service.add_ledger_entry(db_session, part_id=part.id, qty_in=50, reference_type="OPENING")
    db_session.commit()
    sale = sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=customer.id,
        items=[dict(part_id=part.id, qty_entered=5, unit_price=50)],
    )
    sales_service.cancel_sale(db_session, sale.id)
    with pytest.raises(SparePartsValidationError):
        returns_service.create_sale_return(
            db_session, sale_id=sale.id, items=[dict(sale_item_id=sale.items[0].id, qty=1)]
        )


# --- purchase returns --------------------------------------------------

def test_purchase_return_decreases_stock(db_session, part, supplier):
    purchase = purchase_service.create_purchase(
        db_session, supplier_id=supplier.id,
        items=[dict(part_id=part.id, qty=20, unit_cost=100)],
    )
    assert stock_service.get_current_stock(db_session, part.id) == 20

    purchase_item_id = purchase.items[0].id
    purchase_return = returns_service.create_purchase_return(
        db_session, purchase_id=purchase.id,
        items=[dict(purchase_item_id=purchase_item_id, qty=5)],
    )
    assert purchase_return.return_no == "PR-0001"
    assert purchase_return.total == Decimal("500")  # 5 * 100
    assert stock_service.get_current_stock(db_session, part.id) == 15


def test_purchase_return_cannot_exceed_purchased_qty(db_session, part, supplier):
    purchase = purchase_service.create_purchase(
        db_session, supplier_id=supplier.id,
        items=[dict(part_id=part.id, qty=5, unit_cost=100)],
    )
    with pytest.raises(SparePartsValidationError):
        returns_service.create_purchase_return(
            db_session, purchase_id=purchase.id,
            items=[dict(purchase_item_id=purchase.items[0].id, qty=6)],
        )


def test_purchase_return_blocked_when_insufficient_stock_left(db_session, part, supplier, customer):
    purchase = purchase_service.create_purchase(
        db_session, supplier_id=supplier.id,
        items=[dict(part_id=part.id, qty=10, unit_cost=100)],
    )
    # Most of it already sold.
    sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=customer.id,
        items=[dict(part_id=part.id, qty_entered=8, unit_price=150)],
    )
    assert stock_service.get_current_stock(db_session, part.id) == 2

    with pytest.raises(StockError):
        returns_service.create_purchase_return(
            db_session, purchase_id=purchase.id,
            items=[dict(purchase_item_id=purchase.items[0].id, qty=5)],
        )
    # Nothing changed.
    assert stock_service.get_current_stock(db_session, part.id) == 2


def test_purchase_return_requires_posted_purchase(db_session, part, supplier):
    purchase = purchase_service.create_purchase(
        db_session, supplier_id=supplier.id,
        items=[dict(part_id=part.id, qty=5, unit_cost=100)],
    )
    purchase_service.cancel_purchase(db_session, purchase.id)
    with pytest.raises(SparePartsValidationError):
        returns_service.create_purchase_return(
            db_session, purchase_id=purchase.id,
            items=[dict(purchase_item_id=purchase.items[0].id, qty=1)],
        )
