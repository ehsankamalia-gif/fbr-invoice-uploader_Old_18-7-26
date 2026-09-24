"""FBR submission for invoices created in the customer portal.

This is a deliberate, self-contained port of the desktop app's
app/api/fbr_client.py - NOT an import of it. The two apps are kept fully
independent (the desktop app must never be touched or affected by portal
work), but the wire format sent to FBR must stay byte-for-byte identical
between them, since FBR's gateway has repeatedly rejected payloads that
don't exactly match its documented schema (see the desktop app's own
history of "Bulk data upload functionality is no more available" / Code 112
failures). Keep this file in sync with app/api/fbr_client.py's
_transform_to_fbr_format/_validate_payload/_validate_pct_code by hand if
that file ever changes - do not "simplify" or diverge the payload shape.

Per explicit standing instruction, this only ever uses the older
POS-integration scheme (POSID/USIN/PascalCase fields) - never FBR's newer
Digital Invoicing ("di_data") scheme.
"""
import hashlib
import hmac
import json
import logging

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .models import FBRConfiguration

logger = logging.getLogger(__name__)


def get_active_fbr_settings() -> dict:
    """Read the FBR environment currently marked active by the desktop
    app's Settings screen. Read-only - the portal never writes this table."""
    config = FBRConfiguration.objects.filter(is_active=True).first()
    if not config:
        config = FBRConfiguration.objects.filter(environment='SANDBOX').first()
    if not config:
        raise RuntimeError('No FBR configuration found. Configure it from the desktop app first.')

    return {
        'env': config.environment,
        'base_url': config.api_base_url,
        'pos_id': config.pos_id,
        'usin': config.usin,
        'token': config.auth_token,
        'secret_key': config.secret_key,
        'tax_rate': str(config.tax_rate),
        'pct_code': config.pct_code,
        'invoice_type': config.invoice_type,
        'discount': str(config.discount),
        'item_code': config.item_code,
        'item_name': config.item_name,
        'business_name': config.business_name or 'Ehsan Trader',
    }


class FBRClient:
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(requests.RequestException),
    )
    def post_invoice(self, invoice_data: dict, settings: dict):
        base_url = (settings.get('base_url') or '').strip()
        auth_token = settings.get('token', '')

        if not base_url:
            logger.error('FBR API Base URL is not configured!')
            raise Exception('FBR API URL is missing. Please check the FBR Configuration in the desktop app.')

        headers = {
            'Authorization': f'Bearer {auth_token}',
            'Content-Type': 'application/json',
        }

        # The configured base_url is the complete endpoint to POST to -
        # no "/PostData" suffix is assumed or appended (matches the
        # desktop app's fbr_client.py post_invoice).
        url = base_url.rstrip('/')
        if not url.startswith('http'):
            raise Exception(f'Invalid FBR API URL: {url}. Must start with http:// or https://')

        payload = self._transform_to_fbr_format(invoice_data, settings)
        self._validate_payload(payload)

        secret_key = settings.get('secret_key')
        if secret_key:
            payload['Signature'] = self._generate_signature(payload, secret_key)

        logger.info(f"Sending invoice {invoice_data.get('invoice_number')} to FBR...")
        logger.debug(f'FBR Payload: {json.dumps(payload, default=str)}')

        is_production = (settings.get('env', 'SANDBOX') or '').upper() == 'PRODUCTION'

        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=(10, 60),
                verify=is_production,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f'FBR API connection failed: {e}')
            if getattr(e, 'response', None) is not None:
                logger.error(f'FBR Error Response: {e.response.text}')
                raise Exception(f'FBR Error: {e.response.status_code} - {e.response.text}')
            raise

    def _generate_signature(self, payload: dict, secret_key: str) -> str:
        payload_str = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        return hmac.new(secret_key.encode('utf-8'), payload_str.encode('utf-8'), hashlib.sha256).hexdigest().upper()

    def _validate_payload(self, payload: dict):
        required_fields = ['POSID', 'USIN', 'DateTime', 'Items', 'TotalBillAmount', 'PaymentMode', 'InvoiceType']
        for field in required_fields:
            if field not in payload:
                raise ValueError(f'Missing required field in FBR payload: {field}')
            if payload[field] is None:
                raise ValueError(f'Field {field} cannot be None')

        if not isinstance(payload['POSID'], int):
            raise ValueError(f"POSID must be an integer, got {type(payload['POSID'])}")
        if not payload['Items']:
            raise ValueError('Invoice must have at least one item')
        if payload['TotalBillAmount'] <= 0:
            raise ValueError(f"TotalBillAmount must be positive, got {payload['TotalBillAmount']}")
        if payload['PaymentMode'] not in [1, 2, 3, 4, 5, 6]:
            raise ValueError(f"Invalid PaymentMode: {payload['PaymentMode']}. Must be 1-6.")

        if payload.get('BuyerNTN') and len(payload['BuyerNTN']) > 9:
            raise ValueError(f"BuyerNTN exceeds 9 character limit: {payload['BuyerNTN']}")
        if payload.get('BuyerCNIC') and len(payload['BuyerCNIC']) > 13:
            raise ValueError(f"BuyerCNIC exceeds 13 character limit: {payload['BuyerCNIC']}")

        for i, item in enumerate(payload['Items']):
            if not item.get('ItemCode'):
                raise ValueError(f'Item {i} missing ItemCode')
            if not item.get('ItemName'):
                raise ValueError(f'Item {i} missing ItemName')
            if item.get('Quantity', 0) <= 0:
                raise ValueError(f'Item {i} Quantity must be positive')
            if not item.get('PCTCode') or len(item.get('PCTCode')) != 8:
                raise ValueError(f"Item {i} Invalid PCTCode: {item.get('PCTCode')}")
            if item.get('TaxRate') is None:
                raise ValueError(f'Item {i} missing TaxRate')
            if item.get('InvoiceType') not in [1, 2, 3, 11, 12]:
                raise ValueError(f"Item {i} Invalid InvoiceType: {item.get('InvoiceType')}. Must be 1,2,3,11,12.")

    def _validate_pct_code(self, pct_code: str) -> str:
        if not pct_code:
            return '11001010'
        clean_code = str(pct_code).replace('-', '').replace(' ', '').replace('.', '').strip()
        if not clean_code.isdigit() or len(clean_code) != 8:
            logger.warning(f'Invalid PCT Code: {pct_code!r}. Using default.')
            return '11001010'
        return clean_code

    def _transform_to_fbr_format(self, data: dict, settings: dict) -> dict:
        invoice_type_map = {
            'Standard': 1, 'New': 1,
            'Debit Note': 2, 'Debit': 2,
            'Credit Note': 3, 'Credit': 3,
            '3rd Schedule New': 11,
            '3rd Schedule Credit': 12,
        }
        setting_invoice_type = settings.get('invoice_type', 'Standard')
        default_invoice_type_int = invoice_type_map.get(setting_invoice_type, 1)

        total_header_discount = 0.0
        items = []
        for item in data.get('items', []):
            raw_pct = item.get('pct_code') or settings.get('pct_code')
            pct_code = self._validate_pct_code(raw_pct)

            discount = float(item.get('discount', settings.get('discount', 0.0)) or 0.0)
            total_header_discount += discount

            item_invoice_type_str = item.get('invoice_type') or setting_invoice_type
            item_invoice_type_int = invoice_type_map.get(item_invoice_type_str, default_invoice_type_int)

            items.append({
                'ItemCode': str(item.get('item_code')),
                'ItemName': str(item.get('item_name')),
                'Quantity': round(float(item.get('quantity', 0.0)), 2),
                'PCTCode': pct_code,
                'TaxRate': round(float(item.get('tax_rate', 0.0)), 2),
                'SaleValue': round(float(item.get('sale_value', 0.0)), 2),
                'TotalAmount': round(float(item.get('total_amount', 0.0)), 2),
                'TaxCharged': round(float(item.get('tax_charged', 0.0)), 2),
                'Discount': round(discount, 2),
                # Per FBR's official schema there is exactly one further-tax
                # field ("FurtherTax") - kept at 0 per standing instruction
                # not to report a further/additional tax amount (matches
                # the desktop app's fbr_client.py).
                'FurtherTax': 0.0,
                'InvoiceType': item_invoice_type_int,
                'RefUSIN': item.get('ref_usin') or None,
            })

        payment_mode_map = {
            'Cash': 1, 'Card': 2, 'Gift Voucher': 3, 'Loyalty Card': 4,
            'Mixed': 5, 'Cheque': 6, 'Pay Order': 6, 'Online': 5,
        }
        mode_val = data.get('payment_mode', '1')
        if isinstance(mode_val, int):
            mode_int = mode_val
        elif isinstance(mode_val, str) and mode_val.isdigit():
            mode_int = int(mode_val)
        else:
            mode_int = payment_mode_map.get(mode_val, 1)

        dt_obj = data.get('datetime')
        dt_str = dt_obj.strftime('%Y-%m-%d %H:%M:%S') if dt_obj else None

        pos_id = settings.get('pos_id', '')
        try:
            pos_id = int(pos_id)
        except (ValueError, TypeError):
            pass

        usin_value = data.get('invoice_number') or settings.get('usin', '') or ''

        buyer_cnic = data.get('buyer_cnic')
        if buyer_cnic:
            buyer_cnic = str(buyer_cnic).replace('-', '').strip()[:13]
        else:
            buyer_cnic = None

        buyer_ntn = data.get('buyer_ntn')
        if buyer_ntn:
            buyer_ntn = str(buyer_ntn).strip()[:9]
        else:
            buyer_ntn = None

        actual_further_tax = round(float(data.get('total_further_tax', 0.0) or 0.0), 2)
        total_sale = round(float(data.get('total_sale_value', 0.0)), 2)
        total_tax = round(float(data.get('total_tax_charged', 0.0)), 2)
        total_discount = round(float(total_header_discount), 2)
        computed_total = round(total_sale + total_tax + actual_further_tax - total_discount, 2)
        stored_total = round(float(data.get('total_amount', 0.0)), 2)
        final_total = stored_total if (stored_total > 0 and abs(computed_total - stored_total) > 0.01) else computed_total

        return {
            # Per FBR's official spec, InvoiceNumber's status is "Blank" -
            # FBR fills it in with the assigned fiscal invoice number in its
            # response. USIN (below) is our own reference number.
            'InvoiceNumber': '',
            'POSID': pos_id,
            'USIN': usin_value,
            'RefUSIN': data.get('ref_usin') or None,
            'DateTime': dt_str,
            'BuyerNTN': buyer_ntn,
            'BuyerCNIC': buyer_cnic,
            'BuyerName': data.get('buyer_name') or 'Buyer Name',
            'BuyerPhoneNumber': data.get('buyer_phone') or None,
            'TotalSaleValue': total_sale,
            'TotalTaxCharged': total_tax,
            'TotalQuantity': round(float(data.get('total_quantity', 0.0)), 2),
            'Discount': total_discount,
            'FurtherTax': 0.0,
            'TotalBillAmount': final_total,
            'PaymentMode': mode_int,
            'InvoiceType': default_invoice_type_int,
            'Items': items,
        }


fbr_client = FBRClient()
