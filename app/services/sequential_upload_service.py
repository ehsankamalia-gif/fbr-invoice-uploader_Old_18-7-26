
import threading
import time
from typing import List, Optional
from datetime import datetime, timedelta
from sqlalchemy import case, func
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.db.models import Invoice
from app.services.invoice_service import invoice_service
from app.services.settings_service import settings_service
from app.core.logger import logger


class SequentialUploadService:
    """
    A backend service that manages sequential invoice uploading to the FBR portal.
    Enforces strict order processing and persists queue state through application restarts.
    """
    
    def __init__(self):
        self._stop_event = threading.Event()
        self._thread = None
        self._lock = threading.Lock()
        self._is_running = False
        logger.info("SequentialUploadService initialized")
        
    def start(self):
        """Starts the sequential upload service in a background thread."""
        if not self._is_running:
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            self._is_running = True
            logger.info("SequentialUploadService started")
            
    def stop(self):
        """Stops the sequential upload service."""
        if self._is_running:
            self._stop_event.set()
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=2)
            self._is_running = False
            logger.info("SequentialUploadService stopped")
            
    def is_running(self):
        """Checks if the service is currently running."""
        return self._is_running
        
    def _run_loop(self):
        """Main service loop that processes invoices sequentially."""
        logger.info("SequentialUploadService loop started")
        
        while not self._stop_event.is_set():
            try:
                # Process one invoice at a time
                processed = self._process_next_invoice()
                
                if processed:
                    # If we processed an invoice, check immediately for next one
                    continue
                else:
                    # If no invoice was processed, wait before checking again
                    self._stop_event.wait(5)
                    
            except Exception as e:
                logger.error(f"SequentialUploadService error: {str(e)}", exc_info=True)
                self._stop_event.wait(30)
                
        logger.info("SequentialUploadService loop stopped")
        
    def _process_next_invoice(self) -> bool:
        """
        Finds and processes the next invoice in the queue.
        Returns True if an invoice was processed, False otherwise.
        """
        with self._lock:
            db = SessionLocal()
            try:
                # Find the next invoice to process
                invoice = self._get_next_invoice_to_process(db)
                
                if not invoice:
                    logger.debug("No invoices to process")
                    return False
                    
                # Mark as processing
                invoice.is_processing = True
                db.commit()
                
                logger.info(f"Processing invoice {invoice.invoice_number}")
                
                # Process the invoice
                success = False
                try:
                    invoice_service.sync_invoice(db, invoice)
                    db.commit()
                    success = invoice.sync_status == "SYNCED"
                    
                except Exception as e:
                    logger.error(f"Failed to sync invoice {invoice.invoice_number}: {str(e)}")
                    db.rollback()
                    
                # Handle result
                if success:
                    logger.info(f"Invoice {invoice.invoice_number} synced successfully")
                else:
                    logger.warning(f"Invoice {invoice.invoice_number} failed to sync")
                    self._handle_failure(invoice)
                    db.add(invoice)
                    db.commit()
                    
                # Mark as not processing
                invoice.is_processing = False
                invoice.status_updated_at = datetime.utcnow()
                db.add(invoice)
                db.commit()
                
                return True
                
            except Exception as e:
                logger.error(f"Error processing next invoice: {str(e)}", exc_info=True)
                return False
                
            finally:
                db.close()
                
    def _get_next_invoice_to_process(self, db: Session) -> Optional[Invoice]:
        """
        Gets the next invoice to process based on strict sequential order with priorities.
        """
        # Query:
        # 1. Only PENDING status
        # 2. Not currently being processed
        # 3. Next attempt time <= now (or None)
        # 4. Upload attempts < max attempts
        # 5. Order by datetime ascending (FIFO), then by ID ascending (tiebreaker)
        now = datetime.utcnow()
        
        return db.query(Invoice)\
            .filter(
                Invoice.sync_status == "PENDING",
                Invoice.is_processing == False,
                (Invoice.next_upload_attempt <= now) | (Invoice.next_upload_attempt == None),
                Invoice.upload_attempts < Invoice.max_upload_attempts
            )\
            .order_by(Invoice.datetime.asc(), Invoice.id.asc())\
            .first()
            
    def _handle_failure(self, invoice: Invoice):
        """Handles invoice processing failure with exponential backoff."""
        invoice.upload_attempts += 1
        invoice.is_processing = False
        
        # Exponential backoff: 2^(attempt) seconds, with max 1 hour
        backoff_seconds = min(2 ** invoice.upload_attempts * 60, 3600)
        invoice.next_upload_attempt = datetime.utcnow() + timedelta(seconds=backoff_seconds)
        
        logger.warning(
            f"Invoice {invoice.invoice_number} failed. "
            f"Attempt {invoice.upload_attempts}/{invoice.max_upload_attempts}. "
            f"Next attempt in {backoff_seconds//60} minutes"
        )
        
    def queue_invoice_for_upload(self, invoice_id: int):
        """Adds an invoice to the upload queue (or updates its status to PENDING)."""
        with self._lock:
            db = SessionLocal()
            try:
                invoice = db.query(Invoice).get(invoice_id)
                
                if invoice:
                    invoice.sync_status = "PENDING"
                    invoice.is_processing = False
                    invoice.upload_attempts = 0
                    invoice.next_upload_attempt = None
                    invoice.status_updated_at = datetime.utcnow()
                    db.commit()
                    logger.info(f"Invoice {invoice.invoice_number} queued for upload")
                    
            except Exception as e:
                logger.error(f"Error queueing invoice {invoice_id}: {str(e)}")
                db.rollback()
                
            finally:
                db.close()
                
    def cancel_upload(self, invoice_id: int):
        """Cancels a pending invoice upload."""
        with self._lock:
            db = SessionLocal()
            try:
                invoice = db.query(Invoice).get(invoice_id)
                
                if invoice and invoice.sync_status == "PENDING":
                    invoice.sync_status = "FAILED"
                    invoice.is_processing = False
                    invoice.status_updated_at = datetime.utcnow()
                    db.commit()
                    logger.info(f"Invoice {invoice.invoice_number} upload canceled")
                    
            except Exception as e:
                logger.error(f"Error canceling invoice {invoice_id}: {str(e)}")
                db.rollback()
                
            finally:
                db.close()
                
    def get_queue_status(self) -> dict:
        """Returns the current state of the upload queue."""
        db = SessionLocal()
        try:
            # Get counts by status. One aggregate instead of four COUNT(*) round
            # trips, because the invoice screen polls this every 5 seconds.
            totals = db.query(
                func.sum(case((Invoice.sync_status == "PENDING", 1), else_=0)),
                func.sum(case((Invoice.is_processing == True, 1), else_=0)),
                func.sum(case((Invoice.sync_status == "FAILED", 1), else_=0)),
                func.sum(case((Invoice.sync_status == "SYNCED", 1), else_=0)),
            ).one()

            pending_count = int(totals[0] or 0)
            processing_count = int(totals[1] or 0)
            failed_count = int(totals[2] or 0)
            synced_count = int(totals[3] or 0)

            # Get upcoming invoices
            upcoming = db.query(Invoice)\
                .filter(
                    Invoice.sync_status == "PENDING",
                    Invoice.is_processing == False,
                    (Invoice.next_upload_attempt > datetime.utcnow())
                )\
                .order_by(Invoice.next_upload_attempt.asc())\
                .limit(5)\
                .all()
                
            upcoming_data = [
                {
                    "invoice_number": inv.invoice_number,
                    "next_attempt": inv.next_upload_attempt.isoformat() if inv.next_upload_attempt else None
                }
                for inv in upcoming
            ]
            
            # Get currently processing invoice
            current = db.query(Invoice)\
                .filter(Invoice.is_processing == True)\
                .first()
                
            current_data = None
            if current:
                current_data = {
                    "invoice_number": current.invoice_number,
                    "attempt": current.upload_attempts
                }
                
            return {
                "pending": pending_count,
                "processing": processing_count,
                "failed": failed_count,
                "synced": synced_count,
                "current": current_data,
                "upcoming": upcoming_data
            }
            
        finally:
            db.close()
            
    def get_queue_history(self, limit: int = 20) -> List[dict]:
        """Returns a history of invoice upload attempts."""
        db = SessionLocal()
        try:
            invoices = db.query(Invoice)\
                .filter(Invoice.sync_status.in_(["SYNCED", "FAILED"]))\
                .order_by(Invoice.status_updated_at.desc())\
                .limit(limit)\
                .all()
                
            return [
                {
                    "invoice_number": inv.invoice_number,
                    "status": inv.sync_status,
                    "attempts": inv.upload_attempts,
                    "last_attempt": inv.status_updated_at.isoformat(),
                    "response_message": inv.fbr_response_message
                }
                for inv in invoices
            ]
            
        finally:
            db.close()
            
    def reset_failed_uploads(self):
        """Resets all failed upload attempts to pending state."""
        with self._lock:
            db = SessionLocal()
            try:
                failed_invoices = db.query(Invoice)\
                    .filter(Invoice.sync_status == "FAILED")\
                    .all()
                    
                for inv in failed_invoices:
                    inv.sync_status = "PENDING"
                    inv.upload_attempts = 0
                    inv.next_upload_attempt = None
                    inv.is_processing = False
                    inv.status_updated_at = datetime.utcnow()
                    
                db.commit()
                logger.info(f"Reset {len(failed_invoices)} failed invoices")
                
            except Exception as e:
                logger.error(f"Error resetting failed uploads: {str(e)}")
                db.rollback()
                
            finally:
                db.close()


# Singleton instance
sequential_upload_service = SequentialUploadService()
