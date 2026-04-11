import threading
import time
import requests
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.db.models import Invoice
from app.services.invoice_service import invoice_service
from app.services.settings_service import settings_service
from app.core.logger import logger

class SyncService:
    def __init__(self):
        self._stop_event = threading.Event()
        self._thread = None
        self.is_online = False
        self.pending_count = 0
        self._status_callback = None
        self._lock = threading.Lock()

    def start(self):
        """Starts the background sync service"""
        if self._thread is None or not self._thread.is_alive():
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            logger.info("SyncService started.")

    def stop(self):
        """Stops the background sync service"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
            logger.info("SyncService stopped.")

    def set_status_callback(self, callback):
        """Callback(is_online: bool, pending_count: int)"""
        self._status_callback = callback

    def trigger_sync_now(self):
        """Manually triggers a check/sync cycle (non-blocking)"""
        threading.Thread(target=self._single_cycle, daemon=True).start()

    def _run_loop(self):
        """
        Main sync loop with exponential backoff for connectivity checks when offline.
        """
        backoff_delay = 5 # Start with 5 seconds
        max_delay = 60 # Cap at 60 seconds

        while not self._stop_event.is_set():
            start_time = time.time()
            self._single_cycle()
            duration = time.time() - start_time
            
            # Smart Sleep Logic
            if self.is_online:
                # If online, check frequently (e.g. every 10s)
                backoff_delay = 5 # Reset backoff
                sleep_time = max(10 - duration, 1) # Ensure at least 1s sleep
            else:
                # If offline, backoff to save resources
                sleep_time = backoff_delay
                backoff_delay = min(backoff_delay * 1.5, max_delay) # Exponential backoff
            
            # Wait with support for stop_event
            self._stop_event.wait(sleep_time)

    def _single_cycle(self):
        with self._lock: # Prevent overlapping cycles
            try:
                self._check_connectivity()
                self._update_pending_count()
                
                if self.is_online and self.pending_count > 0:
                    self._process_queue()
                    # Update count again after processing
                    self._update_pending_count()
                
                if self._status_callback:
                    # Run callback safely
                    try:
                        self._status_callback(self.is_online, self.pending_count)
                    except Exception as e:
                        logger.error(f"Sync status callback error: {e}")

            except Exception as e:
                logger.error(f"SyncService Error: {e}")

    def _check_connectivity(self):
        try:
            active = settings_service.get_active_settings()
            base_url = (active.get("base_url") or "").strip()
            env = (active.get("env") or "SANDBOX").upper()
            is_production = env == "PRODUCTION"

            endpoints = []
            if base_url:
                if base_url.endswith("/PostData"):
                    endpoints.append(base_url)
                else:
                    endpoints.append(f"{base_url.rstrip('/')}/PostData")
            endpoints.extend([
                "https://www.google.com",
                "https://www.cloudflare.com",
            ])
            
            connected = False
            for url in endpoints:
                try:
                    resp = requests.get(url, timeout=5, verify=is_production)
                    if resp.status_code in (200, 201, 202, 400, 401, 403, 404):
                        connected = True
                        break
                except requests.RequestException:
                    continue
            
            if connected:
                if not self.is_online:
                    logger.info("Connectivity restored. Status: ONLINE")
                self.is_online = True
            else:
                if self.is_online:
                    logger.warning("Connectivity lost. Status: OFFLINE")
                self.is_online = False
                
        except Exception as e:
            logger.error(f"Connectivity check failed unexpectedly: {e}")
            self.is_online = False

    def _update_pending_count(self):
        db = SessionLocal()
        try:
            self.pending_count = db.query(Invoice).filter(Invoice.sync_status == "PENDING").count()
        except Exception as e:
            logger.error(f"Error counting pending invoices: {e}")
        finally:
            db.close()

    def _process_queue(self):
        db = SessionLocal()
        try:
            # Process strictly chronologically (FIFO)
            # Fetch one by one to avoid long transaction locks
            pending = db.query(Invoice).filter(Invoice.sync_status == "PENDING").order_by(Invoice.id.asc()).all()
            
            if pending:
                logger.info(f"SyncService: Processing {len(pending)} pending invoices...")

            for inv in pending:
                if self._stop_event.is_set(): break
                
                # Re-check connectivity occasionally if queue is long? 
                # For now, rely on individual sync failures to stop.
                
                try:
                    # Use existing service method
                    invoice_service.sync_invoice(db, inv)
                    db.commit()
                    
                    if inv.sync_status == "SYNCED":
                        logger.info(f"SyncService: Invoice {inv.invoice_number} synced successfully.")

                except Exception as e:
                    logger.error(f"SyncService: Failed to sync {inv.invoice_number}: {e}")
                    db.rollback()
                    
        finally:
            db.close()

sync_service = SyncService()
