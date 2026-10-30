"""Service layer for suppliers (Phase 2), plus the outstanding-balance
calc (Phase 4) used by the Supplier ledger."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from spare_parts.db.models import SpPayment, SpPurchase, SpPurchaseReturn, SpSupplier
from spare_parts.errors import SparePartsValidationError
from spare_parts.logging_config import get_logger
from spare_parts.utils import to_decimal as _to_decimal

logger = get_logger(__name__)


def search_suppliers(db: Session, query: str = "", active_only: bool = True) -> list[SpSupplier]:
    q = db.query(SpSupplier)
    if active_only:
        q = q.filter(SpSupplier.is_active == True)  # noqa: E712
    query = (query or "").strip()
    if query:
        like = f"%{query}%"
        q = q.filter(or_(SpSupplier.name.ilike(like), SpSupplier.phone.ilike(like)))
    return q.order_by(SpSupplier.name).all()


def list_suppliers(db: Session, active_only: bool = True) -> list[SpSupplier]:
    return search_suppliers(db, active_only=active_only)


def get_supplier(db: Session, supplier_id: int) -> Optional[SpSupplier]:
    return db.query(SpSupplier).filter(SpSupplier.id == supplier_id).first()


def create_supplier(
    db: Session,
    *,
    name: str,
    phone: str = "",
    address: str = "",
    opening_balance=0,
) -> SpSupplier:
    name = (name or "").strip()
    if not name:
        raise SparePartsValidationError("Supplier name is required.")
    supplier = SpSupplier(
        name=name,
        phone=(phone or "").strip() or None,
        address=(address or "").strip() or None,
        opening_balance=_to_decimal(opening_balance, "Opening balance"),
        is_active=True,
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    logger.info(f"Created supplier {supplier.name} (id={supplier.id})")
    return supplier


def update_supplier(db: Session, supplier_id: int, **fields) -> SpSupplier:
    supplier = get_supplier(db, supplier_id)
    if not supplier:
        raise SparePartsValidationError(f"Supplier id={supplier_id} not found.")

    if "name" in fields:
        new_name = (fields["name"] or "").strip()
        if not new_name:
            raise SparePartsValidationError("Supplier name is required.")
        supplier.name = new_name

    for simple_field in ("phone", "address"):
        if simple_field in fields:
            value = fields[simple_field]
            supplier_value = (value or "").strip() or None if isinstance(value, str) else value
            setattr(supplier, simple_field, supplier_value)

    if "opening_balance" in fields and fields["opening_balance"] is not None:
        supplier.opening_balance = _to_decimal(fields["opening_balance"], "Opening balance")

    db.commit()
    db.refresh(supplier)
    logger.info(f"Updated supplier {supplier.name} (id={supplier.id})")
    return supplier


def set_supplier_active(db: Session, supplier_id: int, is_active: bool) -> SpSupplier:
    supplier = get_supplier(db, supplier_id)
    if not supplier:
        raise SparePartsValidationError(f"Supplier id={supplier_id} not found.")
    supplier.is_active = bool(is_active)
    db.commit()
    db.refresh(supplier)
    logger.info(f"Supplier {supplier.name} (id={supplier.id}) is_active={supplier.is_active}")
    return supplier


def get_supplier_outstanding(db: Session, supplier_id: int) -> Decimal:
    """Opening balance, plus the sum of `due` across this supplier's
    currently-POSTED purchases, minus purchase returns (goods sent back
    reduces what we owe them) and minus any payments we've made to them
    since - the live "what we owe them right now" figure. Symmetric to
    customers_service.get_customer_outstanding."""
    supplier = get_supplier(db, supplier_id)
    if not supplier:
        return Decimal("0")
    total_due = db.query(func.coalesce(func.sum(SpPurchase.due), 0)).filter(
        SpPurchase.supplier_id == supplier_id, SpPurchase.status == "POSTED"
    ).scalar()
    total_returns = db.query(func.coalesce(func.sum(SpPurchaseReturn.total), 0)).join(
        SpPurchase, SpPurchase.id == SpPurchaseReturn.purchase_id
    ).filter(SpPurchase.supplier_id == supplier_id, SpPurchaseReturn.status == "POSTED").scalar()
    total_payments = db.query(func.coalesce(func.sum(SpPayment.amount), 0)).filter(
        SpPayment.supplier_id == supplier_id, SpPayment.status == "POSTED"
    ).scalar()
    return (
        Decimal(str(supplier.opening_balance or 0))
        + Decimal(str(total_due or 0))
        - Decimal(str(total_returns or 0))
        - Decimal(str(total_payments or 0))
    )
