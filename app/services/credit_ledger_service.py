from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc, or_, and_
from app.db.session import SessionLocal
from app.db.models import (
    CreditSale, CreditSaleItem, CreditPayment, BuyerLedger,
    Motorcycle, Customer, Price, ProductModel, Invoice, InvoiceItem,
    FinanceCreditSale, FinanceInstallment, FinanceLedger
)
from typing import List, Optional, Dict, Any
import datetime as dt
from app.core.logger import logger
from app.utils.duration_utils import format_duration

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
        """Search for chassis numbers from the inventory."""
        db = self._get_db()
        try:
            search_text = (query or "").strip().upper()
            if not search_text: return []

            from sqlalchemy import collate
            
            # Subquery to identify chassis numbers already used in a credit sale
            sold_credit_chassis = db.query(
                collate(CreditSaleItem.chassis_number, 'utf8mb4_unicode_ci')
            )

            # Core Query: Fetch from inventory (Motorcycle table)
            stmt = db.query(
                Motorcycle.chassis_number,
                ProductModel.model_name,
                Price.total_price,
                Motorcycle.color
            ).join(
                ProductModel, Motorcycle.product_model_id == ProductModel.id
            ).outerjoin(
                Price, (Price.product_model_id == ProductModel.id) & (Price.expiration_date.is_(None))
            ).filter(
                collate(Motorcycle.chassis_number, 'utf8mb4_unicode_ci').ilike(f"%{search_text}%"),
                ~collate(Motorcycle.chassis_number, 'utf8mb4_unicode_ci').in_(sold_credit_chassis)
            ).distinct()

            results = stmt.limit(20).all()
            
            return [
                {
                    "chassis": r[0], 
                    "model": r[1] or "Unknown", 
                    "cash_price": r[2] or 0.0,
                    "color": r[3] or ""
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
                
                # Extract description before creating CreditSaleItem model
                user_desc = item_data.pop('description', None)
                
                item = CreditSaleItem(sale_id=sale.id, **item_data)
                db.add(item)
                
                # Update Motorcycle Status
                motorcycle = db.query(Motorcycle).filter(Motorcycle.chassis_number == item_data['chassis_number']).first()
                if motorcycle:
                    motorcycle.status = "SOLD"

                # Individual Ledger Entry for this Chassis (Debit)
                current_balance += item_data['credit_price']
                
                # Base description: Requirement: “Motorcycle Sale - Honda CD 70 - Chassis No: ABC12345”
                desc_text = f"Motorcycle Sale - {item_data.get('model', 'Unknown')} - Chassis No: {item_data['chassis_number']}"
                
                # Add payment commitment (Requirement 1 & 4)
                duration_m = sale.duration_months
                duration_d = sale.duration_days
                if (duration_m and duration_m > 0) or (duration_d and duration_d > 0):
                    formatted = format_duration(duration_m or 0, duration_d or 0)
                    commitment_text = f"Customer committed to clear payment within {formatted}."
                    desc_text += f"\n{commitment_text}"
                
                # If user provided a description, append it on a new line
                if user_desc and user_desc.strip():
                    desc_text += f"\n{user_desc.strip()}"
                
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
                mode_suffix = f" (via {sale.advance_payment_mode})" if hasattr(sale, 'advance_payment_mode') and sale.advance_payment_mode else ""
                current_balance -= sale.advance_payment
                advance_entry = BuyerLedger(
                    date=sale.sale_date,
                    buyer_id=sale.buyer_id,
                    description=f"Advance Payment Received - Invoice #{sale.id}{mode_suffix}",
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
                mode_suffix = f" (via {payment.payment_mode})" if hasattr(payment, 'payment_mode') and payment.payment_mode else ""
                current_balance -= payment.amount
                payment_entry = BuyerLedger(
                    date=payment.payment_date,
                    buyer_id=payment.buyer_id,
                    description=f"Payment Received{mode_suffix}{ref_suffix}",
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
            
            return query.order_by(BuyerLedger.date.asc(), BuyerLedger.id.asc()).all()
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

    def create_finance_sale(self, sale_data: Dict[str, Any]) -> FinanceCreditSale:
        """Process a new advanced finance sale with its own independent ledger."""
        db = self._get_db()
        try:
            # 1. Generate unique Sale ID if not provided (e.g., FIN-20240508-001)
            if not sale_data.get('sale_id'):
                count = db.query(FinanceCreditSale).count()
                sale_data['sale_id'] = f"FIN-{dt.datetime.now().strftime('%Y%m%d')}-{count+1:03d}"
            
            # 2. Create Finance Sale Record
            finance_sale = FinanceCreditSale(**sale_data)
            db.add(finance_sale)
            db.flush()

            # 3. Create initial Debit entry in Finance Ledger
            desc_text = f"Motorcycle Finance - {finance_sale.model} - Chassis: {finance_sale.chassis_no}"
            
            # Add engine no if exists
            if finance_sale.engine_no:
                desc_text += f"\nEngine No: {finance_sale.engine_no}"
                
            # Add payment commitment (Requirement 1 & 4)
            duration_m = finance_sale.duration_months
            duration_d = finance_sale.duration_days
            if (duration_m and duration_m > 0) or (duration_d and duration_d > 0):
                formatted = format_duration(duration_m or 0, duration_d or 0)
                commitment_text = f"Customer committed to clear payment within {formatted}."
                desc_text += f"\n{commitment_text}"

            ledger_entry = FinanceLedger(
                ledger_id=f"L-{finance_sale.sale_id}",
                customer_id=finance_sale.customer_id,
                sale_id=finance_sale.id,
                entry_type="DEBIT",
                description=desc_text,
                debit=finance_sale.credit_price,
                credit=0.0,
                balance=finance_sale.credit_price,
                entry_date=finance_sale.sale_date
            )
            db.add(ledger_entry)

            # 4. Handle Down Payment (Credit entry)
            if finance_sale.down_payment > 0:
                current_balance = finance_sale.credit_price - finance_sale.down_payment
                mode_suffix = f" (via {finance_sale.down_payment_method})" if hasattr(finance_sale, 'down_payment_method') and finance_sale.down_payment_method else ""
                
                desc = f"Down Payment Received - {finance_sale.sale_id}{mode_suffix}"
                if finance_sale.notes and finance_sale.notes.strip():
                    desc += f"\nNote: {finance_sale.notes}"

                down_payment_entry = FinanceLedger(
                    ledger_id=f"L-{finance_sale.sale_id}-DP",
                    customer_id=finance_sale.customer_id,
                    sale_id=finance_sale.id,
                    entry_type="CREDIT",
                    description=desc,
                    debit=0.0,
                    credit=finance_sale.down_payment,
                    balance=current_balance,
                    entry_date=finance_sale.sale_date
                )
                db.add(down_payment_entry)
                finance_sale.remaining_balance = current_balance

            db.commit()
            db.refresh(finance_sale)
            return finance_sale
        except Exception as e:
            db.rollback()
            logger.error(f"Error creating finance sale: {e}")
            raise e
        finally:
            db.close()

    def create_finance_installment(self, payment_data: Dict[str, Any]) -> FinanceInstallment:
        """Process an installment for a specific advanced finance account."""
        db = self._get_db()
        try:
            # 1. Generate Payment ID
            count = db.query(FinanceInstallment).count()
            payment_data['payment_id'] = f"PAY-{dt.datetime.now().strftime('%Y%m%d')}-{count+1:03d}"
            
            installment = FinanceInstallment(**payment_data)
            db.add(installment)
            
            # 2. Update Finance Sale Remaining Balance
            sale = db.query(FinanceCreditSale).filter(FinanceCreditSale.id == installment.sale_id).first()
            if not sale:
                raise ValueError("Finance account not found.")
            
            old_balance = sale.remaining_balance
            new_balance = old_balance - installment.paid_amount
            sale.remaining_balance = new_balance
            
            if new_balance <= 0:
                sale.status = "CLOSED"
            
            # 3. Create Ledger Entry
            mode_suffix = f" (via {installment.payment_method})" if hasattr(installment, 'payment_method') and installment.payment_method else ""
            desc = f"Installment Received - {sale.sale_id}{mode_suffix}"
            if installment.reference_no and installment.reference_no.strip():
                desc += f"\nRef: {installment.reference_no}"
            if installment.notes and installment.notes.strip():
                desc += f"\nNote: {installment.notes}"

            ledger_entry = FinanceLedger(
                ledger_id=f"L-{installment.payment_id}",
                customer_id=installment.customer_id,
                sale_id=installment.sale_id,
                entry_type="CREDIT",
                description=desc,
                debit=0.0,
                credit=installment.paid_amount,
                balance=new_balance,
                entry_date=installment.payment_date
            )
            db.add(ledger_entry)
            
            db.commit()
            db.refresh(installment)
            return installment
        except Exception as e:
            db.rollback()
            logger.error(f"Error processing finance installment: {e}")
            raise e
        finally:
            db.close()

    def get_active_finance_accounts(self, query: str = None) -> List[FinanceCreditSale]:
        """Retrieve all active advanced finance accounts."""
        db = self._get_db()
        try:
            stmt = db.query(FinanceCreditSale).filter(FinanceCreditSale.status != "CLOSED")
            if query:
                stmt = stmt.filter(
                    or_(
                        FinanceCreditSale.customer_name.ilike(f"%{query}%"),
                        FinanceCreditSale.chassis_no.ilike(f"%{query}%"),
                        FinanceCreditSale.sale_id.ilike(f"%{query}%")
                    )
                )
            results = stmt.order_by(FinanceCreditSale.sale_date.desc()).all()
            
            # Expunge all objects to make them safe for use outside the session
            for acc in results:
                db.expunge(acc)
                
            return results
        finally:
            db.close()

    def get_due_finance_accounts(self) -> List[Dict[str, Any]]:
        """Identify overdue finance accounts."""
        db = self._get_db()
        try:
            today = dt.datetime.now()
            # 1. Fetch all active accounts
            active_sales = db.query(FinanceCreditSale).filter(
                FinanceCreditSale.status != "CLOSED"
            ).all()
            
            results = []
            for sale in active_sales:
                # 2. Check if overdue (due_date < today)
                if sale.due_date < today:
                    # Update status to OVERDUE if not already set
                    if sale.status != "OVERDUE":
                        sale.status = "OVERDUE"
                    
                    overdue_days = (today - sale.due_date).days
                    results.append({
                        "account": sale,
                        "overdue_days": max(0, overdue_days)
                    })
                elif sale.status == "OVERDUE":
                    # Revert to ACTIVE if payment/date extension made it not overdue anymore
                    sale.status = "ACTIVE"
            
            db.commit()
            
            # 3. Expunge all objects to make them safe for use outside the session
            # This prevents the "not bound to a Session" error in the UI
            for r in results:
                db.refresh(r['account'])
                db.expunge(r['account'])

            # Sort by most overdue first
            results.sort(key=lambda x: x['overdue_days'], reverse=True)
            return results
        finally:
            db.close()

    def get_finance_sale_ledger(self, sale_id: int) -> List[FinanceLedger]:
        """Get ledger entries for a specific motorcycle finance account."""
        db = self._get_db()
        try:
            return db.query(FinanceLedger).options(joinedload(FinanceLedger.sale)).filter(FinanceLedger.sale_id == sale_id).order_by(FinanceLedger.entry_date.asc(), FinanceLedger.id.asc()).all()
        finally:
            db.close()

    def get_combined_ledger(self, customer_id: int, start_date: dt.date = None, end_date: dt.date = None) -> List[Dict[str, Any]]:
        """Retrieve a combined master ledger showing both old and advanced credit transactions."""
        db = self._get_db()
        try:
            # 1. Fetch Old Ledger entries
            old_entries = db.query(BuyerLedger).filter(BuyerLedger.buyer_id == customer_id)
            if start_date:
                old_entries = old_entries.filter(BuyerLedger.date >= dt.datetime.combine(start_date, dt.time.min))
            if end_date:
                old_entries = old_entries.filter(BuyerLedger.date <= dt.datetime.combine(end_date, dt.time.max))
            
            # 2. Fetch New Finance Ledger entries
            new_entries = db.query(FinanceLedger).filter(FinanceLedger.customer_id == customer_id)
            if start_date:
                new_entries = new_entries.filter(FinanceLedger.entry_date >= dt.datetime.combine(start_date, dt.time.min))
            if end_date:
                new_entries = new_entries.filter(FinanceLedger.entry_date <= dt.datetime.combine(end_date, dt.time.max))
            
            # 3. Combine and sort
            combined = []
            for e in old_entries.all():
                combined.append({
                    "date": e.date,
                    "created_at": e.created_at, # Consistent with new entries
                    "description": e.description,
                    "sale_id": "OLD-SYSTEM",
                    "debit": e.debit,
                    "credit": e.credit,
                    "balance": e.balance, # Balance is tricky here since they are separate running totals
                    "type": "OLD"
                })
            
            for e in new_entries.all():
                combined.append({
                    "date": e.entry_date,
                    "created_at": e.created_at, # Using created_at for secondary sort
                    "description": e.description,
                    "sale_id": e.sale.sale_id if e.sale else "N/A",
                    "debit": e.debit,
                    "credit": e.credit,
                    "balance": e.balance,
                    "type": "ADVANCED"
                })
            
            # Sort by date and then by creation time
            combined.sort(key=lambda x: (x['date'], x.get('created_at') or dt.datetime.min))
            
            # Recalculate combined running balance
            running_bal = 0.0
            for item in combined:
                running_bal += (item['debit'] - item['credit'])
                item['combined_balance'] = running_bal
                
            return combined
        finally:
            db.close()

    def get_customer_active_finance_accounts(self, customer_id: int) -> List[FinanceCreditSale]:
        """Fetch all active advanced finance accounts for a specific customer."""
        db = self._get_db()
        try:
            return db.query(FinanceCreditSale).filter(
                FinanceCreditSale.customer_id == customer_id,
                FinanceCreditSale.status != "CLOSED"
            ).all()
        finally:
            db.close()

    def get_dashboard_stats(self) -> Dict[str, Any]:
        """Retrieve overview stats for the dashboard including both Old and Advanced Finance systems."""
        db = self._get_db()
        try:
            # 1. Total Credit Sales (Old + Advanced)
            old_sales = db.query(func.sum(CreditSale.total_credit_price)).scalar() or 0.0
            adv_sales = db.query(func.sum(FinanceCreditSale.credit_price)).scalar() or 0.0
            total_sales = old_sales + adv_sales
            
            # 2. Total Received (Old + Advanced)
            old_received = db.query(func.sum(CreditPayment.amount)).scalar() or 0.0
            adv_received = db.query(func.sum(FinanceInstallment.paid_amount)).scalar() or 0.0
            total_received = old_received + adv_received
            
            # 3. Buyer-wise aggregates
            # A. Old System Balances (Latest balance from BuyerLedger)
            old_subquery = db.query(
                BuyerLedger.buyer_id,
                func.max(BuyerLedger.id).label('max_id')
            ).group_by(BuyerLedger.buyer_id).subquery()
            
            old_balances = db.query(BuyerLedger).options(joinedload(BuyerLedger.buyer)).join(
                old_subquery, BuyerLedger.id == old_subquery.c.max_id
            ).all()
            
            # B. Advanced System Balances (Sum of remaining_balance from FinanceCreditSale)
            adv_balances = db.query(
                FinanceCreditSale.customer_id,
                func.sum(FinanceCreditSale.remaining_balance).label('total_remaining'),
                func.count(FinanceCreditSale.id).label('total_units'),
                func.max(FinanceCreditSale.sale_date).label('last_sale')
            ).group_by(FinanceCreditSale.customer_id).all()

            # 4. Consolidate everything into a single map per customer
            consolidated = {} # customer_id -> dict
            
            # Add Old System data
            for b in old_balances:
                if b.balance != 0:
                    name = b.buyer.name if b.buyer else f"Unknown (ID: {b.buyer_id})"
                    consolidated[b.buyer_id] = {
                        "id": b.buyer_id,
                        "name": name,
                        "balance": float(b.balance),
                        "total_units": 0, # To be incremented
                        "last_payment_date": "N/A"
                    }
            
            # Add/Update with Advanced System data
            for customer_id, remaining, units, last_sale in adv_balances:
                if customer_id not in consolidated:
                    # Need to fetch name if not in old system
                    cust = db.query(Customer).filter(Customer.id == customer_id).first()
                    name = cust.name if cust else f"Customer {customer_id}"
                    consolidated[customer_id] = {
                        "id": customer_id,
                        "name": name,
                        "balance": 0.0,
                        "total_units": 0,
                        "last_payment_date": "N/A"
                    }
                
                consolidated[customer_id]["balance"] += float(remaining)
                consolidated[customer_id]["total_units"] += int(units)

            # 5. Fetch Last Payment Date per customer (across both systems)
            for cid in consolidated:
                # Last payment from Old System
                last_p_old = db.query(func.max(CreditPayment.payment_date)).filter(CreditPayment.buyer_id == cid).scalar()
                # Last payment from Advanced System
                last_p_adv = db.query(func.max(FinanceInstallment.payment_date)).filter(FinanceInstallment.customer_id == cid).scalar()
                
                dates = [d for d in [last_p_old, last_p_adv] if d]
                if dates:
                    latest = max(dates)
                    consolidated[cid]["last_payment_date"] = latest.strftime('%d-%m-%Y')

            # Final list and total outstanding
            stats_balances = list(consolidated.values())
            stats_balances.sort(key=lambda x: x['balance'], reverse=True)
            total_outstanding = sum([b['balance'] for b in stats_balances])

            return {
                "total_sales": total_sales,
                "total_received": total_received,
                "total_outstanding": total_outstanding,
                "buyer_balances": stats_balances
            }
        finally:
            db.close()

credit_ledger_service = CreditLedgerService()
