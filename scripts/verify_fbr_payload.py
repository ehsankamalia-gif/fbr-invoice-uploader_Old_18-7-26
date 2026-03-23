import json
from unittest.mock import patch, MagicMock
from datetime import datetime
from app.api.fbr_client import fbr_client
from app.services.settings_service import settings_service
from app.api.schemas import InvoiceCreate, InvoiceItemCreate
from app.services.invoice_service import invoice_service
from app.db.session import SessionLocal
from app.db.models import FBRConfiguration, Price, ProductModel

def verify_payload_structure():
    print("--- FBR Payload Verification Starting ---")
    
    # Mock data
    item_in = InvoiceItemCreate(
        item_code="MOTO-001",
        item_name="Honda CD70",
        quantity=1,
        tax_rate=18.0,
        sale_value=100000.0,
        tax_charged=18000.0,
        further_tax=3000.0, # This is the "Additional Tax" we are looking for
        pct_code="87112010",
        model_name="CD70",
        color="RED"
    )
    
    invoice_data = {
        "invoice_number": "TEST-INV-001",
        "datetime": datetime.now(),
        "buyer_name": "Test Buyer",
        "buyer_cnic": "33303-1234567-1",
        "payment_mode": "Cash",
        "total_sale_value": 100000.0,
        "total_tax_charged": 18000.0,
        "total_further_tax": 3000.0,
        "total_quantity": 1,
        "total_amount": 121000.0,
        "items": [
            {
                "item_code": item_in.item_code,
                "item_name": item_in.item_name,
                "quantity": item_in.quantity,
                "tax_rate": item_in.tax_rate,
                "sale_value": item_in.sale_value,
                "tax_charged": item_in.tax_charged,
                "further_tax": item_in.further_tax,
                "total_amount": 121000.0,
                "pct_code": item_in.pct_code,
                "discount": 0.0
            }
        ]
    }

    # Mock settings
    mock_settings = {
        "env": "SANDBOX",
        "base_url": "https://esp.fbr.gov.pk:8243/PT/v1",
        "pos_id": "123456",
        "usin": "TEST",
        "token": "MOCK_TOKEN",
        "secret_key": "MOCK_SECRET_KEY",
        "tax_rate": "18.0",
        "pct_code": "8711.2010",
        "invoice_type": "Standard",
        "discount": "0.0",
        "item_code": "MOTO",
        "item_name": "Motorcycle",
        "business_name": "Ehsan Trader"
    }

    with patch.object(settings_service, 'get_active_settings', return_value=mock_settings):
        # We want to intercept the payload before it's sent
        # The payload is generated inside post_invoice calling _transform_to_fbr_format
        
        # 1. Directly test transformation
        payload = fbr_client._transform_to_fbr_format(invoice_data, mock_settings)
        
        print("\n[STEP 1] Inspecting Transformed Payload (FBR Schema):")
        print(f"Root level 'TotalFurtherTax': {payload.get('TotalFurtherTax')}")
        print(f"Root level 'TotalAdditionalTax': {payload.get('TotalAdditionalTax')}")
        print(f"Root level 'TotalOtherTax': {payload.get('TotalOtherTax')}")
        
        item = payload.get('Items')[0]
        print(f"\nItem level 'FurtherTax': {item.get('FurtherTax')}")
        print(f"Item level 'AdditionalTax': {item.get('AdditionalTax')}")
        print(f"Item level 'OtherTax': {item.get('OtherTax')}")

        # 2. Check Signature generation
        signature = fbr_client._generate_signature(payload, mock_settings["secret_key"])
        print(f"\n[STEP 2] Signature generated: {signature}")

        # Assertions for verification report
        assert payload.get('TotalFurtherTax') == 3000.0, "TotalFurtherTax missing or incorrect"
        assert payload.get('TotalAdditionalTax') == 3000.0, "TotalAdditionalTax missing or incorrect"
        assert payload.get('TotalOtherTax') == 3000.0, "TotalOtherTax missing or incorrect"
        assert item.get('FurtherTax') == 3000.0, "FurtherTax missing or incorrect"
        assert item.get('AdditionalTax') == 3000.0, "AdditionalTax missing or incorrect"
        assert item.get('OtherTax') == 3000.0, "OtherTax missing or incorrect"
        
        print("\n--- Verification Result: SUCCESS ---")
        print("Evidence: All mandatory additional tax fields are present in the payload.")

if __name__ == "__main__":
    verify_payload_structure()
