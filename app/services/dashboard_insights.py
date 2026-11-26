"""Numbers behind the Dashboard's new panels (read-only; nothing here changes an invoice).

  * glance():        today / this month totals and what they are compared with
  * daily_series():  one point per day for the sales-trend chart
  * attention():     failed + pending FBR uploads that need a person

"Sales" means every saved invoice (whatever its FBR state) - its date is Invoice.datetime and its value
Invoice.total_amount. The aggregation is done in Python on just two columns, so it behaves the same on
MySQL and SQLite (no date functions that differ between them).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import case

PENDING, FAILED = "PENDING", "FAILED"


@dataclass(frozen=True)
class Period:
    count: int = 0
    amount: float = 0.0


@dataclass(frozen=True)
class DayPoint:
    day: dt.date
    count: int
    amount: float


@dataclass(frozen=True)
class Trend:
    """How `current` compares with `previous`. direction: up / down / flat / new (previous was 0)."""
    direction: str
    pct: Optional[float] = None


@dataclass(frozen=True)
class AttentionRow:
    invoice_id: int
    invoice_number: str
    buyer: str
    amount: float
    status: str                 # FAILED | PENDING
    message: str
    attempts: int
    when: Optional[dt.datetime]


@dataclass(frozen=True)
class Attention:
    failed: int = 0
    pending: int = 0
    rows: list = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.failed + self.pending


def _midnight(day: dt.date) -> dt.datetime:
    return dt.datetime.combine(day, dt.time.min)


def period_totals(db, start: dt.datetime, end: dt.datetime) -> Period:
    """Invoices with start <= datetime < end."""
    from app.db.models import Invoice

    rows = (
        db.query(Invoice.total_amount)
        .filter(Invoice.datetime >= start, Invoice.datetime < end)
        .all()
    )
    return Period(count=len(rows), amount=float(sum(float(r[0] or 0) for r in rows)))


def trend(current: float, previous: float) -> Trend:
    if previous == 0:
        return Trend("new") if current > 0 else Trend("flat")
    pct = (current - previous) / previous * 100.0
    if abs(pct) < 0.05:
        return Trend("flat", 0.0)
    return Trend("up" if pct > 0 else "down", pct)


def glance(db, now: Optional[dt.datetime] = None) -> dict:
    """Today vs yesterday, and this month so far vs the same number of days last month."""
    now = now or dt.datetime.now()
    today = now.date()
    yesterday = today - dt.timedelta(days=1)
    first_this = today.replace(day=1)
    first_prev = (first_this - dt.timedelta(days=1)).replace(day=1)
    # same span last month: days 1..today.day, but never running into this month
    prev_end = min(_midnight(first_prev) + dt.timedelta(days=today.day), _midnight(first_this))
    return {
        "today": period_totals(db, _midnight(today), _midnight(today + dt.timedelta(days=1))),
        "yesterday": period_totals(db, _midnight(yesterday), _midnight(today)),
        "month": period_totals(db, _midnight(first_this), _midnight(today + dt.timedelta(days=1))),
        "last_month_same_span": period_totals(db, _midnight(first_prev), prev_end),
    }


def daily_series(db, days: int, today: Optional[dt.date] = None) -> list[DayPoint]:
    """One point per day for the last `days` days, oldest first, today last; days with no sales are zero."""
    from app.db.models import Invoice

    days = max(1, int(days))
    today = today or dt.date.today()
    first = today - dt.timedelta(days=days - 1)
    rows = (
        db.query(Invoice.datetime, Invoice.total_amount)
        .filter(Invoice.datetime >= _midnight(first), Invoice.datetime < _midnight(today + dt.timedelta(days=1)))
        .all()
    )
    counts: dict[dt.date, int] = {}
    amounts: dict[dt.date, float] = {}
    for when, total in rows:
        if when is None:
            continue
        day = when.date()
        counts[day] = counts.get(day, 0) + 1
        amounts[day] = amounts.get(day, 0.0) + float(total or 0)
    return [
        DayPoint(day=first + dt.timedelta(days=i), count=counts.get(first + dt.timedelta(days=i), 0),
                 amount=amounts.get(first + dt.timedelta(days=i), 0.0))
        for i in range(days)
    ]


def attention(db, limit: int = 6) -> Attention:
    """Invoices FBR has not accepted: FAILED ones first, then pending, oldest first within each.
    The pending count uses the same rule as the Dashboard's Pending card and the Pending list."""
    from app.db.models import Customer, Invoice

    not_uploaded = Invoice.fbr_invoice_number == None  # noqa: E711
    failed = db.query(Invoice).filter(not_uploaded, Invoice.sync_status == FAILED).count()
    pending = db.query(Invoice).filter(
        not_uploaded, (Invoice.sync_status == None) | (Invoice.sync_status != FAILED)  # noqa: E711
    ).count()

    rows = (
        db.query(Invoice.id, Invoice.invoice_number, Customer.name, Invoice.total_amount, Invoice.sync_status,
                 Invoice.fbr_response_message, Invoice.upload_attempts, Invoice.datetime)
        .outerjoin(Customer, Invoice.customer_id == Customer.id)
        .filter(not_uploaded)
        .order_by(case((Invoice.sync_status == FAILED, 0), else_=1), Invoice.datetime.asc(), Invoice.id.asc())
        .limit(max(0, int(limit)))
        .all()
    )
    return Attention(
        failed=failed,
        pending=pending,
        rows=[
            AttentionRow(
                invoice_id=r[0], invoice_number=r[1] or "", buyer=r[2] or "", amount=float(r[3] or 0),
                status=FAILED if r[4] == FAILED else PENDING, message=r[5] or "", attempts=int(r[6] or 0), when=r[7],
            )
            for r in rows
        ],
    )
