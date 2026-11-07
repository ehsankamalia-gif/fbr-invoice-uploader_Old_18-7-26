"""Purchase entry service: creates a purchase (header + items), updates
the stock ledger and each part's moving-average cost, and supports
cancelling a posted purchase (reversing its stock effect).

Every save here runs as one transaction - header, items, stock ledger
entries, and cost updates all commit together or all roll back (see
spare_parts/__init__.py's data-integrity rules).
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from spare_parts.db.models import SpPurchase, SpPurchaseItem
from spare_parts.errors import SparePartsValidationError
from spare_parts.services import parts_service, stock_service, suppliers_service
from spare_parts.services.settings_service import get_settings
from spare_parts.utils import to_decimal
from spare_parts.logging_config import get_logger

logger = get_logger(__name__)


def generate_purchase_no(db: Session) -> str:
    """Next purchase number as <prefix><count+1>, zero-padded to 4
    digits (e.g. PO-0001). Based on a row count, not MAX(id)-derived
    parsing, so it stays correct even if a very old row is ever removed
    by hand in the database directly."""
    settings = get_settings(db)
    prefix = settings.purchase_no_prefix or "PO-"
    count = db.query(SpPurchase).count()
    for attempt in range(count + 1, count + 1000):
        candidate = f"{prefix}{attempt:04d}"
        exists = db.query(SpPurchase.id).filter(SpPurchase.purchase_no == candidate).first()
        if not exists:
            return candidate
    raise SparePartsValidationError("Could not generate a unique purchase number.")


def _validate_items(items: list[dict]) -> tuple[list[dict], Decimal]:
    if not items:
        raise SparePartsValidationError("Add at least one item.")

    validated = []
    subtotal = Decimal("0")
    for idx, raw in enumerate(items, start=1):
        part_id = raw.get("part_id")
        if not part_id:
            raise SparePartsValidationError(f"Line {idx}: select a part.")
        try:
            qty = int(raw.get("qty") or 0)
        except (TypeError, ValueError):
            raise SparePartsValidationError(f"Line {idx}: quantity must be a whole number.")
        if qty <= 0:
            raise SparePartsValidationError(f"Line {idx}: quantity must be greater than zero.")

        unit_cost = to_decimal(raw.get("unit_cost"), f"Line {idx} unit cost")
        if unit_cost < 0:
            raise SparePartsValidationError(f"Line {idx}: unit cost cannot be negative.")
        line_discount = to_decimal(raw.get("discount", 0), f"Line {idx} discount")
        if line_discount < 0:
            raise SparePartsValidationError(f"Line {idx}: discount cannot be negative.")

        line_total = (unit_cost * qty) - line_discount
        if line_total < 0:
            raise SparePartsValidationError(f"Line {idx}: discount cannot exceed the line amount.")

        validated.append(dict(
            part_id=part_id, qty=qty, unit_cost=unit_cost,
            discount=line_discount, line_total=line_total,
        ))
        subtotal += line_total

    return validated, subtotal


def create_purchase(
    db: Session,
    *,
    supplier_id: int,
    items: list[dict],
    purchase_date: Optional[dt.datetime] = None,
    discount=0,
    paid=0,
    notes: str = "",
) -> SpPurchase:
    """items: list of {part_id, qty, unit_cost, discount}."""
    supplier = suppliers_service.get_supplier(db, supplier_id)
    if not supplier or not supplier.is_active:
        raise SparePartsValidationError("Select a valid, active supplier.")

    validated_items, subtotal = _validate_items(items)

    header_discount = to_decimal(discount, "Discount")
    if header_discount < 0:
        raise SparePartsValidationError("Discount cannot be negative.")
    total = subtotal - header_discount
    if total < 0:
        raise SparePartsValidationError("Discount cannot exceed the subtotal.")

    paid_amount = to_decimal(paid, "Paid amount")
    if paid_amount < 0:
        raise SparePartsValidationError("Paid amount cannot be negative.")
    due = total - paid_amount

    try:
        purchase = SpPurchase(
            purchase_no=generate_purchase_no(db),
            supplier_id=supplier.id,
            purchase_date=purchase_date or dt.datetime.utcnow(),
            subtotal=subtotal,
            discount=header_discount,
            total=total,
            paid=paid_amount,
            due=due,
            status="POSTED",
            notes=(notes or "").strip() or None,
        )
        db.add(purchase)
        db.flush()  # assigns purchase.id for the items/ledger rows below

        for item in validated_items:
            part = parts_service.get_part(db, item["part_id"])
            if not part:
                raise SparePartsValidationError(f"Part id={item['part_id']} not found.")

            db.add(SpPurchaseItem(
                purchase_id=purchase.id,
                part_id=part.id,
                qty=item["qty"],
                unit_cost=item["unit_cost"],
                discount=item["discount"],
                line_total=item["line_total"],
            ))

            # Moving average cost: weight the existing stock's cost against
            # this purchase's cost. A part with no/negative prior stock
            # just takes this purchase's unit cost outright - there is
            # nothing meaningful to average against.
            old_qty = stock_service.get_current_stock(db, part.id)
            if old_qty <= 0:
                part.cost_price = item["unit_cost"]
            else:
                old_value = Decimal(old_qty) * Decimal(part.cost_price or 0)
                new_value = Decimal(item["qty"]) * item["unit_cost"]
                part.cost_price = (
                    (old_value + new_value) / Decimal(old_qty + item["qty"])
                ).quantize(Decimal("0.01"))

            stock_service.add_ledger_entry(
                db,
                part_id=part.id,
                qty_in=item["qty"],
                reference_type="PURCHASE",
                reference_id=purchase.id,
                note=f"Purchase {purchase.purchase_no}",
            )

        db.commit()
        logger.info(f"Created purchase {purchase.purchase_no} (id={purchase.id}) total={total}")
        return purchase
    except Exception:
        db.rollback()
        raise


def cancel_purchase(db: Session, purchase_id: int, reason: str = "") -> SpPurchase:
    """Reverses a POSTED purchase's stock effect and marks it CANCELLED.

    Blocks (raising SparePartsValidationError, nothing is changed) if
    reversing any item would take that part negative - e.g. a stock
    adjustment reduced it below what this purchase added, in a later
    phase. Does not attempt to retroactively "unmix" the moving-average
    cost_price other purchases may have layered on top of this one since
    - that is a standard, accepted simplification in small-business stock
    systems, not a bug; flagged here and in the Phase 2 summary.
    """
    purchase = get_purchase(db, purchase_id)
    if not purchase:
        raise SparePartsValidationError(f"Purchase id={purchase_id} not found.")
    if purchase.status == "CANCELLED":
        raise SparePartsValidationError("This purchase is already cancelled.")

    # Pre-flight: check every item before changing anything, so a failure
    # on item 3 of 5 never leaves items 1-2 partially reversed.
    for item in purchase.items:
        current = stock_service.get_current_stock(db, item.part_id)
        if current - item.qty < 0:
            settings = get_settings(db)
            if not settings.allow_negative_stock:
                part = parts_service.get_part(db, item.part_id)
                part_label = part.part_no if part else f"id={item.part_id}"
                raise SparePartsValidationError(
                    f"Cannot cancel: reversing part {part_label} ({item.qty} units) "
                    f"would take its stock negative (currently {current})."
                )

    try:
        for item in purchase.items:
            stock_service.add_ledger_entry(
                db,
                part_id=item.part_id,
                qty_out=item.qty,
                reference_type="PURCHASE_CANCEL",
                reference_id=purchase.id,
                note=f"Cancelled {purchase.purchase_no}" + (f": {reason}" if reason else ""),
            )
        purchase.status = "CANCELLED"
        if reason:
            note = f"[Cancelled: {reason}]"
            purchase.notes = f"{purchase.notes}\n{note}" if purchase.notes else note
        db.commit()
        logger.info(f"Cancelled purchase {purchase.purchase_no} (id={purchase.id})")
        return purchase
    except Exception:
        db.rollback()
        raise


def list_purchases(
    db: Session,
    *,
    supplier_id: Optional[int] = None,
    status: Optional[str] = None,
) -> list[SpPurchase]:
    q = db.query(SpPurchase)
    if supplier_id:
        q = q.filter(SpPurchase.supplier_id == supplier_id)
    if status:
        q = q.filter(SpPurchase.status == status)
    return q.order_by(SpPurchase.purchase_date.desc(), SpPurchase.id.desc()).all()


def get_purchase(db: Session, purchase_id: int) -> Optional[SpPurchase]:
    return db.query(SpPurchase).filter(SpPurchase.id == purchase_id).first()
