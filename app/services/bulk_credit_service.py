from sqlalchemy.orm import Session, joinedload
from app.db.session import SessionLocal
from app.db.models import (
    BulkCreditPurchase, BulkCreditItem, CreditPaymentSchedule, 
    Customer, Motorcycle, CustomerType
)
from typing import List, Optional, Dict, Any
import datetime as dt
from app.core.logger import logger
from app.services.customer_portal_service import customer_portal_service

class BulkCreditService:
    def _get_db(self) -> Session:
        return SessionLocal()

    def create_bulk_purchase(self, header_data: Dict[str, Any], items_data: List[Dict[str, Any]]) -> BulkCreditPurchase:
        """
        Creates a bulk credit purchase with items and updates inventory.
        """
        db = self._get_db()
        try:
            # 1. Validate Credit Limit (Example: 1,000,000 for individuals, 10,000,000 for dealers if not set)
            customer = db.query(Customer).filter(Customer.id == header_data.get('customer_id')).first()
            limit = 10000000 if customer and customer.type == CustomerType.DEALER else 1000000
            
            # Check existing active balance
            active_balance = db.query(BulkCreditPurchase).filter(
                BulkCreditPurchase.customer_name == header_data['customer_name'],
                BulkCreditPurchase.status == "ACTIVE"
            ).with_entities(BulkCreditPurchase.remaining_balance).all()
            
            total_active = sum([b[0] for b in active_balance])
            if (total_active + header_data['remaining_balance']) > limit:
                raise ValueError(f"Credit limit exceeded. Current active: {total_active:,.2f}, New: {header_data['remaining_balance']:,.2f}, Limit: {limit:,.2f}")

            # 2. Create Purchase Header
            purchase = BulkCreditPurchase(**header_data)
            db.add(purchase)
            db.flush() # Get purchase.id

            # 3. Create Items and Update Inventory
            for item in items_data:
                bulk_item = BulkCreditItem(purchase_id=purchase.id, **item)
                db.add(bulk_item)
                
                # Update Motorcycle Status
                motorcycle = db.query(Motorcycle).filter(Motorcycle.chassis_number == item['chassis_no']).first()
                if motorcycle:
                    motorcycle.status = "SOLD"
                    motorcycle.sale_price = item['net_price']
            
            # 4. Generate Payment Schedule (Consolidated)
            if purchase.months > 0:
                installment_amount = purchase.remaining_balance / purchase.months
                start_date = purchase.date or dt.datetime.utcnow()
                for i in range(1, purchase.months + 1):
                    due_date = start_date + dt.timedelta(days=30 * i)
                    schedule = CreditPaymentSchedule(
                        purchase_id=purchase.id,
                        installment_no=i,
                        due_date=due_date,
                        amount_due=installment_amount,
                        status="PENDING"
                    )
                    db.add(schedule)

            # Create portal account if it doesn't exist
            try:
                customer_portal_service.create_account_for_credit_sale(
                    customer_id=header_data.get('customer_id')
                )
            except Exception as e:
                logger.error(f"Error creating portal account during bulk purchase: {e}", exc_info=True)
            
            db.commit()
            db.refresh(purchase)
            logger.info(f"Bulk credit purchase {purchase.id} created for {purchase.customer_name}")
            return purchase
        except Exception as e:
            db.rollback()
            logger.error(f"Error creating bulk purchase: {e}", exc_info=True)
            raise e
        finally:
            db.close()

    def get_all_purchases(self) -> List[BulkCreditPurchase]:
        db = self._get_db()
        try:
            return db.query(BulkCreditPurchase).options(
                joinedload(BulkCreditPurchase.items)
            ).order_by(BulkCreditPurchase.date.desc()).all()
        finally:
            db.close()

    def get_purchase_details(self, purchase_id: int) -> Optional[BulkCreditPurchase]:
        db = self._get_db()
        try:
            return db.query(BulkCreditPurchase).options(
                joinedload(BulkCreditPurchase.items),
                joinedload(BulkCreditPurchase.schedules)
            ).filter(BulkCreditPurchase.id == purchase_id).first()
        finally:
            db.close()

    def search_available_motorcycles(self, query: str) -> List[Motorcycle]:
        """Search for motorcycles that are IN_STOCK."""
        db = self._get_db()
        try:
            return db.query(Motorcycle).filter(
                Motorcycle.status == "IN_STOCK",
                (Motorcycle.chassis_number.ilike(f"%{query}%")) |
                (Motorcycle.engine_number.ilike(f"%{query}%"))
            ).limit(20).all()
        finally:
            db.close()

bulk_credit_service = BulkCreditService()
