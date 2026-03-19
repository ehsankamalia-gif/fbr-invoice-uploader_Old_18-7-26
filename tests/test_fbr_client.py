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
    assert fbr_data["Items"][0]["FurtherTax"] == 3.0

def test_transform_to_fbr_format(invoice_data):
    client = FBRClient()
    settings = {"pos_id": 123, "pct_code": "11001010"}
    fbr_data = client._transform_to_fbr_format(invoice_data, settings)
    
    assert fbr_data["InvoiceNumber"] == "INV-001"
    assert len(fbr_data["Items"]) == 1 # Was "items"
    assert fbr_data["Items"][0]["ItemCode"] == "1" # Was "items"

@patch("requests.post")
def test_post_invoice_success(mock_post, invoice_data):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"InvoiceNumber": "FBR-123456", "Response": "Success"}
    mock_post.return_value = mock_response

    client = FBRClient()
    response = client.post_invoice(invoice_data)
    
    assert response["InvoiceNumber"] == "FBR-123456"
    mock_post.assert_called_once()
