from sqlalchemy.orm import Session
import requests
from tenacity import RetryError
from app.db.models import Invoice, InvoiceItem, Motorcycle, Customer, CustomerType, ProductModel
from app.api.schemas import InvoiceCreate
from app.api.fbr_client import fbr_client
from app.core.logger import logger
from app.services.captured_data_service import captured_data_service
from datetime import datetime
from typing import Optional, List
import json

class InvoiceService:
    def _ensure_sold_inventory_for_fiscalized_invoice(self, db: Session, invoice: Invoice, invoice_in: InvoiceCreate) -> None:
        if not invoice or not invoice.is_fiscalized:
            return

        for idx, item_in in enumerate(invoice_in.items or []):
            chassis = (getattr(item_in, "chassis_number", None) or "").strip().upper()
            if not chassis:
                continue

            engine_raw = (getattr(item_in, "engine_number", None) or "").strip()
            engine = engine_raw.upper() if engine_raw else f"UNKNOWN-{chassis}"

            bike = db.query(Motorcycle).filter(Motorcycle.chassis_number == chassis).first()
            if not bike:
                model_name = (getattr(item_in, "model_name", None) or "").strip()
                color = (getattr(item_in, "color", None) or "").strip().upper()
                if not model_name:
                    logger.warning(f"AUDIT: Out-of-stock chassis {chassis} submitted, but model_name missing; inventory entry not created.")
                    continue

                product_model = db.query(ProductModel).filter(ProductModel.model_name == model_name).first()
                if not product_model:
                    product_model = ProductModel(model_name=model_name, make="Honda")
                    db.add(product_model)
                    db.flush()

                bike = Motorcycle(
                    chassis_number=chassis,
                    engine_number=engine,
                    product_model_id=product_model.id,
                    year=datetime.now().year,
                    color=color or None,
                    cost_price=0.0,
                    sale_price=0.0,
                    status="SOLD",
                    purchase_date=datetime.now(),
                )
                db.add(bike)
                db.flush()
                logger.info(f"AUDIT: Created SOLD inventory entry for out-of-stock chassis {chassis} after successful FBR submission.")
            else:
                prev_status = (bike.status or "").upper()
                if prev_status != "SOLD":
                    bike.status = "SOLD"
                    db.add(bike)
                    logger.info(f"AUDIT: Updated inventory status for chassis {chassis}: {prev_status} -> SOLD (after successful FBR submission).")

            try:
                if invoice.items and idx < len(invoice.items):
                    invoice.items[idx].motorcycle_id = bike.id
                    db.add(invoice.items[idx])
            except Exception:
                pass

            try:
                captured_data_service.delete_by_chassis(db, chassis)
            except Exception as cleanup_err:
                logger.error(f"AUDIT: Failed to delete captured data for chassis {chassis}: {cleanup_err}")

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

    def is_chassis_uploaded_to_fbr(self, db: Session, chassis_number: str) -> bool:
        """
        Check if a chassis number has already been uploaded to FBR.
        Returns True if the chassis is linked to a fiscalized invoice OR a pending sync.
        """
        if not chassis_number:
            return False
        
        chassis_number = chassis_number.upper().strip()
        
        # Check through Motorcycle relationship
        from app.db.models import Invoice, InvoiceItem, Motorcycle
        exists = db.query(InvoiceItem).join(Invoice).filter(
            InvoiceItem.motorcycle_id.in_(
                db.query(Motorcycle.id).filter(Motorcycle.chassis_number == chassis_number)
            ),
            # Block if it's already fiscalized OR currently pending/retrying
            (Invoice.is_fiscalized == True) | (Invoice.sync_status == "PENDING")
        ).first()
        
        return exists is not None

    def create_invoice(self, db: Session, invoice_in: InvoiceCreate):
        # 1. Calculate totals
        total_sale_value = 0.0
        total_tax_charged = 0.0
        total_further_tax = 0.0
        total_quantity = 0.0
        total_amount = 0.0

        db_items = []
        seen_chassis = set()
        for item in invoice_in.items:
            # 1. Internal duplicate check (same invoice)
            if item.chassis_number:
                if item.chassis_number.upper() in seen_chassis:
                    logger.error(f"AUDIT FAILURE: Duplicate chassis {item.chassis_number} in the same invoice items list.")
                    raise ValueError(f"Duplicate chassis {item.chassis_number} found in the items list.")
                seen_chassis.add(item.chassis_number.upper())

            # 2. Mandatory Duplicate Upload Prevention (Database check)
            if item.chassis_number:
                logger.info(f"AUDIT: Validating uniqueness for chassis {item.chassis_number} before sync.")
                if self.is_chassis_uploaded_to_fbr(db, item.chassis_number):
                    logger.error(f"AUDIT FAILURE: Attempted to re-upload chassis {item.chassis_number} which is already fiscalized or pending sync.")
                    raise ValueError(f"This Chassis number {item.chassis_number} is already uploaded to FBR or has a pending submission.")

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

            motorcycle_id = None
            if item.chassis_number:
                lookup_chassis = item.chassis_number.upper().strip()
                bike = db.query(Motorcycle).filter(Motorcycle.chassis_number == lookup_chassis).first()
                if bike:
                    motorcycle_id = bike.id
                    if (bike.status or "").upper() != "IN_STOCK":
                        logger.info(
                            f"AUDIT: Chassis {lookup_chassis} is out-of-stock ({bike.status}); proceeding with FBR submission per workflow."
                        )
                else:
                    logger.info(f"AUDIT: Chassis {lookup_chassis} not found in inventory; proceeding with FBR submission per workflow.")

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
                discount=item.discount,
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
            discount=invoice_in.discount,
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

            if db_invoice.is_fiscalized:
                try:
                    self._ensure_sold_inventory_for_fiscalized_invoice(db, db_invoice, invoice_in)
                    db.commit()
                    db.refresh(db_invoice)
                except Exception as inv_err:
                    db.rollback()
                    logger.error(f"AUDIT: Inventory adjustment failed after FBR success for {invoice_in.invoice_number}: {inv_err}", exc_info=True)
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
                        "discount": item.discount,
                        "chassis_number": item.motorcycle.chassis_number if item.motorcycle else None,
                        "engine_number": item.motorcycle.engine_number if item.motorcycle else None
                    } for item in invoice.items
                ]
            }

            logger.info(f"Syncing invoice {invoice.invoice_number} to FBR...")
            
            # This might raise requests.RequestException if offline
            try:
                response = fbr_client.post_invoice(invoice_data)
                logger.info(f"FBR API Raw Response for {invoice.invoice_number}: {response}")
            except Exception as sync_err:
                logger.error(f"FBR API Call failed for {invoice.invoice_number}: {sync_err}", exc_info=True)
                raise sync_err
            
            # FBR Success is indicated by Code 100
            response_code = str(response.get("Code")) if response and response.get("Code") else None
            is_success = response_code == "100"
            
            # ECHO DETECTION:
            # If FBR returns the same USIN we sent as the FBR Invoice Number, 
            # it indicates a silent failure/echo bug in FBR.
            returned_fbr_id = response.get("InvoiceNumber")
            internal_usin = invoice.invoice_number # mapped to USIN in FBRClient
            is_echo = returned_fbr_id == internal_usin
            
            if is_success and returned_fbr_id and not is_echo:
                invoice.fbr_invoice_number = returned_fbr_id
                invoice.is_fiscalized = True
                invoice.sync_status = "SYNCED"
                invoice.status_updated_at = datetime.utcnow()
                invoice.fbr_response_code = response_code
                invoice.fbr_response_message = "Success"
                invoice.fbr_full_response = response
                
                logger.info(f"FBR SUCCESS: Invoice {invoice.invoice_number} fiscalized as {returned_fbr_id}")

                # Auto-delete captured data if chassis exists (Cleanup after successful FBR upload)
                try:
                    for item in invoice.items:
                        # Access motorcycle via relationship to get chassis number
                        if item.motorcycle and item.motorcycle.chassis_number:
                            captured_data_service.delete_by_chassis(db, item.motorcycle.chassis_number)
                except Exception as cleanup_err:
                     logger.error(f"Error cleaning up captured data for invoice {invoice.invoice_number}: {cleanup_err}")

            elif is_echo:
                # Echo detected -> Treat as failure
                logger.error(f"FBR ECHO FAILURE: FBR returned echoed Invoice Number {returned_fbr_id} for {invoice.invoice_number}")
                invoice.sync_status = "FAILED"
                invoice.status_updated_at = datetime.utcnow()
                invoice.fbr_response_message = "FBR returned echoed Invoice Number (FBR Glitch)"
                invoice.fbr_full_response = response
                # We raise an exception so the UI knows it was a critical error
                raise Exception("FBR returned echoed Invoice Number. Please check FBR Portal.")
            else:
                # API returned but with error (e.g. Logic Error)
                # Keep as FAILED so user checks it.
                invoice.sync_status = "FAILED"
                invoice.status_updated_at = datetime.utcnow()
                invoice.fbr_response_message = response.get("Response", "Unknown Error") if response else "No response"
                invoice.fbr_full_response = response
                logger.warning(f"FBR API Error for {invoice.invoice_number}: {invoice.fbr_response_message}")
                
            db.add(invoice) # Ensure update
            # Note: Commit is handled by caller (create_invoice or background sync)
            
        except requests.RequestException as re:
            # Network Error -> Keep as PENDING for retry
            logger.warning(f"Network error syncing {invoice.invoice_number}: {re}")
            invoice.sync_status = "PENDING"
            invoice.status_updated_at = datetime.utcnow()
            invoice.fbr_response_message = f"Network Error - Queued for retry: {str(re)[:300]}"
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
                    invoice.fbr_response_message = f"Network Error (Max Retries) - Queued for retry: {str(original_exception)[:300]}"
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
