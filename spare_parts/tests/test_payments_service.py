"""Unit tests for spare_parts.services.payments_service: recording and
cancelling IN (customer receipts) and OUT (supplier disbursements)
payments, and the independent RCV-/PAY- numbering series.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from spare_parts.db.base import SpareBase
from spare_parts.db import models  # noqa: F401
from spare_parts.errors import SparePartsValidationError
from spare_parts.services import customers_service, payments_service, suppliers_service


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
def customer(db_session):
    return customers_service.create_customer(db_session, name="ACME Garage", type="WHOLESALE")


@pytest.fixture()
def supplier(db_session):
    return suppliers_service.create_supplier(db_session, name="Parts Supply Co")


def test_payment_no_series_independent_per_direction(db_session, customer, supplier):
    rcv1 = payments_service.create_payment(db_session, direction="IN", party_id=customer.id, amount=100)
    pay1 = payments_service.create_payment(db_session, direction="OUT", party_id=supplier.id, amount=50)
    rcv2 = payments_service.create_payment(db_session, direction="IN", party_id=customer.id, amount=100)
    assert rcv1.payment_no == "RCV-0001"
    assert pay1.payment_no == "PAY-0001"
    assert rcv2.payment_no == "RCV-0002"


def test_create_payment_in_requires_customer(db_session, supplier):
    with pytest.raises(SparePartsValidationError):
        payments_service.create_payment(db_session, direction="IN", party_id=supplier.id, amount=100)


def test_create_payment_out_requires_supplier(db_session, customer):
    with pytest.raises(SparePartsValidationError):
        payments_service.create_payment(db_session, direction="OUT", party_id=customer.id, amount=100)


def test_create_payment_rejects_zero_or_negative_amount(db_session, customer):
    with pytest.raises(SparePartsValidationError):
        payments_service.create_payment(db_session, direction="IN", party_id=customer.id, amount=0)
    with pytest.raises(SparePartsValidationError):
        payments_service.create_payment(db_session, direction="IN", party_id=customer.id, amount=-10)


def test_create_payment_rejects_invalid_direction(db_session, customer):
    with pytest.raises(SparePartsValidationError):
        payments_service.create_payment(db_session, direction="SIDEWAYS", party_id=customer.id, amount=10)


def test_cancel_payment(db_session, customer):
    payment = payments_service.create_payment(db_session, direction="IN", party_id=customer.id, amount=100)
    payments_service.cancel_payment(db_session, payment.id, reason="data entry mistake")
    db_session.refresh(payment)
    assert payment.status == "CANCELLED"


def test_cancel_already_cancelled_payment_rejected(db_session, customer):
    payment = payments_service.create_payment(db_session, direction="IN", party_id=customer.id, amount=100)
    payments_service.cancel_payment(db_session, payment.id)
    with pytest.raises(SparePartsValidationError):
        payments_service.cancel_payment(db_session, payment.id)


def test_list_payments_filters_by_direction_and_party(db_session, customer, supplier):
    payments_service.create_payment(db_session, direction="IN", party_id=customer.id, amount=100)
    payments_service.create_payment(db_session, direction="OUT", party_id=supplier.id, amount=50)
    assert len(payments_service.list_payments(db_session, direction="IN")) == 1
    assert len(payments_service.list_payments(db_session, direction="OUT")) == 1
    assert len(payments_service.list_payments(db_session, customer_id=customer.id)) == 1


# --- outstanding balance now nets out payments (Phase 4) --------------------

def test_customer_outstanding_reduced_by_payment(db_session, customer):
    from spare_parts.services import parts_service, sales_service, stock_service
    part = parts_service.create_part(db_session, part_no="PB-1", name="Brake Pad")
    stock_service.add_ledger_entry(db_session, part_id=part.id, qty_in=50, reference_type="OPENING")
    db_session.commit()

    sale = sales_service.create_sale(
        db_session, sale_type="WHOLESALE", customer_id=customer.id,
        items=[dict(part_id=part.id, qty_entered=10, unit_price=100)], paid=0,
    )
    assert sale.due == Decimal("1000")
    assert customers_service.get_customer_outstanding(db_session, customer.id) == Decimal("1000")

    payments_service.create_payment(db_session, direction="IN", party_id=customer.id, amount=400)
    assert customers_service.get_customer_outstanding(db_session, customer.id) == Decimal("600")


def test_cancelled_payment_does_not_reduce_outstanding(db_session, customer):
    from spare_parts.services import parts_service, sales_service, stock_service
    part = parts_service.create_part(db_session, part_no="PB-2", name="Clutch Plate")
    stock_service.add_ledger_entry(db_session, part_id=part.id, qty_in=50, reference_type="OPENING")
    db_session.commit()
    sales_service.create_sale(
        db_session, sale_type="WHOLESALE", customer_id=customer.id,
        items=[dict(part_id=part.id, qty_entered=5, unit_price=100)], paid=0,
    )
    payment = payments_service.create_payment(db_session, direction="IN", party_id=customer.id, amount=200)
    payments_service.cancel_payment(db_session, payment.id)
    assert customers_service.get_customer_outstanding(db_session, customer.id) == Decimal("500")


def test_supplier_outstanding_reduced_by_payment(db_session, supplier):
    from spare_parts.services import parts_service, purchase_service
    part = parts_service.create_part(db_session, part_no="PB-3", name="Air Filter")
    purchase = purchase_service.create_purchase(
        db_session, supplier_id=supplier.id,
        items=[dict(part_id=part.id, qty=20, unit_cost=50)], paid=0,
    )
    assert purchase.due == Decimal("1000")
    assert suppliers_service.get_supplier_outstanding(db_session, supplier.id) == Decimal("1000")

    payments_service.create_payment(db_session, direction="OUT", party_id=supplier.id, amount=300)
    assert suppliers_service.get_supplier_outstanding(db_session, supplier.id) == Decimal("700")
