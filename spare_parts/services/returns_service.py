"""Sale returns and purchase returns - both linked to their original
invoice, both reverse stock (in opposite directions), both run as one
transaction per spare_parts/__init__.py's data-integrity rules.

A sale return increases stock (goods physically come back from the
customer). A purchase return decreases stock (goods go back to the
supplier) and can raise StockError if there isn't enough stock left to
send back - e.g. most of it was already resold.

Partial returns are supported: each return line references the specific
original item it reverses and cannot exceed that line's quantity minus
whatever has already been returned against it in an earlier return.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from spare_parts.db.models import (
    SpPurchaseReturn,
    SpPurchaseReturnItem,
    SpSaleReturn,
    SpSaleReturnItem,
)
from spare_parts.errors import SparePartsValidationError
from spare_parts.services import purchase_service, sales_service, stock_service
from spare_parts.logging_config import get_logger

logger = get_logger(__name__)


def _generate_return_no(db: Session, prefix: str, model_cls) -> str:
    count = db.query(model_cls).count()
    for attempt in range(count + 1, count + 1000):
        candidate = f"{prefix}{attempt:04d}"
        exists = db.query(model_cls.id).filter(model_cls.return_no == candidate).first()
        if not exists:
            return candidate
    raise SparePartsValidationError("Could not generate a unique return number.")


# --- Sale returns ------------------------------------------------------

def _already_returned_by_sale_item(db: Session, sale_id: int) -> dict[int, int]:
    rows = (
        db.query(SpSaleReturnItem.sale_item_id, func.coalesce(func.sum(SpSaleReturnItem.qty), 0))
        .join(SpSaleReturn, SpSaleReturn.id == SpSaleReturnItem.return_id)
        .filter(SpSaleReturn.sale_id == sale_id)
        .group_by(SpSaleReturnItem.sale_item_id)
        .all()
    )
    return {sale_item_id: int(qty) for sale_item_id, qty in rows}


def create_sale_return(
    db: Session,
    *,
    sale_id: int,
    items: list[dict],
    return_date: Optional[dt.datetime] = None,
    notes: str = "",
) -> SpSaleReturn:
    """items: list of {sale_item_id, qty}."""
    sale = sales_service.get_sale(db, sale_id)
    if not sale:
        raise SparePartsValidationError("Original sale not found.")
    if sale.status != "POSTED":
        raise SparePartsValidationError("Can only return items from a POSTED sale.")
    if not items:
        raise SparePartsValidationError("Select at least one item to return.")

    sale_items_by_id = {si.id: si for si in sale.items}
    already_returned = _already_returned_by_sale_item(db, sale_id)

    validated = []
    subtotal = Decimal("0")
    for idx, raw in enumerate(items, start=1):
        sale_item_id = raw.get("sale_item_id")
        si = sale_items_by_id.get(sale_item_id)
        if not si:
            raise SparePartsValidationError(f"Line {idx}: original sale item not found.")
        try:
            qty = int(raw.get("qty") or 0)
        except (TypeError, ValueError):
            raise SparePartsValidationError(f"Line {idx}: quantity must be a whole number.")
        if qty <= 0:
            raise SparePartsValidationError(f"Line {idx}: quantity must be greater than zero.")

        max_returnable = si.qty - already_returned.get(sale_item_id, 0)
        if qty > max_returnable:
            raise SparePartsValidationError(
                f"Line {idx}: cannot return {qty} - only {max_returnable} still returnable "
                f"for this item."
            )

        line_total = Decimal(str(si.unit_price)) * qty
        validated.append(dict(sale_item_id=sale_item_id, part_id=si.part_id, qty=qty, unit_price=si.unit_price))
        subtotal += line_total

    try:
        sale_return = SpSaleReturn(
            return_no=_generate_return_no(db, "SR-", SpSaleReturn),
            sale_id=sale.id,
            return_date=return_date or dt.datetime.utcnow(),
            subtotal=subtotal,
            total=subtotal,
            notes=(notes or "").strip() or None,
            status="POSTED",
        )
        db.add(sale_return)
        db.flush()

        for item in validated:
            line_total = Decimal(str(item["unit_price"])) * item["qty"]
            db.add(SpSaleReturnItem(
                return_id=sale_return.id,
                sale_item_id=item["sale_item_id"],
                part_id=item["part_id"],
                qty=item["qty"],
                unit_price=item["unit_price"],
                line_total=line_total,
            ))
            stock_service.add_ledger_entry(
                db,
                part_id=item["part_id"],
                qty_in=item["qty"],
                reference_type="SALE_RETURN",
                reference_id=sale_return.id,
                note=f"Return {sale_return.return_no} (sale {sale.sale_no})",
            )

        db.commit()
        logger.info(f"Created sale return {sale_return.return_no} (id={sale_return.id})")
        return sale_return
    except Exception:
        db.rollback()
        raise


def list_sale_returns(db: Session, *, sale_id: Optional[int] = None) -> list[SpSaleReturn]:
    q = db.query(SpSaleReturn)
    if sale_id:
        q = q.filter(SpSaleReturn.sale_id == sale_id)
    return q.order_by(SpSaleReturn.return_date.desc(), SpSaleReturn.id.desc()).all()


def get_sale_return(db: Session, return_id: int) -> Optional[SpSaleReturn]:
    return db.query(SpSaleReturn).filter(SpSaleReturn.id == return_id).first()


# --- Purchase returns ------------------------------------------------------

def _already_returned_by_purchase_item(db: Session, purchase_id: int) -> dict[int, int]:
    rows = (
        db.query(SpPurchaseReturnItem.purchase_item_id, func.coalesce(func.sum(SpPurchaseReturnItem.qty), 0))
        .join(SpPurchaseReturn, SpPurchaseReturn.id == SpPurchaseReturnItem.return_id)
        .filter(SpPurchaseReturn.purchase_id == purchase_id)
        .group_by(SpPurchaseReturnItem.purchase_item_id)
        .all()
    )
    return {purchase_item_id: int(qty) for purchase_item_id, qty in rows}


def create_purchase_return(
    db: Session,
    *,
    purchase_id: int,
    items: list[dict],
    return_date: Optional[dt.datetime] = None,
    notes: str = "",
) -> SpPurchaseReturn:
    """items: list of {purchase_item_id, qty}."""
    purchase = purchase_service.get_purchase(db, purchase_id)
    if not purchase:
        raise SparePartsValidationError("Original purchase not found.")
    if purchase.status != "POSTED":
        raise SparePartsValidationError("Can only return items from a POSTED purchase.")
    if not items:
        raise SparePartsValidationError("Select at least one item to return.")

    purchase_items_by_id = {pi.id: pi for pi in purchase.items}
    already_returned = _already_returned_by_purchase_item(db, purchase_id)

    validated = []
    subtotal = Decimal("0")
    for idx, raw in enumerate(items, start=1):
        purchase_item_id = raw.get("purchase_item_id")
        pi = purchase_items_by_id.get(purchase_item_id)
        if not pi:
            raise SparePartsValidationError(f"Line {idx}: original purchase item not found.")
        try:
            qty = int(raw.get("qty") or 0)
        except (TypeError, ValueError):
            raise SparePartsValidationError(f"Line {idx}: quantity must be a whole number.")
        if qty <= 0:
            raise SparePartsValidationError(f"Line {idx}: quantity must be greater than zero.")

        max_returnable = pi.qty - already_returned.get(purchase_item_id, 0)
        if qty > max_returnable:
            raise SparePartsValidationError(
                f"Line {idx}: cannot return {qty} - only {max_returnable} still returnable "
                f"for this item."
            )

        validated.append(dict(purchase_item_id=purchase_item_id, part_id=pi.part_id, qty=qty, unit_cost=pi.unit_cost))
        subtotal += Decimal(str(pi.unit_cost)) * qty

    try:
        purchase_return = SpPurchaseReturn(
            return_no=_generate_return_no(db, "PR-", SpPurchaseReturn),
            purchase_id=purchase.id,
            return_date=return_date or dt.datetime.utcnow(),
            subtotal=subtotal,
            total=subtotal,
            notes=(notes or "").strip() or None,
            status="POSTED",
        )
        db.add(purchase_return)
        db.flush()

        for item in validated:
            line_total = Decimal(str(item["unit_cost"])) * item["qty"]
            db.add(SpPurchaseReturnItem(
                return_id=purchase_return.id,
                purchase_item_id=item["purchase_item_id"],
                part_id=item["part_id"],
                qty=item["qty"],
                unit_cost=item["unit_cost"],
                line_total=line_total,
            ))
            # Goods leaving stock back to the supplier - raises StockError
            # (a SparePartsValidationError) if not enough is left, e.g.
            # most of this purchase was already resold.
            stock_service.add_ledger_entry(
                db,
                part_id=item["part_id"],
                qty_out=item["qty"],
                reference_type="PURCHASE_RETURN",
                reference_id=purchase_return.id,
                note=f"Return {purchase_return.return_no} (purchase {purchase.purchase_no})",
            )

        db.commit()
        logger.info(f"Created purchase return {purchase_return.return_no} (id={purchase_return.id})")
        return purchase_return
    except Exception:
        db.rollback()
        raise


def list_purchase_returns(db: Session, *, purchase_id: Optional[int] = None) -> list[SpPurchaseReturn]:
    q = db.query(SpPurchaseReturn)
    if purchase_id:
        q = q.filter(SpPurchaseReturn.purchase_id == purchase_id)
    return q.order_by(SpPurchaseReturn.return_date.desc(), SpPurchaseReturn.id.desc()).all()


def get_purchase_return(db: Session, return_id: int) -> Optional[SpPurchaseReturn]:
    return db.query(SpPurchaseReturn).filter(SpPurchaseReturn.id == return_id).first()
