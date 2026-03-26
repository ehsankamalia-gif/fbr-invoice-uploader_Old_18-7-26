import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from app.api.fbr_client import FBRClient
from app.api.schemas import InvoiceCreate, InvoiceItemCreate

@pytest.fixture
def invoice_data():
    return {
        "invoice_number": "INV-001",
        "datetime": datetime.now(), 
        "buyer_name": "John Doe",
        "total_amount": 117.0, # Added missing field
        "total_quantity": 1,   # Added missing field
        "total_sale_value": 100.0, # Added missing field
        "total_tax_charged": 17.0, # Added missing field
        "payment_mode": "Cash", # Added missing field
        "items": [
            {
                "item_code": "1",
                "item_name": "Test Item",
                "quantity": 1,
                "tax_rate": 17.0,
                "sale_value": 100.0,
                "total_amount": 117.0,
                "tax_charged": 17.0,
                "pct_code": "11001010"
            }
        ]
    }

def test_transform_to_fbr_format_with_further_tax():
    invoice_data = {
        "invoice_number": "INV-001",
        "datetime": datetime.now(), 
        "buyer_name": "John Doe",
        "total_amount": 120.0,
        "total_quantity": 1,
        "total_sale_value": 100.0,
        "total_tax_charged": 17.0,
        "total_further_tax": 3.0,
        "payment_mode": "Cash",
        "items": [
            {
                "item_code": "1",
                "item_name": "Test Item",
                "quantity": 1,
                "tax_rate": 17.0,
                "sale_value": 100.0,
                "total_amount": 120.0,
                "tax_charged": 17.0,
                "further_tax": 3.0,
                "pct_code": "11001010"
            }
        ]
    }
    client = FBRClient()
    settings = {"pos_id": 123, "pct_code": "11001010"}
    fbr_data = client._transform_to_fbr_format(invoice_data, settings)
    
    assert fbr_data["TotalFurtherTax"] == 3.0
    assert fbr_data["TotalFurtherTaxCharged"] == 3.0
    assert fbr_data["TotalFurtherTaxAmount"] == 3.0
    assert fbr_data["FurtherTax"] == 3.0 # Root alias
    assert fbr_data["FurtherTaxCharged"] == 3.0 # Root alias
    assert fbr_data["TotalAdditionalTax"] == 3.0
    assert fbr_data["TotalAdditionalTaxCharged"] == 3.0
    assert fbr_data["TotalOtherTax"] == 3.0
    
    assert fbr_data["Items"][0]["FurtherTax"] == 3.0
    assert fbr_data["Items"][0]["FurtherTaxCharged"] == 3.0
    assert fbr_data["Items"][0]["FurtherTaxAmount"] == 3.0
    assert fbr_data["Items"][0]["AdditionalTax"] == 3.0
    assert fbr_data["Items"][0]["AdditionalTaxCharged"] == 3.0
    assert fbr_data["Items"][0]["OtherTax"] == 3.0
    
    # Check PoSFee
    assert fbr_data["PoSFee"] == 1.0
    assert fbr_data["TotalPoSFee"] == 1.0
    assert fbr_data["TotalBillAmount"] == 121.0 # 120 + 1.0 PoSFee

def test_transform_to_fbr_format_with_business_rules():
    """Verify that settings from the business rules image are applied correctly."""
    invoice_data = {
        "invoice_number": "INV-1001",
        "datetime": datetime.now(), 
        "buyer_name": "John Doe",
        "total_amount": 118.0,
        "total_quantity": 1,
        "total_sale_value": 100.0,
        "total_tax_charged": 18.0,
        "total_further_tax": 0.0,
        "payment_mode": "Cash",
        "items": [
            {
                "item_code": "ITEMCODE-MOTO",
                "item_name": "Honda Motorcycle",
                "quantity": 1,
                "tax_rate": 18.0,
                "sale_value": 100.0,
                "total_amount": 118.0,
                "tax_charged": 18.0,
                "further_tax": 0.0,
                "pct_code": "8711.2010"
            }
        ]
    }
    
    # Settings as per the provided image
    settings = {
        "pos_id": 123,
        "business_name": "Ehsan Trader Kamalia Pakistan",
        "tax_rate": 18.0,
        "pct_code": "8711.2010",
        "item_code": "ITEMCODE",
        "item_name": "Honda",
        "invoice_type": "Standard",
        "discount": 0.0
    }
    
    client = FBRClient()
    fbr_data = client._transform_to_fbr_format(invoice_data, settings)
    
    assert fbr_data["InvoiceType"] == 1 # Standard
    assert fbr_data["Items"][0]["InvoiceType"] == 1
    assert fbr_data["Items"][0]["TaxRate"] == 18.0
    assert fbr_data["Items"][0]["Discount"] == 0.0
    assert fbr_data["Items"][0]["PCTCode"] == "87112010" # Stripped format

def test_transform_to_fbr_format(invoice_data):
    client = FBRClient()
    settings = {"pos_id": 123, "pct_code": "11001010"}
    fbr_data = client._transform_to_fbr_format(invoice_data, settings)
    
    assert fbr_data["InvoiceNumber"] == "INV-001"
    assert len(fbr_data["Items"]) == 1 # Was "items"
    assert fbr_data["Items"][0]["ItemCode"] == "1" # Was "items"

@patch("app.services.settings_service.settings_service.get_active_settings")
@patch("requests.post")
def test_post_invoice_success(mock_post, mock_settings, invoice_data):
    mock_settings.return_value = {
        "pos_id": 123456,
        "token": "MOCK_TOKEN",
        "base_url": "https://esp.fbr.gov.pk:8243/PT/v1",
        "env": "SANDBOX"
    }
    
    # Ensure invoice data has required fields for validation
    invoice_data["buyer_cnic"] = "33303-1234567-1"
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"InvoiceNumber": "FBR-123456", "Code": "100", "Response": "Success"}
    mock_post.return_value = mock_response

    client = FBRClient()
    response = client.post_invoice(invoice_data)
    
    assert response["InvoiceNumber"] == "FBR-123456"
    mock_post.assert_called_once()
