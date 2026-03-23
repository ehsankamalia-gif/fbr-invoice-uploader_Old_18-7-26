import time
import logging
from PyQt6.QtCore import QObject, pyqtSignal, QThread
from app.services.evolution_api_client import EvolutionAPIClient
# from app.core.logger import logger # Removing this as we'll use standard logging or a local logger
from app.db.session import SessionLocal
from app.db.models import SMSCampaign, SMSQueue, SMSStatus, AuditLog
from app.services import excel_service
import datetime as dt
import math

# Use a local logger to avoid NameErrors and potential circular imports
logger = logging.getLogger(__name__)

class WhatsAppWorker(QThread):
    """Background worker for WhatsApp status monitoring and campaign processing."""
    status_received = pyqtSignal(str)
    qr_received = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    message_result = pyqtSignal(bool, str)
    campaign_progress = pyqtSignal(int, int, int) # sent, failed, total

    def __init__(self, api_client: EvolutionAPIClient):
        super().__init__()
        self.api_client = api_client
        self._is_running = True
        self._action_queue = []
        self._active_campaign_id = None
        # Configuration for retries
        self.base_retry_delay = 300 # 5 minutes base
        self.max_retry_delay = 86400 # 24 hours max

    def set_action(self, action: str):
        self._action_queue.append(action)

    def set_active_campaign(self, campaign_id):
        self._active_campaign_id = campaign_id

    def run(self):
        logger.info("WhatsApp monitoring and campaign thread started.")
        while self._is_running:
            try:
                # 1. Handle Pending Actions (Status/Reset)
                while self._action_queue:
                    action = self._action_queue.pop(0)
                    if action == "status":
                        self._check_status()
                    elif action == "reset":
                        self._reset_instance()

                # 2. Periodic Status Check
                state = self._check_status()

                # 3. Process Active Campaign if Connected
                if state == "open":
                    if not self._active_campaign_id:
                        # Auto-resume running campaigns
                        self._resume_running_campaign()
                    
                    if self._active_campaign_id:
                        self._process_campaigns()
                    
                    # 4. Handle Automated Retries for temporary failures
                    self._handle_automated_retries()
                elif self._active_campaign_id:
                    logger.warning(f"Campaign {self._active_campaign_id} paused - WhatsApp state is {state}")
                
            except Exception as e:
                logger.error(f"WhatsApp worker error: {e}")
                self.error_occurred.emit(str(e))
            
            time.sleep(5) # Poll every 5 seconds for faster campaign processing

    def _check_status(self):
        logger.debug("Checking WhatsApp connection status...")
        state_data = self.api_client.get_connection_state()
        
        if "error" in state_data:
            err = state_data["error"]
            logger.error(f"WhatsApp status check failed: {err}")
            self.status_received.emit(f"error: {err}")
            return "error"

        instance_data = state_data.get("instance", {})
        state = instance_data.get("state", "OFFLINE")
        logger.info(f"WhatsApp Instance State: {state}")
        self.status_received.emit(state)

        if state != "open":
            logger.debug("Fetching QR code...")
            qr_data = self.api_client.get_qr_code()
            if qr_data and "base64" in qr_data:
                logger.info("QR code received.")
                self.qr_received.emit(qr_data["base64"])
            elif "error" in qr_data:
                logger.warning(f"Failed to fetch QR: {qr_data['error']}")
        
        return state

    def _resume_running_campaign(self):
        db = SessionLocal()
        try:
            campaign = db.query(SMSCampaign).filter(
                SMSCampaign.channel == "WHATSAPP",
                SMSCampaign.status == "RUNNING",
                SMSCampaign.is_deleted == False
            ).order_by(SMSCampaign.created_at.desc()).first()
            if campaign:
                logger.info(f"Auto-resuming campaign {campaign.id} ({campaign.name})")
                self._active_campaign_id = campaign.id
        except Exception as e:
            logger.error(f"Error resuming campaign: {e}")
        finally:
            db.close()

    def _reset_instance(self):
        success, result = self.api_client.logout_instance()
        if success:
            self.status_received.emit("disconnected")
        else:
            self.error_occurred.emit(f"Reset failed: {result}")

    def _process_campaigns(self):
        db = SessionLocal()
        try:
            campaign = db.query(SMSCampaign).filter(
                SMSCampaign.id == self._active_campaign_id,
                SMSCampaign.status == "RUNNING",
                SMSCampaign.is_deleted == False
            ).first()

            if not campaign:
                logger.debug(f"Campaign {self._active_campaign_id} not found or not RUNNING.")
                self._active_campaign_id = None
                return

            # Process a batch of 10 messages
            messages = db.query(SMSQueue).filter(
                SMSQueue.campaign_id == campaign.id,
                SMSQueue.status == "PENDING"
            ).limit(10).all()

            if not messages:
                logger.info(f"No pending messages for campaign {campaign.id}. Completing.")
                campaign.status = "COMPLETED"
                campaign.completed_at = dt.datetime.utcnow()
                db.commit()
                self._active_campaign_id = None
                return

            logger.info(f"Processing {len(messages)} messages for campaign {campaign.id} ({campaign.name})")
            for msg in messages:
                if not self._is_running: break
                if self._active_campaign_id != campaign.id:
                    logger.info(f"Campaign {campaign.id} is no longer active in worker. Stopping batch.")
                    break
                
                # Check WhatsApp connection before each message
                state_data = self.api_client.get_connection_state()
                if state_data.get("instance", {}).get("state") != "open":
                    logger.warning("WhatsApp connection lost during campaign. Pausing.")
                    break

                self._attempt_send(db, msg, campaign)
                
                db.commit()
                self.campaign_progress.emit(campaign.sent_count, campaign.failed_count, campaign.total_recipients)
                time.sleep(2) # Rate limiting to avoid WhatsApp ban

        except Exception as e:
            logger.error(f"Campaign processing error: {e}")
            self.error_occurred.emit(f"Campaign Error: {e}")
        finally:
            db.close()

    def _handle_automated_retries(self):
        """Automatically retries failed messages using exponential backoff."""
        db = SessionLocal()
        try:
            now = dt.datetime.utcnow()
            # Find messages that are FAILED but eligible for retry
            retryable_msgs = db.query(SMSQueue).filter(
                SMSQueue.status == "FAILED",
                SMSQueue.retry_count < SMSQueue.max_retries,
                SMSQueue.next_retry_at <= now
            ).limit(5).all()

            for msg in retryable_msgs:
                logger.info(f"Automated Retry [Attempt {msg.retry_count + 1}]: {msg.phone_number}")
                campaign = msg.campaign
                self._attempt_send(db, msg, campaign)
                db.commit()
                
                if campaign:
                    self.campaign_progress.emit(campaign.sent_count, campaign.failed_count, campaign.total_recipients)
                
                time.sleep(2)
        except Exception as e:
            logger.error(f"Automated retry error: {e}")
        finally:
            db.close()

    def _attempt_send(self, db, msg, campaign):
        """Internal helper to send a message and handle retry logic with pre-send validation."""
        logger.debug(f"Validating and sending message to {msg.phone_number}...")
        
        # 1. Pre-send Number Existence Validation
        exists, result = self.api_client.check_number_exists(msg.phone_number)
        
        if not exists:
            msg.status = "FAILED"
            msg.error_message = str(result) # "This number is not on WhatsApp" or validation error
            if campaign: campaign.failed_count += 1
            logger.info(f"Skipping {msg.phone_number}: {result}")
            
            # Record skip in history
            history = msg.retry_history or []
            history.append({
                "timestamp": dt.datetime.utcnow().isoformat(),
                "error": str(result),
                "attempt": msg.retry_count + 1,
                "is_temporary": False
            })
            msg.retry_history = history
            return

        # 2. Proceed with sending if validation passes
        success, send_result = self.api_client.send_text(msg.phone_number, msg.message)
        
        if success:
            msg.status = "SENT"
            msg.sent_at = dt.datetime.utcnow()
            if campaign: campaign.sent_count += 1
            logger.debug(f"Message sent to {msg.phone_number}")
        else:
            # result is the error message from send_text
            result = str(send_result)
            # Check if it's a temporary failure (Network, Timeout, etc) or Permanent (Invalid Number)
            result_str = str(result).lower()
            is_temporary = any(term in result_str for term in [
                "network", "timeout", "server error", "500", "503", "504", "connection", 
                "reset", "failed to fetch", "econnreset", "etimedout"
            ])
            
            # Permanent failures: Invalid numbers, blocked, etc.
            is_permanent = any(term in result_str for term in [
                "invalid format", "not registered", "not found", "400", "401", "403", "blocked"
            ])
            
            if is_temporary and msg.retry_count < msg.max_retries:
                # Exponential Backoff Calculation: base * 2^attempt
                delay = min(self.base_retry_delay * (2 ** msg.retry_count), self.max_retry_delay)
                msg.next_retry_at = dt.datetime.utcnow() + dt.timedelta(seconds=delay)
                msg.status = "PENDING" # Re-queue for retry
                logger.info(f"Temporary failure for {msg.phone_number}. Re-queued for retry at {msg.next_retry_at}")
            else:
                msg.status = "FAILED"
                if campaign: campaign.failed_count += 1
            
            msg.retry_count += 1
            msg.error_message = str(result)
            
            # Log to retry history
            history = msg.retry_history or []
            history.append({
                "timestamp": dt.datetime.utcnow().isoformat(),
                "error": str(result),
                "attempt": msg.retry_count,
                "is_temporary": is_temporary
            })
            msg.retry_history = history
            logger.warning(f"Failed to send to {msg.phone_number}: {result}")

    def stop(self):
        self._is_running = False

class WhatsAppService(QObject):
    """Service layer for WhatsApp operations and campaigns."""
    
    def __init__(self):
        super().__init__()
        self.api_client = EvolutionAPIClient()
        self.worker = None

    def start_monitoring(self, status_callback=None, qr_callback=None):
        if self.worker and self.worker.isRunning():
            # Already running, just connect new callbacks if provided
            if status_callback:
                try: self.worker.status_received.connect(status_callback)
                except: pass
            if qr_callback:
                try: self.worker.qr_received.connect(qr_callback)
                except: pass
            # Trigger an immediate status check
            self.worker.set_action("status")
            return
        
        self.worker = WhatsAppWorker(self.api_client)
        if status_callback:
            self.worker.status_received.connect(status_callback)
        if qr_callback:
            self.worker.qr_received.connect(qr_callback)
        self.worker.start()

    def send_quick_message(self, number: str, text: str):
        """Send a test message."""
        def run_send():
            success, result = self.api_client.send_text(number, text)
            if self.worker:
                self.worker.message_result.emit(success, str(result))
        
        import threading
        threading.Thread(target=run_send, daemon=True).start()

    def create_campaign_from_excel(self, name: str, template: str, file_path: str) -> int:
        """Parse Excel and create a new WhatsApp campaign."""
        logger.info(f"Creating campaign '{name}' from file: {file_path}")
        recipients, columns = excel_service.parse_recipients(file_path)
        logger.info(f"Found {len(recipients)} recipients with columns: {columns}")
        
        db = SessionLocal()
        try:
            new_campaign = SMSCampaign(
                name=name,
                template=template,
                channel="WHATSAPP",
                total_recipients=len(recipients),
                excel_file_path=file_path,
                merge_fields=columns,
                status="PENDING",
                sent_count=0,
                failed_count=0,
                is_deleted=False
            )
            db.add(new_campaign)
            db.flush() # Get ID

            # Audit Log
            audit = AuditLog(
                action="CREATE",
                resource_type="CAMPAIGN",
                resource_id=new_campaign.id,
                details={"name": name, "recipients": len(recipients)}
            )
            db.add(audit)

            # Try to find the phone column more intelligently
            keywords = ["phone", "mobile", "number", "contact", "wa", "cell"]
            phone_col = next((c for c in columns if any(k in c.lower() for k in keywords)), columns[0])
            logger.info(f"Using column '{phone_col}' for phone numbers.")

            for person in recipients:
                # Merge template fields
                msg_text = template
                for col in columns:
                    placeholder = "{" + col + "}"
                    val = str(person.get(col, ""))
                    msg_text = msg_text.replace(placeholder, val)
                
                phone_val = str(person.get(phone_col, "")).strip()
                if "." in phone_val:
                    phone_val = phone_val.split(".")[0] # Clean float strings if any

                new_msg = SMSQueue(
                    campaign_id=new_campaign.id,
                    channel="WHATSAPP",
                    phone_number=phone_val,
                    recipient_name=str(person.get("name", "Recipient")),
                    message=msg_text,
                    status="PENDING",
                    retry_count=0,
                    max_retries=3,
                    is_read=False,
                    response_received=False
                )
                db.add(new_msg)
            
            db.commit()
            logger.info(f"Campaign {new_campaign.id} created with {len(recipients)} messages.")
            return new_campaign.id
        except Exception as e:
            logger.error(f"Error creating campaign: {e}")
            db.rollback()
            raise e
        finally:
            db.close()

    def validate_campaign_prerequisites(self, campaign_id: int) -> tuple[bool, str]:
        """Validates budget, targeting, and creative assets before starting."""
        db = SessionLocal()
        try:
            campaign = db.query(SMSCampaign).filter(SMSCampaign.id == campaign_id).first()
            if not campaign:
                return False, "Campaign not found"
            
            # 1. Targeting Check: Ensure there are recipients
            if campaign.total_recipients == 0:
                return False, "No targeting recipients found for this campaign."
            
            # 2. Creative Check: Template not empty
            if not campaign.template or len(campaign.template.strip()) < 5:
                return False, "Creative assets missing: Campaign template is too short or empty."
            
            # 3. Budget/Quota Check (Mock for now)
            # In a real app, check credits or budget limit here
            logger.info(f"Prerequisite check passed for campaign {campaign_id}")
            return True, "Ready"
        finally:
            db.close()

    def start_campaign(self, campaign_id: int, user_id: int = None):
        """Starts or resumes a campaign with prerequisite validation and state management."""
        if not self.check_authorization("START_CAMPAIGN", user_id):
            return False, "Unauthorized"

        # 1. State & Prerequisite Validation
        success, message = self.validate_campaign_prerequisites(campaign_id)
        if not success:
            logger.warning(f"Campaign {campaign_id} failed prerequisites: {message}")
            return False, message

        db = SessionLocal()
        try:
            # Use transaction to ensure state transition is atomic
            campaign = db.query(SMSCampaign).filter(
                SMSCampaign.id == campaign_id, 
                SMSCampaign.is_deleted == False
            ).with_for_update().first()

            if not campaign:
                return False, "Campaign not found or deleted"
            
            if campaign.status in ["RUNNING", "COMPLETED"]:
                return False, f"Invalid operation: Campaign is already {campaign.status}"

            # 2. Update State
            campaign.status = "RUNNING"
            if not campaign.started_at:
                campaign.started_at = dt.datetime.utcnow()
            
            # 3. Audit Log
            audit = AuditLog(
                action="START",
                resource_type="CAMPAIGN",
                resource_id=campaign_id,
                user_id=user_id,
                details={
                    "status": campaign.status,
                    "started_at": campaign.started_at.isoformat(),
                    "total": campaign.total_recipients
                }
            )
            db.add(audit)
            
            db.commit()
            logger.info(f"Campaign {campaign_id} activated successfully at {campaign.started_at}")
            
            if self.worker:
                self.worker.set_active_campaign(campaign_id)
            return True, "Campaign started successfully"
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to start campaign {campaign_id}: {e}", exc_info=True)
            return False, str(e)
        finally:
            db.close()

    def pause_campaign(self, campaign_id: int, reason: str = "User manual stop", user_id: int = None):
        """Immediately pauses a running campaign."""
        if not self.check_authorization("PAUSE_CAMPAIGN", user_id):
            return False, "Unauthorized"

        db = SessionLocal()
        try:
            campaign = db.query(SMSCampaign).filter(
                SMSCampaign.id == campaign_id,
                SMSCampaign.is_deleted == False
            ).with_for_update().first()

            if not campaign:
                return False, "Campaign not found"
            
            if campaign.status != "RUNNING":
                return False, f"Invalid operation: Cannot pause campaign in {campaign.status} state"

            # 1. Update State
            campaign.status = "PAUSED"
            campaign.paused_at = dt.datetime.utcnow()
            
            # 2. Audit Log
            audit = AuditLog(
                action="PAUSE",
                resource_type="CAMPAIGN",
                resource_id=campaign_id,
                user_id=user_id,
                details={
                    "reason": reason,
                    "paused_at": campaign.paused_at.isoformat(),
                    "progress": f"{campaign.sent_count}/{campaign.total_recipients}"
                }
            )
            db.add(audit)
            
            db.commit()
            logger.info(f"Campaign {campaign_id} paused successfully. Reason: {reason}")
            
            # Notify worker to drop this campaign from its active processing
            if self.worker and self.worker._active_campaign_id == campaign_id:
                self.worker._active_campaign_id = None
                
            return True, "Campaign paused successfully"
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to pause campaign {campaign_id}: {e}", exc_info=True)
            return False, str(e)
        finally:
            db.close()

    def check_authorization(self, action: str, user_id: int = None) -> bool:
        """
        Stub for authorization check. 
        In a real scenario, this would check if user_id has the required permissions/role.
        For now, we return True but log the check.
        """
        logger.info(f"Authorization check for action '{action}' (user: {user_id})")
        # Example of how this could be implemented:
        # db = SessionLocal()
        # user = db.query(User).filter(User.id == user_id).first()
        # if user and user.role == 'admin': return True
        return True

    def soft_delete_campaign(self, campaign_id: int, user_id: int = None):
        """Safely marks a campaign as deleted (soft delete) with audit trail and authorization check."""
        if not self.check_authorization("DELETE_CAMPAIGN", user_id):
            logger.warning(f"Unauthorized delete attempt for campaign {campaign_id} by user {user_id}")
            return False

        db = SessionLocal()
        try:
            # Use transaction to ensure all updates succeed or fail together
            campaign = db.query(SMSCampaign).filter(SMSCampaign.id == campaign_id).with_for_update().first()
            if campaign:
                if campaign.is_deleted:
                    logger.info(f"Campaign {campaign_id} already deleted.")
                    return True

                campaign.is_deleted = True
                campaign.deleted_at = dt.datetime.utcnow()
                campaign.status = "CANCELLED"
                
                # Cancel all pending messages
                cancelled_count = db.query(SMSQueue).filter(
                    SMSQueue.campaign_id == campaign_id, 
                    SMSQueue.status == "PENDING"
                ).update({"status": "CANCELLED"}, synchronize_session='fetch')

                # Audit Log with rich details
                audit = AuditLog(
                    action="SOFT_DELETE",
                    resource_type="CAMPAIGN",
                    resource_id=campaign_id,
                    user_id=user_id,
                    details={
                        "name": campaign.name,
                        "cancelled_messages": cancelled_count,
                        "timestamp": dt.datetime.utcnow().isoformat()
                    }
                )
                db.add(audit)
                
                db.commit()
                logger.info(f"Successfully soft-deleted campaign {campaign_id} ('{campaign.name}')")
                
                if self.worker and self.worker._active_campaign_id == campaign_id:
                    self.worker._active_campaign_id = None
                return True
            return False
        except Exception as e:
            db.rollback()
            logger.error(f"Soft delete failed for campaign {campaign_id}: {e}", exc_info=True)
            return False
        finally:
            db.close()

    def retry_failed_messages(self, campaign_id: int, user_id: int = None):
        """Manually triggers a retry for all failed messages in a campaign with authorization check."""
        if not self.check_authorization("RETRY_CAMPAIGN", user_id):
            return False

        db = SessionLocal()
        try:
            campaign = db.query(SMSCampaign).filter(SMSCampaign.id == campaign_id).with_for_update().first()
            if not campaign:
                return False

            # Find all failed messages for this campaign
            failed_msgs = db.query(SMSQueue).filter(
                SMSQueue.campaign_id == campaign_id,
                SMSQueue.status == "FAILED"
            ).all()
            
            if not failed_msgs:
                logger.info(f"No failed messages to retry for campaign {campaign_id}")
                return True

            for msg in failed_msgs:
                msg.status = "PENDING"
                msg.retry_count = 0
                msg.next_retry_at = dt.datetime.utcnow()
            
            campaign.status = "RUNNING"
            campaign.failed_count = 0 # Reset failed count for clean UI update
            
            # Audit Log
            audit = AuditLog(
                action="RETRY_ALL",
                resource_type="CAMPAIGN",
                resource_id=campaign_id,
                user_id=user_id,
                details={
                    "count": len(failed_msgs),
                    "timestamp": dt.datetime.utcnow().isoformat()
                }
            )
            db.add(audit)

            db.commit()
            logger.info(f"Triggered retry for {len(failed_msgs)} messages in campaign {campaign_id}")
            
            if self.worker:
                self.worker.set_active_campaign(campaign_id)
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Retry trigger failed for campaign {campaign_id}: {e}", exc_info=True)
            return False
        finally:
            db.close()

# Singleton instance for global use
whatsapp_service = WhatsAppService()
