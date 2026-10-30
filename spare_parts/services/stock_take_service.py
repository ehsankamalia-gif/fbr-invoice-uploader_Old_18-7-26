"""Stock Take: a formal physical-count reconciliation, instead of one
part-at-a-time adjustment.

Freeze a system_qty snapshot per part when the count starts
(create_stock_take), enter counted_qty per line over time while DRAFT
(update_counted_qty), then post once (post_stock_take) - which is the
ONLY thing here that actually writes to sp_stock_ledger, via
stock_service.add_ledger_entry directly (never
stock_service.create_adjustment - that function commits/rolls back per
call with no reference_id, which is right for its own callers, the
single-part dialog and the per-row-tolerant CSV importer, but wrong
here: posting a stock take needs the same all-or-nothing atomicity as
create_sale/create_purchase, and a traceable reference_type/reference_id
pointing back at the stock take, same as "PURCHASE"/"SALE" already do).

No in-place edit once POSTED - same cancel-and-reenter convention as
Purchases/Sales.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy.orm import Session

from spare_parts.db.models import SpStockTake, SpStockTakeItem
from spare_parts.errors import SparePartsValidationError
from spare_parts.services import parts_service, stock_service
from spare_parts.services.settings_service import get_settings
from spare_parts.logging_config import get_logger

logger = get_logger(__name__)


def generate_stock_take_no(db: Session) -> str:
    """Same count-and-retry pattern as purchase_service.generate_purchase_no."""
    settings = get_settings(db)
    prefix = settings.stock_take_no_prefix or "ST-"
    count = db.query(SpStockTake).count()
    for attempt in range(count + 1, count + 1000):
        candidate = f"{prefix}{attempt:04d}"
        exists = db.query(SpStockTake.id).filter(SpStockTake.take_no == candidate).first()
        if not exists:
            return candidate
    raise SparePartsValidationError("Could not generate a unique stock take number.")


def create_stock_take(
    db: Session,
    *,
    category_id: Optional[int] = None,
    brand_id: Optional[int] = None,
    query: str = "",
    notes: str = "",
) -> SpStockTake:
    """Snapshots system_qty for every active part matching the optional
    category/brand/query filter (omit all three to count every active
    part) into a new DRAFT stock take. Raises if the filter matches no
    parts - an empty count sheet is never useful."""
    parts = parts_service.search_parts(
        db, query=query, category_id=category_id, brand_id=brand_id, active_only=True,
    )
    if not parts:
        raise SparePartsValidationError("No active parts match this filter - nothing to count.")

    stock_by_id = stock_service.get_current_stock_bulk(db, [p.id for p in parts])

    try:
        stock_take = SpStockTake(
            take_no=generate_stock_take_no(db),
            take_date=dt.datetime.utcnow(),
            status="DRAFT",
            notes=(notes or "").strip() or None,
        )
        db.add(stock_take)
        db.flush()

        for part in parts:
            db.add(SpStockTakeItem(
                stock_take_id=stock_take.id,
                part_id=part.id,
                system_qty=stock_by_id.get(part.id, 0),
                counted_qty=None,
            ))

        db.commit()
        db.refresh(stock_take)
        logger.info(f"Created stock take {stock_take.take_no} (id={stock_take.id}) with {len(parts)} part(s).")
        return stock_take
    except Exception:
        db.rollback()
        raise


def get_stock_take(db: Session, stock_take_id: int) -> Optional[SpStockTake]:
    return db.query(SpStockTake).filter(SpStockTake.id == stock_take_id).first()


def list_stock_takes(db: Session) -> list[SpStockTake]:
    return db.query(SpStockTake).order_by(SpStockTake.take_date.desc()).all()


def update_counted_qty(db: Session, item_id: int, counted_qty: Optional[int]) -> SpStockTakeItem:
    """Edits one line's counted quantity while its stock take is still
    DRAFT. counted_qty=None means "not counted yet" (back to blank)."""
    item = db.query(SpStockTakeItem).filter(SpStockTakeItem.id == item_id).first()
    if not item:
        raise SparePartsValidationError(f"Stock take item id={item_id} not found.")
    if item.stock_take.status != "DRAFT":
        raise SparePartsValidationError("Only a DRAFT stock take can be edited.")
    if counted_qty is not None:
        counted_qty = int(counted_qty)
        if counted_qty < 0:
            raise SparePartsValidationError("Counted quantity cannot be negative.")
    item.counted_qty = counted_qty
    db.commit()
    db.refresh(item)
    return item


def post_stock_take(db: Session, stock_take_id: int) -> dict:
    """Posts every counted line's variance (counted_qty - system_qty) as
    one ADJUSTMENT-equivalent stock ledger entry each, all inside ONE
    transaction (all-or-nothing, unlike stock_service.create_adjustment's
    per-call commit), then locks the stock take to POSTED.

    Before posting, re-reads each item's LIVE current stock and compares
    it to the system_qty snapshot - if stock moved (a sale/purchase
    happened elsewhere while this stayed DRAFT), that part's drift is
    collected as a non-blocking warning for the caller to show, but the
    posted diff is always counted_qty - system_qty (the snapshot), which
    is the structurally correct formula regardless of drift - NOT a
    re-check against live stock.

    Returns {"stock_take": SpStockTake, "adjusted_count": int,
    "drift_warnings": [str, ...]}."""
    stock_take = get_stock_take(db, stock_take_id)
    if not stock_take:
        raise SparePartsValidationError(f"Stock take id={stock_take_id} not found.")
    if stock_take.status != "DRAFT":
        raise SparePartsValidationError(f"Only a DRAFT stock take can be posted (this one is {stock_take.status}).")

    items_to_post = [item for item in stock_take.items if item.counted_qty is not None]
    if not items_to_post:
        raise SparePartsValidationError("Enter a counted quantity for at least one part before posting.")

    try:
        drift_warnings = []
        adjusted_count = 0
        for item in items_to_post:
            live_qty = stock_service.get_current_stock(db, item.part_id)
            if live_qty != item.system_qty:
                part = item.part
                drift_warnings.append(
                    f"{part.part_no} - {part.name}: stock changed by "
                    f"{live_qty - item.system_qty:+d} unit(s) since this count started "
                    f"(was {item.system_qty}, now {live_qty}) - consider re-counting it."
                )

            diff = item.counted_qty - item.system_qty
            if diff == 0:
                continue
            stock_service.add_ledger_entry(
                db,
                part_id=item.part_id,
                qty_in=diff if diff > 0 else 0,
                qty_out=-diff if diff < 0 else 0,
                reference_type="STOCK_TAKE",
                reference_id=stock_take.id,
                note=f"Stock Take {stock_take.take_no}",
            )
            adjusted_count += 1

        stock_take.status = "POSTED"
        db.commit()
        db.refresh(stock_take)
        logger.info(
            f"Posted stock take {stock_take.take_no} (id={stock_take.id}): "
            f"{adjusted_count} adjustment(s), {len(drift_warnings)} drift warning(s)."
        )
        return dict(stock_take=stock_take, adjusted_count=adjusted_count, drift_warnings=drift_warnings)
    except Exception:
        db.rollback()
        raise


def cancel_stock_take(db: Session, stock_take_id: int) -> SpStockTake:
    """Only while DRAFT - a POSTED stock take already changed real stock
    and can't be un-posted (same as Purchases/Sales: cancel the
    resulting adjustments individually if a POSTED stock take turns out
    to have been wrong, rather than trying to reverse the whole thing)."""
    stock_take = get_stock_take(db, stock_take_id)
    if not stock_take:
        raise SparePartsValidationError(f"Stock take id={stock_take_id} not found.")
    if stock_take.status != "DRAFT":
        raise SparePartsValidationError("Only a DRAFT stock take can be cancelled.")
    db.delete(stock_take)
    db.commit()
    logger.info(f"Cancelled (deleted) DRAFT stock take id={stock_take_id}.")
    return stock_take
