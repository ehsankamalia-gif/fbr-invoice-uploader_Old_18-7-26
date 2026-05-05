from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc, or_
from app.db.session import SessionLocal
from app.db.models import (
    CreditSale, CreditSaleItem, CreditPayment, BuyerLedger,
    Motorcycle, Customer, Price, ProductModel, Invoice, InvoiceItem
)
from typing import List, Optional, Dict, Any
import datetime as dt
from app.core.logger import logger

class CreditLedgerService:
    def _get_db(self) -> Session:
        return SessionLocal()

    def get_buyer_suggestions(self, query: str) -> List[Dict[str, Any]]:
        """Search for buyer names, phones, or CNICs and return details."""
        db = self._get_db()
        try:
            from sqlalchemy import or_
            results = db.query(Customer.id, Customer.name, Customer.type, Customer.phone, Customer.cnic).filter(
                or_(
                    Customer.name.ilike(f"%{query}%"),
                    Customer.phone.ilike(f"%{query}%"),
                    Customer.cnic.ilike(f"%{query}%")
                )
            ).limit(20).all()
            return [
                {
                    "id": r[0], 
                    "name": r[1], 
                    "type": r[2], 
                    "phone": r[3] or "N/A", 
                    "cnic": r[4] or "N/A"
                } for r in results
            ]
        finally:
            db.close()

    def get_buyer_type(self, name: str) -> Optional[Dict[str, Any]]:
        """Get the type and ID of a specific buyer."""
        db = self._get_db()
        try:
            buyer = db.query(Customer).filter(Customer.name == name).first()
            if buyer:
                return {
                    "id": buyer.id,
                    "type": "Dealer" if buyer.type == "DEALER" else "Customer"
                }
            return None
        finally:
            db.close()

    def get_chassis_suggestions(self, query: str) -> List[Dict[str, Any]]:
        """Search for chassis numbers from the inventory that are marked as SOLD and have FBR invoices.
        Requirement: Chassis must come from inventory (Motorcycle table)."""
        db = self._get_db()
        try:
            search_text = (query or "").strip().upper()
            if not search_text: return []

            # Fix for MySQL Collation Mismatch (Requirement: Read text in picture)
            # Enforce utf8mb4_unicode_ci for all chassis comparisons to prevent "Illegal mix of collations"
            from sqlalchemy import collate
            
            # Subquery to identify chassis numbers already used in a credit sale
            sold_credit_chassis = db.query(
                collate(CreditSaleItem.chassis_number, 'utf8mb4_unicode_ci')
            ).subquery()

            # Core Query: Fetch from inventory (Motorcycle table)
            stmt = db.query(
                Motorcycle.chassis_number,
                ProductModel.model_name,
                Price.total_price,
                Motorcycle.color,
                Invoice.fbr_invoice_number
            ).join(
                ProductModel, Motorcycle.product_model_id == ProductModel.id
            ).join(
                InvoiceItem, InvoiceItem.motorcycle_id == Motorcycle.id
            ).join(
                Invoice, Invoice.id == InvoiceItem.invoice_id
            ).outerjoin(
                Price, (Price.product_model_id == ProductModel.id) & (Price.expiration_date.is_(None))
            ).filter(
                collate(Motorcycle.chassis_number, 'utf8mb4_unicode_ci').ilike(f"%{search_text}%"),
                Motorcycle.status == 'SOLD',
                or_(
                    Invoice.fbr_invoice_number.is_not(None),
                    Invoice.is_fiscalized == True,
                    Invoice.sync_status == "SENT"
                ),
                ~collate(Motorcycle.chassis_number, 'utf8mb4_unicode_ci').in_(sold_credit_chassis)
            ).distinct()

            results = stmt.limit(20).all()
            
            logger.info(f"CHASSIS SEARCH (FIXED COLLATION): '{search_text}' found {len(results)} sold results")
            
            return [
                {
                    "chassis": r[0], 
                    "model": r[1] or "Unknown", 
                    "cash_price": r[2] or 0.0,
                    "color": r[3] or "",
                    "fbr_inv": r[4] or "AVAILABLE"
                } for r in results
            ]
        except Exception as e:
            logger.error(f"Error in get_chassis_suggestions: {e}")
            return []
        finally:
            db.close()

    def check_chassis_unique(self, chassis_number: str) -> bool:
        """Check if chassis has already been sold on credit."""
        db = self._get_db()
        try:
            from sqlalchemy import collate
            exists = db.query(CreditSaleItem).filter(
                collate(CreditSaleItem.chassis_number, 'utf8mb4_unicode_ci') == chassis_number
            ).first()
            return exists is None
        finally:
            db.close()

    def check_chassis_exists(self, chassis_number: str) -> bool:
        """Check if a chassis exists in the inventory at all."""
        db = self._get_db()
        try:
            from sqlalchemy import collate
            record = db.query(Motorcycle).filter(
                collate(Motorcycle.chassis_number, 'utf8mb4_unicode_ci') == chassis_number
            ).first()
            return record is not None
        finally:
            db.close()

    def validate_fbr_invoice(self, chassis_number: str) -> bool:
        """Check if a chassis is SOLD and has a valid FBR invoice."""
        db = self._get_db()
        try:
            from sqlalchemy import collate
            chassis_number = (chassis_number or "").strip().upper()
            record = db.query(Invoice).join(
                InvoiceItem, InvoiceItem.invoice_id == Invoice.id
            ).join(
                Motorcycle, Motorcycle.id == InvoiceItem.motorcycle_id
            ).filter(
                collate(Motorcycle.chassis_number, 'utf8mb4_unicode_ci') == chassis_number,
                Motorcycle.status == 'SOLD',
                or_(
                    Invoice.is_fiscalized == True,
                    Invoice.fbr_invoice_number.is_not(None),
                    Invoice.sync_status == "SENT"
                )
            ).first()
            return record is not None
        finally:
            db.close()

    def create_credit_sale(self, sale_data: Dict[str, Any], items: List[Dict[str, Any]]) -> CreditSale:
        """Process a new credit sale with individual ledger entries per motorcycle."""
        db = self._get_db()
        try:
            # 1. Create Sale Record
            sale = CreditSale(**sale_data)
            db.add(sale)
            db.flush()

            # 2. Add Items, Update Inventory, and Create Individual Ledger Entries
            # Get latest balance to start progressive calculation
            last_ledger = db.query(BuyerLedger).filter(
                BuyerLedger.buyer_id == sale.buyer_id
            ).order_by(desc(BuyerLedger.id)).first()
            current_balance = last_ledger.balance if last_ledger else 0.0

            for item_data in items:
                # Check uniqueness at DB level
                if not self.check_chassis_unique(item_data['chassis_number']):
                    raise ValueError(f"Chassis {item_data['chassis_number']} already sold on credit.")
                
                item = CreditSaleItem(sale_id=sale.id, **item_data)
                db.add(item)
                
                # Update Motorcycle Status
                motorcycle = db.query(Motorcycle).filter(Motorcycle.chassis_number == item_data['chassis_number']).first()
                if motorcycle:
                    motorcycle.status = "SOLD"

                # Individual Ledger Entry for this Chassis (Debit)
                current_balance += item_data['credit_price']
                # Requirement: “Motorcycle Sale - Honda CD 70 - Chassis No: ABC12345”
                desc_text = f"Motorcycle Sale - {item_data.get('model', 'Unknown')} - Chassis No: {item_data['chassis_number']}"
                
                ledger_entry = BuyerLedger(
                    date=sale.sale_date,
                    buyer_id=sale.buyer_id,
                    chassis_number=item_data['chassis_number'],
                    description=desc_text,
                    debit=item_data['credit_price'],
                    credit=0.0,
                    balance=current_balance,
                    reference_id=sale.id,
                    reference_type="SALE"
                )
                db.add(ledger_entry)

            # 3. Create Ledger Entry for Advance Payment (if any)
            if sale.advance_payment > 0:
                current_balance -= sale.advance_payment
                advance_entry = BuyerLedger(
                    date=sale.sale_date,
                    buyer_id=sale.buyer_id,
                    description=f"Advance Payment Received - Invoice #{sale.id}",
                    debit=0.0,
                    credit=sale.advance_payment,
                    balance=current_balance,
                    reference_id=sale.id,
                    reference_type="PAYMENT"
                )
                db.add(advance_entry)

            db.commit()
            db.refresh(sale)
            return sale
        except Exception as e:
            db.rollback()
            logger.error(f"Error creating credit sale: {e}")
            raise e
        finally:
            db.close()

    def create_payment(self, payment_data: Dict[str, Any]) -> CreditPayment:
        """Process a payment and update the ledger with progressive balance, penalty, and discount."""
        db = self._get_db()
        try:
            payment = CreditPayment(**payment_data)
            db.add(payment)
            db.flush()

            # Get latest balance
            last_ledger = db.query(BuyerLedger).filter(
                BuyerLedger.buyer_id == payment.buyer_id
            ).order_by(desc(BuyerLedger.id)).first()
            current_balance = last_ledger.balance if last_ledger else 0.0

            # Reference suffix for descriptions
            ref_suffix = f"\nRef: {payment.invoice_reference}" if payment.invoice_reference and payment.invoice_reference.strip() else ""

            # 1. Handle Penalty (Debit - increases balance)
            if payment.penalty_amount > 0:
                current_balance += payment.penalty_amount
                penalty_entry = BuyerLedger(
                    date=payment.payment_date,
                    buyer_id=payment.buyer_id,
                    description=f"Late Payment Penalty{ref_suffix}",
                    debit=payment.penalty_amount,
                    credit=0.0,
                    balance=current_balance,
                    reference_id=payment.id,
                    reference_type="PAYMENT"
                )
                db.add(penalty_entry)

            # 2. Handle Discount (Credit - decreases balance)
            if payment.discount_amount > 0:
                current_balance -= payment.discount_amount
                discount_entry = BuyerLedger(
                    date=payment.payment_date,
                    buyer_id=payment.buyer_id,
                    description=f"Early Payment Discount{ref_suffix}",
                    debit=0.0,
                    credit=payment.discount_amount,
                    balance=current_balance,
                    reference_id=payment.id,
                    reference_type="PAYMENT"
                )
                db.add(discount_entry)

            # 3. Handle Base Payment (Credit - decreases balance)
            if payment.amount > 0:
                current_balance -= payment.amount
                payment_entry = BuyerLedger(
                    date=payment.payment_date,
                    buyer_id=payment.buyer_id,
                    description=f"Payment Received{ref_suffix}",
                    debit=0.0,
                    credit=payment.amount,
                    balance=current_balance,
                    reference_id=payment.id,
                    reference_type="PAYMENT"
                )
                db.add(payment_entry)

            db.commit()
            db.refresh(payment)
            return payment
        except Exception as e:
            db.rollback()
            logger.error(f"Error processing payment: {e}")
            raise e
        finally:
            db.close()

    def get_ledger(self, buyer_id: int, start_date: Optional[dt.date] = None, end_date: Optional[dt.date] = None, chassis_number: Optional[str] = None) -> List[BuyerLedger]:
        """Retrieve ledger entries for a buyer with optional filters including Chassis Number."""
        db = self._get_db()
        try:
            # Join with Customer to get the name dynamically (though it's usually known by the UI)
            query = db.query(BuyerLedger).options(joinedload(BuyerLedger.buyer)).filter(BuyerLedger.buyer_id == buyer_id)
            
            if chassis_number:
                query = query.filter(BuyerLedger.chassis_number.ilike(f"%{chassis_number}%"))
                
            if start_date:
                query = query.filter(BuyerLedger.date >= dt.datetime.combine(start_date, dt.time.min))
            if end_date:
                query = query.filter(BuyerLedger.date <= dt.datetime.combine(end_date, dt.time.max))
            
            return query.order_by(BuyerLedger.id.asc()).all()
        finally:
            db.close()

    def get_customer_details(self, customer_id: int) -> Optional[Dict[str, Any]]:
        """Fetch full details for a customer."""
        db = self._get_db()
        try:
            c = db.query(Customer).filter(Customer.id == customer_id).first()
            if c:
                return {
                    "name": c.name,
                    "father_name": c.father_name or "N/A",
                    "address": c.address or "N/A",
                    "phone": c.phone or "N/A",
                    "cnic": c.cnic or "N/A"
                }
            return None
        finally:
            db.close()

    def get_dashboard_stats(self) -> Dict[str, Any]:
        """Retrieve overview stats for the dashboard."""
        db = self._get_db()
        try:
            total_sales = db.query(func.sum(CreditSale.total_credit_price)).scalar() or 0.0
            total_received = db.query(func.sum(CreditPayment.amount)).scalar() or 0.0
            
            # Buyer-wise balances (latest balance from ledger per buyer)
            subquery = db.query(
                BuyerLedger.buyer_id,
                func.max(BuyerLedger.id).label('max_id')
            ).group_by(BuyerLedger.buyer_id).subquery()
            
            buyer_balances = db.query(BuyerLedger).options(joinedload(BuyerLedger.buyer)).join(
                subquery, BuyerLedger.id == subquery.c.max_id
            ).all()
            
            total_outstanding = sum([b.balance for b in buyer_balances])
            
            # Filter out any orphaned records where buyer might be None
            stats_balances = []
            for b in buyer_balances:
                if b.balance != 0:
                    name = b.buyer.name if b.buyer else f"Unknown (ID: {b.buyer_id})"
                    stats_balances.append({"id": b.buyer_id, "name": name, "balance": b.balance})

            return {
                "total_sales": total_sales,
                "total_received": total_received,
                "total_outstanding": total_outstanding,
                "buyer_balances": stats_balances
            }
        finally:
            db.close()

credit_ledger_service = CreditLedgerService()
