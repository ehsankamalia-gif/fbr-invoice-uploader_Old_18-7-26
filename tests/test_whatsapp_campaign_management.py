import pytest
import datetime as dt
from unittest.mock import MagicMock, patch
from app.db.session import SessionLocal
from app.db.models import SMSCampaign, SMSQueue, AuditLog, SMSStatus
from app.services.whatsapp_service import WhatsAppService, WhatsAppWorker

@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()

@pytest.fixture
def whatsapp_service():
    service = WhatsAppService()
    service.api_client = MagicMock()
    return service

def test_soft_delete_campaign(db, whatsapp_service):
    # Create a dummy campaign
    campaign = SMSCampaign(
        name="Test Campaign",
        template="Hello {name}",
        channel="WHATSAPP",
        total_recipients=1,
        status="PENDING",
        is_deleted=False
    )
    db.add(campaign)
    db.commit()
    campaign_id = campaign.id

    # Create a dummy message
    msg = SMSQueue(
        campaign_id=campaign_id,
        phone_number="923001234567",
        message="Hello Test",
        status="PENDING"
    )
    db.add(msg)
    db.commit()

    # Perform soft delete
    success = whatsapp_service.soft_delete_campaign(campaign_id, user_id=99)
    assert success is True

    # Verify campaign is deleted
    db.expire_all()
    c = db.query(SMSCampaign).filter(SMSCampaign.id == campaign_id).first()
    assert c.is_deleted is True
    assert c.status == "CANCELLED"
    assert c.deleted_at is not None

    # Verify message is cancelled
    m = db.query(SMSQueue).filter(SMSQueue.campaign_id == campaign_id).first()
    assert m.status == "CANCELLED"

    # Verify audit log
    audit = db.query(AuditLog).filter(
        AuditLog.resource_id == campaign_id,
        AuditLog.action == "SOFT_DELETE"
    ).first()
    assert audit is not None
    assert audit.user_id == 99
    assert audit.details["name"] == "Test Campaign"

def test_retry_logic_exponential_backoff(db, whatsapp_service):
    # Mock API client to return a temporary failure
    whatsapp_service.api_client.send_text.return_value = (False, "Network Error (503)")
    
    worker = WhatsAppWorker(whatsapp_service.api_client)
    
    # Create a dummy message
    msg = SMSQueue(
        phone_number="923001234567",
        message="Retry Test",
        status="PENDING",
        retry_count=0,
        max_retries=3
    )
    db.add(msg)
    db.commit()
    
    # Attempt 1
    worker._attempt_send(db, msg, None)
    db.commit()
    
    assert msg.status == "PENDING" # Should be re-queued
    assert msg.retry_count == 1
    assert msg.next_retry_at is not None
    assert len(msg.retry_history) == 1
    assert msg.retry_history[0]['is_temporary'] is True
    
    # Check exponential backoff (base 300 * 2^0 = 300s)
    delay = (msg.next_retry_at - dt.datetime.utcnow()).total_seconds()
    assert 290 < delay < 310

    # Attempt 2
    worker._attempt_send(db, msg, None)
    db.commit()
    assert msg.retry_count == 2
    delay = (msg.next_retry_at - dt.datetime.utcnow()).total_seconds()
    # 300 * 2^1 = 600s
    assert 590 < delay < 610

def test_manual_retry_trigger(db, whatsapp_service):
    campaign = SMSCampaign(
        name="Retry Campaign",
        template="Test",
        channel="WHATSAPP",
        status="FAILED",
        failed_count=5
    )
    db.add(campaign)
    db.commit()
    
    for i in range(5):
        msg = SMSQueue(
            campaign_id=campaign.id,
            phone_number=f"92300{i}",
            message="Test",
            status="FAILED"
        )
        db.add(msg)
    db.commit()
    
    # Trigger manual retry
    success = whatsapp_service.retry_failed_messages(campaign.id, user_id=1)
    assert success is True
    
    db.expire_all()
    assert campaign.status == "RUNNING"
    assert campaign.failed_count == 0
    
    msgs = db.query(SMSQueue).filter(SMSQueue.campaign_id == campaign.id).all()
    for m in msgs:
        assert m.status == "PENDING"
        assert m.retry_count == 0

def test_permanent_failure(db, whatsapp_service):
    whatsapp_service.api_client.send_text.return_value = (False, "Number not registered on WhatsApp (400)")
    
    worker = WhatsAppWorker(whatsapp_service.api_client)
    msg = SMSQueue(
        phone_number="923001234567",
        message="Permanent Test",
        status="PENDING"
    )
    db.add(msg)
    db.commit()
    
    worker._attempt_send(db, msg, None)
    db.commit()
    
    assert msg.status == "FAILED"
    assert msg.next_retry_at is None
    assert msg.retry_history[0]['is_temporary'] is False

def test_number_existence_check(db, whatsapp_service):
    # Mock existence check to return False
    whatsapp_service.api_client.check_number_exists.return_value = (False, "This number is not on WhatsApp")
    
    worker = WhatsAppWorker(whatsapp_service.api_client)
    msg = SMSQueue(
        phone_number="923000000000",
        message="Validation Test",
        status="PENDING"
    )
    db.add(msg)
    db.commit()
    
    worker._attempt_send(db, msg, None)
    db.commit()
    
    assert msg.status == "FAILED"
    assert msg.error_message == "This number is not on WhatsApp"
    # send_text should NOT have been called
    whatsapp_service.api_client.send_text.assert_not_called()

def test_campaign_lifecycle_start_pause(db, whatsapp_service):
    # Create a dummy campaign
    campaign = SMSCampaign(
        name="Lifecycle Test",
        template="Hello {name}",
        channel="WHATSAPP",
        total_recipients=10,
        status="PENDING"
    )
    db.add(campaign)
    db.commit()
    
    # 1. Start Campaign
    success, message = whatsapp_service.start_campaign(campaign.id, user_id=1)
    assert success is True
    assert "started successfully" in message.lower()
    
    db.expire_all()
    assert campaign.status == "RUNNING"
    assert campaign.started_at is not None
    
    # 2. Pause Campaign
    success, message = whatsapp_service.pause_campaign(campaign.id, reason="Testing pause", user_id=1)
    assert success is True
    assert "paused successfully" in message.lower()
    
    db.expire_all()
    assert campaign.status == "PAUSED"
    assert campaign.paused_at is not None
    
    # 3. Resume (Start) Campaign
    success, message = whatsapp_service.start_campaign(campaign.id, user_id=1)
    assert success is True
    assert campaign.status == "RUNNING"
    
    # 4. Invalid State Transition (Pause a COMPLETED campaign)
    campaign.status = "COMPLETED"
    db.commit()
    
    success, message = whatsapp_service.pause_campaign(campaign.id, user_id=1)
    assert success is False
    assert "Invalid operation" in message

def test_campaign_prerequisites_validation(db, whatsapp_service):
    # Campaign with no recipients
    campaign = SMSCampaign(
        name="Empty Test",
        template="Hello",
        channel="WHATSAPP",
        total_recipients=0
    )
    db.add(campaign)
    db.commit()
    
    success, message = whatsapp_service.start_campaign(campaign.id, user_id=1)
    assert success is False
    assert "No targeting recipients" in message
    
    # Campaign with short template
    campaign.total_recipients = 10
    campaign.template = "hi"
    db.commit()
    
    success, message = whatsapp_service.start_campaign(campaign.id, user_id=1)
    assert success is False
    assert "Creative assets missing" in message
