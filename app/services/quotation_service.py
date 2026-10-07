from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session, selectinload

from app.core.logger import logger
from app.db.models import Quotation, QuotationAccessoryItem, QuotationCounter, QuotationItem, pk_now


class QuotationService:
    def generate_next_seq(self, db: Session) -> int:
        counter = (
            db.query(QuotationCounter)
            .filter(QuotationCounter.counter_key == "GLOBAL")
            .with_for_update()
            .first()
        )
        if not counter:
            counter = QuotationCounter(counter_key="GLOBAL", last_seq=0, updated_at=dt.datetime.utcnow())
            db.add(counter)
            db.flush()
            counter = (
                db.query(QuotationCounter)
                .filter(QuotationCounter.counter_key == "GLOBAL")
                .with_for_update()
                .first()
            )
            if not counter:
                raise RuntimeError("Unable to initialize quotation counter.")

        counter.last_seq = int(counter.last_seq or 0) + 1
        counter.updated_at = dt.datetime.utcnow()
        db.flush()
        return int(counter.last_seq)

    def generate_quotation_number(self, db: Session) -> str:
        seq = self.generate_next_seq(db)
        return f"Q-{seq:06d}"

    def _validate_items(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not items:
            raise ValueError("At least one line item is required.")

        validated: List[Dict[str, Any]] = []
        for idx, raw in enumerate(items, start=1):
            model = str((raw.get("motorcycle_model") or "")).strip().upper()
            color = str((raw.get("color") or "")).strip().upper()
            try:
                quantity = float(raw.get("quantity") or 0)
            except (TypeError, ValueError):
                quantity = 0.0
            try:
                unit_price = float(raw.get("unit_price") or 0)
            except (TypeError, ValueError):
                unit_price = 0.0

            if not model:
                raise ValueError(f"Line {idx}: Motorcycle Model is required.")
            if quantity <= 0:
                raise ValueError(f"Line {idx}: Quantity must be greater than zero.")
            if unit_price <= 0:
                raise ValueError(f"Line {idx}: Unit Price must be greater than zero.")

            validated.append({
                "line_no": idx,
                "motorcycle_model": model,
                "color": color,
                "quantity": quantity,
                "unit_price": unit_price,
                "line_total": round(quantity * unit_price, 2),
            })
        return validated

    def _validate_accessory_items(self, accessory_items: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """Accessories (helmet, safeguard, etc.) are manually named and
        priced by staff - deliberately no catalog to look up, unlike
        motorcycle line items. Optional: a quotation can have zero
        accessories. Unit price may be zero (e.g. a promotional freebie
        line), but never negative."""
        if not accessory_items:
            return []

        validated: List[Dict[str, Any]] = []
        for idx, raw in enumerate(accessory_items, start=1):
            name = str((raw.get("item_name") or "")).strip().upper()
            try:
                quantity = float(raw.get("quantity") or 0)
            except (TypeError, ValueError):
                quantity = 0.0
            try:
                unit_price = float(raw.get("unit_price") or 0)
            except (TypeError, ValueError):
                unit_price = 0.0

            if not name:
                raise ValueError(f"Accessory {idx}: Item Name is required.")
            if quantity <= 0:
                raise ValueError(f"Accessory {idx}: Quantity must be greater than zero.")
            if unit_price < 0:
                raise ValueError(f"Accessory {idx}: Unit Price cannot be negative.")

            validated.append({
                "line_no": idx,
                "item_name": name,
                "quantity": quantity,
                "unit_price": unit_price,
                "line_total": round(quantity * unit_price, 2),
            })
        return validated

    def create_quotation(
        self,
        db: Session,
        customer_name: str,
        items: List[Dict[str, Any]],
        accessory_items: Optional[List[Dict[str, Any]]] = None,
        customer_phone: Optional[str] = None,
        customer_address: Optional[str] = None,
        discount_amount: float = 0.0,
        valid_until: Optional[dt.datetime] = None,
        notes: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> Quotation:
        name = (customer_name or "").strip().upper()
        if not name:
            raise ValueError("Customer Name is required.")

        validated_items = self._validate_items(items)
        validated_accessory_items = self._validate_accessory_items(accessory_items)
        moto_subtotal = round(sum(i["line_total"] for i in validated_items), 2)
        accessories_subtotal = round(sum(i["line_total"] for i in validated_accessory_items), 2)
        subtotal = round(moto_subtotal + accessories_subtotal, 2)

        discount = float(discount_amount or 0.0)
        if discount < 0:
            raise ValueError("Discount cannot be negative.")
        if discount > subtotal:
            raise ValueError("Discount cannot be greater than Subtotal.")

        total_amount = round(subtotal - discount, 2)
        now = pk_now()

        quotation = Quotation(
            quotation_number=self.generate_quotation_number(db),
            created_at=now,
            updated_at=now,
            customer_name=name,
            customer_phone=(customer_phone or "").strip(),
            customer_address=(customer_address or "").strip().upper(),
            subtotal=subtotal,
            accessories_subtotal=accessories_subtotal,
            discount_amount=discount,
            total_amount=total_amount,
            valid_until=valid_until,
            notes=(notes or "").strip(),
            status="PENDING",
            created_by=(created_by or "").strip() or None,
        )
        db.add(quotation)

        try:
            db.flush()
            for item in validated_items:
                db.add(QuotationItem(quotation_id=quotation.id, **item))
            for accessory in validated_accessory_items:
                db.add(QuotationAccessoryItem(quotation_id=quotation.id, **accessory))
            db.commit()
            db.refresh(quotation)
        except Exception as e:
            db.rollback()
            logger.error(f"Quotation create failed: {e}", exc_info=True)
            raise

        return quotation

    def update_quotation(
        self,
        db: Session,
        quotation_number: str,
        customer_name: Optional[str] = None,
        customer_phone: Optional[str] = None,
        customer_address: Optional[str] = None,
        items: Optional[List[Dict[str, Any]]] = None,
        accessory_items: Optional[List[Dict[str, Any]]] = None,
        discount_amount: Optional[float] = None,
        valid_until: Optional[dt.datetime] = None,
        notes: Optional[str] = None,
    ) -> Quotation:
        quotation = self.get_by_number(db, quotation_number)
        if not quotation:
            raise ValueError("Quotation not found.")
        if quotation.status != "PENDING":
            raise ValueError("Only PENDING quotations can be modified.")

        if customer_name is not None:
            name = customer_name.strip().upper()
            if not name:
                raise ValueError("Customer Name is required.")
            quotation.customer_name = name
        if customer_phone is not None:
            quotation.customer_phone = customer_phone.strip()
        if customer_address is not None:
            quotation.customer_address = customer_address.strip().upper()
        if valid_until is not None:
            quotation.valid_until = valid_until
        if notes is not None:
            quotation.notes = notes.strip()

        if items is not None:
            validated_items = self._validate_items(items)
            for existing in list(quotation.items):
                db.delete(existing)
            db.flush()
            for item in validated_items:
                db.add(QuotationItem(quotation_id=quotation.id, **item))
            db.flush()

        if accessory_items is not None:
            validated_accessory_items = self._validate_accessory_items(accessory_items)
            for existing in list(quotation.accessory_items):
                db.delete(existing)
            db.flush()
            for accessory in validated_accessory_items:
                db.add(QuotationAccessoryItem(quotation_id=quotation.id, **accessory))
            db.flush()

        if items is not None or accessory_items is not None:
            db.refresh(quotation)
            moto_subtotal = round(sum(i.line_total for i in quotation.items), 2)
            accessories_subtotal = round(sum(a.line_total for a in quotation.accessory_items), 2)
            quotation.subtotal = round(moto_subtotal + accessories_subtotal, 2)
            quotation.accessories_subtotal = accessories_subtotal

        if discount_amount is not None:
            discount = float(discount_amount or 0.0)
            if discount < 0:
                raise ValueError("Discount cannot be negative.")
            if discount > quotation.subtotal:
                raise ValueError("Discount cannot be greater than Subtotal.")
            quotation.discount_amount = discount

        quotation.total_amount = round(float(quotation.subtotal) - float(quotation.discount_amount), 2)
        quotation.updated_at = pk_now()

        try:
            db.commit()
            db.refresh(quotation)
        except Exception as e:
            db.rollback()
            logger.error(f"Quotation update failed: {e}", exc_info=True)
            raise

        return quotation

    def cancel_quotation(self, db: Session, quotation_number: str) -> Quotation:
        quotation = self.get_by_number(db, quotation_number)
        if not quotation:
            raise ValueError("Quotation not found.")
        if quotation.status == "CANCELLED":
            raise ValueError("Quotation is already cancelled.")

        quotation.status = "CANCELLED"
        quotation.updated_at = pk_now()
        try:
            db.commit()
            db.refresh(quotation)
        except Exception as e:
            db.rollback()
            logger.error(f"Quotation cancel failed: {e}", exc_info=True)
            raise
        return quotation

    def reactivate_quotation(self, db: Session, quotation_number: str) -> Quotation:
        quotation = self.get_by_number(db, quotation_number)
        if not quotation:
            raise ValueError("Quotation not found.")
        if quotation.status != "CANCELLED":
            raise ValueError("Only cancelled quotations can be reactivated.")

        quotation.status = "PENDING"
        quotation.updated_at = pk_now()
        try:
            db.commit()
            db.refresh(quotation)
        except Exception as e:
            db.rollback()
            logger.error(f"Quotation reactivate failed: {e}", exc_info=True)
            raise
        return quotation

    def get_by_number(self, db: Session, quotation_number: str) -> Optional[Quotation]:
        key = (quotation_number or "").strip()
        if not key:
            return None
        return (
            db.query(Quotation)
            .options(selectinload(Quotation.items), selectinload(Quotation.accessory_items))
            .filter(Quotation.quotation_number == key)
            .first()
        )

    def list_quotations(
        self,
        db: Session,
        limit: int = 300,
        status: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Quotation]:
        q = db.query(Quotation).options(selectinload(Quotation.items), selectinload(Quotation.accessory_items))
        if status and status != "ALL":
            q = q.filter(Quotation.status == status)
        if search:
            from sqlalchemy import func
            s = f"%{(search or '').strip().upper()}%"
            q = q.filter(
                (func.upper(Quotation.customer_name).like(s))
                | (func.upper(Quotation.quotation_number).like(s))
                | (func.upper(Quotation.customer_phone).like(s))
            )
        return q.order_by(Quotation.id.desc()).limit(int(limit or 300)).all()


quotation_service = QuotationService()
