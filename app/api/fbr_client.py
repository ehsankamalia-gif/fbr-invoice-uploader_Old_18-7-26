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
                timeout=(10, 60),
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
        
        if payload["PaymentMode"] not in [1, 2, 3, 4, 5, 6]:
             raise ValueError(f"Invalid PaymentMode: {payload['PaymentMode']}. Must be 1-6.")

        # Validate Buyer NTN length (max 9 chars with hyphen, e.g. 1234567-8)
        if payload.get("BuyerNTN"):
            if len(payload["BuyerNTN"]) > 9:
                raise ValueError(f"BuyerNTN exceeds 9 character limit: {payload['BuyerNTN']}")

        # Validate Buyer CNIC length (max 13 digits, stripped of hyphens)
        if payload.get("BuyerCNIC"):
            if len(payload["BuyerCNIC"]) > 13:
                raise ValueError(f"BuyerCNIC exceeds 13 character limit: {payload['BuyerCNIC']}")

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
            if item.get("InvoiceType") not in [1, 2, 3, 11, 12]:
                 raise ValueError(f"Item {i} Invalid InvoiceType: {item.get('InvoiceType')}. Must be 1,2,3,11,12.")

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
        # FBR Spec: 1=New, 2=Debit, 3=Credit, 11=3rd Schedule New, 12=3rd Schedule Credit
        invoice_type_map = {
            "Standard": 1,
            "New": 1,
            "Debit Note": 2,
            "Debit": 2,
            "Credit Note": 3,
            "Credit": 3,
            "3rd Schedule New": 11,
            "3rd Schedule Credit": 12,
        }
        
        # Get default invoice type from settings or fall back to Standard/New (1)
        setting_invoice_type = settings.get("invoice_type", "Standard")
        default_invoice_type_int = invoice_type_map.get(setting_invoice_type, 1)

        total_header_discount = 0.0
        total_further = 0.0
        total_additional = 0.0
        total_other = 0.0
        items = []
        for item in data.get("items", []):
            raw_pct = item.get("pct_code")
            if not raw_pct and settings.get("pct_code"):
                raw_pct = settings.get("pct_code")
                
            pct_code = self._validate_pct_code(raw_pct)
            
            discount = float(item.get("discount", settings.get("discount", 0.0)))
            total_header_discount += discount

            item_invoice_type_str = item.get("invoice_type") or setting_invoice_type
            item_invoice_type_int = invoice_type_map.get(item_invoice_type_str, default_invoice_type_int)

            item_ref_usin = item.get("ref_usin") or None

            ft = round(float(item.get("further_tax", 0.0)), 2)
            total_further += ft

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
                "FurtherTax": ft,
                "FurtherTaxCharged": ft,
                "FurtherTaxAmount": ft,
                "AdditionalTax": ft,
                "AdditionalTaxCharged": ft,
                "OtherTax": ft,
                "InvoiceType": item_invoice_type_int,
                "RefUSIN": item_ref_usin,
            })

        # Map Payment Mode string to Integer - MATCHES FBR OFFICIAL TABLE 1
        # 1. Cash, 2. Card, 3. Gift Voucher, 4. Loyalty Card, 5. Mixed, 6. Cheque
        payment_mode_map = {
            "Cash": 1,
            "Card": 2,
            "Gift Voucher": 3,
            "Loyalty Card": 4,
            "Mixed": 5,
            "Cheque": 6,
            # Common aliases used in existing code (backward compat):
            "Pay Order": 6,  # Map Pay Order to Cheque (6) as closest match
            "Online": 5,     # Map Online to Mixed (5) as closest match since not in FBR list
        }
        
        mode_str = data.get("payment_mode", "1")
        # Handle if it is already int or string digit
        if isinstance(mode_str, int):
            mode_int = mode_str
        elif isinstance(mode_str, str) and mode_str.isdigit():
             mode_int = int(mode_str)
        else:
             mode_int = payment_mode_map.get(mode_str, 1) # Default to 1 (Cash)

        # Format DateTime as YYYY-MM-DD HH:MM:SS
        # Use Asia/Karachi timezone if available; if naive datetime provided, assume it's already PKT
        dt_str = None
        dt_obj = data.get("datetime")
        if dt_obj:
            try:
                import datetime as dt_mod
                try:
                    from zoneinfo import ZoneInfo
                    PKT = ZoneInfo("Asia/Karachi")
                except Exception:
                    PKT = dt_mod.timezone(dt_mod.timedelta(hours=5))

                if dt_obj.tzinfo is None:
                    # Naive datetime: treat as already in PKT
                    dt_str = dt_obj.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    # Aware datetime: convert to PKT
                    dt_pkt = dt_obj.astimezone(PKT)
                    dt_str = dt_pkt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                # Fallback to naive stringification
                dt_str = dt_obj.strftime("%Y-%m-%d %H:%M:%S")

        # Handle POSID casting if numeric
        pos_id = settings.get("pos_id", "")
        try:
             pos_id = int(pos_id)
        except (ValueError, TypeError):
             pass

        # USIN = Unique Sales Invoice Number, must be unique per invoice.
        # Use the actual internal invoice_number (prefix+sequence) instead of just the settings prefix.
        # Fall back to settings prefix only if invoice_number is missing.
        usin_value = data.get("invoice_number") or settings.get("usin", "") or ""

        # Format CNIC (Strip dashes for FBR compliance, max 13 digits)
        buyer_cnic = data.get("buyer_cnic")
        if buyer_cnic:
            buyer_cnic = str(buyer_cnic).replace("-", "").strip()
            if len(buyer_cnic) > 13:
                buyer_cnic = buyer_cnic[:13]
        else:
            buyer_cnic = None # FBR allows null for CNIC if NTN is provided

        buyer_ntn = data.get("buyer_ntn")
        if buyer_ntn:
            buyer_ntn = str(buyer_ntn).strip()
            # Keep hyphen for NTN (e.g. 1234567-8 is 9 chars with hyphen)
            if len(buyer_ntn) > 9:
                buyer_ntn = buyer_ntn[:9]
        else:
            buyer_ntn = None # FBR allows null for NTN if CNIC is provided

        # FBR Requirement: At least one of BuyerCNIC or BuyerNTN must be provided.
        # If both are missing, use a generic fallback or log warning.
        if not buyer_cnic and not buyer_ntn:
             logger.warning(f"Both BuyerCNIC and BuyerNTN are missing for invoice {data.get('invoice_number')}")

        # Optional Header-level RefUSIN (for Debit/Credit Note referencing original invoice USIN)
        ref_usin_header = data.get("ref_usin") or None

        total_further_rounded = round(float(data.get("total_further_tax", 0.0)), 2)
        # TotalAdditionalTax = TotalFurtherTax (for unregistered buyer "Further Tax" == "Additional Tax" on FBR side)
        total_additional_rounded = total_further_rounded
        total_other_rounded = total_further_rounded

        # TotalBillAmount: SaleValue + TaxCharged + FurtherTax - Discount
        total_sale = round(float(data.get("total_sale_value", 0.0)), 2)
        total_tax = round(float(data.get("total_tax_charged", 0.0)), 2)
        total_discount = round(float(total_header_discount), 2)
        computed_total = round(total_sale + total_tax + total_further_rounded - total_discount, 2)
        stored_total = round(float(data.get("total_amount", 0.0)), 2)
        if stored_total > 0 and abs(computed_total - stored_total) > 0.01:
            final_total = stored_total
        else:
            final_total = computed_total

        return {
            "InvoiceNumber": data.get("invoice_number", ""),
            "POSID": pos_id,
            "USIN": usin_value,
            "RefUSIN": ref_usin_header,
            "DateTime": dt_str,
            "BuyerNTN": buyer_ntn,
            "BuyerCNIC": buyer_cnic,
            "BuyerName": data.get("buyer_name") or "Buyer Name",
            "BuyerPhoneNumber": data.get("buyer_phone") or None,
            "TotalSaleValue": total_sale,
            "TotalTaxCharged": total_tax,
            "TotalFurtherTax": total_further_rounded,
            "TotalFurtherTaxCharged": total_further_rounded,
            "TotalFurtherTaxAmount": total_further_rounded,
            "TotalAdditionalTax": total_additional_rounded,
            "TotalAdditionalTaxCharged": total_additional_rounded,
            "TotalOtherTax": total_other_rounded,
            "TotalQuantity": round(float(data.get("total_quantity", 0.0)), 2),
            "Discount": total_discount,
            "FurtherTax": total_further_rounded,
            "FurtherTaxCharged": total_further_rounded,
            "FurtherTaxAmount": total_further_rounded,
            "AdditionalTax": total_additional_rounded,
            "AdditionalTaxCharged": total_additional_rounded,
            "OtherTax": total_other_rounded,
            "TotalBillAmount": final_total,
            "PaymentMode": mode_int,
            "InvoiceType": default_invoice_type_int,
            "Items": items
        }

fbr_client = FBRClient()
