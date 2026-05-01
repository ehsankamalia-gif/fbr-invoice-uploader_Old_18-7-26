from __future__ import annotations

import datetime as dt
import secrets
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.core.logger import logger
from app.db.models import (
    CreditBookEntryType,
    CreditBookTransaction,
    Customer,
    DealerProfile,
    FinanceApplicantType,
    FinanceApplication,
    FinanceApplicationItem,
    FinanceApplicationStatus,
    FinanceAudit,
    FinanceCreditBureauInquiry,
    FinanceInstallment,
    FinanceInstallmentStatus,
    FinanceInventoryReservation,
    FinanceLoan,
    FinanceLoanItem,
    FinanceLoanStatus,
    FinancePayment,
    FinancePaymentAllocation,
    FinancePaymentMethod,
    FinancePaymentStatus,
    FinancePortalToken,
    FinanceRefinance,
    Motorcycle,
    ProductModel,
)


@dataclass(frozen=True)
class AmortizationRow:
    installment_no: int
    due_date: dt.datetime
    principal: float
    interest: float
    fees: float
    total: float


class FinancingService:
    def _month_key_for_ts(self, ts: dt.datetime) -> str:
        return ts.strftime("%Y-%m")

    def _require_role(self, db: Session, user_id: Optional[int], allowed: List[str]) -> None:
        if not user_id:
            return
        from app.db.models import User

        user = db.query(User).filter(User.id == int(user_id)).first()
        if not user:
            raise ValueError("User not found.")
        role = (user.role or "").strip().lower()
        if role and allowed and role not in [r.lower() for r in allowed]:
            raise PermissionError("Forbidden.")

    def _audit(self, db: Session, action: str, entity_type: str, entity_id: Optional[int], user_id: Optional[int], details: Dict[str, Any]) -> None:
        db.add(
            FinanceAudit(
                action=(action or "").strip().upper(),
                user_id=int(user_id) if user_id else None,
                entity_type=(entity_type or "").strip(),
                entity_id=int(entity_id) if entity_id else None,
                details=details or {},
            )
        )

    def _validate_terms(self, term_months: int) -> None:
        t = int(term_months or 0)
        if t < 1 or t > 60:
            raise ValueError("Repayment period must be between 1 and 60 months.")

    def _calc_emi(self, principal: float, annual_rate: float, months: int) -> float:
        p = float(principal or 0.0)
        n = int(months or 0)
        if n <= 0:
            raise ValueError("Invalid term.")
        r = float(annual_rate or 0.0) / 1200.0
        if abs(r) < 1e-9:
            return round(p / n, 2)
        x = (1.0 + r) ** n
        emi = p * r * x / (x - 1.0)
        return round(emi, 2)

    def _add_months(self, d: dt.datetime, months: int) -> dt.datetime:
        y = d.year + (d.month - 1 + months) // 12
        m = (d.month - 1 + months) % 12 + 1
        day = min(d.day, [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
        return dt.datetime(y, m, day, d.hour, d.minute, d.second)

    def generate_amortization_schedule(
        self,
        financed_amount: float,
        interest_rate_annual: float,
        term_months: int,
        start_date: dt.datetime,
        first_due_date: Optional[dt.datetime] = None,
    ) -> Tuple[float, float, float, List[AmortizationRow]]:
        p = round(float(financed_amount or 0.0), 2)
        if p <= 0:
            raise ValueError("Financed amount must be greater than zero.")
        n = int(term_months or 0)
        if n < 1:
            raise ValueError("Invalid term.")
        r = float(interest_rate_annual or 0.0) / 1200.0
        emi = self._calc_emi(p, interest_rate_annual, n)

        remaining = p
        rows: List[AmortizationRow] = []
        due = first_due_date if isinstance(first_due_date, dt.datetime) else self._add_months(start_date, 1)
        total_interest = 0.0
        total_payable = 0.0

        for i in range(1, n + 1):
            interest = round(remaining * r, 2) if r > 0 else 0.0
            principal_component = round(emi - interest, 2)
            if i == n:
                principal_component = round(remaining, 2)
                emi_final = round(principal_component + interest, 2)
                total = emi_final
            else:
                total = emi
            remaining = round(remaining - principal_component, 2)
            if remaining < 0:
                remaining = 0.0
            total_interest = round(total_interest + interest, 2)
            total_payable = round(total_payable + total, 2)
            rows.append(
                AmortizationRow(
                    installment_no=i,
                    due_date=due,
                    principal=principal_component,
                    interest=interest,
                    fees=0.0,
                    total=total,
                )
            )
            due = self._add_months(due, 1)
        return emi, total_interest, total_payable, rows

    def _score_application(self, app: FinanceApplication, expected_emi: float, dealer_profile: Optional[DealerProfile]) -> Tuple[int, str, Dict[str, Any]]:
        income = float(app.monthly_income or 0.0)
        ratio = (expected_emi / income) if income > 0 else 1.0

        score = 650
        factors: Dict[str, Any] = {"emi": expected_emi, "income": income, "emi_to_income": ratio}

        if app.income_verified:
            score += 30
            factors["income_verified"] = True
        else:
            score -= 20
            factors["income_verified"] = False

        if ratio <= 0.25:
            score += 60
        elif ratio <= 0.4:
            score += 20
        elif ratio <= 0.55:
            score -= 40
        else:
            score -= 120

        if dealer_profile and dealer_profile.is_verified:
            score += 40
            factors["dealer_verified"] = True
        else:
            factors["dealer_verified"] = False

        if app.bureau_score is not None:
            bs = int(app.bureau_score or 0)
            score += int((bs - 600) / 10)
            factors["bureau_score"] = bs

        if score >= 760:
            tier = "A"
        elif score >= 700:
            tier = "B"
        elif score >= 640:
            tier = "C"
        else:
            tier = "D"

        return int(max(300, min(900, score))), tier, factors

    def _sum_application_total(self, items: List[FinanceApplicationItem]) -> float:
        return float(sum(float(i.total_price or 0.0) for i in items))

    def create_application(
        self,
        db: Session,
        customer_id: int,
        applicant_type: str,
        requested_term_months: int,
        down_payment_amount: float,
        actor_user_id: Optional[int] = None,
    ) -> FinanceApplication:
        self._validate_terms(requested_term_months)

        cust = db.query(Customer).filter(Customer.id == int(customer_id)).first()
        if not cust:
            raise ValueError("Customer not found.")

        at = (applicant_type or "").strip().upper()
        if at not in ("CUSTOMER", "DEALER"):
            raise ValueError("Invalid applicant type.")

        dealer_profile_id = None
        if at == "DEALER":
            dp = db.query(DealerProfile).filter(DealerProfile.customer_id == cust.id).first()
            if dp:
                dealer_profile_id = dp.id

        app = FinanceApplication(
            applicant_type=at,
            customer_id=cust.id,
            dealer_profile_id=dealer_profile_id,
            status=FinanceApplicationStatus.DRAFT,
            requested_term_months=int(requested_term_months),
            down_payment_percent=0.0,
            interest_rate_annual=0.0,
            cash_total_price=0.0,
            requested_total_price=0.0,
            requested_down_payment_amount=float(down_payment_amount or 0.0),
            requested_financed_amount=0.0,
            monthly_income=None,
            income_verified=False,
            income_verification_method=None,
        )
        try:
            db.add(app)
            db.flush()
            self._audit(
                db,
                action="CREATE_APPLICATION",
                entity_type="FINANCE_APPLICATION",
                entity_id=app.id,
                user_id=actor_user_id,
                details={"customer_id": cust.id, "applicant_type": at},
            )
            db.commit()
            db.refresh(app)
            return app
        except Exception as exc:
            db.rollback()
            logger.error(f"Create finance application failed: {exc}", exc_info=True)
            raise

    def add_application_item(
        self,
        db: Session,
        application_id: int,
        product_model_id: Optional[int],
        motorcycle_id: Optional[int],
        color: str,
        quantity: int,
        cash_unit_price: float,
        unit_price: float,
        actor_user_id: Optional[int] = None,
    ) -> FinanceApplication:
        app = db.query(FinanceApplication).filter(FinanceApplication.id == int(application_id)).first()
        if not app:
            raise ValueError("Application not found.")
        if (app.status or "").upper() not in (FinanceApplicationStatus.DRAFT, FinanceApplicationStatus.SUBMITTED, FinanceApplicationStatus.IN_REVIEW):
            raise ValueError("Application can no longer be edited.")

        qty = int(quantity or 0)
        if qty <= 0:
            raise ValueError("Quantity must be greater than zero.")
        cash_price = float(cash_unit_price or 0.0)
        if cash_price <= 0:
            raise ValueError("Cash unit price must be greater than zero.")
        price = float(unit_price or 0.0)
        if price <= 0:
            raise ValueError("Unit price must be greater than zero.")

        pm = None
        if product_model_id:
            pm = db.query(ProductModel).filter(ProductModel.id == int(product_model_id)).first()
            if not pm:
                raise ValueError("Product model not found.")

        moto = None
        if motorcycle_id:
            moto = db.query(Motorcycle).filter(Motorcycle.id == int(motorcycle_id)).first()
            if not moto:
                raise ValueError("Motorcycle not found.")
            if (moto.status or "").upper() != "IN_STOCK":
                raise ValueError("Motorcycle is not available in stock.")

        item = FinanceApplicationItem(
            application_id=app.id,
            motorcycle_id=moto.id if moto else None,
            product_model_id=pm.id if pm else None,
            color=(color or "").strip().upper() or None,
            quantity=qty,
            cash_unit_price=cash_price,
            cash_total_price=round(cash_price * qty, 2),
            unit_price=price,
            total_price=round(price * qty, 2),
        )
        try:
            db.add(item)
            db.flush()
            items = db.query(FinanceApplicationItem).filter(FinanceApplicationItem.application_id == app.id).all()
            credit_total = round(self._sum_application_total(items), 2)
            cash_total = round(float(sum(float(i.cash_total_price or 0.0) for i in items)), 2)
            dp_amt = round(float(app.requested_down_payment_amount or 0.0), 2)
            fin_amt = round(credit_total - dp_amt, 2)
            if fin_amt < 0:
                fin_amt = 0.0
            dp_pct = round((dp_amt / cash_total) * 100.0, 2) if cash_total > 0 else 0.0
            app.cash_total_price = cash_total
            app.requested_total_price = credit_total
            app.requested_financed_amount = fin_amt
            app.down_payment_percent = dp_pct
            db.add(app)
            self._audit(
                db,
                action="ADD_APPLICATION_ITEM",
                entity_type="FINANCE_APPLICATION",
                entity_id=app.id,
                user_id=actor_user_id,
                details={"item_id": item.id, "cash_total": cash_total, "credit_total": credit_total},
            )
            db.commit()
            db.refresh(app)
            return app
        except Exception as exc:
            db.rollback()
            logger.error(f"Add application item failed: {exc}", exc_info=True)
            raise

    def set_down_payment_amount(self, db: Session, application_id: int, down_payment_amount: float, actor_user_id: Optional[int] = None) -> FinanceApplication:
        app = db.query(FinanceApplication).filter(FinanceApplication.id == int(application_id)).first()
        if not app:
            raise ValueError("Application not found.")
        amt = float(down_payment_amount or 0.0)
        if amt < 0:
            raise ValueError("Invalid down payment amount.")
        items = db.query(FinanceApplicationItem).filter(FinanceApplicationItem.application_id == app.id).all()
        credit_total = round(self._sum_application_total(items), 2)
        cash_total = round(float(sum(float(i.cash_total_price or 0.0) for i in items)), 2)
        if amt > credit_total:
            raise ValueError("Down payment cannot be greater than total credit price.")
        dp_pct = round((amt / cash_total) * 100.0, 2) if cash_total > 0 else 0.0
        app.requested_down_payment_amount = round(amt, 2)
        app.down_payment_percent = dp_pct
        app.cash_total_price = cash_total
        app.requested_total_price = credit_total
        app.requested_financed_amount = round(credit_total - amt, 2)
        try:
            db.add(app)
            self._audit(db, "SET_DOWN_PAYMENT", "FINANCE_APPLICATION", app.id, actor_user_id, {"amount": amt, "percent": dp_pct})
            db.commit()
            db.refresh(app)
            return app
        except Exception as exc:
            db.rollback()
            logger.error(f"Set down payment failed: {exc}", exc_info=True)
            raise

    def reserve_motorcycle(
        self,
        db: Session,
        application_id: int,
        motorcycle_id: int,
        expires_in_hours: int = 72,
        actor_user_id: Optional[int] = None,
    ) -> FinanceInventoryReservation:
        app = db.query(FinanceApplication).filter(FinanceApplication.id == int(application_id)).first()
        if not app:
            raise ValueError("Application not found.")
        moto = db.query(Motorcycle).filter(Motorcycle.id == int(motorcycle_id)).first()
        if not moto:
            raise ValueError("Motorcycle not found.")
        if (moto.status or "").upper() != "IN_STOCK":
            raise ValueError("Motorcycle is not available in stock.")

        existing = (
            db.query(FinanceInventoryReservation)
            .filter(FinanceInventoryReservation.motorcycle_id == moto.id)
            .filter(FinanceInventoryReservation.released_at.is_(None))
            .filter(FinanceInventoryReservation.status == "RESERVED")
            .first()
        )
        if existing:
            raise ValueError("Motorcycle is already reserved for financing.")

        now = dt.datetime.utcnow()
        exp = now + dt.timedelta(hours=int(expires_in_hours or 72))
        res = FinanceInventoryReservation(application_id=app.id, motorcycle_id=moto.id, reserved_at=now, expires_at=exp, status="RESERVED")
        try:
            db.add(res)
            db.flush()
            self._audit(
                db,
                action="RESERVE_INVENTORY",
                entity_type="FINANCE_APPLICATION",
                entity_id=app.id,
                user_id=actor_user_id,
                details={"motorcycle_id": moto.id, "reservation_id": res.id},
            )
            db.commit()
            db.refresh(res)
            return res
        except Exception as exc:
            db.rollback()
            logger.error(f"Reserve motorcycle failed: {exc}", exc_info=True)
            raise

    def submit_application(self, db: Session, application_id: int, actor_user_id: Optional[int] = None) -> FinanceApplication:
        app = db.query(FinanceApplication).filter(FinanceApplication.id == int(application_id)).first()
        if not app:
            raise ValueError("Application not found.")
        if (app.status or "").upper() not in (FinanceApplicationStatus.DRAFT, FinanceApplicationStatus.SUBMITTED):
            raise ValueError("Application cannot be submitted.")

        items = db.query(FinanceApplicationItem).filter(FinanceApplicationItem.application_id == app.id).all()
        if not items:
            raise ValueError("Please add at least one item.")
        credit_total = round(self._sum_application_total(items), 2)
        cash_total = round(float(sum(float(i.cash_total_price or 0.0) for i in items)), 2)
        if credit_total <= 0:
            raise ValueError("Invalid application total.")
        if cash_total <= 0:
            raise ValueError("Invalid cash total price.")

        try:
            dp_amt = round(float(app.requested_down_payment_amount or 0.0), 2)
            if dp_amt <= 0:
                raise ValueError("Down payment amount is required.")
            if dp_amt > credit_total:
                raise ValueError("Down payment cannot be greater than total credit price.")
            dp_pct = round((dp_amt / cash_total) * 100.0, 2) if cash_total > 0 else 0.0
            if dp_pct < 10.0:
                raise ValueError("Down payment must be at least 10% of cash price.")

            app.cash_total_price = cash_total
            app.requested_total_price = credit_total
            app.down_payment_percent = dp_pct
            app.requested_financed_amount = round(credit_total - dp_amt, 2)
            app.status = FinanceApplicationStatus.APPROVED
            app.approved_by_user_id = int(actor_user_id) if actor_user_id else None
            app.approved_at = dt.datetime.utcnow()
            db.add(app)
            db.flush()
            self._audit(
                db,
                "SUBMIT_APPLICATION",
                "FINANCE_APPLICATION",
                app.id,
                actor_user_id,
                {"cash_total": cash_total, "credit_total": credit_total, "down_payment": dp_amt, "down_payment_percent": dp_pct},
            )

            existing_loan = db.query(FinanceLoan).filter(FinanceLoan.application_id == app.id).first()
            loan = existing_loan or self.create_loan_from_application(db, app.id, actor_user_id=actor_user_id, commit=False)

            from app.services.credit_book_service import credit_book_service

            existing_sale = (
                db.query(CreditBookTransaction)
                .filter(CreditBookTransaction.finance_loan_id == loan.id)
                .filter(CreditBookTransaction.entry_type == CreditBookEntryType.SALE.value)
                .filter(CreditBookTransaction.is_void.is_(False))
                .first()
            )
            if not existing_sale:
                credit_book_service.create_transaction(
                    db=db,
                    customer_id=int(app.customer_id),
                    direction="DEBIT",
                    entry_type=CreditBookEntryType.SALE.value,
                    amount=float(credit_total),
                    reference_number=str(loan.loan_number or ""),
                    description="Financing Sale",
                    timestamp=dt.datetime.utcnow(),
                    finance_application_id=int(app.id),
                    finance_loan_id=int(loan.id),
                    created_by_user_id=int(actor_user_id) if actor_user_id else None,
                    commit=False,
                    sync_financing=False,
                )

            if dp_amt > 0:
                existing_dp = (
                    db.query(CreditBookTransaction)
                    .filter(CreditBookTransaction.finance_loan_id == loan.id)
                    .filter(CreditBookTransaction.entry_type == CreditBookEntryType.PAYMENT.value)
                    .filter(CreditBookTransaction.description.ilike("%Down Payment%"))
                    .filter(CreditBookTransaction.is_void.is_(False))
                    .first()
                )
                if not existing_dp:
                    credit_book_service.create_transaction(
                        db=db,
                        customer_id=int(app.customer_id),
                        direction="CREDIT",
                        entry_type=CreditBookEntryType.PAYMENT.value,
                        amount=float(dp_amt),
                        reference_number=str(loan.loan_number or ""),
                        description="Down Payment",
                        timestamp=dt.datetime.utcnow(),
                        finance_application_id=int(app.id),
                        finance_loan_id=int(loan.id),
                        created_by_user_id=int(actor_user_id) if actor_user_id else None,
                        commit=False,
                        sync_financing=False,
                    )

            db.commit()
            db.refresh(app)
            return app
        except Exception as exc:
            db.rollback()
            logger.error(f"Submit application failed: {exc}", exc_info=True)
            raise

    def run_credit_assessment(self, db: Session, application_id: int, provider: str = "INTERNAL", actor_user_id: Optional[int] = None) -> FinanceApplication:
        app = db.query(FinanceApplication).filter(FinanceApplication.id == int(application_id)).first()
        if not app:
            raise ValueError("Application not found.")

        if float(app.requested_financed_amount or 0.0) <= 0:
            raise ValueError("Application has no financed amount.")

        dealer_profile = None
        if app.dealer_profile_id:
            dealer_profile = db.query(DealerProfile).filter(DealerProfile.id == int(app.dealer_profile_id)).first()

        emi = self._calc_emi(float(app.requested_financed_amount or 0.0), float(app.interest_rate_annual or 0.0), int(app.requested_term_months or 0))
        score, tier, factors = self._score_application(app, emi, dealer_profile)

        app.credit_score = score
        app.risk_tier = (dealer_profile.risk_tier_override if dealer_profile and dealer_profile.risk_tier_override else tier)
        app.risk_profile = factors
        app.bureau_provider = (provider or "").strip() or None
        try:
            db.add(app)
            db.flush()
            inquiry = FinanceCreditBureauInquiry(
                customer_id=app.customer_id,
                application_id=app.id,
                provider=(provider or "INTERNAL").strip(),
                request_id=None,
                status="COMPLETED",
                score=score,
                risk_grade=app.risk_tier,
                response_summary={"source": "internal", "factors": factors},
            )
            db.add(inquiry)
            self._audit(db, "ASSESS_APPLICATION", "FINANCE_APPLICATION", app.id, actor_user_id, {"score": score, "tier": app.risk_tier})
            db.commit()
            db.refresh(app)
            return app
        except Exception as exc:
            db.rollback()
            logger.error(f"Credit assessment failed: {exc}", exc_info=True)
            raise

    def approve_application(self, db: Session, application_id: int, actor_user_id: Optional[int] = None) -> FinanceApplication:
        self._require_role(db, actor_user_id, allowed=["admin", "manager"])
        app = db.query(FinanceApplication).filter(FinanceApplication.id == int(application_id)).first()
        if not app:
            raise ValueError("Application not found.")
        if (app.status or "").upper() not in (FinanceApplicationStatus.SUBMITTED, FinanceApplicationStatus.IN_REVIEW):
            raise ValueError("Application cannot be approved.")
        app.status = FinanceApplicationStatus.APPROVED
        app.approved_by_user_id = int(actor_user_id) if actor_user_id else None
        app.approved_at = dt.datetime.utcnow()
        try:
            db.add(app)
            self._audit(db, "APPROVE_APPLICATION", "FINANCE_APPLICATION", app.id, actor_user_id, {"risk_tier": app.risk_tier, "score": app.credit_score})
            db.commit()
            db.refresh(app)
            return app
        except Exception as exc:
            db.rollback()
            logger.error(f"Approve application failed: {exc}", exc_info=True)
            raise

    def reject_application(self, db: Session, application_id: int, reason: str, actor_user_id: Optional[int] = None) -> FinanceApplication:
        self._require_role(db, actor_user_id, allowed=["admin", "manager"])
        app = db.query(FinanceApplication).filter(FinanceApplication.id == int(application_id)).first()
        if not app:
            raise ValueError("Application not found.")
        if (app.status or "").upper() in (FinanceApplicationStatus.APPROVED, FinanceApplicationStatus.REJECTED, FinanceApplicationStatus.CANCELLED):
            raise ValueError("Application cannot be rejected.")
        r = (reason or "").strip()
        if not r:
            raise ValueError("Rejection reason is required.")
        app.status = FinanceApplicationStatus.REJECTED
        app.decision_reason = r
        try:
            db.add(app)
            self._audit(db, "REJECT_APPLICATION", "FINANCE_APPLICATION", app.id, actor_user_id, {"reason": r})
            db.commit()
            db.refresh(app)
            return app
        except Exception as exc:
            db.rollback()
            logger.error(f"Reject application failed: {exc}", exc_info=True)
            raise

    def _generate_loan_number(self) -> str:
        return f"LN-{dt.datetime.utcnow().strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"

    def create_loan_from_application(
        self,
        db: Session,
        application_id: int,
        start_date: Optional[dt.datetime] = None,
        late_fee_flat: float = 0.0,
        late_fee_daily_percent: float = 0.0,
        grace_days: int = 0,
        actor_user_id: Optional[int] = None,
        commit: bool = True,
    ) -> FinanceLoan:
        self._require_role(db, actor_user_id, allowed=["admin", "manager"])
        app = db.query(FinanceApplication).filter(FinanceApplication.id == int(application_id)).first()
        if not app:
            raise ValueError("Application not found.")
        if (app.status or "").upper() != FinanceApplicationStatus.APPROVED:
            raise ValueError("Only approved applications can be converted to loans.")

        items = db.query(FinanceApplicationItem).filter(FinanceApplicationItem.application_id == app.id).all()
        credit_total = round(self._sum_application_total(items), 2)
        cash_total = round(float(sum(float(i.cash_total_price or 0.0) for i in items)), 2)
        if credit_total <= 0:
            raise ValueError("Invalid application total.")
        if cash_total <= 0:
            raise ValueError("Invalid cash total price.")

        dp_amt = round(float(app.requested_down_payment_amount or 0.0), 2)
        fin_amt = round(credit_total - dp_amt, 2)
        if fin_amt <= 0:
            raise ValueError("Invalid financed amount.")

        sdt = start_date if isinstance(start_date, dt.datetime) else dt.datetime.utcnow()
        emi, total_interest, total_payable, rows = self.generate_amortization_schedule(
            financed_amount=fin_amt,
            interest_rate_annual=float(app.interest_rate_annual or 0.0),
            term_months=int(app.requested_term_months or 0),
            start_date=sdt,
        )

        loan = FinanceLoan(
            loan_number=self._generate_loan_number(),
            customer_id=app.customer_id,
            dealer_profile_id=app.dealer_profile_id,
            application_id=app.id,
            status=FinanceLoanStatus.ACTIVE,
            cash_total_price=cash_total,
            credit_total_price=credit_total,
            principal_amount=cash_total,
            down_payment_amount=dp_amt,
            financed_amount=fin_amt,
            interest_rate_annual=float(app.interest_rate_annual or 0.0),
            term_months=int(app.requested_term_months or 0),
            emi_amount=float(emi),
            total_interest=float(total_interest),
            total_payable=float(credit_total),
            late_fee_flat=float(late_fee_flat or 0.0),
            late_fee_daily_percent=float(late_fee_daily_percent or 0.0),
            grace_days=int(grace_days or 0),
            start_date=sdt,
            next_due_date=rows[0].due_date if rows else None,
        )
        try:
            db.add(loan)
            db.flush()
            for it in items:
                if it.motorcycle_id:
                    moto = db.query(Motorcycle).filter(Motorcycle.id == int(it.motorcycle_id)).first()
                    if moto and (moto.status or "").upper() == "IN_STOCK":
                        moto.status = "SOLD"
                        db.add(moto)
                db.add(
                    FinanceLoanItem(
                        loan_id=loan.id,
                        motorcycle_id=it.motorcycle_id,
                        product_model_id=it.product_model_id,
                        color=it.color,
                        quantity=int(it.quantity or 1),
                        cash_unit_price=float(it.cash_unit_price or 0.0),
                        cash_total_price=float(it.cash_total_price or 0.0),
                        unit_price=float(it.unit_price or 0.0),
                        total_price=float(it.total_price or 0.0),
                    )
                )
            for r in rows:
                db.add(
                    FinanceInstallment(
                        loan_id=loan.id,
                        installment_no=r.installment_no,
                        due_date=r.due_date,
                        principal_due=float(r.principal),
                        interest_due=float(r.interest),
                        fees_due=float(r.fees),
                        total_due=float(r.total),
                        status=FinanceInstallmentStatus.DUE,
                    )
                )
            self._audit(db, "CREATE_LOAN", "FINANCE_LOAN", loan.id, actor_user_id, {"application_id": app.id, "loan_number": loan.loan_number})
            existing_token = (
                db.query(FinancePortalToken)
                .filter(FinancePortalToken.customer_id == loan.customer_id)
                .filter(FinancePortalToken.revoked_at.is_(None))
                .order_by(FinancePortalToken.created_at.desc())
                .first()
            )
            now = dt.datetime.utcnow()
            if not existing_token or (existing_token.expires_at and existing_token.expires_at <= now):
                db.add(
                    FinancePortalToken(
                        customer_id=loan.customer_id,
                        token=secrets.token_hex(24),
                        created_at=now,
                        expires_at=now + dt.timedelta(days=365),
                        revoked_at=None,
                    )
                )
            if commit:
                db.commit()
                db.refresh(loan)
            return loan
        except Exception as exc:
            db.rollback()
            logger.error(f"Create loan failed: {exc}", exc_info=True)
            raise

    def _calc_installment_penalty(self, loan: FinanceLoan, inst: FinanceInstallment, as_of: dt.datetime) -> float:
        if not inst.due_date:
            return 0.0
        if inst.status == FinanceInstallmentStatus.PAID:
            return 0.0
        grace = int(loan.grace_days or 0)
        start = inst.due_date + dt.timedelta(days=grace)
        if as_of <= start:
            return 0.0
        days = (as_of.date() - start.date()).days
        if days <= 0:
            return 0.0
        base = float(inst.total_due or 0.0)
        flat = float(loan.late_fee_flat or 0.0)
        daily_pct = float(loan.late_fee_daily_percent or 0.0) / 100.0
        penalty = flat + (base * daily_pct * float(days))
        return round(max(0.0, penalty), 2)

    def recalculate_penalties(
        self,
        db: Session,
        loan_id: int,
        as_of: Optional[dt.datetime] = None,
        actor_user_id: Optional[int] = None,
        commit: bool = True,
    ) -> FinanceLoan:
        loan = db.query(FinanceLoan).filter(FinanceLoan.id == int(loan_id)).first()
        if not loan:
            raise ValueError("Loan not found.")
        if (loan.status or "").upper() != FinanceLoanStatus.ACTIVE:
            return loan

        now = as_of if isinstance(as_of, dt.datetime) else dt.datetime.utcnow()
        try:
            insts = (
                db.query(FinanceInstallment)
                .filter(FinanceInstallment.loan_id == loan.id)
                .order_by(FinanceInstallment.installment_no.asc())
                .all()
            )
            changed = 0
            for inst in insts:
                penalty = self._calc_installment_penalty(loan, inst, now)
                if penalty > float(inst.late_fee_accrued or 0.0):
                    inst.late_fee_accrued = penalty
                    inst.late_fee_last_calculated_at = now
                    inst.fees_due = float(penalty)
                    inst.total_due = round(float(inst.principal_due or 0.0) + float(inst.interest_due or 0.0) + float(inst.fees_due or 0.0), 2)
                    if inst.status in (FinanceInstallmentStatus.DUE, FinanceInstallmentStatus.PARTIAL) and now.date() > inst.due_date.date():
                        inst.status = FinanceInstallmentStatus.LATE
                    db.add(inst)
                    changed += 1
            if changed:
                self._audit(db, "RECALC_PENALTIES", "FINANCE_LOAN", loan.id, actor_user_id, {"installments_updated": changed})
            if commit:
                db.commit()
                db.refresh(loan)
            return loan
        except Exception as exc:
            db.rollback()
            logger.error(f"Recalculate penalties failed: {exc}", exc_info=True)
            raise

    def record_payment(
        self,
        db: Session,
        loan_id: int,
        amount: float,
        method: str,
        reference_number: str = "",
        provider: str = "",
        timestamp: Optional[dt.datetime] = None,
        received_by_user_id: Optional[int] = None,
        actor_user_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        commit: bool = True,
        sync_credit_book: bool = True,
    ) -> FinancePayment:
        loan = db.query(FinanceLoan).filter(FinanceLoan.id == int(loan_id)).first()
        if not loan:
            raise ValueError("Loan not found.")
        if (loan.status or "").upper() != FinanceLoanStatus.ACTIVE:
            raise ValueError("Payment can only be recorded for ACTIVE loans.")

        amt = float(amount or 0.0)
        if amt <= 0:
            raise ValueError("Amount must be greater than zero.")

        m = (method or "").strip().upper()
        valid_methods = {e.value for e in FinancePaymentMethod}
        if m not in valid_methods:
            raise ValueError("Invalid payment method.")

        ts = timestamp if isinstance(timestamp, dt.datetime) else dt.datetime.utcnow()

        self.recalculate_penalties(db, loan.id, as_of=ts, actor_user_id=actor_user_id, commit=commit)

        payment = FinancePayment(
            loan_id=loan.id,
            customer_id=loan.customer_id,
            timestamp=ts,
            amount=amt,
            method=m,
            provider=(provider or "").strip() or None,
            reference_number=(reference_number or "").strip() or None,
            status=FinancePaymentStatus.POSTED,
            received_by_user_id=int(received_by_user_id) if received_by_user_id else None,
            payment_metadata=metadata or None,
        )

        try:
            db.add(payment)
            db.flush()

            remaining = amt
            insts = (
                db.query(FinanceInstallment)
                .filter(FinanceInstallment.loan_id == loan.id)
                .order_by(FinanceInstallment.installment_no.asc())
                .all()
            )

            for inst in insts:
                if remaining <= 0:
                    break
                if inst.status == FinanceInstallmentStatus.PAID:
                    continue

                fees_out = max(0.0, float(inst.fees_due or 0.0) - float(inst.paid_fees or 0.0))
                int_out = max(0.0, float(inst.interest_due or 0.0) - float(inst.paid_interest or 0.0))
                prin_out = max(0.0, float(inst.principal_due or 0.0) - float(inst.paid_principal or 0.0))

                alloc_fees = min(remaining, fees_out)
                remaining = round(remaining - alloc_fees, 2)
                alloc_interest = min(remaining, int_out)
                remaining = round(remaining - alloc_interest, 2)
                alloc_principal = min(remaining, prin_out)
                remaining = round(remaining - alloc_principal, 2)

                allocated_total = round(alloc_fees + alloc_interest + alloc_principal, 2)
                if allocated_total <= 0:
                    continue

                inst.paid_fees = round(float(inst.paid_fees or 0.0) + alloc_fees, 2)
                inst.paid_interest = round(float(inst.paid_interest or 0.0) + alloc_interest, 2)
                inst.paid_principal = round(float(inst.paid_principal or 0.0) + alloc_principal, 2)
                inst.paid_total = round(float(inst.paid_total or 0.0) + allocated_total, 2)

                if inst.paid_total + 0.005 >= float(inst.total_due or 0.0):
                    inst.status = FinanceInstallmentStatus.PAID
                    inst.paid_at = ts
                else:
                    inst.status = FinanceInstallmentStatus.PARTIAL

                db.add(inst)
                db.add(
                    FinancePaymentAllocation(
                        payment_id=payment.id,
                        installment_id=inst.id,
                        principal_amount=float(alloc_principal),
                        interest_amount=float(alloc_interest),
                        fees_amount=float(alloc_fees),
                        total_allocated=float(allocated_total),
                    )
                )

            next_inst = (
                db.query(FinanceInstallment)
                .filter(FinanceInstallment.loan_id == loan.id)
                .filter(FinanceInstallment.status != FinanceInstallmentStatus.PAID)
                .order_by(FinanceInstallment.installment_no.asc())
                .first()
            )
            loan.next_due_date = next_inst.due_date if next_inst else None
            db.add(loan)

            self._audit(
                db,
                "RECORD_PAYMENT",
                "FINANCE_LOAN",
                loan.id,
                actor_user_id,
                {"payment_id": payment.id, "amount": amt, "unallocated": remaining},
            )
            if sync_credit_book:
                from app.services.credit_book_service import credit_book_service

                credit_book_service.create_transaction(
                    db=db,
                    customer_id=int(loan.customer_id),
                    direction="CREDIT",
                    entry_type=CreditBookEntryType.PAYMENT.value,
                    amount=float(amt),
                    reference_number=str(loan.loan_number or ""),
                    description="Financing Payment",
                    timestamp=ts,
                    finance_loan_id=int(loan.id),
                    created_by_user_id=int(actor_user_id) if actor_user_id else None,
                    commit=False,
                    sync_financing=False,
                )

            if commit:
                db.commit()
                db.refresh(payment)
            return payment
        except Exception as exc:
            db.rollback()
            logger.error(f"Record payment failed: {exc}", exc_info=True)
            raise

    def calculate_payoff(self, db: Session, loan_id: int, as_of: Optional[dt.datetime] = None) -> Dict[str, float]:
        loan = db.query(FinanceLoan).filter(FinanceLoan.id == int(loan_id)).first()
        if not loan:
            raise ValueError("Loan not found.")
        now = as_of if isinstance(as_of, dt.datetime) else dt.datetime.utcnow()
        self.recalculate_penalties(db, loan.id, as_of=now)

        insts = db.query(FinanceInstallment).filter(FinanceInstallment.loan_id == loan.id).all()
        outstanding_principal = 0.0
        outstanding_interest = 0.0
        outstanding_fees = 0.0
        for i in insts:
            outstanding_principal += max(0.0, float(i.principal_due or 0.0) - float(i.paid_principal or 0.0))
            outstanding_interest += max(0.0, float(i.interest_due or 0.0) - float(i.paid_interest or 0.0))
            outstanding_fees += max(0.0, float(i.fees_due or 0.0) - float(i.paid_fees or 0.0))

        total = round(outstanding_principal + outstanding_interest + outstanding_fees, 2)
        return {
            "outstanding_principal": round(outstanding_principal, 2),
            "outstanding_interest": round(outstanding_interest, 2),
            "outstanding_fees": round(outstanding_fees, 2),
            "payoff_total": total,
        }

    def refinance_loan(
        self,
        db: Session,
        old_loan_id: int,
        new_term_months: int,
        new_interest_rate_annual: float,
        fees: float = 0.0,
        actor_user_id: Optional[int] = None,
    ) -> FinanceLoan:
        self._require_role(db, actor_user_id, allowed=["admin", "manager"])
        old = db.query(FinanceLoan).filter(FinanceLoan.id == int(old_loan_id)).first()
        if not old:
            raise ValueError("Loan not found.")
        if (old.status or "").upper() != FinanceLoanStatus.ACTIVE:
            raise ValueError("Only ACTIVE loans can be refinanced.")

        payoff = self.calculate_payoff(db, old.id)
        financed_amount = float(payoff["payoff_total"]) + float(fees or 0.0)
        if financed_amount <= 0:
            raise ValueError("Invalid refinance amount.")

        sdt = dt.datetime.utcnow()
        emi, total_interest, total_payable, rows = self.generate_amortization_schedule(
            financed_amount=financed_amount,
            interest_rate_annual=float(new_interest_rate_annual),
            term_months=int(new_term_months),
            start_date=sdt,
        )

        new = FinanceLoan(
            loan_number=self._generate_loan_number(),
            customer_id=old.customer_id,
            dealer_profile_id=old.dealer_profile_id,
            application_id=None,
            status=FinanceLoanStatus.ACTIVE,
            cash_total_price=float(getattr(old, "cash_total_price", 0.0) or 0.0),
            credit_total_price=float(getattr(old, "credit_total_price", 0.0) or 0.0),
            principal_amount=float(financed_amount),
            down_payment_amount=0.0,
            financed_amount=float(financed_amount),
            interest_rate_annual=float(new_interest_rate_annual),
            term_months=int(new_term_months),
            emi_amount=float(emi),
            total_interest=float(total_interest),
            total_payable=float(total_payable),
            late_fee_flat=float(old.late_fee_flat or 0.0),
            late_fee_daily_percent=float(old.late_fee_daily_percent or 0.0),
            grace_days=int(old.grace_days or 0),
            start_date=sdt,
            next_due_date=rows[0].due_date if rows else None,
        )

        try:
            old.status = FinanceLoanStatus.REFINANCED
            old.closed_at = sdt
            old.closed_reason = "Refinanced"
            db.add(old)

            db.add(new)
            db.flush()

            old_items = db.query(FinanceLoanItem).filter(FinanceLoanItem.loan_id == old.id).all()
            for it in old_items:
                db.add(
                    FinanceLoanItem(
                        loan_id=new.id,
                        motorcycle_id=it.motorcycle_id,
                        product_model_id=it.product_model_id,
                        color=it.color,
                        quantity=int(it.quantity or 1),
                        cash_unit_price=float(getattr(it, "cash_unit_price", 0.0) or 0.0),
                        cash_total_price=float(getattr(it, "cash_total_price", 0.0) or 0.0),
                        unit_price=float(it.unit_price or 0.0),
                        total_price=float(it.total_price or 0.0),
                    )
                )

            for r in rows:
                db.add(
                    FinanceInstallment(
                        loan_id=new.id,
                        installment_no=r.installment_no,
                        due_date=r.due_date,
                        principal_due=float(r.principal),
                        interest_due=float(r.interest),
                        fees_due=float(r.fees),
                        total_due=float(r.total),
                        status=FinanceInstallmentStatus.DUE,
                    )
                )

            db.add(FinanceRefinance(old_loan_id=old.id, new_loan_id=new.id, created_at=sdt, reason="Refinance", fees=float(fees or 0.0)))
            self._audit(db, "REFINANCE_LOAN", "FINANCE_LOAN", old.id, actor_user_id, {"new_loan_id": new.id, "fees": float(fees or 0.0)})
            db.commit()
            db.refresh(new)
            return new
        except Exception as exc:
            db.rollback()
            logger.error(f"Refinance failed: {exc}", exc_info=True)
            raise

    def ensure_portal_token(self, db: Session, customer_id: int, expires_days: int = 365) -> FinancePortalToken:
        cid = int(customer_id or 0)
        if cid <= 0:
            raise ValueError("Customer is required.")
        existing = (
            db.query(FinancePortalToken)
            .filter(FinancePortalToken.customer_id == cid)
            .filter(FinancePortalToken.revoked_at.is_(None))
            .order_by(FinancePortalToken.created_at.desc())
            .first()
        )
        if existing and (not existing.expires_at or existing.expires_at > dt.datetime.utcnow()):
            return existing
        token = secrets.token_hex(24)
        now = dt.datetime.utcnow()
        exp = now + dt.timedelta(days=int(expires_days or 365))
        row = FinancePortalToken(customer_id=cid, token=token, created_at=now, expires_at=exp, revoked_at=None)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def portfolio_metrics(self, db: Session, as_of: Optional[dt.datetime] = None) -> Dict[str, float]:
        now = as_of if isinstance(as_of, dt.datetime) else dt.datetime.utcnow()
        active_loans = db.query(func.count(FinanceLoan.id)).filter(FinanceLoan.status == FinanceLoanStatus.ACTIVE).scalar() or 0
        total_financed = (
            db.query(func.coalesce(func.sum(FinanceLoan.financed_amount), 0.0))
            .filter(FinanceLoan.status == FinanceLoanStatus.ACTIVE)
            .scalar()
            or 0.0
        )

        overdue = (
            db.query(func.count(FinanceInstallment.id))
            .join(FinanceLoan, FinanceInstallment.loan_id == FinanceLoan.id)
            .filter(FinanceLoan.status == FinanceLoanStatus.ACTIVE)
            .filter(FinanceInstallment.status.in_([FinanceInstallmentStatus.DUE, FinanceInstallmentStatus.PARTIAL, FinanceInstallmentStatus.LATE]))
            .filter(FinanceInstallment.due_date < now)
            .scalar()
            or 0
        )

        total_due = (
            db.query(func.coalesce(func.sum(FinanceInstallment.total_due - FinanceInstallment.paid_total), 0.0))
            .join(FinanceLoan, FinanceInstallment.loan_id == FinanceLoan.id)
            .filter(FinanceLoan.status == FinanceLoanStatus.ACTIVE)
            .filter(FinanceInstallment.status != FinanceInstallmentStatus.PAID)
            .scalar()
            or 0.0
        )
        total_paid = (
            db.query(func.coalesce(func.sum(FinancePayment.amount), 0.0))
            .filter(FinancePayment.status == FinancePaymentStatus.POSTED)
            .scalar()
            or 0.0
        )
        return {
            "active_loans": float(active_loans),
            "total_financed": float(total_financed),
            "overdue_installments": float(overdue),
            "total_outstanding": float(round(total_due, 2)),
            "total_paid": float(round(total_paid, 2)),
        }


financing_service = FinancingService()
