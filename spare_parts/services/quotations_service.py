"""Quotations: a pre-sale price quote - deliberately NOT a stock hold
(no sp_stock_ledger effect, no reservation against other open POS cards
- reusing pos_page.py's reservation subsystem would pull in POS-card-
specific state this doesn't need) and NOT in-place editable once
CONVERTED/CANCELLED, same lock-after-terminal-status convention as
Purchases/Sales.

Converting into a real sale goes through the existing, UNMODIFIED
sales_service.create_sale (convert_to_sale) and HONORS the quoted
unit_price as-is - a quotation is a price commitment, never silently
repriced to whatever the part's current retail_price/wholesale_price
happens to be by the time it's converted. Stock availability is
naturally checked by create_sale's own add_ledger_entry negative-stock
guard - no separate stock re-check is needed here.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from spare_parts.db.models import SpQuotation, SpQuotationItem, SpSale
from spare_parts.errors import SparePartsValidationError
from spare_parts.services import customers_service, parts_service, sales_service
from spare_parts.services.settings_service import get_settings
from spare_parts.utils import to_decimal
from spare_parts.logging_config import get_logger

logger = get_logger(__name__)

VALID_SALE_TYPES = ("RETAIL", "WHOLESALE")
_UNSET = object()


def generate_quote_no(db: Session) -> str:
    """Same count-and-retry pattern as purchase_service.generate_purchase_no."""
    settings = get_settings(db)
    prefix = settings.quotation_no_prefix or "QT-"
    count = db.query(SpQuotation).count()
    for attempt in range(count + 1, count + 1000):
        candidate = f"{prefix}{attempt:04d}"
        exists = db.query(SpQuotation.id).filter(SpQuotation.quote_no == candidate).first()
        if not exists:
            return candidate
    raise SparePartsValidationError("Could not generate a unique quotation number.")


def _validate_items(db: Session, items: list[dict]) -> tuple[list[dict], Decimal]:
    """Same shape as sales_service._validate_items, minus cost_price/
    warranty_days (a quotation never affects COGS or warranty until
    converted, at which point create_sale captures those itself)."""
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
        ))
        subtotal += line_total

    return validated, subtotal


def _compute_totals(db: Session, validated_items, subtotal, discount, tax_percent):
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
    return header_discount, tax_pct, tax_amount, total


def create_quotation(
    db: Session,
    *,
    sale_type: str,
    customer_id: Optional[int] = None,
    walk_in_customer_name: str = "",
    items: list[dict],
    valid_until: Optional[dt.datetime] = None,
    discount=0,
    tax_percent=None,
    notes: str = "",
) -> SpQuotation:
    sale_type = (sale_type or "").upper()
    if sale_type not in VALID_SALE_TYPES:
        raise SparePartsValidationError("Sale type must be RETAIL or WHOLESALE.")

    customer = None
    if customer_id:
        customer = customers_service.get_customer(db, customer_id)
        if not customer or not customer.is_active:
            raise SparePartsValidationError("Select a valid, active customer.")

    validated_items, subtotal = _validate_items(db, items)
    header_discount, tax_pct, tax_amount, total = _compute_totals(
        db, validated_items, subtotal, discount, tax_percent,
    )

    try:
        quotation = SpQuotation(
            quote_no=generate_quote_no(db),
            customer_id=customer.id if customer else None,
            walk_in_customer_name=(
                None if customer else ((walk_in_customer_name or "").strip() or None)
            ),
            sale_type=sale_type,
            quote_date=dt.datetime.utcnow(),
            valid_until=valid_until,
            subtotal=subtotal,
            discount=header_discount,
            tax_percent=tax_pct,
            tax_amount=tax_amount,
            total=total,
            status="DRAFT",
            notes=(notes or "").strip() or None,
        )
        db.add(quotation)
        db.flush()

        for item in validated_items:
            db.add(SpQuotationItem(
                quotation_id=quotation.id,
                part_id=item["part_id"],
                qty=item["qty"],
                sold_as=item["sold_as"],
                pack_qty=item["qty_entered"] if item["sold_as"] == "PACK" else None,
                unit_price=item["unit_price"],
                discount=item["discount"],
                line_total=item["line_total"],
            ))

        db.commit()
        db.refresh(quotation)
        logger.info(f"Created quotation {quotation.quote_no} (id={quotation.id}).")
        return quotation
    except Exception:
        db.rollback()
        raise


def get_quotation(db: Session, quotation_id: int) -> Optional[SpQuotation]:
    return db.query(SpQuotation).filter(SpQuotation.id == quotation_id).first()


def list_quotations(db: Session, status: Optional[str] = None) -> list[SpQuotation]:
    q = db.query(SpQuotation)
    if status:
        q = q.filter(SpQuotation.status == status)
    return q.order_by(SpQuotation.quote_date.desc()).all()


def update_quotation(
    db: Session,
    quotation_id: int,
    *,
    items: list[dict],
    discount=0,
    tax_percent=None,
    notes: str = "",
    valid_until=_UNSET,
) -> SpQuotation:
    """Only while DRAFT - replaces all items and recomputes totals, same
    pattern as sales_service.update_sale but simpler (no stock to
    reconcile, since a quotation never touched it)."""
    quotation = get_quotation(db, quotation_id)
    if not quotation:
        raise SparePartsValidationError(f"Quotation id={quotation_id} not found.")
    if quotation.status != "DRAFT":
        raise SparePartsValidationError(f"Only a DRAFT quotation can be edited (this one is {quotation.status}).")

    validated_items, subtotal = _validate_items(db, items)
    header_discount, tax_pct, tax_amount, total = _compute_totals(
        db, validated_items, subtotal, discount, tax_percent,
    )

    try:
        for old_item in list(quotation.items):
            db.delete(old_item)
        db.flush()

        for item in validated_items:
            db.add(SpQuotationItem(
                quotation_id=quotation.id,
                part_id=item["part_id"],
                qty=item["qty"],
                sold_as=item["sold_as"],
                pack_qty=item["qty_entered"] if item["sold_as"] == "PACK" else None,
                unit_price=item["unit_price"],
                discount=item["discount"],
                line_total=item["line_total"],
            ))

        quotation.subtotal = subtotal
        quotation.discount = header_discount
        quotation.tax_percent = tax_pct
        quotation.tax_amount = tax_amount
        quotation.total = total
        quotation.notes = (notes or "").strip() or None
        if valid_until is not _UNSET:
            quotation.valid_until = valid_until

        db.commit()
        db.refresh(quotation)
        logger.info(f"Updated quotation {quotation.quote_no} (id={quotation.id}).")
        return quotation
    except Exception:
        db.rollback()
        raise


def cancel_quotation(db: Session, quotation_id: int) -> SpQuotation:
    quotation = get_quotation(db, quotation_id)
    if not quotation:
        raise SparePartsValidationError(f"Quotation id={quotation_id} not found.")
    if quotation.status != "DRAFT":
        raise SparePartsValidationError(f"Only a DRAFT quotation can be cancelled (this one is {quotation.status}).")
    quotation.status = "CANCELLED"
    db.commit()
    db.refresh(quotation)
    logger.info(f"Cancelled quotation {quotation.quote_no} (id={quotation.id}).")
    return quotation


def convert_to_sale(
    db: Session,
    quotation_id: int,
    *,
    paid=0,
    payment_method: str = "Cash",
) -> SpSale:
    """Converts a DRAFT quotation into a real POSTED sale - HONORS the
    quoted unit_price verbatim (sales_service._validate_items takes
    unit_price as given, it never re-derives it from the part's current
    price), never silently repricing. Locks the quotation to CONVERTED,
    linked to the resulting sale. Credit-limit checking (for a WHOLESALE
    quotation) is the UI's job, same as SaleCardWidget._check_credit_limit
    wraps customers_service.check_credit_limit before checkout today -
    create_sale itself never blocks on credit by design."""
    quotation = get_quotation(db, quotation_id)
    if not quotation:
        raise SparePartsValidationError(f"Quotation id={quotation_id} not found.")
    if quotation.status != "DRAFT":
        raise SparePartsValidationError(
            f"Only a DRAFT quotation can be converted to a sale (this one is {quotation.status})."
        )

    items = []
    for item in quotation.items:
        qty_entered = item.pack_qty if item.sold_as == "PACK" else item.qty
        items.append(dict(
            part_id=item.part_id, qty_entered=qty_entered, sold_as=item.sold_as,
            unit_price=item.unit_price, discount=item.discount,
        ))

    try:
        sale = sales_service.create_sale(
            db,
            sale_type=quotation.sale_type,
            customer_id=quotation.customer_id,
            walk_in_customer_name=quotation.walk_in_customer_name or "",
            items=items,
            discount=quotation.discount,
            tax_percent=quotation.tax_percent,
            paid=paid,
            payment_method=payment_method,
            notes=f"Converted from quotation {quotation.quote_no}",
        )
        quotation.status = "CONVERTED"
        quotation.converted_sale_id = sale.id
        db.commit()
        db.refresh(quotation)
        logger.info(f"Converted quotation {quotation.quote_no} (id={quotation.id}) to sale {sale.sale_no}.")
        return sale
    except Exception:
        db.rollback()
        raise
