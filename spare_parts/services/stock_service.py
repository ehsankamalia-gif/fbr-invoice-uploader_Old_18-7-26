"""Core stock-ledger primitives, shared by every service that moves stock:
purchases, sales, returns, and manual adjustments.

Stock is never stored as a column anywhere - it is always the running
balance of sp_stock_ledger for a part (see spare_parts/__init__.py).
add_ledger_entry() is the ONLY function in this whole module allowed to
write a sp_stock_ledger row; every other service calls it rather than
inserting ledger rows itself, so the negative-stock guard and balance
computation can never be bypassed or duplicated.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from spare_parts.db.models import SpStockLedger
from spare_parts.errors import SparePartsValidationError
from spare_parts.services.settings_service import get_settings
from spare_parts.logging_config import get_logger

logger = get_logger(__name__)


class StockError(SparePartsValidationError):
    """Raised when a stock movement would take a part negative and the
    module setting to allow that is off. Inherits SparePartsValidationError
    (not a bare ValueError) so UI code's `except SparePartsValidationError`
    around a save always catches this too - the same class of bug fixed in
    Phase 2 for parts_service/suppliers_service (see spare_parts/errors.py)."""


def get_current_stock(db: Session, part_id: int) -> int:
    """Current balance for one part. Reads through the caller's session,
    so it sees this transaction's own uncommitted writes too (needed when
    a single save computes several movements for the same part before
    committing)."""
    qty_in_total = db.query(func.coalesce(func.sum(SpStockLedger.qty_in), 0)).filter(
        SpStockLedger.part_id == part_id
    ).scalar()
    qty_out_total = db.query(func.coalesce(func.sum(SpStockLedger.qty_out), 0)).filter(
        SpStockLedger.part_id == part_id
    ).scalar()
    return int(qty_in_total) - int(qty_out_total)


def get_current_stock_bulk(db: Session, part_ids: list[int]) -> dict[int, int]:
    """Current balance for several parts in one query - used by list/report
    screens so they don't run one query per row."""
    if not part_ids:
        return {}
    rows = (
        db.query(
            SpStockLedger.part_id,
            func.coalesce(func.sum(SpStockLedger.qty_in), 0),
            func.coalesce(func.sum(SpStockLedger.qty_out), 0),
        )
        .filter(SpStockLedger.part_id.in_(part_ids))
        .group_by(SpStockLedger.part_id)
        .all()
    )
    balances = {part_id: int(qty_in) - int(qty_out) for part_id, qty_in, qty_out in rows}
    for part_id in part_ids:
        balances.setdefault(part_id, 0)
    return balances


def get_ledger_entries(db: Session, part_id: int) -> list[SpStockLedger]:
    """Full movement history for one part, oldest first - the audit trail
    behind get_current_stock()'s running balance. Read-only; powers the
    "check the stock" Stock Ledger view (see
    spare_parts/ui/stock_ledger_dialog.py) so a current-stock number is
    never just an opaque figure - every purchase/sale/return/adjustment
    that produced it is visible and traceable."""
    return (
        db.query(SpStockLedger)
        .filter(SpStockLedger.part_id == part_id)
        .order_by(SpStockLedger.entry_date, SpStockLedger.id)
        .all()
    )


def add_ledger_entry(
    db: Session,
    *,
    part_id: int,
    qty_in: int = 0,
    qty_out: int = 0,
    reference_type: str,
    reference_id: Optional[int] = None,
    note: str = "",
    entry_date: Optional[dt.datetime] = None,
) -> SpStockLedger:
    """Records one stock movement and returns the new ledger row (not yet
    committed - the caller's transaction decides when to commit/rollback,
    so this can be one of several movements that must all succeed or none
    do). Raises StockError if the resulting balance would be negative and
    sp_settings.allow_negative_stock is False.
    """
    qty_in = max(0, int(qty_in or 0))
    qty_out = max(0, int(qty_out or 0))
    if qty_in == 0 and qty_out == 0:
        raise ValueError("add_ledger_entry requires a non-zero qty_in or qty_out.")

    current_balance = get_current_stock(db, part_id)
    new_balance = current_balance + qty_in - qty_out

    if new_balance < 0:
        settings = get_settings(db)
        if not settings.allow_negative_stock:
            raise StockError(
                f"This movement would take part id={part_id} to a negative "
                f"balance ({new_balance}). Enable 'Allow negative stock' in "
                f"Spare Parts settings to override."
            )

    entry = SpStockLedger(
        part_id=part_id,
        qty_in=qty_in,
        qty_out=qty_out,
        balance=new_balance,
        reference_type=reference_type,
        reference_id=reference_id,
        note=(note or "").strip() or None,
        entry_date=entry_date or dt.datetime.utcnow(),
    )
    db.add(entry)
    db.flush()  # Makes this entry visible to the next get_current_stock()
    # call in the same transaction (e.g. a second line of the same part
    # number in one purchase), without committing the whole transaction.
    logger.debug(
        f"Stock ledger: part_id={part_id} in={qty_in} out={qty_out} "
        f"balance={new_balance} ref={reference_type}:{reference_id}"
    )
    return entry


def create_adjustment(
    db: Session,
    *,
    part_id: int,
    direction: str,
    qty: int,
    reason: str,
    adjustment_date: Optional[dt.datetime] = None,
) -> SpStockLedger:
    """The direct answer to "how do I add/remove quantity for a part":
    unlike a purchase or sale, this is a single manual ledger entry with
    no header/items to build, for things like setting a brand-new part's
    starting quantity or correcting a count after a physical stocktake.
    Still goes through add_ledger_entry like every other movement (see
    spare_parts/__init__.py - stock is never written directly), so the
    negative-stock guard applies here too (raises StockError on OUT past
    zero, same as a sale would).

    direction: "IN" to add stock, "OUT" to remove it. A reason is
    required so the ledger stays a meaningful audit trail rather than a
    column of unexplained numbers.
    """
    direction = (direction or "").upper()
    if direction not in ("IN", "OUT"):
        raise SparePartsValidationError("Direction must be IN or OUT.")
    qty = int(qty or 0)
    if qty <= 0:
        raise SparePartsValidationError("Quantity must be greater than zero.")
    reason = (reason or "").strip()
    if not reason:
        raise SparePartsValidationError("A reason is required for a stock adjustment.")

    try:
        entry = add_ledger_entry(
            db,
            part_id=part_id,
            qty_in=qty if direction == "IN" else 0,
            qty_out=qty if direction == "OUT" else 0,
            reference_type="ADJUSTMENT",
            note=reason,
            entry_date=adjustment_date,
        )
        db.commit()
        logger.info(f"Stock adjustment: part_id={part_id} direction={direction} qty={qty} reason={reason!r}")
        return entry
    except Exception:
        db.rollback()
        raise
