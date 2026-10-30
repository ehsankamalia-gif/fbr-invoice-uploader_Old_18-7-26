"""Read-only statement-of-account builder for a customer or supplier
(Phase 4). Merges every POSTED transaction that touches the party's
running balance - in date order, with a running balance after each row -
into one list the UI just renders as a table. Nothing here writes
anything; it only reads what sales_service/purchase_service/
returns_service/payments_service already created.

Convention used for every row, regardless of party type: `debit`
increases the balance owed, `credit` decreases it. A sale/purchase row
carries both (debit=total, credit=paid-at-the-time) so its net effect is
exactly that transaction's own `due` - later payments and returns are
their own separate rows.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from spare_parts.services import customers_service, payments_service, purchase_service, returns_service, sales_service, suppliers_service


def get_customer_ledger(db: Session, customer_id: int) -> list[dict]:
    """Returns a list of rows sorted by date, each:
    {date, type, ref_no, debit, credit, balance}, starting from an
    "Opening Balance" row and ending at the customer's current
    outstanding balance (matches customers_service.get_customer_outstanding)."""
    customer = customers_service.get_customer(db, customer_id)
    if not customer:
        return []

    rows: list[dict] = []
    for sale in sales_service.list_sales(db, customer_id=customer_id, status="POSTED"):
        rows.append(dict(
            date=sale.sale_date, type="Sale", ref_no=sale.sale_no,
            debit=Decimal(str(sale.total)), credit=Decimal(str(sale.paid)),
        ))
    for sale_return in returns_service.list_sale_returns(db):
        if sale_return.status != "POSTED":
            continue
        if not sale_return.sale or sale_return.sale.customer_id != customer_id:
            continue
        rows.append(dict(
            date=sale_return.return_date, type="Sale Return", ref_no=sale_return.return_no,
            debit=Decimal("0"), credit=Decimal(str(sale_return.total)),
        ))
    for payment in payments_service.list_payments(db, direction="IN", customer_id=customer_id, status="POSTED"):
        rows.append(dict(
            date=payment.payment_date, type="Payment Received", ref_no=payment.payment_no,
            debit=Decimal("0"), credit=Decimal(str(payment.amount)),
        ))

    return _build_statement(rows, opening_balance=Decimal(str(customer.opening_balance or 0)))


def get_supplier_ledger(db: Session, supplier_id: int) -> list[dict]:
    """Symmetric to get_customer_ledger - matches
    suppliers_service.get_supplier_outstanding."""
    supplier = suppliers_service.get_supplier(db, supplier_id)
    if not supplier:
        return []

    rows: list[dict] = []
    for purchase in purchase_service.list_purchases(db, supplier_id=supplier_id, status="POSTED"):
        rows.append(dict(
            date=purchase.purchase_date, type="Purchase", ref_no=purchase.purchase_no,
            debit=Decimal(str(purchase.total)), credit=Decimal(str(purchase.paid)),
        ))
    for purchase_return in returns_service.list_purchase_returns(db):
        if purchase_return.status != "POSTED":
            continue
        if not purchase_return.purchase or purchase_return.purchase.supplier_id != supplier_id:
            continue
        rows.append(dict(
            date=purchase_return.return_date, type="Purchase Return", ref_no=purchase_return.return_no,
            debit=Decimal("0"), credit=Decimal(str(purchase_return.total)),
        ))
    for payment in payments_service.list_payments(db, direction="OUT", supplier_id=supplier_id, status="POSTED"):
        rows.append(dict(
            date=payment.payment_date, type="Payment Made", ref_no=payment.payment_no,
            debit=Decimal("0"), credit=Decimal(str(payment.amount)),
        ))

    return _build_statement(rows, opening_balance=Decimal(str(supplier.opening_balance or 0)))


def _build_statement(rows: list[dict], *, opening_balance: Decimal) -> list[dict]:
    rows.sort(key=lambda r: r["date"])
    running = opening_balance
    statement = [dict(
        date=rows[0]["date"] if rows else dt.datetime.utcnow(),
        type="Opening Balance", ref_no="",
        debit=opening_balance if opening_balance > 0 else Decimal("0"),
        credit=-opening_balance if opening_balance < 0 else Decimal("0"),
        balance=running,
    )]
    for row in rows:
        running += row["debit"] - row["credit"]
        statement.append(dict(
            date=row["date"], type=row["type"], ref_no=row["ref_no"],
            debit=row["debit"], credit=row["credit"], balance=running,
        ))
    return statement
