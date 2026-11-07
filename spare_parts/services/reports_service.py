"""Read-only reporting/aggregation for Phase 5: stock valuation + low
stock, sales/purchases totals over a date range, receivables & payables,
and the dashboard summary that stitches all of these together.

Every function here only reads what the other services already wrote -
nothing in this module performs a write.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from spare_parts.db.models import SpCustomer, SpPart, SpPurchase, SpSale, SpSaleItem
from spare_parts.services import customers_service, parts_service, purchase_service, sales_service, stock_service, suppliers_service

PERIOD_DAILY = "DAILY"
PERIOD_MONTHLY = "MONTHLY"
PERIOD_QUARTERLY = "QUARTERLY"
PERIOD_CUSTOM = "CUSTOM"
VALID_PROFIT_PERIODS = (PERIOD_DAILY, PERIOD_MONTHLY, PERIOD_QUARTERLY, PERIOD_CUSTOM)


def profit_period_range(period: str, *, reference_date: Optional[dt.date] = None) -> tuple[dt.datetime, dt.datetime]:
    """Returns (date_from, date_to) covering the whole DAILY/MONTHLY/
    QUARTERLY period that reference_date (default: today) falls in, each
    inclusive of its first and last instant. CUSTOM has no computed
    range - the caller supplies its own date_from/date_to in that case,
    this is only for the three quick-filter presets."""
    today = reference_date or dt.date.today()
    period = (period or "").upper()
    if period == PERIOD_DAILY:
        start, end = today, today
    elif period == PERIOD_MONTHLY:
        start = today.replace(day=1)
        end = (start.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
    elif period == PERIOD_QUARTERLY:
        quarter_start_month = ((today.month - 1) // 3) * 3 + 1
        start = today.replace(month=quarter_start_month, day=1)
        end_month = quarter_start_month + 2
        if end_month > 12:  # pragma: no cover - quarter_start_month caps at 10, so end_month caps at 12
            end_month -= 12
        end = (start.replace(month=end_month, day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
    else:
        raise ValueError(f"profit_period_range only computes DAILY/MONTHLY/QUARTERLY, not {period!r}.")
    return dt.datetime.combine(start, dt.time.min), dt.datetime.combine(end, dt.time.max)


def get_stock_report(
    db: Session, *, query: str = "", low_stock_only: bool = False, active_only: bool = True
) -> list[dict]:
    """One row per part: {part, current_stock, stock_value, is_low}.
    stock_value = current_stock * part.cost_price (today's valuation, not
    a historical-cost/profit figure - see the Phase 5 summary for why a
    margin report isn't included: per-sale cost isn't captured at sale
    time, only the part's current cost_price). `query` filters by part
    no/name/barcode/compatible model, same matching as the Parts page."""
    parts = parts_service.search_parts(db, query=query, active_only=active_only)
    stock_by_id = stock_service.get_current_stock_bulk(db, [p.id for p in parts])

    rows = []
    for part in parts:
        qty = stock_by_id.get(part.id, 0)
        value = Decimal(str(part.cost_price or 0)) * qty
        is_low = qty <= (part.reorder_level or 0)
        if low_stock_only and not is_low:
            continue
        rows.append(dict(part=part, current_stock=qty, stock_value=value, is_low=is_low))

    rows.sort(key=lambda r: r["part"].name)
    return rows


def get_reorder_suggestions(db: Session) -> list[dict]:
    """One row per active part at/below its reorder_level: {part,
    current_stock, reorder_level, suggested_qty}. suggested_qty is how
    much to bring stock back up to - part.reorder_qty if the user set
    one, else just reorder_level itself. Feeds the Reports > Reorder
    Suggestions tab's "Create Purchase from Selected" action."""
    low_stock_rows = get_stock_report(db, low_stock_only=True)
    rows = []
    for entry in low_stock_rows:
        part = entry["part"]
        target = part.reorder_qty or part.reorder_level or 0
        suggested_qty = max(target - entry["current_stock"], 0)
        rows.append(dict(
            part=part, current_stock=entry["current_stock"],
            reorder_level=part.reorder_level, suggested_qty=suggested_qty,
        ))
    return rows


def _empty_totals() -> dict:
    return dict(
        count=0, subtotal=Decimal("0"), discount=Decimal("0"), tax_amount=Decimal("0"),
        total=Decimal("0"), paid=Decimal("0"), due=Decimal("0"),
    )


def get_sales_report(
    db: Session,
    *,
    date_from: Optional[dt.datetime] = None,
    date_to: Optional[dt.datetime] = None,
    sale_type: Optional[str] = None,
) -> dict:
    """{rows: [SpSale...], totals: {count, subtotal, discount, tax_amount,
    total, paid, due}} for POSTED sales in [date_from, date_to] (inclusive
    on both ends - pass a date_to with time 23:59:59 to include that whole
    day)."""
    q = db.query(SpSale).filter(SpSale.status == "POSTED")
    if date_from is not None:
        q = q.filter(SpSale.sale_date >= date_from)
    if date_to is not None:
        q = q.filter(SpSale.sale_date <= date_to)
    if sale_type:
        q = q.filter(SpSale.sale_type == sale_type)
    rows = q.order_by(SpSale.sale_date).all()

    totals = _empty_totals()
    totals["count"] = len(rows)
    for sale in rows:
        totals["subtotal"] += Decimal(str(sale.subtotal))
        totals["discount"] += Decimal(str(sale.discount))
        totals["tax_amount"] += Decimal(str(sale.tax_amount))
        totals["total"] += Decimal(str(sale.total))
        totals["paid"] += Decimal(str(sale.paid))
        totals["due"] += Decimal(str(sale.due))
    return dict(rows=rows, totals=totals)


def get_profit_report(
    db: Session,
    *,
    date_from: Optional[dt.datetime] = None,
    date_to: Optional[dt.datetime] = None,
) -> dict:
    """Gross profit (Revenue - COGS) for POSTED sales in [date_from,
    date_to] (inclusive on both ends, same convention as
    get_sales_report).

    Revenue per sale = subtotal - discount (i.e. the net sale value
    BEFORE tax - tax collected is passed on to FBR, not business income,
    so it is deliberately excluded from profit).

    COGS per sale = sum over its items of qty * cost_price, using each
    item's OWN cost_price snapshot (the part's cost_price at the moment
    it was sold - see SpSaleItem.cost_price / sales_service.create_sale)
    where available. A sale item saved before that column existed has
    cost_price=NULL; such lines fall back to the part's CURRENT
    cost_price as a best-effort estimate, and `has_estimated_cost` is
    set on that row (and `estimated_rows_count` in totals) so the UI can
    flag that the figure isn't exact.

    Returns {rows: [{sale, revenue, cogs, gross_profit, margin_pct,
    has_estimated_cost}, ...], totals: {count, revenue, cogs,
    gross_profit, margin_pct, estimated_rows_count}}.
    """
    q = db.query(SpSale).filter(SpSale.status == "POSTED")
    if date_from is not None:
        q = q.filter(SpSale.sale_date >= date_from)
    if date_to is not None:
        q = q.filter(SpSale.sale_date <= date_to)
    sales = q.order_by(SpSale.sale_date).all()

    rows = []
    total_revenue = Decimal("0")
    total_cogs = Decimal("0")
    estimated_rows_count = 0
    for sale in sales:
        revenue = Decimal(str(sale.subtotal)) - Decimal(str(sale.discount))
        cogs = Decimal("0")
        has_estimated_cost = False
        for item in sale.items:
            if item.cost_price is not None:
                unit_cost = Decimal(str(item.cost_price))
            else:
                has_estimated_cost = True
                unit_cost = Decimal(str(item.part.cost_price or 0)) if item.part else Decimal("0")
            cogs += unit_cost * item.qty
        gross_profit = revenue - cogs
        margin_pct = (gross_profit / revenue * 100) if revenue > 0 else Decimal("0")

        rows.append(dict(
            sale=sale, revenue=revenue, cogs=cogs, gross_profit=gross_profit,
            margin_pct=margin_pct, has_estimated_cost=has_estimated_cost,
        ))
        total_revenue += revenue
        total_cogs += cogs
        if has_estimated_cost:
            estimated_rows_count += 1

    total_gross_profit = total_revenue - total_cogs
    total_margin_pct = (total_gross_profit / total_revenue * 100) if total_revenue > 0 else Decimal("0")

    return dict(
        rows=rows,
        totals=dict(
            count=len(sales), revenue=total_revenue, cogs=total_cogs,
            gross_profit=total_gross_profit, margin_pct=total_margin_pct,
            estimated_rows_count=estimated_rows_count,
        ),
    )


def get_purchases_report(
    db: Session,
    *,
    date_from: Optional[dt.datetime] = None,
    date_to: Optional[dt.datetime] = None,
    supplier_id: Optional[int] = None,
) -> dict:
    """Symmetric to get_sales_report, for POSTED purchases."""
    q = db.query(SpPurchase).filter(SpPurchase.status == "POSTED")
    if date_from is not None:
        q = q.filter(SpPurchase.purchase_date >= date_from)
    if date_to is not None:
        q = q.filter(SpPurchase.purchase_date <= date_to)
    if supplier_id:
        q = q.filter(SpPurchase.supplier_id == supplier_id)
    rows = q.order_by(SpPurchase.purchase_date).all()

    totals = _empty_totals()
    totals["count"] = len(rows)
    for purchase in rows:
        totals["subtotal"] += Decimal(str(purchase.subtotal))
        totals["discount"] += Decimal(str(purchase.discount))
        totals["total"] += Decimal(str(purchase.total))
        totals["paid"] += Decimal(str(purchase.paid))
        totals["due"] += Decimal(str(purchase.due))
    return dict(rows=rows, totals=totals)


def get_receivables_payables_report(db: Session) -> dict:
    """{receivables: [{party, balance}...], total_receivables,
    payables: [{party, balance}...], total_payables} - only parties with
    a positive outstanding balance are included, sorted highest first."""
    receivables = []
    for customer in customers_service.list_customers(db, active_only=False):
        balance = customers_service.get_customer_outstanding(db, customer.id)
        if balance > 0:
            receivables.append(dict(party=customer, balance=balance))
    receivables.sort(key=lambda r: r["balance"], reverse=True)

    payables = []
    for supplier in suppliers_service.list_suppliers(db, active_only=False):
        balance = suppliers_service.get_supplier_outstanding(db, supplier.id)
        if balance > 0:
            payables.append(dict(party=supplier, balance=balance))
    payables.sort(key=lambda r: r["balance"], reverse=True)

    return dict(
        receivables=receivables,
        total_receivables=sum((r["balance"] for r in receivables), Decimal("0")),
        payables=payables,
        total_payables=sum((p["balance"] for p in payables), Decimal("0")),
    )


def search_warranty(db: Session, query: str = "") -> list[dict]:
    """One row per sold line that carries a warranty (warranty_expires_at
    is not NULL), newest sale first: {sale, item, part, customer_name,
    warranty_expires_at, is_active}. `query` matches part no/name, sale
    no, or customer name (registered or walk-in) - blank returns every
    warrantied line. Only POSTED sales are included (a cancelled sale's
    warranty is moot)."""
    q = (
        db.query(SpSaleItem)
        .join(SpSale, SpSale.id == SpSaleItem.sale_id)
        .join(SpPart, SpPart.id == SpSaleItem.part_id)
        .outerjoin(SpCustomer, SpCustomer.id == SpSale.customer_id)
        .filter(SpSale.status == "POSTED")
        .filter(SpSaleItem.warranty_expires_at.isnot(None))
    )
    query = (query or "").strip()
    if query:
        like = f"%{query}%"
        q = q.filter(or_(
            SpPart.part_no.ilike(like),
            SpPart.name.ilike(like),
            SpSale.sale_no.ilike(like),
            SpCustomer.name.ilike(like),
            SpSale.walk_in_customer_name.ilike(like),
        ))
    items = q.order_by(SpSale.sale_date.desc()).all()

    now = dt.datetime.utcnow()
    rows = []
    for item in items:
        sale = item.sale
        customer_name = sale.customer.name if sale.customer else (sale.walk_in_customer_name or "Walk-in")
        rows.append(dict(
            sale=sale, item=item, part=item.part, customer_name=customer_name,
            warranty_expires_at=item.warranty_expires_at,
            is_active=item.warranty_expires_at >= now,
        ))
    return rows


def get_dashboard_summary(db: Session, *, recent_limit: int = 5) -> dict:
    """Everything the Dashboard page needs in one call."""
    today_start = dt.datetime.combine(dt.date.today(), dt.time.min)
    today_end = dt.datetime.combine(dt.date.today(), dt.time.max)

    stock_rows = get_stock_report(db)
    total_stock_value = sum((r["stock_value"] for r in stock_rows), Decimal("0"))
    low_stock_rows = [r for r in stock_rows if r["is_low"]]

    today_sales = get_sales_report(db, date_from=today_start, date_to=today_end)
    today_purchases = get_purchases_report(db, date_from=today_start, date_to=today_end)
    rp = get_receivables_payables_report(db)

    return dict(
        total_parts=len(stock_rows),
        total_stock_value=total_stock_value,
        low_stock_rows=low_stock_rows,
        today_sales_count=today_sales["totals"]["count"],
        today_sales_total=today_sales["totals"]["total"],
        today_purchases_count=today_purchases["totals"]["count"],
        today_purchases_total=today_purchases["totals"]["total"],
        total_receivables=rp["total_receivables"],
        total_payables=rp["total_payables"],
        recent_sales=sales_service.list_sales(db)[:recent_limit],
        recent_purchases=purchase_service.list_purchases(db)[:recent_limit],
    )
