"""Unit tests for spare_parts.services.quotations_service."""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from spare_parts.db.base import SpareBase
from spare_parts.db import models  # noqa: F401
from spare_parts.errors import SparePartsValidationError
from spare_parts.services import customers_service, parts_service, quotations_service, stock_service


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
        db_session, part_no="QT-1", name="Quoted Part",
        pack_size=10, retail_price=100, wholesale_price=80, cost_price=50,
    )
    stock_service.add_ledger_entry(db_session, part_id=p.id, qty_in=100, reference_type="OPENING")
    db_session.commit()
    return p


@pytest.fixture()
def customer(db_session):
    return customers_service.create_customer(db_session, name="Quote Customer", type="RETAIL")


def test_create_quotation_computes_totals(db_session, part, customer):
    quote = quotations_service.create_quotation(
        db_session, sale_type="RETAIL", customer_id=customer.id,
        items=[dict(part_id=part.id, qty_entered=2, unit_price=100)],
        tax_percent=10,
    )
    assert quote.status == "DRAFT"
    assert quote.subtotal == Decimal("200")
    assert quote.tax_amount == Decimal("20.00")
    assert quote.total == Decimal("220.00")
    assert quote.quote_no.startswith("QT-")


def test_create_quotation_never_touches_stock(db_session, part, customer):
    before = stock_service.get_current_stock(db_session, part.id)
    quotations_service.create_quotation(
        db_session, sale_type="RETAIL", customer_id=customer.id,
        items=[dict(part_id=part.id, qty_entered=5, unit_price=100)],
    )
    after = stock_service.get_current_stock(db_session, part.id)
    assert before == after  # quotations are never a stock movement


def test_create_quotation_allows_walk_in(db_session, part):
    quote = quotations_service.create_quotation(
        db_session, sale_type="RETAIL", customer_id=None,
        walk_in_customer_name="Someone At The Counter",
        items=[dict(part_id=part.id, qty_entered=1, unit_price=100)],
    )
    assert quote.customer_id is None
    assert quote.walk_in_customer_name == "Someone At The Counter"


def test_update_quotation_only_while_draft(db_session, part, customer):
    quote = quotations_service.create_quotation(
        db_session, sale_type="RETAIL", customer_id=customer.id,
        items=[dict(part_id=part.id, qty_entered=1, unit_price=100)],
    )
    updated = quotations_service.update_quotation(
        db_session, quote.id, items=[dict(part_id=part.id, qty_entered=3, unit_price=100)],
    )
    assert updated.subtotal == Decimal("300")

    quotations_service.cancel_quotation(db_session, quote.id)
    with pytest.raises(SparePartsValidationError):
        quotations_service.update_quotation(
            db_session, quote.id, items=[dict(part_id=part.id, qty_entered=1, unit_price=100)],
        )


def test_cancel_quotation_only_while_draft(db_session, part, customer):
    quote = quotations_service.create_quotation(
        db_session, sale_type="RETAIL", customer_id=customer.id,
        items=[dict(part_id=part.id, qty_entered=1, unit_price=100)],
    )
    cancelled = quotations_service.cancel_quotation(db_session, quote.id)
    assert cancelled.status == "CANCELLED"
    with pytest.raises(SparePartsValidationError):
        quotations_service.cancel_quotation(db_session, quote.id)


def test_convert_to_sale_honors_quoted_price_even_if_part_price_changed(db_session, part, customer):
    quote = quotations_service.create_quotation(
        db_session, sale_type="RETAIL", customer_id=customer.id,
        items=[dict(part_id=part.id, qty_entered=2, unit_price=100)],
    )
    # Part's retail price goes up after quoting - the sale must still
    # honor the ORIGINALLY QUOTED price, not the new current price.
    parts_service.update_part(db_session, part.id, retail_price=150)

    sale = quotations_service.convert_to_sale(db_session, quote.id)
    assert sale.items[0].unit_price == Decimal("100")
    assert sale.subtotal == Decimal("200")

    db_session.refresh(quote)
    assert quote.status == "CONVERTED"
    assert quote.converted_sale_id == sale.id


def test_convert_to_sale_decrements_stock(db_session, part, customer):
    quote = quotations_service.create_quotation(
        db_session, sale_type="RETAIL", customer_id=customer.id,
        items=[dict(part_id=part.id, qty_entered=10, unit_price=100)],
    )
    before = stock_service.get_current_stock(db_session, part.id)
    quotations_service.convert_to_sale(db_session, quote.id)
    after = stock_service.get_current_stock(db_session, part.id)
    assert before - after == 10


def test_convert_to_sale_threads_walk_in_customer_name(db_session, part):
    quote = quotations_service.create_quotation(
        db_session, sale_type="RETAIL", customer_id=None,
        walk_in_customer_name="Walk-In Buyer",
        items=[dict(part_id=part.id, qty_entered=1, unit_price=100)],
    )
    sale = quotations_service.convert_to_sale(db_session, quote.id)
    assert sale.walk_in_customer_name == "Walk-In Buyer"


def test_convert_to_sale_preserves_pack_quantities(db_session, part, customer):
    quote = quotations_service.create_quotation(
        db_session, sale_type="RETAIL", customer_id=customer.id,
        items=[dict(part_id=part.id, qty_entered=2, sold_as="PACK", unit_price=10)],
    )
    sale = quotations_service.convert_to_sale(db_session, quote.id)
    # pack_size=10, 2 packs entered -> 20 base units.
    assert sale.items[0].qty == 20
    assert sale.items[0].sold_as == "PACK"


def test_convert_to_sale_only_works_once(db_session, part, customer):
    quote = quotations_service.create_quotation(
        db_session, sale_type="RETAIL", customer_id=customer.id,
        items=[dict(part_id=part.id, qty_entered=1, unit_price=100)],
    )
    quotations_service.convert_to_sale(db_session, quote.id)
    with pytest.raises(SparePartsValidationError):
        quotations_service.convert_to_sale(db_session, quote.id)


def test_convert_to_sale_respects_negative_stock_guard(db_session, customer):
    part = parts_service.create_part(db_session, part_no="QT-LOW", name="Low Stock Part", retail_price=100)
    stock_service.add_ledger_entry(db_session, part_id=part.id, qty_in=2, reference_type="OPENING")
    db_session.commit()

    quote = quotations_service.create_quotation(
        db_session, sale_type="RETAIL", customer_id=customer.id,
        items=[dict(part_id=part.id, qty_entered=5, unit_price=100)],
    )
    with pytest.raises(SparePartsValidationError):
        quotations_service.convert_to_sale(db_session, quote.id)
    db_session.refresh(quote)
    assert quote.status == "DRAFT"  # failed conversion leaves the quote untouched