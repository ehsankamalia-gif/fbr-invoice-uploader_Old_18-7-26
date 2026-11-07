"""Unit tests for spare_parts.services.reports_service: stock valuation,
sales/purchases totals over a date range, receivables & payables, and
the dashboard summary rollup.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from spare_parts.db.base import SpareBase
from spare_parts.db import models  # noqa: F401
from spare_parts.services import (
    customers_service,
    parts_service,
    payments_service,
    purchase_service,
    reports_service,
    sales_service,
    stock_service,
    suppliers_service,
)


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SpareBase.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()
    engine.dispose()


# --- stock report ------------------------------------------------------

def test_stock_report_computes_value_and_low_stock_flag(db_session):
    low_part = parts_service.create_part(
        db_session, part_no="R-1", name="Low Part", cost_price=10, reorder_level=5,
    )
    stock_service.add_ledger_entry(db_session, part_id=low_part.id, qty_in=3, reference_type="OPENING")
    ok_part = parts_service.create_part(
        db_session, part_no="R-2", name="OK Part", cost_price=20, reorder_level=5,
    )
    stock_service.add_ledger_entry(db_session, part_id=ok_part.id, qty_in=50, reference_type="OPENING")
    db_session.commit()

    rows = reports_service.get_stock_report(db_session)
    by_part_no = {r["part"].part_no: r for r in rows}
    assert by_part_no["R-1"]["current_stock"] == 3
    assert by_part_no["R-1"]["stock_value"] == Decimal("30")
    assert by_part_no["R-1"]["is_low"] is True
    assert by_part_no["R-2"]["is_low"] is False

    low_only = reports_service.get_stock_report(db_session, low_stock_only=True)
    assert [r["part"].part_no for r in low_only] == ["R-1"]


def test_stock_report_query_filters_to_matching_parts(db_session):
    parts_service.create_part(db_session, part_no="BRK-100", name="Front Brake Pad")
    parts_service.create_part(db_session, part_no="CLT-200", name="Clutch Plate")

    matches = reports_service.get_stock_report(db_session, query="brake")
    assert [r["part"].part_no for r in matches] == ["BRK-100"]

    by_part_no = reports_service.get_stock_report(db_session, query="CLT-200")
    assert [r["part"].part_no for r in by_part_no] == ["CLT-200"]

    no_match = reports_service.get_stock_report(db_session, query="nonexistent-xyz")
    assert no_match == []


# --- sales / purchases report -------------------------------------------

def test_sales_report_date_range_and_totals(db_session):
    customer = customers_service.create_customer(db_session, name="C1", type="RETAIL")
    part = parts_service.create_part(db_session, part_no="R-3", name="Part")
    stock_service.add_ledger_entry(db_session, part_id=part.id, qty_in=100, reference_type="OPENING")
    db_session.commit()

    old_sale = sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=customer.id,
        items=[dict(part_id=part.id, qty_entered=1, unit_price=100)],
        sale_date=dt.datetime(2020, 1, 1),
    )
    recent_sale = sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=customer.id,
        items=[dict(part_id=part.id, qty_entered=2, unit_price=100)],
        paid=200,
    )

    report = reports_service.get_sales_report(
        db_session, date_from=dt.datetime.utcnow() - dt.timedelta(days=1),
        date_to=dt.datetime.utcnow() + dt.timedelta(days=1),
    )
    sale_nos = [s.sale_no for s in report["rows"]]
    assert recent_sale.sale_no in sale_nos
    assert old_sale.sale_no not in sale_nos
    assert report["totals"]["count"] == 1
    assert report["totals"]["total"] == Decimal("200")
    assert report["totals"]["paid"] == Decimal("200")
    assert report["totals"]["due"] == Decimal("0")


def test_sales_report_excludes_cancelled(db_session):
    customer = customers_service.create_customer(db_session, name="C2", type="RETAIL")
    part = parts_service.create_part(db_session, part_no="R-4", name="Part")
    stock_service.add_ledger_entry(db_session, part_id=part.id, qty_in=10, reference_type="OPENING")
    db_session.commit()
    sale = sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=customer.id,
        items=[dict(part_id=part.id, qty_entered=1, unit_price=100)],
    )
    sales_service.cancel_sale(db_session, sale.id)
    report = reports_service.get_sales_report(db_session)
    assert report["totals"]["count"] == 0


def test_purchases_report_filters_by_supplier(db_session):
    supplier_a = suppliers_service.create_supplier(db_session, name="SA")
    supplier_b = suppliers_service.create_supplier(db_session, name="SB")
    part = parts_service.create_part(db_session, part_no="R-5", name="Part")

    purchase_service.create_purchase(
        db_session, supplier_id=supplier_a.id, items=[dict(part_id=part.id, qty=10, unit_cost=50)],
    )
    purchase_service.create_purchase(
        db_session, supplier_id=supplier_b.id, items=[dict(part_id=part.id, qty=5, unit_cost=50)],
    )

    report = reports_service.get_purchases_report(db_session, supplier_id=supplier_a.id)
    assert report["totals"]["count"] == 1
    assert report["rows"][0].supplier_id == supplier_a.id


# --- receivables / payables ---------------------------------------------

def test_receivables_payables_only_includes_positive_balances(db_session):
    paid_up_customer = customers_service.create_customer(db_session, name="PaidUp", type="RETAIL")
    owing_customer = customers_service.create_customer(db_session, name="Owing", type="WHOLESALE")
    part = parts_service.create_part(db_session, part_no="R-6", name="Part")
    stock_service.add_ledger_entry(db_session, part_id=part.id, qty_in=100, reference_type="OPENING")
    db_session.commit()

    sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=paid_up_customer.id,
        items=[dict(part_id=part.id, qty_entered=1, unit_price=100)], paid=100,
    )
    sales_service.create_sale(
        db_session, sale_type="WHOLESALE", customer_id=owing_customer.id,
        items=[dict(part_id=part.id, qty_entered=5, unit_price=100)], paid=0,
    )

    report = reports_service.get_receivables_payables_report(db_session)
    names = [r["party"].name for r in report["receivables"]]
    assert "Owing" in names
    assert "PaidUp" not in names
    assert report["total_receivables"] == Decimal("500")


def test_receivables_sorted_highest_first(db_session):
    part = parts_service.create_part(db_session, part_no="R-7", name="Part")
    stock_service.add_ledger_entry(db_session, part_id=part.id, qty_in=100, reference_type="OPENING")
    db_session.commit()
    small = customers_service.create_customer(db_session, name="Small", type="WHOLESALE")
    big = customers_service.create_customer(db_session, name="Big", type="WHOLESALE")
    sales_service.create_sale(
        db_session, sale_type="WHOLESALE", customer_id=small.id,
        items=[dict(part_id=part.id, qty_entered=1, unit_price=100)], paid=0,
    )
    sales_service.create_sale(
        db_session, sale_type="WHOLESALE", customer_id=big.id,
        items=[dict(part_id=part.id, qty_entered=10, unit_price=100)], paid=0,
    )
    report = reports_service.get_receivables_payables_report(db_session)
    assert [r["party"].name for r in report["receivables"]] == ["Big", "Small"]


# --- profit report -------------------------------------------------------

def test_profit_report_computes_revenue_cogs_and_margin(db_session):
    customer = customers_service.create_customer(db_session, name="ProfitCust", type="RETAIL")
    part = parts_service.create_part(db_session, part_no="P-1", name="Part", cost_price=50, retail_price=100)
    stock_service.add_ledger_entry(db_session, part_id=part.id, qty_in=10, reference_type="OPENING")
    db_session.commit()

    sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=customer.id,
        items=[dict(part_id=part.id, qty_entered=2, unit_price=100)],
    )

    report = reports_service.get_profit_report(db_session)
    assert report["totals"]["count"] == 1
    assert report["totals"]["revenue"] == Decimal("200")
    assert report["totals"]["cogs"] == Decimal("100")
    assert report["totals"]["gross_profit"] == Decimal("100")
    assert report["totals"]["margin_pct"] == Decimal("50")
    assert report["totals"]["estimated_rows_count"] == 0
    assert report["rows"][0]["has_estimated_cost"] is False


def test_profit_report_revenue_nets_out_header_discount(db_session):
    customer = customers_service.create_customer(db_session, name="DiscCust", type="RETAIL")
    part = parts_service.create_part(db_session, part_no="P-2", name="Part", cost_price=50, retail_price=100)
    stock_service.add_ledger_entry(db_session, part_id=part.id, qty_in=10, reference_type="OPENING")
    db_session.commit()

    sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=customer.id,
        items=[dict(part_id=part.id, qty_entered=2, unit_price=100)],
        discount=20,
    )

    report = reports_service.get_profit_report(db_session)
    # subtotal=200, header discount=20 -> revenue=180; cogs unaffected by discount.
    assert report["totals"]["revenue"] == Decimal("180")
    assert report["totals"]["cogs"] == Decimal("100")
    assert report["totals"]["gross_profit"] == Decimal("80")


def test_profit_report_excludes_cancelled_sales(db_session):
    customer = customers_service.create_customer(db_session, name="CancelCust", type="RETAIL")
    part = parts_service.create_part(db_session, part_no="P-3", name="Part", cost_price=50, retail_price=100)
    stock_service.add_ledger_entry(db_session, part_id=part.id, qty_in=10, reference_type="OPENING")
    db_session.commit()

    sale = sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=customer.id,
        items=[dict(part_id=part.id, qty_entered=1, unit_price=100)],
    )
    sales_service.cancel_sale(db_session, sale.id)

    report = reports_service.get_profit_report(db_session)
    assert report["totals"]["count"] == 0
    assert report["totals"]["revenue"] == Decimal("0")


def test_profit_report_date_range_filters(db_session):
    customer = customers_service.create_customer(db_session, name="RangeCust", type="RETAIL")
    part = parts_service.create_part(db_session, part_no="P-4", name="Part", cost_price=50, retail_price=100)
    stock_service.add_ledger_entry(db_session, part_id=part.id, qty_in=10, reference_type="OPENING")
    db_session.commit()

    sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=customer.id,
        items=[dict(part_id=part.id, qty_entered=1, unit_price=100)],
        sale_date=dt.datetime(2020, 1, 1),
    )
    sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=customer.id,
        items=[dict(part_id=part.id, qty_entered=1, unit_price=100)],
    )

    report = reports_service.get_profit_report(
        db_session, date_from=dt.datetime.utcnow() - dt.timedelta(days=1),
        date_to=dt.datetime.utcnow() + dt.timedelta(days=1),
    )
    assert report["totals"]["count"] == 1


def test_profit_report_falls_back_to_current_cost_when_snapshot_missing(db_session):
    """Simulates a sale item saved before the cost_price column existed."""
    customer = customers_service.create_customer(db_session, name="LegacyCust", type="RETAIL")
    part = parts_service.create_part(db_session, part_no="P-5", name="Part", cost_price=50, retail_price=100)
    stock_service.add_ledger_entry(db_session, part_id=part.id, qty_in=10, reference_type="OPENING")
    db_session.commit()

    sale = sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=customer.id,
        items=[dict(part_id=part.id, qty_entered=2, unit_price=100)],
    )
    # Blank out the snapshot (as a legacy pre-migration row would be) and
    # change the part's CURRENT cost - the report must fall back to it.
    sale.items[0].cost_price = None
    part.cost_price = 70
    db_session.commit()

    report = reports_service.get_profit_report(db_session)
    assert report["totals"]["cogs"] == Decimal("140")  # 2 * 70 (current cost, not the original 50)
    assert report["totals"]["estimated_rows_count"] == 1
    assert report["rows"][0]["has_estimated_cost"] is True


# --- profit period presets ------------------------------------------------

def test_profit_period_range_daily():
    date_from, date_to = reports_service.profit_period_range(
        reports_service.PERIOD_DAILY, reference_date=dt.date(2026, 3, 15),
    )
    assert date_from == dt.datetime(2026, 3, 15, 0, 0, 0)
    assert date_to.date() == dt.date(2026, 3, 15)
    assert date_to.hour == 23 and date_to.minute == 59


def test_profit_period_range_monthly_handles_leap_february():
    date_from, date_to = reports_service.profit_period_range(
        reports_service.PERIOD_MONTHLY, reference_date=dt.date(2024, 2, 10),
    )
    assert date_from.date() == dt.date(2024, 2, 1)
    assert date_to.date() == dt.date(2024, 2, 29)  # 2024 is a leap year


def test_profit_period_range_monthly_non_leap_february():
    date_from, date_to = reports_service.profit_period_range(
        reports_service.PERIOD_MONTHLY, reference_date=dt.date(2026, 2, 10),
    )
    assert date_from.date() == dt.date(2026, 2, 1)
    assert date_to.date() == dt.date(2026, 2, 28)


def test_profit_period_range_quarterly():
    date_from, date_to = reports_service.profit_period_range(
        reports_service.PERIOD_QUARTERLY, reference_date=dt.date(2026, 11, 20),
    )
    assert date_from.date() == dt.date(2026, 10, 1)
    assert date_to.date() == dt.date(2026, 12, 31)

    date_from2, date_to2 = reports_service.profit_period_range(
        reports_service.PERIOD_QUARTERLY, reference_date=dt.date(2026, 5, 3),
    )
    assert date_from2.date() == dt.date(2026, 4, 1)
    assert date_to2.date() == dt.date(2026, 6, 30)


def test_profit_period_range_rejects_custom():
    with pytest.raises(ValueError):
        reports_service.profit_period_range(reports_service.PERIOD_CUSTOM)


# --- reorder suggestions ---------------------------------------------------

def test_reorder_suggestions_uses_reorder_qty_when_set(db_session):
    part = parts_service.create_part(
        db_session, part_no="RQ-1", name="Low Part", reorder_level=10, reorder_qty=50,
    )
    stock_service.add_ledger_entry(db_session, part_id=part.id, qty_in=4, reference_type="OPENING")
    db_session.commit()

    rows = reports_service.get_reorder_suggestions(db_session)
    assert len(rows) == 1
    assert rows[0]["part"].part_no == "RQ-1"
    assert rows[0]["current_stock"] == 4
    assert rows[0]["suggested_qty"] == 46  # bring up to reorder_qty=50


def test_reorder_suggestions_falls_back_to_reorder_level(db_session):
    part = parts_service.create_part(db_session, part_no="RQ-2", name="Low Part 2", reorder_level=10)
    stock_service.add_ledger_entry(db_session, part_id=part.id, qty_in=3, reference_type="OPENING")
    db_session.commit()

    rows = reports_service.get_reorder_suggestions(db_session)
    assert rows[0]["suggested_qty"] == 7  # bring up to reorder_level=10 (no reorder_qty set)


def test_reorder_suggestions_excludes_parts_above_reorder_level(db_session):
    part = parts_service.create_part(db_session, part_no="RQ-3", name="OK Part", reorder_level=5)
    stock_service.add_ledger_entry(db_session, part_id=part.id, qty_in=50, reference_type="OPENING")
    db_session.commit()

    rows = reports_service.get_reorder_suggestions(db_session)
    assert rows == []


# --- warranty lookup ---------------------------------------------------

def test_search_warranty_finds_active_warranty(db_session):
    customer = customers_service.create_customer(db_session, name="WarrantyCust", type="RETAIL")
    part = parts_service.create_part(
        db_session, part_no="WR-1", name="Warrantied Part", retail_price=100, warranty_days=365,
    )
    stock_service.add_ledger_entry(db_session, part_id=part.id, qty_in=5, reference_type="OPENING")
    db_session.commit()

    sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=customer.id,
        items=[dict(part_id=part.id, qty_entered=1, unit_price=100)],
    )

    rows = reports_service.search_warranty(db_session)
    assert len(rows) == 1
    assert rows[0]["part"].part_no == "WR-1"
    assert rows[0]["customer_name"] == "WarrantyCust"
    assert rows[0]["is_active"] is True


def test_search_warranty_flags_expired(db_session):
    customer = customers_service.create_customer(db_session, name="ExpiredCust", type="RETAIL")
    part = parts_service.create_part(
        db_session, part_no="WR-2", name="Old Warranty Part", retail_price=100, warranty_days=10,
    )
    stock_service.add_ledger_entry(db_session, part_id=part.id, qty_in=5, reference_type="OPENING")
    db_session.commit()

    sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=customer.id,
        items=[dict(part_id=part.id, qty_entered=1, unit_price=100)],
        sale_date=dt.datetime(2020, 1, 1),
    )

    rows = reports_service.search_warranty(db_session)
    assert len(rows) == 1
    assert rows[0]["is_active"] is False


def test_search_warranty_excludes_parts_without_warranty(db_session):
    customer = customers_service.create_customer(db_session, name="NoWarrantyCust", type="RETAIL")
    part = parts_service.create_part(db_session, part_no="WR-3", name="Plain Part", retail_price=100)
    stock_service.add_ledger_entry(db_session, part_id=part.id, qty_in=5, reference_type="OPENING")
    db_session.commit()

    sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=customer.id,
        items=[dict(part_id=part.id, qty_entered=1, unit_price=100)],
    )

    assert reports_service.search_warranty(db_session) == []


def test_search_warranty_query_matches_part_and_customer(db_session):
    customer = customers_service.create_customer(db_session, name="FindMe Customer", type="RETAIL")
    part = parts_service.create_part(
        db_session, part_no="WR-FIND", name="Findable Part", retail_price=100, warranty_days=30,
    )
    stock_service.add_ledger_entry(db_session, part_id=part.id, qty_in=5, reference_type="OPENING")
    db_session.commit()
    sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=customer.id,
        items=[dict(part_id=part.id, qty_entered=1, unit_price=100)],
    )

    assert len(reports_service.search_warranty(db_session, query="WR-FIND")) == 1
    assert len(reports_service.search_warranty(db_session, query="FindMe")) == 1
    assert len(reports_service.search_warranty(db_session, query="nonexistent-xyz")) == 0


# --- dashboard summary ---------------------------------------------------

def test_dashboard_summary_rolls_up_everything(db_session):
    customer = customers_service.create_customer(db_session, name="DashCust", type="WHOLESALE")
    supplier = suppliers_service.create_supplier(db_session, name="DashSupp")
    part = parts_service.create_part(db_session, part_no="R-8", name="Part", cost_price=10, reorder_level=5)
    stock_service.add_ledger_entry(db_session, part_id=part.id, qty_in=3, reference_type="OPENING")
    db_session.commit()

    sales_service.create_sale(
        db_session, sale_type="WHOLESALE", customer_id=customer.id,
        items=[dict(part_id=part.id, qty_entered=1, unit_price=100)], paid=0,
    )
    purchase_service.create_purchase(
        db_session, supplier_id=supplier.id, items=[dict(part_id=part.id, qty=1, unit_cost=10)], paid=0,
    )
    payments_service.create_payment(db_session, direction="IN", party_id=customer.id, amount=20)

    summary = reports_service.get_dashboard_summary(db_session)
    assert summary["total_parts"] == 1
    assert summary["today_sales_count"] == 1
    assert summary["today_purchases_count"] == 1
    assert summary["total_receivables"] == Decimal("80")  # 100 - 20 payment
    assert summary["total_payables"] == Decimal("10")
    assert len(summary["low_stock_rows"]) == 1
    assert len(summary["recent_sales"]) == 1
    assert len(summary["recent_purchases"]) == 1
