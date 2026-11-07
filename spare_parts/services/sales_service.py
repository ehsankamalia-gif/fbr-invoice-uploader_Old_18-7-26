"""Sales entry service: creates a sale (header + items), decrements the
stock ledger, and supports cancelling a posted sale (reversing it).

Every save runs as one transaction (see spare_parts/__init__.py). Unlike
purchases, a sale never touches a part's cost_price - selling doesn't
change what you paid for the stock.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from spare_parts.db.models import SpSale, SpSaleItem, SpSaleReturn
from spare_parts.errors import SparePartsValidationError
from spare_parts.services import customers_service, parts_service, stock_service
from spare_parts.services.settings_service import get_settings
from spare_parts.utils import to_decimal
from spare_parts.logging_config import get_logger

logger = get_logger(__name__)

VALID_SALE_TYPES = ("RETAIL", "WHOLESALE")


def generate_sale_no(db: Session, sale_type: str) -> str:
    """Next sale number in the series for this sale_type (e.g. WS-0001
    for WHOLESALE, RT-0001 for RETAIL) - the two series are tracked and
    numbered completely independently of each other."""
    settings = get_settings(db)
    prefix = settings.wholesale_no_prefix if sale_type == "WHOLESALE" else settings.retail_no_prefix
    prefix = prefix or ("WS-" if sale_type == "WHOLESALE" else "RT-")
    count = db.query(SpSale).filter(SpSale.sale_type == sale_type).count()
    for attempt in range(count + 1, count + 1000):
        candidate = f"{prefix}{attempt:04d}"
        exists = db.query(SpSale.id).filter(SpSale.sale_no == candidate).first()
        if not exists:
            return candidate
    raise SparePartsValidationError("Could not generate a unique sale number.")


def _validate_items(db: Session, items: list[dict]) -> tuple[list[dict], Decimal]:
    if not items:
        raise SparePartsValidationError("Add at least one item.")

    validated = []
    subtotal = Decimal("0")
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

        try:
            qty_entered = int(raw.get("qty_entered") or 0)
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
        line_discount = to_decimal(raw.get("discount", 0), f"Line {idx} discount")
        if line_discount < 0:
            raise SparePartsValidationError(f"Line {idx}: discount cannot be negative.")

        line_total = (unit_price * base_qty) - line_discount
        if line_total < 0:
            raise SparePartsValidationError(f"Line {idx}: discount cannot exceed the line amount.")

        validated.append(dict(
            part_id=part.id, qty=base_qty, qty_entered=qty_entered, sold_as=sold_as,
            unit_price=unit_price, discount=line_discount, line_total=line_total,
            cost_price=Decimal(str(part.cost_price or 0)),
            warranty_days=int(part.warranty_days or 0),
        ))
        subtotal += line_total

    return validated, subtotal


def create_sale(
    db: Session,
    *,
    sale_type: str,
    customer_id: Optional[int] = None,
    walk_in_customer_name: str = "",
    items: list[dict],
    sale_date: Optional[dt.datetime] = None,
    discount=0,
    tax_percent=None,
    paid=0,
    payment_method: str = "Cash",
    notes: str = "",
) -> SpSale:
    """items: list of {part_id, qty_entered, sold_as ("UNIT"/"PACK"), unit_price, discount}.

    customer_id is optional for RETAIL (walk-in); required for WHOLESALE.
    Credit-limit checking is the UI's job (see
    customers_service.check_credit_limit) - this function never blocks on
    it, only "warn when exceeded" per spec, not "prevent".

    walk_in_customer_name: the name typed at the counter without
    selecting/creating a registered customer - ignored when customer_id
    is set (the registered customer's own name is used instead). Purely
    for display (receipt/sales list), never used for credit tracking.
    """
    sale_type = (sale_type or "").upper()
    if sale_type not in VALID_SALE_TYPES:
        raise SparePartsValidationError("Sale type must be RETAIL or WHOLESALE.")

    customer = None
    if customer_id:
        customer = customers_service.get_customer(db, customer_id)
        if not customer or not customer.is_active:
            raise SparePartsValidationError("Select a valid, active customer.")
    elif sale_type == "WHOLESALE":
        raise SparePartsValidationError("Wholesale sales require a customer.")

    validated_items, subtotal = _validate_items(db, items)

    header_discount = to_decimal(discount, "Discount")
    if header_discount < 0:
        raise SparePartsValidationError("Discount cannot be negative.")
    taxable = subtotal - header_discount
    if taxable < 0:
        raise SparePartsValidationError("Discount cannot exceed the subtotal.")

    settings = get_settings(db)
    tax_pct = (
        to_decimal(tax_percent, "Tax %") if tax_percent is not None
        else Decimal(str(settings.default_tax_percent or 0))
    )
    if tax_pct < 0:
        raise SparePartsValidationError("Tax % cannot be negative.")
    tax_amount = (taxable * tax_pct / Decimal("100")).quantize(Decimal("0.01"))
    total = taxable + tax_amount

    paid_amount = to_decimal(paid, "Paid amount")
    if paid_amount < 0:
        raise SparePartsValidationError("Paid amount cannot be negative.")
    due = total - paid_amount

    try:
        sale = SpSale(
            sale_no=generate_sale_no(db, sale_type),
            sale_type=sale_type,
            customer_id=customer.id if customer else None,
            walk_in_customer_name=(
                None if customer else ((walk_in_customer_name or "").strip() or None)
            ),
            sale_date=sale_date or dt.datetime.utcnow(),
            subtotal=subtotal,
            discount=header_discount,
            tax_percent=tax_pct,
            tax_amount=tax_amount,
            total=total,
            paid=paid_amount,
            due=due,
            payment_method=(payment_method or "Cash").strip() or "Cash",
            status="POSTED",
            notes=(notes or "").strip() or None,
        )
        db.add(sale)
        db.flush()

        for item in validated_items:
            db.add(SpSaleItem(
                sale_id=sale.id,
                part_id=item["part_id"],
                qty=item["qty"],
                sold_as=item["sold_as"],
                pack_qty=item["qty_entered"] if item["sold_as"] == "PACK" else None,
                unit_price=item["unit_price"],
                discount=item["discount"],
                line_total=item["line_total"],
                cost_price=item["cost_price"],
                warranty_expires_at=(
                    sale.sale_date + dt.timedelta(days=item["warranty_days"])
                    if item["warranty_days"] > 0 else None
                ),
            ))
            # Raises StockError (a SparePartsValidationError) if this
            # would take the part negative and negative stock isn't
            # allowed - propagates out, db.rollback() below undoes the
            # header/items/earlier lines too.
            stock_service.add_ledger_entry(
                db,
                part_id=item["part_id"],
                qty_out=item["qty"],
                reference_type="SALE",
                reference_id=sale.id,
                note=f"Sale {sale.sale_no}",
            )

        db.commit()
        logger.info(f"Created sale {sale.sale_no} (id={sale.id}) type={sale_type} total={total}")
        return sale
    except Exception:
        db.rollback()
        raise


def update_sale(
    db: Session,
    sale_id: int,
    *,
    items: list[dict],
    discount=0,
    tax_percent=None,
    paid=0,
    payment_method: str = "Cash",
    notes: str = "",
) -> SpSale:
    """Replaces a POSTED sale's items and recalculates its totals in
    place - same sale_no/id, not a cancel-and-recreate, so anything
    already referencing this sale (a return, a ledger note) stays
    accurate. sale_type and customer_id are intentionally NOT editable
    here: changing either has knock-on effects (sale_no series, pricing
    basis, credit checks) that are safer handled via cancel_sale +
    create_sale, which already exist for exactly that.

    Stock is reconciled as one net delta per part (old total qty for
    that part across all lines vs new total qty), not a blind
    reverse-everything-then-reapply-everything - so the ledger only
    gets an entry for a part whose quantity actually changed. Still
    goes through stock_service.add_ledger_entry like every other
    movement (see spare_parts/__init__.py), so the negative-stock guard
    applies here too.
    """
    sale = get_sale(db, sale_id)
    if not sale:
        raise SparePartsValidationError(f"Sale id={sale_id} not found.")
    if sale.status != "POSTED":
        raise SparePartsValidationError(f"Only a POSTED sale can be edited (this one is {sale.status}).")

    existing_returns = db.query(SpSaleReturn.id).filter(
        SpSaleReturn.sale_id == sale_id, SpSaleReturn.status == "POSTED"
    ).first()
    if existing_returns:
        raise SparePartsValidationError(
            "This sale already has a return recorded against it and can no "
            "longer be edited, to keep the return's record accurate. "
            "Cancel this sale and enter a corrected one instead."
        )

    validated_items, subtotal = _validate_items(db, items)

    header_discount = to_decimal(discount, "Discount")
    if header_discount < 0:
        raise SparePartsValidationError("Discount cannot be negative.")
    taxable = subtotal - header_discount
    if taxable < 0:
        raise SparePartsValidationError("Discount cannot exceed the subtotal.")

    settings = get_settings(db)
    tax_pct = (
        to_decimal(tax_percent, "Tax %") if tax_percent is not None
        else Decimal(str(settings.default_tax_percent or 0))
    )
    if tax_pct < 0:
        raise SparePartsValidationError("Tax % cannot be negative.")
    tax_amount = (taxable * tax_pct / Decimal("100")).quantize(Decimal("0.01"))
    total = taxable + tax_amount

    paid_amount = to_decimal(paid, "Paid amount")
    if paid_amount < 0:
        raise SparePartsValidationError("Paid amount cannot be negative.")
    due = total - paid_amount

    old_qty_by_part: dict[int, int] = {}
    for old_item in sale.items:
        old_qty_by_part[old_item.part_id] = old_qty_by_part.get(old_item.part_id, 0) + old_item.qty
    new_qty_by_part: dict[int, int] = {}
    for item in validated_items:
        new_qty_by_part[item["part_id"]] = new_qty_by_part.get(item["part_id"], 0) + item["qty"]

    try:
        for old_item in list(sale.items):
            db.delete(old_item)
        db.flush()

        for item in validated_items:
            db.add(SpSaleItem(
                sale_id=sale.id,
                part_id=item["part_id"],
                qty=item["qty"],
                sold_as=item["sold_as"],
                pack_qty=item["qty_entered"] if item["sold_as"] == "PACK" else None,
                unit_price=item["unit_price"],
                discount=item["discount"],
                line_total=item["line_total"],
                cost_price=item["cost_price"],
                # Recomputed from the part's CURRENT warranty_days, same
                # accepted-drift tradeoff as cost_price above - editing an
                # old sale doesn't retroactively know what warranty_days
                # was at the ORIGINAL sale time, only what it is now.
                warranty_expires_at=(
                    sale.sale_date + dt.timedelta(days=item["warranty_days"])
                    if item["warranty_days"] > 0 else None
                ),
            ))

        for part_id in set(old_qty_by_part) | set(new_qty_by_part):
            delta = new_qty_by_part.get(part_id, 0) - old_qty_by_part.get(part_id, 0)
            if delta > 0:
                stock_service.add_ledger_entry(
                    db, part_id=part_id, qty_out=delta,
                    reference_type="SALE_EDIT", reference_id=sale.id,
                    note=f"Edited {sale.sale_no} (+{delta} sold)",
                )
            elif delta < 0:
                stock_service.add_ledger_entry(
                    db, part_id=part_id, qty_in=-delta,
                    reference_type="SALE_EDIT", reference_id=sale.id,
                    note=f"Edited {sale.sale_no} ({-delta} back in stock)",
                )

        sale.subtotal = subtotal
        sale.discount = header_discount
        sale.tax_percent = tax_pct
        sale.tax_amount = tax_amount
        sale.total = total
        sale.paid = paid_amount
        sale.due = due
        sale.payment_method = (payment_method or "Cash").strip() or "Cash"
        sale.notes = (notes or "").strip() or None

        db.commit()
        logger.info(f"Updated sale {sale.sale_no} (id={sale.id}) total={total}")
        return sale
    except Exception:
        db.rollback()
        raise


def cancel_sale(db: Session, sale_id: int, reason: str = "") -> SpSale:
    """Reverses a POSTED sale's stock effect (adds the stock back - this
    can never go negative, unlike cancelling a purchase) and marks it
    CANCELLED."""
    sale = get_sale(db, sale_id)
    if not sale:
        raise SparePartsValidationError(f"Sale id={sale_id} not found.")
    if sale.status == "CANCELLED":
        raise SparePartsValidationError("This sale is already cancelled.")

    try:
        for item in sale.items:
            stock_service.add_ledger_entry(
                db,
                part_id=item.part_id,
                qty_in=item.qty,
                reference_type="SALE_CANCEL",
                reference_id=sale.id,
                note=f"Cancelled {sale.sale_no}" + (f": {reason}" if reason else ""),
            )
        sale.status = "CANCELLED"
        if reason:
            note = f"[Cancelled: {reason}]"
            sale.notes = f"{sale.notes}\n{note}" if sale.notes else note
        db.commit()
        logger.info(f"Cancelled sale {sale.sale_no} (id={sale.id})")
        return sale
    except Exception:
        db.rollback()
        raise


def list_sales(
    db: Session,
    *,
    sale_type: Optional[str] = None,
    customer_id: Optional[int] = None,
    status: Optional[str] = None,
) -> list[SpSale]:
    q = db.query(SpSale)
    if sale_type:
        q = q.filter(SpSale.sale_type == sale_type)
    if customer_id:
        q = q.filter(SpSale.customer_id == customer_id)
    if status:
        q = q.filter(SpSale.status == status)
    return q.order_by(SpSale.sale_date.desc(), SpSale.id.desc()).all()


def get_sale(db: Session, sale_id: int) -> Optional[SpSale]:
    return db.query(SpSale).filter(SpSale.id == sale_id).first()
