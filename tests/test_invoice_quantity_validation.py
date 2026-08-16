"""Test that all invoice items have quantity 1 as per user request."""

import pytest
from datetime import datetime
from unittest.mock import patch
from app.services.invoice_service import InvoiceService
from app.api.schemas import InvoiceCreate, InvoiceItemCreate
from app.db.models import Base, ProductModel, Customer
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database session for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    yield Session()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def invoice_service():
    """Create an instance of InvoiceService for testing."""
    return InvoiceService()


@pytest.fixture
def sample_invoice_data(db_session):
    """Create sample data for testing."""
    # Create product model
    product_model = ProductModel(
        model_name="Honda CD70",
        make="Honda",
        engine_capacity="70cc"
    )
    db_session.add(product_model)

    # Create customer
    customer = Customer(
        name="Test Customer",
        cnic="12345-6789012-3",
        phone="03001234567",
        address="Test Address"
    )
    db_session.add(customer)
    db_session.commit()

    return {
        "product_model": product_model,
        "customer": customer
    }


def test_invoice_item_quantity_enforced_to_1(invoice_service, db_session, sample_invoice_data):
    """Test that all invoice items are created with quantity 1, regardless of input."""
    # Create invoice with items having various quantities
    items = [
        InvoiceItemCreate(
            item_code="MOTO-001",
            item_name="Honda CD70",
            quantity=5,  # Should be enforced to 1
            tax_rate=18.0,
            sale_value=100000.0,
            tax_charged=18000.0,
            total_amount=118000.0,
            pct_code="87112010",
            chassis_number="CH-1234567890",
            engine_number="EN-123456",
            model_name="Honda CD70",
            color="Red"
        ),
        InvoiceItemCreate(
            item_code="MOTO-002",
            item_name="Honda CG125",
            quantity=10,  # Should be enforced to 1
            tax_rate=18.0,
            sale_value=150000.0,
            tax_charged=27000.0,
            total_amount=177000.0,
            pct_code="87112010",
            chassis_number="CH-0987654321",
            engine_number="EN-098765",
            model_name="Honda CG125",
            color="Black"
        ),
        InvoiceItemCreate(
            item_code="MOTO-003",
            item_name="Honda 125",
            quantity=0,  # Should be enforced to 1
            tax_rate=18.0,
            sale_value=200000.0,
            tax_charged=36000.0,
            total_amount=236000.0,
            pct_code="87112010",
            chassis_number="CH-5555555555",
            engine_number="EN-555555",
            model_name="Honda 125",
            color="Blue"
        )
    ]

    invoice_in = InvoiceCreate(
        invoice_number="INV-TEST-001",
        datetime=datetime.now(),
        buyer_name="John Doe",
        buyer_cnic="33303-1234567-1",
        payment_mode="Cash",
        items=items
    )

    # Mock FBR API to return success
    with patch("app.services.invoice_service.fbr_client.post_invoice") as mock_post:
        mock_post.return_value = {
            "InvoiceNumber": "1000000000000001",
            "Response": "Success",
            "Code": "100"
        }

        result = invoice_service.create_invoice(db_session, invoice_in)

        # Verify the invoice was created successfully
        assert result is not None
        assert result.invoice_number == "INV-TEST-001"
        assert result.is_fiscalized == True

        # Verify all items have quantity 1
        for item in result.items:
            assert item.quantity == 1

        # Verify totals were calculated correctly (each item is treated as quantity 1)
        assert result.total_quantity == 3  # 3 items, each quantity 1
        assert result.total_sale_value == 100000 + 150000 + 200000  # 450000
        assert result.total_tax_charged == 18000 + 27000 + 36000  # 81000
        assert result.total_amount == 118000 + 177000 + 236000  # 531000


def test_quantity_spin_box_is_disabled():
    """Test that the quantity spin box is disabled in the UI."""
    # Since we modified the UI file directly, we don't need to run a full Qt test
    # We can simply check the code in main_window.py to verify our changes
    import os
    test_file_path = os.path.abspath(__file__)
    project_root = os.path.dirname(os.path.dirname(test_file_path))
    main_window_path = os.path.join(project_root, 'app', 'qt_ui', 'main_window.py')
    
    with open(main_window_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check that the quantity spin box is configured correctly
    assert 'self.invoice_quantity_spin.setRange(1, 1)' in content
    assert 'self.invoice_quantity_spin.setValue(1)' in content
    assert 'self.invoice_quantity_spin.setDisabled(True)' in content
    
    # Verify that the valueChanged connection is removed
    assert 'self.invoice_quantity_spin.valueChanged.connect' not in content
