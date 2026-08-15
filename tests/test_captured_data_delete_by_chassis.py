import pytest
from app.services.captured_data_service import CapturedDataService
from app.db.models import CapturedData, Base, Invoice, InvoiceItem, Motorcycle, Customer, ProductModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import logging
from datetime import datetime

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Setup in-memory DB for testing
engine = create_engine("sqlite:///:memory:")
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

@pytest.fixture
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture
def service(db_session):
    svc = CapturedDataService()
    svc.db = db_session
    return svc

def test_delete_by_chassis(service, db_session):
    """Test that delete_by_chassis works correctly"""
    # Setup Data
    chassis_number = "CH-123-TEST"
    record = CapturedData(
        name="Test Customer",
        father="Test Father",
        cnic="12345-6789012-3",
        cell="03001234567",
        address="Test Address",
        chassis_number=chassis_number,
        engine_number="ENG-123",
        model="Honda CD70",
        color="Red"
    )
    db_session.add(record)
    db_session.commit()
    
    # Verify record exists
    existing = db_session.query(CapturedData).filter(CapturedData.chassis_number == chassis_number).first()
    assert existing is not None
    assert existing.chassis_number == chassis_number
    
    # Test deletion
    success = service.delete_by_chassis(db_session, chassis_number)
    assert success is True
    
    # Verify record is deleted
    deleted = db_session.query(CapturedData).filter(CapturedData.chassis_number == chassis_number).first()
    assert deleted is None

def test_delete_by_chassis_not_found(service, db_session):
    """Test deleting a chassis that doesn't exist"""
    success = service.delete_by_chassis(db_session, "NON-EXISTENT-CHASSIS")
    assert success is False

def test_delete_by_chassis_empty(service, db_session):
    """Test deleting with empty chassis number"""
    success = service.delete_by_chassis(db_session, "")
    assert success is False


