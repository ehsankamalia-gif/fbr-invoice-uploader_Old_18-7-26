"""Held sales ("drafts"): an unfinished POS card saved without touching
stock, so a cashier can set a customer's cart aside and come back to it
later without losing what was already entered or blocking other
customers. Finalizing a draft into a real sale still goes entirely
through sales_service.create_sale - nothing in this file ever writes to
the stock ledger (see spare_parts/__init__.py: stock is only reduced
when a sale is actually finalized).
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from spare_parts.db.models import SpHeldSale, SpHeldSaleItem
from spare_parts.errors import SparePartsValidationError
from spare_parts.services import parts_service
from spare_parts.utils import to_decimal
from spare_parts.logging_config import get_logger

logger = get_logger(__name__)


def generate_hold_no(db: Session) -> str:
    count = db.query(SpHeldSale).count()
    for attempt in range(count + 1, count + 1000):
        candidate = f"HOLD-{attempt:04d}"
        if not db.query(SpHeldSale.id).filter(SpHeldSale.hold_no == candidate).first():
            return candidate
    raise SparePartsValidationError("Could not generate a unique hold number.")


def _validate_draft_items(db: Session, items: list[dict]) -> list[dict]:
    """Lighter than sales_service._validate_items (no stock/credit/
    business checks - those happen for real only when a draft is
    finalized into an actual sale), but accepts the exact same item
    shape (part_id, sold_as, qty_entered, unit_price, discount, and now
    price_type) coming straight off a SaleCardWidget, including the same
    pack-to-base-unit conversion, so a card's items translate identically
    whether it's being completed or held. `qty` is accepted as a
    fallback key for callers that already have base-unit quantities
    (e.g. existing tests). price_type defaults to RETAIL if omitted."""
    if not items:
        raise SparePartsValidationError("Add at least one item before holding this sale.")
    validated = []
    for idx, raw in enumerate(items, start=1):
        part_id = raw.get("part_id")
        if not part_id:
            raise SparePartsValidationError(f"Line {idx}: select a part.")
        part = parts_service.get_part(db, part_id)
        if not part:
            raise SparePartsValidationError(f"Line {idx}: part not found.")

        sold_as = (raw.get("sold_as") or "UNIT").upper()
        if sold_as not in ("UNIT", "PACK"):
            sold_as = "UNIT"

        price_type = (raw.get("price_type") or "RETAIL").upper()
        if price_type not in ("RETAIL", "WHOLESALE"):
            price_type = "RETAIL"

        raw_qty = raw.get("qty_entered", raw.get("qty"))
        try:
            qty_entered = int(raw_qty or 0)
        except (TypeError, ValueError):
            raise SparePartsValidationError(f"Line {idx}: quantity must be a whole number.")
        if qty_entered <= 0:
            raise SparePartsValidationError(f"Line {idx}: quantity must be greater than zero.")

        base_qty = qty_entered * (part.pack_size if sold_as == "PACK" else 1)
        if base_qty <= 0:
            raise SparePartsValidationError(f"Line {idx}: resulting quantity must be greater than zero.")

        unit_price = to_decimal(raw.get("unit_price"), f"Line {idx} price")
        if unit_price < 0:
            raise SparePartsValidationError(f"Line {idx}: price cannot be negative.")
        discount = to_decimal(raw.get("discount", 0), f"Line {idx} discount")
        if discount < 0:
            raise SparePartsValidationError(f"Line {idx}: discount cannot be negative.")

        line_total = (unit_price * base_qty) - discount
        if line_total < 0:
            line_total = Decimal("0")

        validated.append(dict(
            part_id=part.id, qty=base_qty, sold_as=sold_as,
            pack_qty=qty_entered if sold_as == "PACK" else None,
            price_type=price_type,
            unit_price=unit_price, discount=discount, line_total=line_total,
        ))
    return validated


def create_held_sale(
    db: Session,
    *,
    reference: str = "",
    card_label: str = "",
    sale_type: str,
    customer_id: Optional[int] = None,
    items: list[dict],
    discount=0,
    tax_percent=None,
    paid=0,
    payment_method: str = "Cash",
    notes: str = "",
) -> SpHeldSale:
    sale_type = (sale_type or "RETAIL").upper()
    validated_items = _validate_draft_items(db, items)
    try:
        held = SpHeldSale(
            hold_no=generate_hold_no(db),
            reference=(reference or "").strip() or None,
            card_label=(card_label or "").strip() or None,
            sale_type=sale_type,
            customer_id=customer_id or None,
            discount=to_decimal(discount, "Discount"),
            tax_percent=to_decimal(tax_percent, "Tax %") if tax_percent is not None else Decimal("0"),
            paid=to_decimal(paid, "Paid amount"),
            payment_method=(payment_method or "Cash").strip() or "Cash",
            notes=(notes or "").strip() or None,
            held_at=dt.datetime.utcnow(),
        )
        db.add(held)
        db.flush()
        for item in validated_items:
            db.add(SpHeldSaleItem(held_sale_id=held.id, **item))
        db.commit()
        logger.info(f"Held sale {held.hold_no} (id={held.id}), {len(validated_items)} item(s)")
        return held
    except Exception:
        db.rollback()
        raise


def update_held_sale(
    db: Session,
    held_sale_id: int,
    *,
    reference: Optional[str] = None,
    card_label: Optional[str] = None,
    sale_type: Optional[str] = None,
    customer_id=...,  # sentinel: only overwritten if explicitly passed (None is a valid value - walk-in)
    items: Optional[list[dict]] = None,
    discount=None,
    tax_percent=None,
    paid=None,
    payment_method: Optional[str] = None,
    notes: Optional[str] = None,
) -> SpHeldSale:
    """Re-holding a card that was previously resumed from a draft updates
    that SAME draft record instead of creating a duplicate - see
    spare_parts/ui/pos_page.py, which tracks each open card's
    held_sale_id once it's linked to one."""
    held = get_held_sale(db, held_sale_id)
    if not held:
        raise SparePartsValidationError(f"Held sale id={held_sale_id} not found.")

    validated_items = _validate_draft_items(db, items) if items is not None else None

    try:
        if validated_items is not None:
            for old_item in list(held.items):
                db.delete(old_item)
            db.flush()
            for item in validated_items:
                db.add(SpHeldSaleItem(held_sale_id=held.id, **item))

        if reference is not None:
            held.reference = reference.strip() or None
        if card_label is not None:
            held.card_label = card_label.strip() or None
        if sale_type:
            held.sale_type = sale_type.upper()
        if customer_id is not ...:
            held.customer_id = customer_id or None
        if discount is not None:
            held.discount = to_decimal(discount, "Discount")
        if tax_percent is not None:
            held.tax_percent = to_decimal(tax_percent, "Tax %")
        if paid is not None:
            held.paid = to_decimal(paid, "Paid amount")
        if payment_method is not None:
            held.payment_method = payment_method.strip() or "Cash"
        if notes is not None:
            held.notes = notes.strip() or None

        held.held_at = dt.datetime.utcnow()
        db.commit()
        logger.info(f"Re-held sale {held.hold_no} (id={held.id})")
        return held
    except Exception:
        db.rollback()
        raise


def list_held_sales(db: Session) -> list[SpHeldSale]:
    return db.query(SpHeldSale).order_by(SpHeldSale.held_at.desc()).all()


def get_held_sale(db: Session, held_sale_id: int) -> Optional[SpHeldSale]:
    return db.query(SpHeldSale).filter(SpHeldSale.id == held_sale_id).first()


def delete_held_sale(db: Session, held_sale_id: int) -> None:
    held = get_held_sale(db, held_sale_id)
    if not held:
        return
    try:
        db.delete(held)
        db.commit()
        logger.info(f"Deleted held sale {held.hold_no} (id={held_sale_id})")
    except Exception:
        db.rollback()
        raise


def get_reserved_qty_for_part(db: Session, part_id: int, *, exclude_held_sale_id: Optional[int] = None) -> int:
    """Total quantity of this part sitting in held drafts right now -
    combined with each open POS card's own in-memory total (see
    spare_parts/ui/pos_page.py), this lets the cashier be warned before
    the same part is oversold across simultaneous open sales. Stock
    itself is only actually decremented at finalize time (create_sale),
    where the real negative-stock guard applies - this is purely an
    early, advisory heads-up.

    exclude_held_sale_id lets a card that's already linked to a draft
    exclude that draft's own reservation when re-checking itself (since
    the card's current in-memory items already stand in for it)."""
    q = db.query(SpHeldSaleItem.qty).filter(SpHeldSaleItem.part_id == part_id)
    if exclude_held_sale_id:
        q = q.filter(SpHeldSaleItem.held_sale_id != exclude_held_sale_id)
    return sum((row[0] for row in q.all()), 0)


def held_sale_overall_type(held: SpHeldSale) -> tuple[str, bool]:
    """(overall_type, is_mixed) computed from each item's own price_type -
    mirrors SaleCardWidget._compute_overall_type() server-side, for
    displaying an accurate "Type" in the Held Sales list even for a
    mixed-pricing draft. Falls back to the draft's header sale_type for
    any item saved before price_type existed (migration v6)."""
    types = {(item.price_type or held.sale_type) for item in held.items}
    if not types:
        return held.sale_type, False
    overall = "WHOLESALE" if "WHOLESALE" in types else "RETAIL"
    return overall, len(types) > 1


def held_sale_total(held: SpHeldSale) -> Decimal:
    """Computed the same way a real sale's total is derived from its
    items - used for display in the Held Sales list."""
    subtotal = sum((Decimal(str(i.line_total)) for i in held.items), Decimal("0"))
    taxable = subtotal - Decimal(str(held.discount or 0))
    if taxable < 0:
        taxable = Decimal("0")
    tax_amount = (taxable * Decimal(str(held.tax_percent or 0)) / Decimal("100")).quantize(Decimal("0.01"))
    return taxable + tax_amount
