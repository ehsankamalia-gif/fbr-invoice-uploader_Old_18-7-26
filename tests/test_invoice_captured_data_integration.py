import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.models import Base, Invoice, InvoiceItem, Motorcycle, Customer, CapturedData, ProductModel
from app.services.invoice_service import InvoiceService
from app.api.schemas import InvoiceCreate, InvoiceItemCreate
from app.core.config import settings
from datetime import datetime

# Setup DB Fixture
@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

@pytest.fixture
def invoice_service():
    return InvoiceService()

def test_invoice_creation_with_captured_data_cleanup(db_session, invoice_service):
    """Test that captured data record is deleted after successful FBR upload"""
    # Create product model first
    product_model = ProductModel(
        model_name="Honda CD70",
        make="Honda",
        engine_capacity="70cc"
    )
    db_session.add(product_model)
    db_session.commit()
    
    # Setup Captured Data
    chassis_number = "CH-TEST-CAPTURE-001"
    captured_record = CapturedData(
        name="Test Customer for Capture",
        father="Test Father",
        cnic="11111-1111111-1",
        cell="03001111111",
        address="Test Address",
        chassis_number=chassis_number,
        engine_number="ENG-123",
        model="Honda CD70",
        color="Red"
    )
    db_session.add(captured_record)
    db_session.commit()
    
    # Verify captured data exists before invoice creation
    existing_captured = db_session.query(CapturedData).filter(CapturedData.chassis_number == chassis_number).first()
    assert existing_captured is not None
    assert existing_captured.chassis_number == chassis_number
    
    # Create motorcycle in stock
    motorcycle = Motorcycle(
        product_model_id=product_model.id,
        chassis_number=chassis_number,
        engine_number="ENG-123",
        status="IN_STOCK",
        cost_price=50000,
        sale_price=60000,
        year=2024
    )
    db_session.add(motorcycle)
    
    # Create customer
    customer = Customer(
        name="Test Customer",
        cnic="11111-1111111-1",
        phone="03001111111",
        address="Test Address"
    )
    db_session.add(customer)
    
    db_session.commit()
    
    # Prepare Invoice Data
    item = InvoiceItemCreate(
        item_code="MOTO-001", 
        item_name="Honda CD70", 
        quantity=1, 
        tax_rate=18.0, 
        sale_value=100000.0,
        tax_charged=18000.0,
        total_amount=118000.0,
        pct_code="87112010",
        chassis_number=chassis_number,
        engine_number="ENG-123"
    )
    invoice_in = InvoiceCreate(
        invoice_number="INV-CAPTURE-TEST-001",
        datetime=datetime.now(),
        buyer_name="John Doe",
        buyer_cnic="33303-1234567-1",
        payment_mode="Cash",
        items=[item]
    )
    
    # Mock FBR Client to simulate successful submission
    with patch("app.services.invoice_service.fbr_client.post_invoice") as mock_post:
        mock_post.return_value = {
            "InvoiceNumber": "1000000000000001", 
            "Response": "Success", 
            "Code": "100"
        }
        
        # Create invoice (which should trigger FBR sync)
        result = invoice_service.create_invoice(db_session, invoice_in)
        
        # Verify invoice was created successfully
        assert result.invoice_number == "INV-CAPTURE-TEST-001"
        assert result.fbr_invoice_number == "1000000000000001"
        assert result.is_fiscalized == True
        
        # Verify captured data record was deleted
        deleted_captured = db_session.query(CapturedData).filter(CapturedData.chassis_number == chassis_number).first()
        assert deleted_captured is None
        
        # Verify motorcycle still exists and status is updated
        db_session.refresh(motorcycle)
        assert motorcycle.status == "SOLD"

def test_no_captured_data_cleanup_on_fbr_failure(db_session, invoice_service):
    """Test that captured data record is NOT deleted if FBR upload fails"""
    # Create product model first
    product_model = ProductModel(
        model_name="Honda CD70",
        make="Honda",
        engine_capacity="70cc"
    )
    db_session.add(product_model)
    db_session.commit()
    
    # Setup Captured Data
    chassis_number = "CH-TEST-CAPTURE-002"
    captured_record = CapturedData(
        name="Test Customer for Failure",
        father="Test Father",
        cnic="22222-2222222-2",
        cell="03002222222",
        address="Test Address",
        chassis_number=chassis_number,
        engine_number="ENG-456",
        model="Honda CD70",
        color="Black"
    )
    db_session.add(captured_record)
    db_session.commit()
    
    # Create motorcycle in stock
    motorcycle = Motorcycle(
        product_model_id=product_model.id,
        chassis_number=chassis_number,
        engine_number="ENG-456",
        status="IN_STOCK",
        cost_price=50000,
        sale_price=60000,
        year=2024
    )
    db_session.add(motorcycle)
    
    # Create customer
    customer = Customer(
        name="Test Customer",
        cnic="22222-2222222-2",
        phone="03002222222",
        address="Test Address"
    )
    db_session.add(customer)
    
    db_session.commit()
    
    # Prepare Invoice Data
    item = InvoiceItemCreate(
        item_code="MOTO-002", 
        item_name="Honda CD70", 
        quantity=1, 
        tax_rate=18.0, 
        sale_value=100000.0,
        tax_charged=18000.0,
        total_amount=118000.0,
        pct_code="87112010",
        chassis_number=chassis_number,
        engine_number="ENG-456"
    )
    invoice_in = InvoiceCreate(
        invoice_number="INV-CAPTURE-TEST-002",
        datetime=datetime.now(),
        buyer_name="Jane Doe",
        buyer_cnic="44404-4444444-4",
        payment_mode="Cash",
        items=[item]
    )
    
    # Mock FBR Client to simulate failure
    with patch("app.services.invoice_service.fbr_client.post_invoice") as mock_post:
        mock_post.return_value = {
            "Response": "Invalid Data", 
            "Code": "400"
        }
        
        try:
            result = invoice_service.create_invoice(db_session, invoice_in)
            # Should raise exception for failure
            assert False, "Expected exception for FBR failure"
        except Exception as e:
            pass
            
        # Verify captured data record still exists
        existing_captured = db_session.query(CapturedData).filter(CapturedData.chassis_number == chassis_number).first()
        assert existing_captured is not None
        assert existing_captured.chassis_number == chassis_number
        
        # Verify motorcycle status remains IN_STOCK (rolled back)
        db_session.refresh(motorcycle)
        assert motorcycle.status == "IN_STOCK"
