import requests
import json
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.core.logger import logger
from app.api.schemas import InvoiceCreate
from app.services.settings_service import settings_service

class FBRClient:
    def __init__(self):
        pass

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(requests.RequestException)
    )
    def post_invoice(self, invoice_data: dict):
        """
        Sends invoice data to FBR.
        """
        # Get latest settings dynamically
        settings = settings_service.get_active_settings()
        base_url = settings.get("api_base_url", "")
        auth_token = settings.get("auth_token", "")
        
        headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }

        # Handle URL construction safely
        if base_url.endswith("/PostData"):
             url = base_url
        else:
             url = f"{base_url.rstrip('/')}/PostData"
        
        try:
            # FBR usually expects a specific JSON structure.
            # We map our internal structure to FBR's expected structure here.
            payload = self._transform_to_fbr_format(invoice_data, settings)
            
            # Validate payload before sending
            self._validate_payload(payload)
            
            logger.info(f"Sending invoice {invoice_data.get('invoiceNumber')} to FBR...")
            logger.debug(f"FBR Payload: {json.dumps(payload, default=str)}")
            
            # In a real scenario, we would make the request.
            # For now, if base_url is a placeholder or localhost, it might fail if not running.
            # I'll implement the actual request but catch errors.
            
            response = requests.post(
                url, 
                json=payload, 
                headers=headers, 
                timeout=10,
                verify=False # FBR often uses self-signed certs in test envs, but in prod should be True
            )
            
            response.raise_for_status()
            return response.json()
            
        except requests.RequestException as e:
            logger.error(f"FBR API connection failed: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                 logger.error(f"FBR Error Response: {e.response.text}")
                 # Raise a custom error with the response text so UI can show it
                 raise Exception(f"FBR Error: {e.response.status_code} - {e.response.text}")
            raise e

    def _validate_payload(self, payload: dict):
        """
        Validates the generated payload against FBR specifications.
        Raises ValueError if validation fails.
        """
        required_fields = ["POSID", "USIN", "DateTime", "Items", "TotalBillAmount", "PaymentMode", "InvoiceType"]
        for field in required_fields:
            if field not in payload:
                raise ValueError(f"Missing required field in FBR payload: {field}")
            if payload[field] is None:
                raise ValueError(f"Field {field} cannot be None")

        if not isinstance(payload["POSID"], int):
            raise ValueError(f"POSID must be an integer, got {type(payload['POSID'])}")

        if not payload["Items"]:
            raise ValueError("Invoice must have at least one item")

        if payload["TotalBillAmount"] <= 0:
            raise ValueError(f"TotalBillAmount must be positive, got {payload['TotalBillAmount']}")
        
        if payload["PaymentMode"] not in [1, 2, 3, 4, 5]:
             raise ValueError(f"Invalid PaymentMode: {payload['PaymentMode']}. Must be 1-5.")

        # Validate items
        for i, item in enumerate(payload["Items"]):
            if not item.get("ItemCode"):
                 raise ValueError(f"Item {i} missing ItemCode")
            if not item.get("ItemName"):
                 raise ValueError(f"Item {i} missing ItemName")
            if item.get("Quantity", 0) <= 0:
                 raise ValueError(f"Item {i} Quantity must be positive")
            if not item.get("PCTCode") or len(item.get("PCTCode")) != 8:
                 raise ValueError(f"Item {i} Invalid PCTCode: {item.get('PCTCode')}")
            if item.get("TaxRate") is None:
                 raise ValueError(f"Item {i} missing TaxRate")

    def _validate_pct_code(self, pct_code: str) -> str:
        """
        Validates and formats PCT Code.
        FBR requires strictly 8 digits without dashes.
        """
        if not pct_code:
            return "11001010" # Default General Goods

        # Remove dashes, spaces, and dots (e.g., 8711.2010 -> 87112010)
        clean_code = str(pct_code).replace("-", "").replace(" ", "").replace(".", "").strip()

        # Check if it's numeric and 8 digits
        if not clean_code.isdigit():
             logger.warning(f"Invalid PCT Code format (non-numeric): {pct_code}. Using default.")
             return "11001010"
        
        if len(clean_code) != 8:
             logger.warning(f"Invalid PCT Code length: {pct_code} ({len(clean_code)} digits). Expected 8. Using default.")
             return "11001010"

        return clean_code

    def _transform_to_fbr_format(self, data: dict, settings: dict) -> dict:
        """
        Transforms internal invoice data to FBR compliant JSON.
        """
        items = []
        for item in data.get("items", []):
            # Prioritize item-level PCT, then settings-level if available
            raw_pct = item.get("pct_code")
            if not raw_pct and settings.get("pct_code"):
                raw_pct = settings.get("pct_code")
                
            pct_code = self._validate_pct_code(raw_pct)
            
            items.append({
                "ItemCode": item.get("item_code"),
                "ItemName": item.get("item_name"),
                "Quantity": item.get("quantity"),
                "PCTCode": pct_code,
                "TaxRate": item.get("tax_rate"),
                "SaleValue": item.get("sale_value"),
                "TotalAmount": item.get("total_amount"),
                "TaxCharged": item.get("tax_charged"),
                "Discount": item.get("discount", 0.0),
                "FurtherTax": item.get("further_tax", 0.0),
                "InvoiceType": 1,
                "RefUSIN": None
            })

        # Map Payment Mode string to Integer
        payment_mode_map = {
            "Cash": 1,
            "Card": 2,
            "Cheque": 3,
            "Pay Order": 4,
            "Online": 5
        }
        
        mode_str = data.get("payment_mode", "1")
        # Handle if it is already int or string digit
        if isinstance(mode_str, int):
            mode_int = mode_str
        elif isinstance(mode_str, str) and mode_str.isdigit():
             mode_int = int(mode_str)
        else:
             mode_int = payment_mode_map.get(mode_str, 1) # Default to 1

        # Format DateTime as YYYY-MM-DD HH:MM:SS
        dt_str = None
        if data.get("datetime"):
            dt_str = data.get("datetime").strftime("%Y-%m-%d %H:%M:%S")

        # Handle POSID casting if numeric
        pos_id = settings.get("pos_id", "")
        try:
             pos_id = int(pos_id)
        except (ValueError, TypeError):
             pass

        # Format CNIC (Strip dashes for FBR compliance)
        buyer_cnic = data.get("buyer_cnic")
        if buyer_cnic:
            buyer_cnic = str(buyer_cnic).replace("-", "").strip()
        else:
            buyer_cnic = "1234512345678" # Sample fallback (13 digits)

        return {
            "InvoiceNumber": data.get("invoice_number", ""),
            "POSID": pos_id,
            "USIN": data.get("invoice_number", ""),
            "DateTime": dt_str,
            "BuyerNTN": data.get("buyer_ntn") or "1234567-8",
            "BuyerCNIC": buyer_cnic,
            "BuyerName": data.get("buyer_name") or "Buyer Name",
            "BuyerPhoneNumber": data.get("buyer_phone") or "0000-0000000",
            "TotalBillAmount": data.get("total_amount"),
            "TotalQuantity": data.get("total_quantity"),
            "TotalSaleValue": data.get("total_sale_value"),
            "TotalTaxCharged": data.get("total_tax_charged"),
            "TotalFurtherTax": data.get("total_further_tax", 0.0),
            "PaymentMode": mode_int,
            "InvoiceType": 1,
            "Items": items
        }

fbr_client = FBRClient()
