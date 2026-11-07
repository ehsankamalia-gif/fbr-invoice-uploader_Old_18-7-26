"""Service layer for customers (Phase 3), plus the credit-limit check
used by sales_service before posting a wholesale credit sale."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from spare_parts.db.models import SpCustomer, SpPayment, SpSale, SpSaleReturn
from spare_parts.errors import SparePartsValidationError
from spare_parts.utils import to_decimal
from spare_parts.logging_config import get_logger

logger = get_logger(__name__)

VALID_TYPES = ("RETAIL", "WHOLESALE")


def search_customers(db: Session, query: str = "", active_only: bool = True) -> list[SpCustomer]:
    q = db.query(SpCustomer)
    if active_only:
        q = q.filter(SpCustomer.is_active == True)  # noqa: E712
    query = (query or "").strip()
    if query:
        like = f"%{query}%"
        q = q.filter(or_(
            SpCustomer.name.ilike(like),
            SpCustomer.phone.ilike(like),
            SpCustomer.cnic_ntn.ilike(like),
        ))
    return q.order_by(SpCustomer.name).all()


def list_customers(db: Session, active_only: bool = True) -> list[SpCustomer]:
    return search_customers(db, active_only=active_only)


def get_customer(db: Session, customer_id: int) -> Optional[SpCustomer]:
    return db.query(SpCustomer).filter(SpCustomer.id == customer_id).first()


def create_customer(
    db: Session,
    *,
    name: str,
    type: str = "RETAIL",  # noqa: A002 - matches the spec's field name
    phone: str = "",
    address: str = "",
    cnic_ntn: str = "",
    is_fbr_registered: bool = False,
    credit_limit=0,
    opening_balance=0,
) -> SpCustomer:
    name = (name or "").strip()
    if not name:
        raise SparePartsValidationError("Customer name is required.")
    type_value = (type or "RETAIL").upper()
    if type_value not in VALID_TYPES:
        raise SparePartsValidationError("Customer type must be RETAIL or WHOLESALE.")

    customer = SpCustomer(
        name=name,
        type=type_value,
        phone=(phone or "").strip() or None,
        address=(address or "").strip() or None,
        cnic_ntn=(cnic_ntn or "").strip() or None,
        is_fbr_registered=bool(is_fbr_registered),
        credit_limit=to_decimal(credit_limit, "Credit limit"),
        opening_balance=to_decimal(opening_balance, "Opening balance"),
        is_active=True,
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    logger.info(f"Created customer {customer.name} (id={customer.id}, type={customer.type})")
    return customer


def update_customer(db: Session, customer_id: int, **fields) -> SpCustomer:
    customer = get_customer(db, customer_id)
    if not customer:
        raise SparePartsValidationError(f"Customer id={customer_id} not found.")

    if "name" in fields:
        new_name = (fields["name"] or "").strip()
        if not new_name:
            raise SparePartsValidationError("Customer name is required.")
        customer.name = new_name

    if "type" in fields:
        type_value = (fields["type"] or "RETAIL").upper()
        if type_value not in VALID_TYPES:
            raise SparePartsValidationError("Customer type must be RETAIL or WHOLESALE.")
        customer.type = type_value

    for simple_field in ("phone", "address", "cnic_ntn"):
        if simple_field in fields:
            value = fields[simple_field]
            setattr(customer, simple_field, (value or "").strip() or None if isinstance(value, str) else value)

    if "is_fbr_registered" in fields:
        customer.is_fbr_registered = bool(fields["is_fbr_registered"])

    for money_field in ("credit_limit", "opening_balance"):
        if money_field in fields and fields[money_field] is not None:
            setattr(customer, money_field, to_decimal(fields[money_field], money_field))

    db.commit()
    db.refresh(customer)
    logger.info(f"Updated customer {customer.name} (id={customer.id})")
    return customer


def set_customer_active(db: Session, customer_id: int, is_active: bool) -> SpCustomer:
    customer = get_customer(db, customer_id)
    if not customer:
        raise SparePartsValidationError(f"Customer id={customer_id} not found.")
    customer.is_active = bool(is_active)
    db.commit()
    db.refresh(customer)
    logger.info(f"Customer {customer.name} (id={customer.id}) is_active={customer.is_active}")
    return customer


# --- Credit limit ----------------------------------------------------------

def get_customer_outstanding(db: Session, customer_id: int) -> Decimal:
    """Opening balance, plus the sum of `due` across this customer's
    currently-POSTED sales (each sale's own due is fixed at what was
    collected at sale time), minus sale returns since (goods/credit back
    reduces what they owe) and minus any payments recorded since against
    their account (see spare_parts.services.payments_service /
    ledger_service) - the live "what they owe us right now" figure.

    Phase 4 note: this now also nets out sale returns and payments, which
    Phase 3's version did not yet account for (there was nothing to
    subtract from before Phase 4 added returns-as-credit and payments)."""
    customer = get_customer(db, customer_id)
    if not customer:
        return Decimal("0")
    total_due = db.query(func.coalesce(func.sum(SpSale.due), 0)).filter(
        SpSale.customer_id == customer_id, SpSale.status == "POSTED"
    ).scalar()
    total_returns = db.query(func.coalesce(func.sum(SpSaleReturn.total), 0)).join(
        SpSale, SpSale.id == SpSaleReturn.sale_id
    ).filter(SpSale.customer_id == customer_id, SpSaleReturn.status == "POSTED").scalar()
    total_payments = db.query(func.coalesce(func.sum(SpPayment.amount), 0)).filter(
        SpPayment.customer_id == customer_id, SpPayment.status == "POSTED"
    ).scalar()
    return (
        Decimal(str(customer.opening_balance or 0))
        + Decimal(str(total_due or 0))
        - Decimal(str(total_returns or 0))
        - Decimal(str(total_payments or 0))
    )


def check_credit_limit(
    db: Session, customer_id: int, additional_due
) -> tuple[bool, Decimal, Decimal]:
    """Returns (within_limit, projected_balance, credit_limit).

    A credit_limit of 0 (the default) means "no limit configured" - such
    customers always pass. This is advisory only: sales_service.create_sale
    never blocks on this, the UI decides whether to warn and let the user
    confirm anyway (see spare_parts/__init__.py: "warn when exceeded").
    """
    customer = get_customer(db, customer_id)
    if not customer or not customer.credit_limit or customer.credit_limit <= 0:
        return True, Decimal("0"), Decimal("0")
    current = get_customer_outstanding(db, customer_id)
    projected = current + to_decimal(additional_due, "Due amount")
    within = projected <= customer.credit_limit
    return within, projected, Decimal(str(customer.credit_limit))
