import threading
import time
import logging
import uuid
import datetime as dt
from typing import List, Dict, Any, Optional, Callable
from app.db.session import SessionLocal
from app.db.models import SMSCampaign, SMSQueue, SMSStatus, SMSConfiguration
from app.services.sms_service import sms_service
from app.services.excel_processing_service import ExcelProcessingService
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

class BulkSMSWorker(threading.Thread):
    """
    Background worker for processing a single SMS campaign.
    Handles rate limiting, database updates, and progress signaling.
    """
    
    def __init__(self, campaign_id: int, 
                 on_progress: Optional[Callable[[int, int, int], None]] = None,
                 on_complete: Optional[Callable[[bool, str], None]] = None):
        super().__init__(daemon=True)
        self.campaign_id = campaign_id
        self.on_progress = on_progress
        self.on_complete = on_complete
        self._stop_event = threading.Event()
        self._paused = False

    def stop(self):
        self._stop_event.set()

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def run(self):
        db = SessionLocal()
        try:
            campaign = db.query(SMSCampaign).filter(SMSCampaign.id == self.campaign_id).first()
            if not campaign:
                if self.on_complete: self.on_complete(False, "Campaign not found.")
                return

            config = db.query(SMSConfiguration).first()
            if not config or not config.is_enabled:
                campaign.status = "FAILED"
                campaign.error_message = "SMS Module is disabled in Settings."
                db.commit()
                if self.on_complete: self.on_complete(False, "SMS Module is disabled in settings.")
                return

            campaign.status = "RUNNING"
            db.commit()

            # Get pending messages IDs for this campaign
            msg_ids = [m.id for m in db.query(SMSQueue.id).filter(
                SMSQueue.campaign_id == self.campaign_id,
                SMSQueue.status == SMSStatus.PENDING
            ).all()]

            total_to_process = len(msg_ids)
            total_campaign = campaign.total_recipients or total_to_process
            sent = campaign.sent_count or 0
            failed = campaign.failed_count or 0

            logger.info(f"Starting Campaign {self.campaign_id}: {total_to_process} messages pending.")

            for i, msg_id in enumerate(msg_ids):
                if self._stop_event.is_set():
                    campaign.status = "PAUSED"
                    db.commit()
                    break
                
                while self._paused:
                    if self._stop_event.is_set(): break
                    time.sleep(1)
                
                # Custom delay between messages to avoid carrier blocks
                # Don't delay before the very first message of a fresh campaign
                if i > 0 or sent > 0 or failed > 0:
                    delay = config.delay_seconds or 5
                    logger.info(f"Campaign {self.campaign_id}: Waiting {delay} seconds before next message...")
                    
                    # Sleep in small increments to allow for faster pausing/stopping
                    for _ in range(delay):
                        if self._stop_event.is_set() or self._paused:
                            break
                        time.sleep(1)
                    
                    if self._stop_event.is_set():
                        campaign.status = "PAUSED"
                        db.commit()
                        break

                # Get fresh message object
                msg = db.query(SMSQueue).filter(SMSQueue.id == msg_id).first()
                if not msg: 
                    logger.warning(f"Message ID {msg_id} not found in DB.")
                    continue

                # Update status to SENDING
                msg.status = SMSStatus.SENDING
                db.commit()

                logger.info(f"Campaign {self.campaign_id}: Sending message {i+1}/{total_to_process} to {msg.phone_number}")
                
                success = False
                result = ""
                
                if getattr(config, 'gateway_type', 'WIFI') == 'CLOUD' and config.api_url:
                    success, result = sms_service.send_sms_via_cloud(
                        config.api_url,
                        msg.phone_number,
                        msg.message,
                        config.api_key,
                        config.cloud_username,
                        config.cloud_password
                    )
                else:
                    success, result = sms_service.send_sms_via_wifi(
                        config.gateway_ip, 
                        config.gateway_port, 
                        msg.phone_number, 
                        msg.message,
                        api_key=config.api_key,
                        username=config.gateway_username,
                        password=config.gateway_password,
                        use_https=getattr(config, 'use_https', False)
                    )

                # Re-fetch objects to ensure session consistency
                db.expire_all()
                msg = db.query(SMSQueue).filter(SMSQueue.id == msg_id).first()
                campaign = db.query(SMSCampaign).filter(SMSCampaign.id == self.campaign_id).first()

                if success:
                    msg.status = SMSStatus.SENT
                    msg.sent_at = dt.datetime.utcnow()
                    sent += 1
                    logger.info(f"Campaign {self.campaign_id}: Successfully sent to {msg.phone_number}")
                else:
                    msg.status = SMSStatus.FAILED
                    msg.error_message = result[:255]
                    failed += 1
                    logger.error(f"Campaign {self.campaign_id}: Failed to send to {msg.phone_number}: {result}")
                
                # Update campaign stats and commit immediately
                campaign.sent_count = sent
                campaign.failed_count = failed
                db.commit()

                if self.on_progress:
                    self.on_progress(sent, failed, total_campaign)

            # Finalize Campaign
            if sent + failed >= total_campaign:
                campaign.status = "COMPLETED"
                campaign.completed_at = dt.datetime.utcnow()
                db.commit()
                if self.on_complete: self.on_complete(True, f"Campaign completed. Sent: {sent}, Failed: {failed}")
            else:
                if self.on_complete: self.on_complete(True, "Campaign paused or stopped.")

        except Exception as e:
            logger.error(f"Error in BulkSMSWorker: {e}", exc_info=True)
            try:
                # Reload session to ensure we can update status
                db_err = SessionLocal()
                camp_err = db_err.query(SMSCampaign).filter(SMSCampaign.id == self.campaign_id).first()
                if camp_err:
                    camp_err.status = "FAILED"
                    camp_err.error_message = str(e)[:500]
                    db_err.commit()
                db_err.close()
            except:
                pass
            if self.on_complete: self.on_complete(False, str(e))
        finally:
            db.close()

class BulkSMSService:
    """
    Service for managing bulk SMS campaigns and workers.
    """
    
    def __init__(self):
        self.active_workers: Dict[int, BulkSMSWorker] = {}
        self.excel_service = ExcelProcessingService()

    def _apply_template(self, template: str, data_row: Dict[str, Any]) -> str:
        """
        Replaces placeholders in the template with values from the data row.
        Placeholders should be in the format {column_name}.
        """
        for key, value in data_row.items():
            template = template.replace(f"{{{key}}}", str(value))
        return template

    def create_campaign(self, name: str, template: str, data: List[Dict[str, Any]]) -> int:
        """
        Creates a campaign and its associated messages in the database.
        """
        db = SessionLocal()
        try:
            campaign = SMSCampaign(
                name=name,
                template=template,
                total_recipients=len(data),
                status="PENDING"
            )
            db.add(campaign)
            db.flush()  # Get ID

            phone_col = next((col for col in ['phone', 'number', 'cell', 'mobile'] if col in data[0]), None)
            name_col = next((col for col in ['name', 'customer', 'recipient'] if col in data[0]), "Recipient")

            for item in data:
                message_text = self._apply_template(template, item)
                
                phone_number = item.get(phone_col)
                recipient_name = item.get(name_col, "N/A")

                if not phone_number:
                    continue # Or handle as a failed record

                sms = SMSQueue(
                    campaign_id=campaign.id,
                    phone_number=str(phone_number),
                    recipient_name=str(recipient_name),
                    message=message_text,
                    status=SMSStatus.PENDING
                )
                db.add(sms)
            
            db.commit()
            return campaign.id
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    def get_campaign_details(self, campaign_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieves full details for a campaign, including all its messages.
        """
        db = SessionLocal()
        try:
            campaign = db.query(SMSCampaign).filter(SMSCampaign.id == campaign_id).first()
            if not campaign:
                return None
            
            messages = db.query(SMSQueue).filter(SMSQueue.campaign_id == campaign_id).all()
            
            return {
                "campaign": campaign,
                "messages": messages
            }
        finally:
            db.close()

    def start_campaign(self, campaign_id: int, 
                       on_progress: Optional[Callable[[int, int, int], None]] = None,
                       on_complete: Optional[Callable[[bool, str], None]] = None):
        """
        Starts a background worker for the given campaign.
        """
        if campaign_id in self.active_workers and self.active_workers[campaign_id].is_alive():
            return False, "Campaign is already running."
            
        worker = BulkSMSWorker(campaign_id, on_progress, on_complete)
        self.active_workers[campaign_id] = worker
        worker.start()
        return True, "Campaign started."

    def retry_failed_messages(self, campaign_id: int) -> Tuple[bool, str]:
        """
        Retries all failed messages for a given campaign.
        """
        db = SessionLocal()
        try:
            # Find failed messages and reset their status
            failed_messages = db.query(SMSQueue).filter(
                SMSQueue.campaign_id == campaign_id,
                SMSQueue.status == SMSStatus.FAILED
            ).all()

            if not failed_messages:
                return False, "No failed messages to retry."

            for msg in failed_messages:
                msg.status = SMSStatus.PENDING
                msg.error_message = None # Clear previous error
            
            # Reset campaign status to allow re-running
            campaign = db.query(SMSCampaign).filter(SMSCampaign.id == campaign_id).first()
            if campaign:
                # Decrement the failed count by the number of messages being retried
                campaign.failed_count -= len(failed_messages)
                campaign.status = "PENDING"

            db.commit()
            return True, f"Retrying {len(failed_messages)} failed messages."
        except Exception as e:
            db.rollback()
            logger.error(f"Error retrying failed messages for campaign {campaign_id}: {e}")
            return False, str(e)
        finally:
            db.close()

    def stop_campaign(self, campaign_id: int):
        if campaign_id in self.active_workers:
            self.active_workers[campaign_id].stop()
            return True
        return False

    def delete_campaign(self, campaign_id: int) -> bool:
        """
        Deletes a campaign and its associated messages from the database.
        """
        # First ensure the campaign is not running
        if campaign_id in self.active_workers and self.active_workers[campaign_id].is_alive():
            self.active_workers[campaign_id].stop()
            
        db = SessionLocal()
        try:
            campaign = db.query(SMSCampaign).filter(SMSCampaign.id == campaign_id).first()
            if campaign:
                # Due to cascade="all, delete-orphan" in models.py, 
                # deleting the campaign will also delete all SMSQueue entries.
                db.delete(campaign)
                db.commit()
                return True
            return False
        except Exception as e:
            db.rollback()
            logger.error(f"Error deleting campaign {campaign_id}: {e}")
            raise e
        finally:
            db.close()

bulk_sms_service = BulkSMSService()
