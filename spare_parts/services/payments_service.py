"""Service layer for payments (Phase 4): a customer paying down what they
owe ("IN"), or us paying a supplier what we owe them ("OUT").

Each payment is recorded against the party's general account balance, not
against one specific sale/purchase - see spare_parts.db.models.SpPayment
and spare_parts.services.ledger_service for the running-balance model this
feeds into.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy.orm import Session

from spare_parts.db.models import SpPayment
from spare_parts.errors import SparePartsValidationError
from spare_parts.services import customers_service, suppliers_service
from spare_parts.utils import to_decimal
from spare_parts.logging_config import get_logger

logger = get_logger(__name__)

VALID_DIRECTIONS = ("IN", "OUT")
_PREFIX_BY_DIRECTION = {"IN": "RCV-", "OUT": "PAY-"}


def generate_payment_no(db: Session, direction: str) -> str:
    """Next number in the IN ("RCV-...") or OUT ("PAY-...") series - the
    two series are independent, same pattern as sales_service's RT-/WS-
    split."""
    prefix = _PREFIX_BY_DIRECTION[direction]
    count = db.query(SpPayment).filter(SpPayment.direction == direction).count()
    for attempt in range(count + 1, count + 1000):
        candidate = f"{prefix}{attempt:04d}"
        exists = db.query(SpPayment.id).filter(SpPayment.payment_no == candidate).first()
        if not exists:
            return candidate
    raise SparePartsValidationError("Could not generate a unique payment number.")


def create_payment(
    db: Session,
    *,
    direction: str,
    party_id: int,
    amount,
    payment_method: str = "Cash",
    payment_date: Optional[dt.datetime] = None,
    notes: str = "",
) -> SpPayment:
    """direction "IN": party_id is a customer id (money received from
    them). direction "OUT": party_id is a supplier id (money paid to
    them). party_id is required and validated against an active record of
    the matching kind."""
    direction = (direction or "").upper()
    if direction not in VALID_DIRECTIONS:
        raise SparePartsValidationError("Direction must be IN or OUT.")

    if direction == "IN":
        party = customers_service.get_customer(db, party_id)
        if not party or not party.is_active:
            raise SparePartsValidationError("Select a valid, active customer.")
    else:
        party = suppliers_service.get_supplier(db, party_id)
        if not party or not party.is_active:
            raise SparePartsValidationError("Select a valid, active supplier.")

    amount_dec = to_decimal(amount, "Amount")
    if amount_dec <= 0:
        raise SparePartsValidationError("Amount must be greater than zero.")

    try:
        payment = SpPayment(
            payment_no=generate_payment_no(db, direction),
            direction=direction,
            customer_id=party.id if direction == "IN" else None,
            supplier_id=party.id if direction == "OUT" else None,
            amount=amount_dec,
            payment_method=(payment_method or "Cash").strip() or "Cash",
            payment_date=payment_date or dt.datetime.utcnow(),
            notes=(notes or "").strip() or None,
            status="POSTED",
        )
        db.add(payment)
        db.commit()
        db.refresh(payment)
        logger.info(f"Recorded payment {payment.payment_no} direction={direction} amount={amount_dec}")
        return payment
    except Exception:
        db.rollback()
        raise


def cancel_payment(db: Session, payment_id: int, reason: str = "") -> SpPayment:
    payment = get_payment(db, payment_id)
    if not payment:
        raise SparePartsValidationError(f"Payment id={payment_id} not found.")
    if payment.status == "CANCELLED":
        raise SparePartsValidationError("This payment is already cancelled.")
    try:
        payment.status = "CANCELLED"
        if reason:
            note = f"[Cancelled: {reason}]"
            payment.notes = f"{payment.notes}\n{note}" if payment.notes else note
        db.commit()
        logger.info(f"Cancelled payment {payment.payment_no} (id={payment.id})")
        return payment
    except Exception:
        db.rollback()
        raise


def list_payments(
    db: Session,
    *,
    direction: Optional[str] = None,
    customer_id: Optional[int] = None,
    supplier_id: Optional[int] = None,
    status: Optional[str] = None,
) -> list[SpPayment]:
    q = db.query(SpPayment)
    if direction:
        q = q.filter(SpPayment.direction == direction)
    if customer_id:
        q = q.filter(SpPayment.customer_id == customer_id)
    if supplier_id:
        q = q.filter(SpPayment.supplier_id == supplier_id)
    if status:
        q = q.filter(SpPayment.status == status)
    return q.order_by(SpPayment.payment_date.desc(), SpPayment.id.desc()).all()


def get_payment(db: Session, payment_id: int) -> Optional[SpPayment]:
    return db.query(SpPayment).filter(SpPayment.id == payment_id).first()
