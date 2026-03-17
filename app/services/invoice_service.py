from sqlalchemy.orm import Session
import requests
from tenacity import RetryError
from app.db.models import Invoice, InvoiceItem, Motorcycle, Customer, CustomerType, ProductModel
from app.api.schemas import InvoiceCreate
from app.api.fbr_client import fbr_client
from app.core.logger import logger
from app.services.captured_data_service import captured_data_service
from datetime import datetime
from typing import Optional
import json

class InvoiceService:
    def is_chassis_used_in_posted_invoice(self, db: Session, chassis_number: str) -> bool:
        """
        Check if a chassis number has been used in any posted invoice.
        Returns True if the chassis number is found in any existing invoice.
        """
        if not chassis_number:
            return False
            
        chassis_number = chassis_number.upper()
        
        # Check for existence in InvoiceItems linked to this chassis
        # We join with Invoice to ensure the invoice actually exists (though integrity constraints should ensure this)
        count = db.query(InvoiceItem).join(Motorcycle).join(Invoice).filter(
            Motorcycle.chassis_number == chassis_number
        ).count()
        
        return count > 0

    def create_invoice(self, db: Session, invoice_in: InvoiceCreate):
        # 1. Calculate totals
        total_sale_value = 0.0
        total_tax_charged = 0.0
        total_further_tax = 0.0
        total_quantity = 0.0
        total_amount = 0.0

        db_items = []
        for item in invoice_in.items:
            # Check for Chassis Uniqueness across all fiscalized invoices
            if item.chassis_number:
                # Validate if chassis is already used in a previous invoice
                if self.is_chassis_used_in_posted_invoice(db, item.chassis_number):
                    raise ValueError(f"Invoice with chassis number {item.chassis_number} has already been posted")

            # Trust input values from price table as per user request
            sale_value = item.sale_value
            tax_charged = item.tax_charged
            further_tax = item.further_tax if hasattr(item, 'further_tax') else 0.0
            
            # Calculate line total
            line_total = sale_value + tax_charged + further_tax

            # Update totals
            total_sale_value += sale_value
            total_tax_charged += tax_charged
            total_further_tax += further_tax
            total_quantity += item.quantity
            total_amount += line_total

            # Inventory Logic: Check and Update Status
            motorcycle_id = None
            if item.chassis_number:
                # Find bike by chassis
                lookup_chassis = item.chassis_number.upper()
                bike = db.query(Motorcycle).filter(Motorcycle.chassis_number == lookup_chassis).first()
                if bike:
                    if bike.status != "IN_STOCK":
                        # Check if it was sold in a fiscalized invoice?
                        # Simplified: If status is not IN_STOCK, error.
                        raise ValueError(f"Motorcycle Chassis {lookup_chassis} is already {bike.status}")
                    
                    # Mark as SOLD
                    bike.status = "SOLD"
                    motorcycle_id = bike.id
                    db.add(bike) # Ensure update is tracked
                else:
                    # Create new motorcycle if details are provided (User Request: Add to inventory as SOLD)
                    if getattr(item, 'model_name', None) and getattr(item, 'color', None):
                        product_model = db.query(ProductModel).filter(ProductModel.model_name == item.model_name).first()
                        if product_model:
                            # Use 0.0 for prices as per user request (Do not save price in inventory for auto-created bikes)
                            # Handle empty engine number by making it unique to avoid IntegrityError
                            engine_num = (item.engine_number or "").strip()
                            if not engine_num or engine_num.upper() == "UNKNOWN":
                                engine_num = f"UNKNOWN-{lookup_chassis}"
                            else:
                                engine_num = engine_num.upper()

                            new_bike = Motorcycle(
                                chassis_number=lookup_chassis,
                                engine_number=engine_num,
                                product_model_id=product_model.id,
                                year=datetime.now().year,
                                color=item.color.upper(),
                                cost_price=0.0, 
                                sale_price=0.0,
                                status="SOLD",
                                purchase_date=datetime.now()
                            )
                            db.add(new_bike)
                            db.flush() # To get ID
                            motorcycle_id = new_bike.id
                            logger.info(f"Created new SOLD motorcycle for chassis {item.chassis_number}")
                        else:
                             logger.warning(f"Model {item.model_name} not found. Cannot create motorcycle for chassis {item.chassis_number}.")
                    else:
                        logger.warning(f"Chassis {item.chassis_number} not found in Inventory. Missing model/color to create.")

            db_item = InvoiceItem(
                item_code=item.item_code,
                item_name=item.item_name,
                pct_code=item.pct_code,
                quantity=item.quantity,
                tax_rate=item.tax_rate,
                sale_value=sale_value,
                further_tax=further_tax,
                tax_charged=tax_charged,
                total_amount=line_total,
                motorcycle_id=motorcycle_id
                # Removed chassis_number, engine_number from InvoiceItem
            )
            db_items.append(db_item)

        # Customer Logic: Find or Create
        customer = None
        if invoice_in.buyer_cnic:
            customer = db.query(Customer).filter(Customer.cnic == invoice_in.buyer_cnic).first()
        
        if customer:
            # Update info
            if invoice_in.buyer_name: customer.name = invoice_in.buyer_name.upper()
            if invoice_in.buyer_father_name: customer.father_name = invoice_in.buyer_father_name.upper()
            if invoice_in.buyer_ntn: customer.ntn = (invoice_in.buyer_ntn or "").upper()
            if invoice_in.buyer_phone: customer.phone = invoice_in.buyer_phone
            if invoice_in.buyer_address: customer.address = invoice_in.buyer_address.upper()
            
            # If we explicitly pass DEALER type, ensure it stays/becomes DEALER
            if invoice_in.buyer_type == CustomerType.DEALER:
                customer.type = CustomerType.DEALER
                
            # Reactivate if they were deleted
            customer.is_deleted = False
        else:
            # Create new
            customer = Customer(
                cnic=invoice_in.buyer_cnic,
                name=(invoice_in.buyer_name or "").upper(),
                father_name=(invoice_in.buyer_father_name or "").upper(),
                ntn=(invoice_in.buyer_ntn or "").upper(),
                phone=invoice_in.buyer_phone,
                address=(invoice_in.buyer_address or "").upper(),
                type=invoice_in.buyer_type or CustomerType.INDIVIDUAL
            )
            db.add(customer)
        
        db.flush() # Get customer.id

        # 2. Create Invoice Record Initial State (PENDING)
        # We save it first so we have a record even if FBR fails (Offline Support)
        
        # Get latest settings
        from app.services.settings_service import settings_service
        settings = settings_service.get_active_settings()

        db_invoice = Invoice(
            invoice_number=invoice_in.invoice_number,
            pos_id=settings.get("pos_id", ""),
            usin=invoice_in.invoice_number, 
            datetime=invoice_in.datetime,
            
            customer_id=customer.id,
            
            total_sale_value=total_sale_value,
            total_tax_charged=total_tax_charged,
            total_further_tax=total_further_tax,
            total_quantity=total_quantity,
            total_amount=total_amount,
            payment_mode=invoice_in.payment_mode,
            items=db_items,
            
            # Initial Status
            is_fiscalized=False,
            sync_status="PENDING",
            fbr_response_message="Created locally. Waiting for upload."
        )

        try:
            db.add(db_invoice)
            db.flush() # Save to DB to ensure we have ID and items
            
            # 3. Attempt Immediate Sync
            logger.info(f"AUDIT: Attempting immediate FBR upload for {invoice_in.invoice_number}...")
            self.sync_invoice(db, db_invoice)
            
            db.commit()
            db.refresh(db_invoice)
            return db_invoice

        except Exception as e:
            logger.error(f"Invoice creation/sync process warning: {e}")
            # If we already added it to DB, we commit what we have (Offline mode)
            # If the error was in DB adding, we rollback.
            if db_invoice in db:
                 logger.info("Saving invoice locally due to sync failure.")
                 db.commit()
                 db.refresh(db_invoice)
                 return db_invoice
            else:
                 db.rollback()
                 raise e

    def sync_invoice(self, db: Session, invoice: Invoice):
        """
        Tries to upload a single invoice to FBR.
        Updates status based on response.
        Handles both immediate and background syncs.
        """
        try:
            # Prepare data for client
            # Retrieve customer details
            customer = invoice.customer
            
            invoice_data = {
                "invoice_number": invoice.invoice_number,
                "datetime": invoice.datetime,
                "buyer_name": customer.name if customer else "",
                "buyer_ntn": customer.ntn if customer else "",
                "buyer_cnic": customer.cnic if customer else "",
                "buyer_phone": customer.phone if customer else "",
                "total_sale_value": invoice.total_sale_value,
                "total_tax_charged": invoice.total_tax_charged,
                "total_further_tax": invoice.total_further_tax,
                "total_quantity": invoice.total_quantity,
                "total_amount": invoice.total_amount,
                "payment_mode": invoice.payment_mode,
                "items": [
                    {
                        "item_code": item.item_code,
                        "item_name": item.item_name,
                        "quantity": item.quantity,
                        "tax_rate": item.tax_rate,
                        "sale_value": item.sale_value,
                        "tax_charged": item.tax_charged,
                        "further_tax": item.further_tax,
                        "total_amount": item.total_amount,
                        "pct_code": item.pct_code,
                        "discount": item.discount
                    } for item in invoice.items
                ]
            }

            logger.info(f"Syncing invoice {invoice.invoice_number} to FBR...")
            
            # This might raise requests.RequestException if offline
            response = fbr_client.post_invoice(invoice_data)
            
            # FBR Success is indicated by Code 100
            response_code = str(response.get("Code")) if response and response.get("Code") else None
            is_success = response_code == "100"
            
            if is_success and "InvoiceNumber" in response:
                invoice.fbr_invoice_number = response.get("InvoiceNumber")
                invoice.is_fiscalized = True
                invoice.sync_status = "SYNCED"
                invoice.status_updated_at = datetime.utcnow()
                invoice.fbr_response_code = response_code
                invoice.fbr_response_message = "Success"
                invoice.fbr_full_response = response

                # Auto-delete captured data if chassis exists (Cleanup after successful FBR upload)
                try:
                    for item in invoice.items:
                        # Access motorcycle via relationship to get chassis number
                        if item.motorcycle and item.motorcycle.chassis_number:
                            captured_data_service.delete_by_chassis(db, item.motorcycle.chassis_number)
                except Exception as cleanup_err:
                     logger.error(f"Error cleaning up captured data for invoice {invoice.invoice_number}: {cleanup_err}")

            else:
                # API returned but with error (e.g. Logic Error)
                # Keep as FAILED so user checks it.
                invoice.sync_status = "FAILED"
                invoice.status_updated_at = datetime.utcnow()
                invoice.fbr_response_message = response.get("Response", "Unknown Error") if response else "No response"
                
            db.add(invoice) # Ensure update
            # Note: Commit is handled by caller (create_invoice or background sync)
            
        except requests.RequestException as re:
            # Network Error -> Keep as PENDING for retry
            logger.warning(f"Network error syncing {invoice.invoice_number}: {re}")
            invoice.sync_status = "PENDING"
            invoice.status_updated_at = datetime.utcnow()
            invoice.fbr_response_message = "Network Error - Queued for retry"
            db.add(invoice)

        except RetryError as re:
            # Tenacity RetryError -> Check if underlying cause is Network Error
            # If so, keep as PENDING. If not, FAILED.
            last_attempt = re.last_attempt
            try:
                original_exception = last_attempt.exception()
                if isinstance(original_exception, requests.RequestException):
                    logger.warning(f"Max retries exhausted for {invoice.invoice_number} due to Network Error: {original_exception}")
                    invoice.sync_status = "PENDING"
                    invoice.status_updated_at = datetime.utcnow()
                    invoice.fbr_response_message = "Network Error (Max Retries) - Queued for retry"
                else:
                    logger.error(f"Max retries exhausted for {invoice.invoice_number} due to Logic Error: {original_exception}")
                    invoice.sync_status = "FAILED"
                    invoice.status_updated_at = datetime.utcnow()
                    invoice.fbr_response_message = f"Failed after retries: {str(original_exception)}"
            except Exception:
                 # Fallback if we can't extract exception
                 logger.error(f"RetryError caught but failed to extract cause: {re}")
                 invoice.sync_status = "FAILED"
                 invoice.status_updated_at = datetime.utcnow()
                 invoice.fbr_response_message = "Failed after retries"
            
            db.add(invoice)
            
        except Exception as e:
            # Other errors (Data validation, etc) -> FAILED
            logger.error(f"Invoice sync failed: {e}")
            invoice.sync_status = "FAILED"
            invoice.status_updated_at = datetime.utcnow()
            invoice.fbr_response_message = str(e)
            db.add(invoice)

    def get_last_invoice_by_cnic(self, db: Session, cnic: str) -> Optional[Invoice]:
        """
        Finds the most recent invoice for a given CNIC to auto-populate customer details.
        """
        # Join Customer to filter by CNIC
        return db.query(Invoice).join(Customer).filter(Customer.cnic == cnic).order_by(Invoice.id.desc()).first()

    def generate_next_invoice_number(self, db: Session) -> str:
        """
        Generates the next invoice number based on FBR USIN setting.
        Format: {USIN}-{0001}
        """
        from app.services.settings_service import settings_service
        settings = settings_service.get_active_settings()
        
        usin = settings.get("usin", "")
        if usin:
            usin = usin.strip()
            
        if not usin:
            # Fallback if USIN is missing
            logger.warning("FBR_USIN not set in configuration. Using 'UNKNOWN'.")
            usin = "UNKNOWN"
            
        # Find the last invoice number that starts with this USIN
        last_invoice = db.query(Invoice).filter(
            Invoice.invoice_number.like(f"{usin}-%")
        ).order_by(Invoice.id.desc()).first()
        
        if last_invoice:
            try:
                # Extract the numeric part (last 4 digits)
                parts = last_invoice.invoice_number.split("-")
                last_seq_str = parts[-1]
                last_seq = int(last_seq_str)
                next_seq = last_seq + 1
            except (ValueError, IndexError):
                # If parsing fails, start from 1
                logger.warning(f"Failed to parse sequence from last invoice number: {last_invoice.invoice_number}. Resetting to 1.")
                next_seq = 1
        else:
            next_seq = 1
            
        return f"{usin}-{next_seq:04d}"

invoice_service = InvoiceService()
