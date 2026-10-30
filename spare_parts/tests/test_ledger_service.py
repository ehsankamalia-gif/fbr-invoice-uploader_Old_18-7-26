"""Unit tests for spare_parts.services.ledger_service: the merged,
running-balance statement of account for a customer or supplier."""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from spare_parts.db.base import SpareBase
from spare_parts.db import models  # noqa: F401
from spare_parts.services import (
    customers_service,
    ledger_service,
    parts_service,
    payments_service,
    purchase_service,
    returns_service,
    sales_service,
    stock_service,
    suppliers_service,
)


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
    p = parts_service.create_part(db_session, part_no="LG-1", name="Spark Plug")
    stock_service.add_ledger_entry(db_session, part_id=p.id, qty_in=200, reference_type="OPENING")
    db_session.commit()
    return p


def test_customer_ledger_opening_balance_row_first(db_session):
    customer = customers_service.create_customer(db_session, name="X", type="RETAIL", opening_balance=500)
    rows = ledger_service.get_customer_ledger(db_session, customer.id)
    assert rows[0]["type"] == "Opening Balance"
    assert rows[0]["balance"] == Decimal("500")


def test_customer_ledger_sale_payment_return_sequence(db_session, part):
    customer = customers_service.create_customer(db_session, name="Garage A", type="WHOLESALE")
    sale = sales_service.create_sale(
        db_session, sale_type="WHOLESALE", customer_id=customer.id,
        items=[dict(part_id=part.id, qty_entered=10, unit_price=100)], paid=200,
    )
    # sale: debit 1000, credit 200 (paid at sale time) -> running balance 800
    payments_service.create_payment(db_session, direction="IN", party_id=customer.id, amount=300)
    # payment: credit 300 -> running balance 500
    returns_service.create_sale_return(
        db_session, sale_id=sale.id, items=[dict(sale_item_id=sale.items[0].id, qty=2)]
    )
    # return: credit 200 (2 * 100) -> running balance 300

    rows = ledger_service.get_customer_ledger(db_session, customer.id)
    types = [r["type"] for r in rows]
    assert types == ["Opening Balance", "Sale", "Payment Received", "Sale Return"]
    assert rows[1]["balance"] == Decimal("800")
    assert rows[2]["balance"] == Decimal("500")
    assert rows[3]["balance"] == Decimal("300")

    # Matches the authoritative outstanding-balance calc.
    assert customers_service.get_customer_outstanding(db_session, customer.id) == Decimal("300")


def test_supplier_ledger_purchase_payment_return_sequence(db_session, part):
    supplier = suppliers_service.create_supplier(db_session, name="Supplier A")
    purchase = purchase_service.create_purchase(
        db_session, supplier_id=supplier.id,
        items=[dict(part_id=part.id, qty=20, unit_cost=50)], paid=100,
    )
    # purchase: debit 1000, credit 100 -> running balance 900
    payments_service.create_payment(db_session, direction="OUT", party_id=supplier.id, amount=400)
    # payment: credit 400 -> running balance 500
    returns_service.create_purchase_return(
        db_session, purchase_id=purchase.id, items=[dict(purchase_item_id=purchase.items[0].id, qty=3)]
    )
    # return: credit 150 (3 * 50) -> running balance 350

    rows = ledger_service.get_supplier_ledger(db_session, supplier.id)
    types = [r["type"] for r in rows]
    assert types == ["Opening Balance", "Purchase", "Payment Made", "Purchase Return"]
    assert rows[-1]["balance"] == Decimal("350")
    assert suppliers_service.get_supplier_outstanding(db_session, supplier.id) == Decimal("350")


def test_ledger_excludes_other_parties_transactions(db_session, part):
    customer_a = customers_service.create_customer(db_session, name="A", type="RETAIL")
    customer_b = customers_service.create_customer(db_session, name="B", type="RETAIL")
    sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=customer_a.id,
        items=[dict(part_id=part.id, qty_entered=1, unit_price=100)],
    )
    sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=customer_b.id,
        items=[dict(part_id=part.id, qty_entered=1, unit_price=100)],
    )
    rows_a = ledger_service.get_customer_ledger(db_session, customer_a.id)
    sale_rows = [r for r in rows_a if r["type"] == "Sale"]
    assert len(sale_rows) == 1


def test_ledger_excludes_cancelled_payments(db_session):
    customer = customers_service.create_customer(db_session, name="C", type="RETAIL")
    payment = payments_service.create_payment(db_session, direction="IN", party_id=customer.id, amount=100)
    payments_service.cancel_payment(db_session, payment.id)
    rows = ledger_service.get_customer_ledger(db_session, customer.id)
    assert all(r["type"] != "Payment Received" for r in rows)
