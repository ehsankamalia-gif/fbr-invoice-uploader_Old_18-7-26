import requests
import json
import urllib3
import hmac
import hashlib
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.core.logger import logger
from app.api.schemas import InvoiceCreate
from app.services.settings_service import settings_service

# Suppress only the single InsecureRequestWarning from urllib3 needed for FBR Sandbox
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
        
        # MAPPING FIX: Use correct keys as returned by settings_service.get_active_settings()
        base_url = settings.get("base_url", "")
        auth_token = settings.get("token", "")
        
        if not base_url:
             logger.error("FBR API Base URL is not configured in settings!")
             raise Exception("FBR API URL is missing. Please check FBR Configuration settings.")

        headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }

        # Handle URL construction safely
        if base_url.endswith("/PostData"):
             url = base_url
        else:
             url = f"{base_url.rstrip('/')}/PostData"
        
        if not url.startswith("http"):
             logger.error(f"Invalid FBR API URL: {url}")
             raise Exception(f"Invalid FBR API URL: {url}. Ensure it starts with http:// or https://")
        try:
            # FBR usually expects a specific JSON structure.
            # We map our internal structure to FBR's expected structure here.
            payload = self._transform_to_fbr_format(invoice_data, settings)
            
            # Log the settings used for this transmission as requested by user
            logger.info(f"FBR Sync: Using Business Rules - Name: {settings.get('business_name')}, "
                        f"Tax: {settings.get('tax_rate')}%, PCT: {settings.get('pct_code')}, "
                        f"Type: {settings.get('invoice_type')}, Discount: {settings.get('discount')}%")
            
            # Validate payload before sending
            self._validate_payload(payload)
            
            # Generate and add Signature if secret_key is provided
            secret_key = settings.get("secret_key")
            if secret_key:
                signature = self._generate_signature(payload, secret_key)
                # payload["Signature"] = signature # FBR usually expects it inside the JSON
                # Actually, some versions expect it in the header, some in the body.
                # The standard for Pakistani FBR is in the body.
                # However, looking at _transform_to_fbr_format, it's not there.
                # I'll add it here.
                payload["Signature"] = signature
                logger.info(f"FBR Sync: Payload signed successfully.")
            else:
                logger.warning(f"FBR Sync: No Secret Key configured. Sending unsigned payload.")

            logger.info(f"Sending invoice {invoice_data.get('invoice_number')} to FBR...")
            logger.debug(f"FBR Payload: {json.dumps(payload, default=str)}")
            
            # Determine if SSL verification should be enabled (Enabled for Production, Disabled for Sandbox)
            is_production = settings.get("env", "SANDBOX").upper() == "PRODUCTION"
            
            response = requests.post(
                url, 
                json=payload, 
                headers=headers, 
                timeout=10,
                verify=is_production # FBR uses self-signed certs in SANDBOX but valid certs in PRODUCTION
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

    def _generate_signature(self, payload: dict, secret_key: str) -> str:
        """
        Generates HMAC-SHA256 signature for the payload.
        FBR Pakistan standard: HMAC-SHA256 of the JSON string using the secret key.
        """
        # Ensure we have a consistent JSON string (keys sorted, no extra whitespace)
        # Note: FBR's requirement for JSON normalization might vary, 
        # but sorted keys is a safe standard for deterministic hashing.
        payload_str = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        
        signature = hmac.new(
            secret_key.encode('utf-8'),
            payload_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest().upper()
        
        return signature

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
        # Map Invoice Type string to Integer for FBR
        invoice_type_map = {
            "Standard": 1,
            "Debit Note": 2,
            "Credit Note": 3
        }
        
        # Get default invoice type from settings or fall back to Standard (1)
        setting_invoice_type = settings.get("invoice_type", "Standard")
        default_invoice_type_int = invoice_type_map.get(setting_invoice_type, 1)

        items = []
        for item in data.get("items", []):
            # Prioritize item-level PCT, then settings-level if available
            raw_pct = item.get("pct_code")
            if not raw_pct and settings.get("pct_code"):
                raw_pct = settings.get("pct_code")
                
            pct_code = self._validate_pct_code(raw_pct)
            
            # Use item discount if provided, otherwise default to settings discount
            discount = float(item.get("discount", settings.get("discount", 0.0)))
            
            items.append({
                "ItemCode": str(item.get("item_code")),
                "ItemName": str(item.get("item_name")),
                "Quantity": round(float(item.get("quantity", 0.0)), 2),
                "PCTCode": pct_code,
                "TaxRate": round(float(item.get("tax_rate", 0.0)), 2),
                "SaleValue": round(float(item.get("sale_value", 0.0)), 2),
                "TotalAmount": round(float(item.get("total_amount", 0.0)), 2),
                "TaxCharged": round(float(item.get("tax_charged", 0.0)), 2),
                "Discount": round(discount, 2),
                "FurtherTax": round(float(item.get("further_tax", 0.0)), 2),
                "OtherTax": round(float(item.get("further_tax", 0.0)), 2), # Alias for compatibility
                "InvoiceType": default_invoice_type_int
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
            buyer_cnic = None # FBR allows null for CNIC if NTN is provided

        buyer_ntn = data.get("buyer_ntn")
        if buyer_ntn:
            buyer_ntn = str(buyer_ntn).replace("-", "").strip()
        else:
            buyer_ntn = None # FBR allows null for NTN if CNIC is provided

        # FBR Requirement: At least one of BuyerCNIC or BuyerNTN must be provided.
        # If both are missing, use a generic fallback or log warning.
        if not buyer_cnic and not buyer_ntn:
             logger.warning(f"Both BuyerCNIC and BuyerNTN are missing for invoice {data.get('invoice_number')}")
             # Use a generic fallback CNIC if absolutely necessary, but better to let FBR fail and report it
             # buyer_cnic = "0000000000000" 

        return {
            "InvoiceNumber": data.get("invoice_number", ""),
            "POSID": pos_id,
            "USIN": data.get("invoice_number", ""),
            "DateTime": dt_str,
            "BuyerNTN": buyer_ntn,
            "BuyerCNIC": buyer_cnic,
            "BuyerName": data.get("buyer_name") or "Buyer Name",
            "BuyerPhoneNumber": data.get("buyer_phone") or None,
            "TotalBillAmount": round(float(data.get("total_amount", 0.0)), 2),
            "TotalQuantity": round(float(data.get("total_quantity", 0.0)), 2),
            "TotalSaleValue": round(float(data.get("total_sale_value", 0.0)), 2),
            "TotalTaxCharged": round(float(data.get("total_tax_charged", 0.0)), 2),
            "TotalFurtherTax": round(float(data.get("total_further_tax", 0.0)), 2),
            "TotalOtherTax": round(float(data.get("total_further_tax", 0.0)), 2), # Alias for compatibility
            "PaymentMode": mode_int,
            "InvoiceType": default_invoice_type_int,
            "Items": items
        }

fbr_client = FBRClient()
