from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.core.logger import logger
from app.db.models import CreditBookAudit, CreditBookEntryType, CreditBookTransaction, Customer, FinanceLoan


class CreditBookService:
    def _month_key_for_ts(self, ts: dt.datetime) -> str:
        return ts.strftime("%Y-%m")

    def create_transaction(
        self,
        db: Session,
        customer_id: int,
        direction: str,
        entry_type: str,
        amount: float,
        reference_number: str = "",
        description: str = "",
        timestamp: Optional[dt.datetime] = None,
        related_invoice_id: Optional[int] = None,
        finance_application_id: Optional[int] = None,
        finance_loan_id: Optional[int] = None,
        created_by_user_id: Optional[int] = None,
        commit: bool = True,
        sync_financing: bool = True,
    ) -> CreditBookTransaction:
        cid = int(customer_id or 0)
        if cid <= 0:
            raise ValueError("Customer is required.")

        amt = float(amount or 0.0)
        if amt <= 0:
            raise ValueError("Amount must be greater than zero.")

        dir_norm = (direction or "").strip().upper()
        if dir_norm not in ("DEBIT", "CREDIT"):
            raise ValueError("Invalid direction. Use DEBIT or CREDIT.")

        et_norm = (entry_type or "").strip().upper()
        valid_types = {e.value for e in CreditBookEntryType}
        if et_norm not in valid_types:
            raise ValueError(f"Invalid entry type. Use one of: {', '.join(sorted(valid_types))}.")

        ts = timestamp if isinstance(timestamp, dt.datetime) else dt.datetime.utcnow()
        mk = self._month_key_for_ts(ts)

        customer = db.query(Customer).filter(Customer.id == cid).first()
        if not customer:
            raise ValueError("Customer not found.")

        flid = int(finance_loan_id) if finance_loan_id else None
        if not flid and et_norm == CreditBookEntryType.PAYMENT.value:
            ref = (reference_number or "").strip().upper()
            if ref.startswith("LN-"):
                loan = db.query(FinanceLoan).filter(FinanceLoan.loan_number == ref).first()
                if loan:
                    flid = int(loan.id)

        txn = CreditBookTransaction(
            customer_id=cid,
            timestamp=ts,
            direction=dir_norm,
            entry_type=et_norm,
            amount=amt,
            reference_number=(reference_number or "").strip() or None,
            description=(description or "").strip() or None,
            related_invoice_id=int(related_invoice_id) if related_invoice_id else None,
            finance_application_id=int(finance_application_id) if finance_application_id else None,
            finance_loan_id=flid,
            created_by_user_id=int(created_by_user_id) if created_by_user_id else None,
            month_key=mk,
            is_void=False,
        )
        try:
            db.add(txn)
            db.flush()
            db.add(
                CreditBookAudit(
                    action="CREATE_TXN",
                    user_id=txn.created_by_user_id,
                    transaction_id=txn.id,
                    details={
                        "customer_id": cid,
                        "direction": dir_norm,
                        "entry_type": et_norm,
                        "amount": amt,
                        "reference_number": txn.reference_number,
                        "month_key": mk,
                        "related_invoice_id": txn.related_invoice_id,
                        "finance_application_id": txn.finance_application_id,
                        "finance_loan_id": txn.finance_loan_id,
                    },
                )
            )
            if sync_financing and et_norm == CreditBookEntryType.PAYMENT.value and txn.finance_loan_id:
                from app.services.financing_service import financing_service

                financing_service.record_payment(
                    db=db,
                    loan_id=int(txn.finance_loan_id),
                    amount=float(amt),
                    method="CASH",
                    reference_number=str(txn.reference_number or ""),
                    provider="CREDIT_BOOK",
                    timestamp=ts,
                    received_by_user_id=int(created_by_user_id) if created_by_user_id else None,
                    actor_user_id=int(created_by_user_id) if created_by_user_id else None,
                    metadata={"source": "credit_book"},
                    commit=False,
                    sync_credit_book=False,
                )

            if commit:
                db.commit()
                db.refresh(txn)
            return txn
        except Exception as exc:
            db.rollback()
            logger.error(f"Credit book create_transaction failed: {exc}", exc_info=True)
            raise

    def void_transaction(
        self,
        db: Session,
        transaction_id: int,
        reason: str,
        user_id: Optional[int] = None,
    ) -> CreditBookTransaction:
        tid = int(transaction_id or 0)
        if tid <= 0:
            raise ValueError("Transaction ID is required.")

        txn = db.query(CreditBookTransaction).filter(CreditBookTransaction.id == tid).first()
        if not txn:
            raise ValueError("Transaction not found.")
        if txn.is_void:
            raise ValueError("Transaction is already void.")

        r = (reason or "").strip()
        if not r:
            raise ValueError("Void reason is required.")

        try:
            txn.is_void = True
            txn.void_reason = r
            txn.voided_at = dt.datetime.utcnow()
            db.add(txn)
            db.add(
                CreditBookAudit(
                    action="VOID_TXN",
                    user_id=int(user_id) if user_id else None,
                    transaction_id=txn.id,
                    details={"reason": r},
                )
            )
            db.commit()
            db.refresh(txn)
            return txn
        except Exception as exc:
            db.rollback()
            logger.error(f"Credit book void_transaction failed: {exc}", exc_info=True)
            raise

    def list_transactions(
        self,
        db: Session,
        customer_id: Optional[int] = None,
        direction: str = "ALL",
        include_void: bool = False,
        search: str = "",
        start: Optional[dt.datetime] = None,
        end: Optional[dt.datetime] = None,
        limit: int = 2000,
    ) -> List[CreditBookTransaction]:
        q = db.query(CreditBookTransaction).join(Customer, CreditBookTransaction.customer_id == Customer.id)

        if customer_id:
            q = q.filter(CreditBookTransaction.customer_id == int(customer_id))

        d = (direction or "").strip().upper()
        if d in ("DEBIT", "CREDIT"):
            q = q.filter(CreditBookTransaction.direction == d)

        if not include_void:
            q = q.filter(CreditBookTransaction.is_void.is_(False))

        s = (search or "").strip()
        if s:
            like = f"%{s}%"
            q = q.filter(
                (Customer.name.ilike(like))
                | (Customer.cnic.ilike(like))
                | (Customer.phone.ilike(like))
                | (CreditBookTransaction.reference_number.ilike(like))
                | (CreditBookTransaction.description.ilike(like))
            )

        if isinstance(start, dt.datetime):
            q = q.filter(CreditBookTransaction.timestamp >= start)
        if isinstance(end, dt.datetime):
            q = q.filter(CreditBookTransaction.timestamp <= end)

        return q.order_by(CreditBookTransaction.timestamp.asc(), CreditBookTransaction.id.asc()).limit(int(limit or 2000)).all()

    def list_customer_balances(
        self,
        db: Session,
        search: str = "",
        limit: int = 500,
        min_balance: float = 0.01,
    ) -> List[Dict[str, Any]]:
        debit_sum = func.coalesce(
            func.sum(case((CreditBookTransaction.direction == "DEBIT", CreditBookTransaction.amount), else_=0.0)),
            0.0,
        )
        credit_sum = func.coalesce(
            func.sum(case((CreditBookTransaction.direction == "CREDIT", CreditBookTransaction.amount), else_=0.0)),
            0.0,
        )
        balance_expr = debit_sum - credit_sum

        q = (
            db.query(
                Customer.id.label("customer_id"),
                Customer.name.label("name"),
                Customer.cnic.label("cnic"),
                Customer.phone.label("phone"),
                balance_expr.label("balance"),
            )
            .join(CreditBookTransaction, CreditBookTransaction.customer_id == Customer.id)
            .filter(CreditBookTransaction.is_void.is_(False))
            .group_by(Customer.id)
        )

        s = (search or "").strip()
        if s:
            like = f"%{s}%"
            q = q.filter(
                (Customer.name.ilike(like))
                | (Customer.cnic.ilike(like))
                | (Customer.phone.ilike(like))
            )

        q = q.having(func.abs(balance_expr) >= float(min_balance or 0.0))
        rows = q.order_by(balance_expr.desc()).limit(int(limit or 500)).all()
        return [
            {
                "customer_id": int(r.customer_id),
                "name": str(r.name or ""),
                "cnic": str(r.cnic or ""),
                "phone": str(r.phone or ""),
                "balance": float(r.balance or 0.0),
            }
            for r in rows
        ]

    def get_summary(self, db: Session) -> Dict[str, float]:
        debit_sum = func.coalesce(
            func.sum(
                case(
                    (CreditBookTransaction.direction == "DEBIT", CreditBookTransaction.amount),
                    else_=0.0,
                )
            ),
            0.0,
        )
        credit_sum = func.coalesce(
            func.sum(
                case(
                    (CreditBookTransaction.direction == "CREDIT", CreditBookTransaction.amount),
                    else_=0.0,
                )
            ),
            0.0,
        )
        total_debit, total_credit = (
            db.query(debit_sum.label("d"), credit_sum.label("c"))
            .filter(CreditBookTransaction.is_void.is_(False))
            .first()
            or (0.0, 0.0)
        )

        total_debit_f = float(total_debit or 0.0)
        total_credit_f = float(total_credit or 0.0)
        total_balance_f = total_debit_f - total_credit_f
        customers_count = (
            db.query(func.count(func.distinct(CreditBookTransaction.customer_id)))
            .filter(CreditBookTransaction.is_void.is_(False))
            .scalar()
            or 0
        )
        return {
            "total_debit": total_debit_f,
            "total_credit": total_credit_f,
            "total_balance": total_balance_f,
            "active_customers": float(customers_count),
        }


credit_book_service = CreditBookService()
