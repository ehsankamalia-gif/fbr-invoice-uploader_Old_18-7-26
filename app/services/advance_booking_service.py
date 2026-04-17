from __future__ import annotations

import datetime as dt
from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.logger import logger
from app.db.models import AdvanceBooking


class AdvanceBookingService:
    def generate_next_booking_number(self, db: Session) -> str:
        last = db.query(AdvanceBooking).order_by(AdvanceBooking.id.desc()).first()
        next_seq = (int(last.id) + 1) if last else 1
        prefix = dt.datetime.utcnow().strftime("AB%Y%m")
        return f"{prefix}-{next_seq:05d}"

    def create_booking(
        self,
        db: Session,
        customer_name: str,
        motorcycle_model: str,
        color: str,
        total_price: float,
        advance_paid: float,
        booking_number: Optional[str] = None,
    ) -> AdvanceBooking:
        name = (customer_name or "").strip().upper()
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
            booking_number = self.generate_next_booking_number(db)

        balance = float(total_price) - float(advance_paid)

        booking = AdvanceBooking(
            booking_number=booking_number,
            customer_name=name,
            motorcycle_model=model,
            color=clr,
            total_price=float(total_price),
            advance_paid=float(advance_paid),
            balance_amount=float(balance),
            status="ACTIVE",
        )

        db.add(booking)
        try:
            db.commit()
            db.refresh(booking)
        except Exception as e:
            db.rollback()
            logger.error(f"Advance booking create failed: {e}", exc_info=True)
            raise

        return booking

    def list_bookings(self, db: Session, limit: int = 200) -> List[AdvanceBooking]:
        return (
            db.query(AdvanceBooking)
            .order_by(AdvanceBooking.id.desc())
            .limit(int(limit or 200))
            .all()
        )

    def get_by_booking_number(self, db: Session, booking_number: str) -> Optional[AdvanceBooking]:
        key = (booking_number or "").strip()
        if not key:
            return None
        return db.query(AdvanceBooking).filter(AdvanceBooking.booking_number == key).first()


advance_booking_service = AdvanceBookingService()

