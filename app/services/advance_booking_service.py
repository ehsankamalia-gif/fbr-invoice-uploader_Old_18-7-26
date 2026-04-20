from __future__ import annotations

import datetime as dt
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.logger import logger
from app.db.models import AdvanceBooking, AdvanceBookingAudit, AdvanceBookingModelCounter, SpareLedgerTransaction, pk_now


class AdvanceBookingService:
    def _sanitize_model_code(self, model_name: str) -> str:
        raw = (model_name or "").upper()
        code = "".join(ch for ch in raw if ch.isalnum())
        return code or "MODEL"

    def _month_key_for_ts(self, ts: dt.datetime) -> str:
        if ts.day >= 6:
            cycle_date = ts + dt.timedelta(days=30)
            return cycle_date.strftime("%Y-%m")
        return ts.strftime("%Y-%m")

    def generate_next_model_seq(self, db: Session, model_code: str) -> int:
        code = (model_code or "").strip().upper()
        if not code:
            raise ValueError("Model code is required.")

        counter = (
            db.query(AdvanceBookingModelCounter)
            .filter(AdvanceBookingModelCounter.model_code == code)
            .with_for_update()
            .first()
        )
        if not counter:
            counter = AdvanceBookingModelCounter(model_code=code, last_seq=0, updated_at=dt.datetime.utcnow())
            db.add(counter)
            db.flush()
            counter = (
                db.query(AdvanceBookingModelCounter)
                .filter(AdvanceBookingModelCounter.model_code == code)
                .with_for_update()
                .first()
            )
            if not counter:
                raise RuntimeError("Unable to initialize booking counter.")

        counter.last_seq = int(counter.last_seq or 0) + 1
        counter.updated_at = dt.datetime.utcnow()
        db.flush()
        return int(counter.last_seq)

    def generate_booking_number(self, db: Session, motorcycle_model: str) -> tuple[str, str, int]:
        model_name = (motorcycle_model or "").strip().upper()
        model_code = self._sanitize_model_code(model_name)
        seq = self.generate_next_model_seq(db, model_code)
        return f"{model_code}-{seq}", model_code, seq

    def create_booking(
        self,
        db: Session,
        customer_name: str,
        motorcycle_model: str,
        color: str,
        total_price: float,
        advance_paid: float,
        customer_phone: Optional[str] = None,
        booking_number: Optional[str] = None,
    ) -> AdvanceBooking:
        name = (customer_name or "").strip().upper()
        phone = (customer_phone or "").strip()
        model = (motorcycle_model or "").strip().upper()
        clr = (color or "").strip().upper()

        if not name:
            raise ValueError("Customer Name is required.")
        if not model:
            raise ValueError("Motorcycle Model is required.")
        if not clr:
            raise ValueError("Color is required.")
        if total_price <= 0:
            raise ValueError("Total Price must be greater than zero.")
        if advance_paid < 0:
            raise ValueError("Advance Amount must be zero or greater.")
        if advance_paid > total_price:
            raise ValueError("Advance Amount cannot be greater than Total Price.")

        if not booking_number:
            booking_number, model_code, model_seq = self.generate_booking_number(db, model)
        else:
            model_code = self._sanitize_model_code(model)
            model_seq = None

        balance = float(total_price) - float(advance_paid)
        now = pk_now()

        booking = AdvanceBooking(
            booking_number=booking_number,
            created_at=now,
            customer_name=name,
            customer_phone=phone,
            motorcycle_model=model,
            model_code=model_code,
            model_seq=model_seq,
            color=clr,
            total_price=float(total_price),
            advance_paid=float(advance_paid),
            balance_amount=float(balance),
            status="ACTIVE",
            advance_remaining=float(advance_paid),
            advance_applied=0.0,
            delivery_paid=0.0,
        )

        db.add(booking)
        try:
            db.flush()
            db.add(
                AdvanceBookingAudit(
                    booking_number=booking.booking_number,
                    action="BOOKING_PAYMENT",
                    amount=float(advance_paid),
                    before_advance_remaining=0.0,
                    after_advance_remaining=float(advance_paid),
                    before_balance_amount=float(total_price),
                    after_balance_amount=float(balance),
                    note="Advance received at booking time.",
                )
            )
            if float(advance_paid) > 0:
                ts = now
                mk = self._month_key_for_ts(ts)
                db.add(
                    SpareLedgerTransaction(
                        trans_type="CREDIT",
                        amount=float(advance_paid),
                        cash_type="HARD_CASH",
                        reference_number=booking.booking_number,
                        description=f"Advance Booking - Advance Received - {booking.customer_name} - {booking.motorcycle_model} {booking.color}",
                        month_key=mk,
                        timestamp=ts,
                    )
                )
            db.commit()
            db.refresh(booking)
            
            # Send SMS to customer if phone is provided
            if phone:
                try:
                    self._send_booking_sms(db, booking)
                except Exception as sms_err:
                    logger.error(f"Non-critical SMS failure for {booking.booking_number}: {sms_err}")
                
        except Exception as e:
            db.rollback()
            logger.error(f"Advance booking create failed: {e}", exc_info=True)
            raise

        return booking

    def _send_booking_sms(self, db: Session, booking: AdvanceBooking) -> None:
        """Helper to queue/send SMS for a new booking with customizable template."""
        try:
            from app.services.sms_service import sms_service
            from app.db.models import SMSConfiguration, SMSQueue, SMSStatus
            
            config = db.query(SMSConfiguration).filter(SMSConfiguration.is_enabled == True).first()
            if not config or not booking.customer_phone:
                return

            # Use template if available, otherwise fallback to default
            template = getattr(config, 'booking_template', "")
            if not template:
                template = "Dear {customer}, your booking for {model} ({color}) is confirmed. Booking #: {booking_no}. Paid: Rs. {paid}. Balance: Rs. {balance}."

            msg = template.format(
                customer=booking.customer_name,
                model=booking.motorcycle_model,
                color=booking.color,
                booking_no=booking.booking_number,
                paid=f"{booking.advance_paid:,.0f}",
                balance=f"{booking.balance_amount:,.0f}"
            )
            
            logger.info(f"Queueing booking SMS for {booking.booking_number} to {booking.customer_phone}")
            
            # Queue the message
            sms_entry = SMSQueue(
                phone_number=booking.customer_phone,
                recipient_name=booking.customer_name,
                message=msg,
                status=SMSStatus.PENDING,
                channel="SMS",
                created_at=dt.datetime.utcnow()
            )
            db.add(sms_entry)
            db.commit()
            
            # Try to send immediately
            if config.gateway_type == "WIFI" and config.gateway_ip:
                success, reason = sms_service.send_sms_via_wifi(
                    ip=config.gateway_ip,
                    port=config.gateway_port or "8080",
                    phone_number=booking.customer_phone,
                    msg_content=msg,
                    api_key=config.api_key,
                    username=config.gateway_username,
                    password=config.gateway_password,
                    use_https=config.use_https
                )
                if success:
                    sms_entry.status = SMSStatus.SENT
                    sms_entry.sent_at = dt.datetime.utcnow()
                    db.commit()
                else:
                    sms_entry.status = SMSStatus.FAILED
                    sms_entry.error_message = reason
                    db.commit()
                    
        except Exception as e:
            logger.error(f"Failed to send booking SMS: {e}")

    def update_booking(
        self,
        db: Session,
        booking_number: str,
        customer_name: Optional[str] = None,
        customer_phone: Optional[str] = None,
        motorcycle_model: Optional[str] = None,
        color: Optional[str] = None,
        total_price: Optional[float] = None,
        advance_paid: Optional[float] = None,
    ) -> AdvanceBooking:
        booking = self.get_by_booking_number(db, booking_number)
        if not booking:
            raise ValueError("Booking not found.")
        
        if booking.status != "ACTIVE":
            raise ValueError("Only ACTIVE bookings can be modified.")

        if customer_name:
            booking.customer_name = customer_name.strip().upper()
        if customer_phone is not None:
            booking.customer_phone = customer_phone.strip()
        if motorcycle_model:
            booking.motorcycle_model = motorcycle_model.strip().upper()
        if color:
            booking.color = color.strip().upper()
        
        if total_price is not None:
            if total_price <= 0:
                raise ValueError("Total Price must be greater than zero.")
            booking.total_price = float(total_price)
            
        if advance_paid is not None:
            if advance_paid < 0:
                raise ValueError("Advance Amount must be zero or greater.")
            # Note: Changing advance_paid after booking requires audit and potentially ledger adjustment
            # but for simplicity we'll just update the field and recalculate balance.
            # Realistically, a refund or extra payment should be handled via separate service methods.
            booking.advance_paid = float(advance_paid)
            booking.advance_remaining = float(advance_paid)

        booking.balance_amount = float(booking.total_price) - float(booking.advance_paid)
        
        try:
            db.commit()
            db.refresh(booking)
            return booking
        except Exception as e:
            db.rollback()
            logger.error(f"Advance booking update failed: {e}", exc_info=True)
            raise

    def list_bookings(
        self,
        db: Session,
        limit: int = 200,
        status: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[AdvanceBooking]:
        q = db.query(AdvanceBooking)
        if status:
            q = q.filter(AdvanceBooking.status == status)
        if search:
            s = f"%{(search or '').strip().upper()}%"
            q = q.filter(
                (func.upper(AdvanceBooking.customer_name).like(s))
                | (func.upper(AdvanceBooking.booking_number).like(s))
                | (func.upper(AdvanceBooking.motorcycle_model).like(s))
                | (func.upper(AdvanceBooking.color).like(s))
            )
        return q.order_by(AdvanceBooking.id.desc()).limit(int(limit or 200)).all()

    def get_by_booking_number(self, db: Session, booking_number: str) -> Optional[AdvanceBooking]:
        key = (booking_number or "").strip()
        if not key:
            return None
        return db.query(AdvanceBooking).filter(AdvanceBooking.booking_number == key).first()

    def mark_delivered(self, db: Session, booking_number: str, delivery_paid: float) -> AdvanceBooking:
        booking = self.get_by_booking_number(db, booking_number)
        if not booking:
            raise ValueError("Booking not found.")
        if (booking.status or "").upper() == "DELIVERED":
            raise ValueError("Booking is already marked as delivered.")

        before_remaining = float(getattr(booking, "advance_remaining", 0.0) or 0.0)
        if before_remaining < 0:
            raise ValueError("Invalid advance remaining value.")

        apply_amount = before_remaining

        required_balance = float(getattr(booking, "balance_amount", 0.0) or 0.0)
        pay = float(delivery_paid or 0.0)
        if required_balance < 0:
            raise ValueError("Invalid balance amount.")
        if required_balance > 0:
            if pay <= 0:
                raise ValueError("Remaining balance must be paid in full before delivery.")
            if abs(pay - required_balance) > 0.01:
                raise ValueError(f"Delivery payment must be exactly Rs. {required_balance:,.0f}.")
        else:
            if pay != 0:
                raise ValueError("No balance is due for this booking.")

        booking.status = "DELIVERED"
        booking.delivered_at = pk_now()
        if apply_amount > 0:
            booking.advance_remaining = 0.0
            booking.advance_applied = float(getattr(booking, "advance_applied", 0.0) or 0.0) + apply_amount

        if required_balance > 0:
            booking.delivery_paid = float(getattr(booking, "delivery_paid", 0.0) or 0.0) + pay
            booking.balance_amount = 0.0

        # Final safety check to prevent data corruption
        if booking.advance_remaining < 0 or booking.balance_amount < 0:
            db.rollback()
            raise ValueError("Transaction aborted: Delivery would result in negative financial balances.")

        try:
            if apply_amount > 0:
                db.add(
                    AdvanceBookingAudit(
                        booking_number=booking.booking_number,
                        action="APPLY_ON_DELIVERY",
                        amount=apply_amount,
                        before_advance_remaining=before_remaining,
                        after_advance_remaining=0.0,
                        note="Auto-apply outstanding advance on delivery confirmation.",
                    )
                )

            if required_balance > 0:
                db.add(
                    AdvanceBookingAudit(
                        booking_number=booking.booking_number,
                        action="DELIVERY_PAYMENT",
                        amount=pay,
                        before_advance_remaining=float(getattr(booking, "advance_remaining", 0.0) or 0.0),
                        after_advance_remaining=float(getattr(booking, "advance_remaining", 0.0) or 0.0),
                        before_balance_amount=required_balance,
                        after_balance_amount=0.0,
                        note="Balance collected at delivery.",
                    )
                )
                ts = booking.delivered_at or pk_now()
                mk = self._month_key_for_ts(ts)
                db.add(
                    SpareLedgerTransaction(
                        trans_type="CREDIT",
                        amount=pay,
                        cash_type="HARD_CASH",
                        reference_number=booking.booking_number,
                        description=f"Advance Booking - Delivery Payment - {booking.customer_name} - {booking.motorcycle_model} {booking.color}",
                        month_key=mk,
                        timestamp=ts,
                    )
                )
            db.commit()
            db.refresh(booking)
        except Exception as e:
            db.rollback()
            logger.error(f"Advance booking mark_delivered failed: {e}", exc_info=True)
            raise
        return booking

    def mark_active(self, db: Session, booking_number: str) -> AdvanceBooking:
        booking = self.get_by_booking_number(db, booking_number)
        if not booking:
            raise ValueError("Booking not found.")
        if (booking.status or "").upper() == "ACTIVE":
            raise ValueError("Booking is already active.")

        restore_amount = float(getattr(booking, "advance_applied", 0.0) or 0.0)
        if restore_amount < 0:
            raise ValueError("Invalid applied advance value.")

        before_remaining = float(getattr(booking, "advance_remaining", 0.0) or 0.0)
        after_remaining = before_remaining + restore_amount

        delivered_payment = float(getattr(booking, "delivery_paid", 0.0) or 0.0)
        restored_balance = float(getattr(booking, "total_price", 0.0) or 0.0) - float(getattr(booking, "advance_paid", 0.0) or 0.0)
        if restored_balance < 0:
            restored_balance = 0.0

        booking.status = "ACTIVE"
        booking.delivered_at = None
        booking.advance_remaining = after_remaining
        booking.advance_applied = 0.0
        booking.balance_amount = restored_balance
        booking.delivery_paid = 0.0
        try:
            db.add(
                AdvanceBookingAudit(
                    booking_number=booking.booking_number,
                    action="REVERSE_DELIVERY",
                    amount=restore_amount,
                    before_advance_remaining=before_remaining,
                    after_advance_remaining=after_remaining,
                    note="Reversed delivery status; restored outstanding advance balance.",
                )
            )
            if delivered_payment > 0:
                db.add(
                    AdvanceBookingAudit(
                        booking_number=booking.booking_number,
                        action="REVERSE_DELIVERY_PAYMENT",
                        amount=delivered_payment,
                        before_advance_remaining=after_remaining,
                        after_advance_remaining=after_remaining,
                        before_balance_amount=0.0,
                        after_balance_amount=restored_balance,
                        note="Reversed delivery payment (return/cancellation).",
                    )
                )
                ts = dt.datetime.utcnow()
                mk = self._month_key_for_ts(ts)
                db.add(
                    SpareLedgerTransaction(
                        trans_type="DEBIT",
                        amount=delivered_payment,
                        cash_type="HARD_CASH",
                        reference_number=booking.booking_number,
                        description=f"Advance Booking - Reverse Delivery Payment - {booking.customer_name} - {booking.motorcycle_model} {booking.color}",
                        month_key=mk,
                        timestamp=ts,
                    )
                )
            db.commit()
            db.refresh(booking)
        except Exception as e:
            db.rollback()
            logger.error(f"Advance booking mark_active failed: {e}", exc_info=True)
            raise
        return booking

    def apply_advance(self, db: Session, booking_number: str, amount: float, note: str = "") -> AdvanceBooking:
        booking = self.get_by_booking_number(db, booking_number)
        if not booking:
            raise ValueError("Booking not found.")
        if (booking.status or "").upper() != "ACTIVE":
            raise ValueError("Advance can only be applied for ACTIVE bookings.")

        amt = float(amount or 0.0)
        if amt <= 0:
            raise ValueError("Amount must be greater than zero.")

        before_remaining = float(getattr(booking, "advance_remaining", 0.0) or 0.0)
        if amt > before_remaining:
            raise ValueError("Cannot apply more than outstanding advance amount.")

        after_remaining = before_remaining - amt
        booking.advance_remaining = after_remaining
        booking.advance_applied = float(getattr(booking, "advance_applied", 0.0) or 0.0) + amt

        try:
            db.add(
                AdvanceBookingAudit(
                    booking_number=booking.booking_number,
                    action="APPLY",
                    amount=amt,
                    before_advance_remaining=before_remaining,
                    after_advance_remaining=after_remaining,
                    note=(note or "").strip() or "Manual apply advance.",
                )
            )
            db.commit()
            db.refresh(booking)
        except Exception as e:
            db.rollback()
            logger.error(f"Advance booking apply_advance failed: {e}", exc_info=True)
            raise
        return booking

    def reverse_advance(self, db: Session, booking_number: str, amount: float, note: str = "") -> AdvanceBooking:
        booking = self.get_by_booking_number(db, booking_number)
        if not booking:
            raise ValueError("Booking not found.")

        amt = float(amount or 0.0)
        if amt <= 0:
            raise ValueError("Amount must be greater than zero.")

        applied = float(getattr(booking, "advance_applied", 0.0) or 0.0)
        if amt > applied:
            raise ValueError("Cannot reverse more than applied advance amount.")

        before_remaining = float(getattr(booking, "advance_remaining", 0.0) or 0.0)
        after_remaining = before_remaining + amt

        booking.advance_remaining = after_remaining
        booking.advance_applied = applied - amt

        try:
            db.add(
                AdvanceBookingAudit(
                    booking_number=booking.booking_number,
                    action="REVERSE",
                    amount=amt,
                    before_advance_remaining=before_remaining,
                    after_advance_remaining=after_remaining,
                    note=(note or "").strip() or "Manual reverse advance.",
                )
            )
            db.commit()
            db.refresh(booking)
        except Exception as e:
            db.rollback()
            logger.error(f"Advance booking reverse_advance failed: {e}", exc_info=True)
            raise
        return booking

    def get_summary(self, db: Session) -> dict:
        # Active Bookings (Held)
        outstanding_advance = (
            db.query(func.coalesce(func.sum(AdvanceBooking.advance_remaining), 0.0))
            .filter(AdvanceBooking.status == "ACTIVE")
            .scalar()
            or 0.0
        )
        outstanding_balance = (
            db.query(func.coalesce(func.sum(AdvanceBooking.balance_amount), 0.0))
            .filter(AdvanceBooking.status == "ACTIVE")
            .scalar()
            or 0.0
        )
        active_count = (
            db.query(func.count(AdvanceBooking.id))
            .filter(AdvanceBooking.status == "ACTIVE")
            .scalar()
            or 0
        )

        # Delivered Bookings (Realized)
        delivered_total_value = (
            db.query(func.coalesce(func.sum(AdvanceBooking.total_price), 0.0))
            .filter(AdvanceBooking.status == "DELIVERED")
            .scalar()
            or 0.0
        )
        delivered_advance = (
            db.query(func.coalesce(func.sum(AdvanceBooking.advance_paid), 0.0))
            .filter(AdvanceBooking.status == "DELIVERED")
            .scalar()
            or 0.0
        )
        delivered_balance_collected = (
            db.query(func.coalesce(func.sum(AdvanceBooking.delivery_paid), 0.0))
            .filter(AdvanceBooking.status == "DELIVERED")
            .scalar()
            or 0.0
        )
        delivered_count = (
            db.query(func.count(AdvanceBooking.id))
            .filter(AdvanceBooking.status == "DELIVERED")
            .scalar()
            or 0
        )

        return {
            "outstanding_advance": float(outstanding_advance),
            "outstanding_balance": float(outstanding_balance),
            "active_count": int(active_count),
            "delivered_total_value": float(delivered_total_value),
            "delivered_advance": float(delivered_advance),
            "delivered_balance": float(delivered_balance_collected),
            "delivered_count": int(delivered_count),
        }

    def get_active_counts_by_model(self, db: Session, limit: int = 12) -> List[tuple[str, int]]:
        rows = (
            db.query(AdvanceBooking.motorcycle_model, func.count(AdvanceBooking.id))
            .filter(AdvanceBooking.status == "ACTIVE")
            .group_by(AdvanceBooking.motorcycle_model)
            .order_by(func.count(AdvanceBooking.id).desc(), AdvanceBooking.motorcycle_model.asc())
            .limit(int(limit or 12))
            .all()
        )
        return [(str(m or ""), int(c or 0)) for (m, c) in rows]

    def get_model_booking_counters(self, db: Session, limit: int = 12) -> List[tuple[str, int]]:
        rows = (
            db.query(AdvanceBookingModelCounter.model_code, AdvanceBookingModelCounter.last_seq)
            .order_by(AdvanceBookingModelCounter.last_seq.desc(), AdvanceBookingModelCounter.model_code.asc())
            .limit(int(limit or 12))
            .all()
        )
        return [(str(m or ""), int(c or 0)) for (m, c) in rows]


advance_booking_service = AdvanceBookingService()

