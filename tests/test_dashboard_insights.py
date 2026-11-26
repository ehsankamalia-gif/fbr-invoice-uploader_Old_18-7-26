"""Numbers behind the Dashboard's new panels."""
import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, Customer, Invoice
from app.qt_ui import invoice_list_dialog as ild
from app.services import dashboard_insights as di

NOW = dt.datetime(2026, 11, 27, 15, 0)        # a Friday


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _inv(db, number, when, amount=1000.0, fbr=None, sync="PENDING", buyer="ALI", message=None, attempts=0):
    cust = db.query(Customer).filter_by(cnic=f"c-{buyer}").first()
    if cust is None:
        cust = Customer(cnic=f"c-{buyer}", name=buyer)
        db.add(cust)
        db.flush()
    db.add(Invoice(invoice_number=number, pos_id="1", usin=number, datetime=when, customer_id=cust.id,
                   total_sale_value=amount, total_tax_charged=0.0, total_quantity=1.0, total_amount=amount,
                   fbr_invoice_number=fbr, sync_status=sync, fbr_response_message=message, upload_attempts=attempts))
    db.commit()


# ---- trend ------------------------------------------------------------------------------------
def test_trend_directions():
    assert di.trend(150, 100) == di.Trend("up", 50.0)
    assert di.trend(50, 100) == di.Trend("down", -50.0)
    assert di.trend(100, 100).direction == "flat"
    assert di.trend(5, 0) == di.Trend("new")
    assert di.trend(0, 0).direction == "flat"


# ---- today / month --------------------------------------------------------------------------------
def test_glance_today_vs_yesterday(db):
    _inv(db, "T1", dt.datetime(2026, 11, 27, 0, 0, 0), 100)           # first second of today
    _inv(db, "T2", dt.datetime(2026, 11, 27, 23, 59, 59), 200)        # last second of today
    _inv(db, "Y1", dt.datetime(2026, 11, 26, 12, 0), 500)
    _inv(db, "TOMORROW", dt.datetime(2026, 11, 28, 0, 0, 0), 9999)    # never counted
    g = di.glance(db, NOW)
    assert g["today"] == di.Period(2, 300.0)
    assert g["yesterday"] == di.Period(1, 500.0)


def test_glance_counts_every_saved_invoice_whatever_its_fbr_state(db):
    _inv(db, "A", dt.datetime(2026, 11, 27, 9, 0), 100, fbr="F1", sync="SYNCED")
    _inv(db, "B", dt.datetime(2026, 11, 27, 9, 5), 100, sync="PENDING")
    _inv(db, "C", dt.datetime(2026, 11, 27, 9, 6), 100, sync="FAILED")
    assert di.glance(db, NOW)["today"].count == 3


def test_month_to_date_is_compared_with_the_same_span_last_month(db):
    _inv(db, "N1", dt.datetime(2026, 11, 1, 8, 0), 100)
    _inv(db, "N2", dt.datetime(2026, 11, 27, 8, 0), 100)
    _inv(db, "O1", dt.datetime(2026, 10, 1, 8, 0), 400)               # inside Oct 1..27
    _inv(db, "O2", dt.datetime(2026, 10, 27, 20, 0), 400)             # still inside
    _inv(db, "O3", dt.datetime(2026, 10, 28, 8, 0), 7777)             # after the 27th: not comparable yet
    _inv(db, "S1", dt.datetime(2026, 9, 30, 8, 0), 5555)              # two months ago
    g = di.glance(db, NOW)
    assert g["month"] == di.Period(2, 200.0)
    assert g["last_month_same_span"] == di.Period(2, 800.0)


def test_month_comparison_never_runs_into_the_current_month(db):
    now = dt.datetime(2026, 3, 31, 10, 0)                              # February has only 28 days
    _inv(db, "F1", dt.datetime(2026, 2, 28, 12, 0), 100)
    _inv(db, "M1", dt.datetime(2026, 3, 1, 0, 0, 1), 50)               # March: must not leak into "last month"
    g = di.glance(db, now)
    assert g["last_month_same_span"] == di.Period(1, 100.0)
    assert g["month"] == di.Period(1, 50.0)


def test_january_looks_back_to_december(db):
    now = dt.datetime(2026, 1, 15, 10, 0)
    _inv(db, "D1", dt.datetime(2025, 12, 10, 9, 0), 300)
    assert di.glance(db, now)["last_month_same_span"] == di.Period(1, 300.0)


def test_empty_database_gives_zeroes(db):
    g = di.glance(db, NOW)
    assert all(v == di.Period(0, 0.0) for v in g.values())


# ---- the trend series ---------------------------------------------------------------------------------
def test_daily_series_has_one_point_per_day_oldest_first_with_zero_days(db):
    _inv(db, "D1", dt.datetime(2026, 11, 27, 10, 0), 100)
    _inv(db, "D2", dt.datetime(2026, 11, 27, 11, 0), 50)
    _inv(db, "D3", dt.datetime(2026, 11, 24, 11, 0), 70)
    series = di.daily_series(db, 7, dt.date(2026, 11, 27))
    assert [p.day for p in series] == [dt.date(2026, 11, 21) + dt.timedelta(days=i) for i in range(7)]
    by_day = {p.day: p for p in series}
    assert by_day[dt.date(2026, 11, 27)] == di.DayPoint(dt.date(2026, 11, 27), 2, 150.0)
    assert by_day[dt.date(2026, 11, 24)].amount == 70.0
    assert by_day[dt.date(2026, 11, 25)] == di.DayPoint(dt.date(2026, 11, 25), 0, 0.0)


def test_daily_series_window_edges(db):
    _inv(db, "IN-FIRST", dt.datetime(2026, 11, 21, 0, 0, 0), 10)       # first second of the window
    _inv(db, "OUT-BEFORE", dt.datetime(2026, 11, 20, 23, 59, 59), 99)
    _inv(db, "OUT-AFTER", dt.datetime(2026, 11, 28, 0, 0, 0), 99)
    series = di.daily_series(db, 7, dt.date(2026, 11, 27))
    assert sum(p.amount for p in series) == 10.0 and sum(p.count for p in series) == 1


def test_daily_series_thirty_days_and_minimum_one(db):
    assert len(di.daily_series(db, 30, dt.date(2026, 11, 27))) == 30
    assert len(di.daily_series(db, 0, dt.date(2026, 11, 27))) == 1


# ---- needs attention ------------------------------------------------------------------------------------
def test_attention_lists_failed_first_then_pending_oldest_first(db):
    _inv(db, "P-OLD", dt.datetime(2026, 11, 1, 9, 0), sync="PENDING", message="Network Error", attempts=3)
    _inv(db, "P-NEW", dt.datetime(2026, 11, 20, 9, 0), sync="PENDING")
    _inv(db, "F-NEW", dt.datetime(2026, 11, 25, 9, 0), sync="FAILED", message="Invalid Invoice Type")
    _inv(db, "F-OLD", dt.datetime(2026, 11, 2, 9, 0), sync="FAILED")
    _inv(db, "DONE", dt.datetime(2026, 11, 3, 9, 0), fbr="X", sync="SYNCED")
    a = di.attention(db)
    assert (a.failed, a.pending, a.total) == (2, 2, 4)
    assert [r.invoice_number for r in a.rows] == ["F-OLD", "F-NEW", "P-OLD", "P-NEW"]
    assert [r.status for r in a.rows] == ["FAILED", "FAILED", "PENDING", "PENDING"]
    old = a.rows[2]
    assert old.message == "Network Error" and old.attempts == 3 and old.buyer == "ALI"


def test_attention_limit_keeps_the_full_counts(db):
    for i in range(9):
        _inv(db, f"P{i}", dt.datetime(2026, 11, 1 + i, 9, 0))
    a = di.attention(db, limit=6)
    assert len(a.rows) == 6 and a.pending == 9


def test_attention_pending_count_equals_the_pending_list_and_the_ball(db):
    _inv(db, "A", dt.datetime(2026, 11, 1, 9, 0), sync="PENDING")
    _inv(db, "B", dt.datetime(2026, 11, 2, 9, 0), sync=None)            # old row with no status counts as pending
    _inv(db, "C", dt.datetime(2026, 11, 3, 9, 0), sync="FAILED")
    _inv(db, "D", dt.datetime(2026, 11, 4, 9, 0), fbr="Z", sync="SYNCED")
    assert di.attention(db).pending == ild.count_pending(db) == len(ild.fetch_pending_invoices(db)) == 2


def test_attention_when_everything_is_uploaded(db):
    _inv(db, "OK", dt.datetime(2026, 11, 3, 9, 0), fbr="Z", sync="SYNCED")
    a = di.attention(db)
    assert a.total == 0 and a.rows == []


def test_attention_handles_a_missing_buyer_and_message(db):
    db.add(Invoice(invoice_number="NOBUYER", pos_id="1", usin="N", datetime=dt.datetime(2026, 11, 3, 9, 0),
                   total_sale_value=1.0, total_tax_charged=0.0, total_quantity=1.0, total_amount=1.0,
                   fbr_invoice_number=None, sync_status="PENDING"))
    db.commit()
    row = di.attention(db).rows[0]
    assert row.buyer == "" and row.message == "" and row.amount == 1.0
