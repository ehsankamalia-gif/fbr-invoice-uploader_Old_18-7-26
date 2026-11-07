"""Builds an FBR-submission-style payload for a Spare Parts sale.

The field NAMES and overall shape (POSID, USIN, Items[].ItemCode, the
Table-1 PaymentMode codes, the HMAC-SHA256 signing scheme) mirror the
wire format app/api/fbr_client.py builds for the main Invoice module's
FBR POS-Integration upload, purely so the output is recognizable to
anyone already familiar with that format. Everything else is a
SEPARATE, INDEPENDENT implementation:

- Reads nothing from app.api.fbr_client, app.services.invoice_service,
  or any app.db.models table (Invoice, InvoiceItem, Company,
  FBRConfiguration). Only this module's own SpSale / SpSaleItem /
  SpCustomer / SpFbrEnvironment records are used.
- Uses the FBR configuration saved on THIS module's own Settings page
  (spare_parts.services.settings_service.get_fbr_environment - POS ID,
  USIN, Auth Token, Secret Key) - never the main app's
  FBRConfiguration or FBR_* .env values.
- Builds a payload dict ONLY. Nothing here makes an HTTP call or
  submits anything to FBR - see spare_parts/__init__.py: this module
  has no FBR integration. Wiring an actual submission is a separate,
  future decision this does not make.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from spare_parts.db.models import SpSale
from spare_parts.errors import SparePartsValidationError
from spare_parts.services import settings_service
from spare_parts.logging_config import get_logger

logger = get_logger(__name__)

_CENTS = Decimal("0.01")

# FBR's official Table 1 payment-mode codes. Spare Parts' own
# payment_method vocabulary ("Cash"/"Card"/"Bank Transfer"/"Credit", see
# spare_parts/ui/sale_card_widget.py) doesn't match the main app's, so
# this is its own independent mapping, not a copy of fbr_client.py's.
_PAYMENT_MODE_MAP = {
    "CASH": 1,
    "CARD": 2,
    "GIFT VOUCHER": 3,
    "LOYALTY CARD": 4,
    "BANK TRANSFER": 5,   # No exact FBR code for this - "Mixed" is the closest fit.
    "CREDIT": 5,          # Amount still due, not a tender type - also mapped to "Mixed".
    "CHEQUE": 6,
}
_DEFAULT_PAYMENT_MODE = 1  # Cash

# A completed, POSTED sale is always FBR InvoiceType 1 ("New"/Standard).
# Sale returns (which would be type 3, "Credit Note") aren't covered by
# this function - see build_sale_payload's docstring.
_INVOICE_TYPE_NEW = 1

# SpPart has no per-part PCT/HS code field (see spare_parts/db/models.py),
# so every line uses one default code - the same fallback value
# app/api/fbr_client.py's own _validate_pct_code() substitutes when a
# line has none, chosen here for familiarity only (not imported from
# there). Revisit if this module later tracks real per-part PCT codes.
DEFAULT_PCT_CODE = "11001010"

_VALID_PAYMENT_MODES = (1, 2, 3, 4, 5, 6)
_VALID_INVOICE_TYPES = (1, 2, 3, 11, 12)


def _round2(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(_CENTS, rounding=ROUND_HALF_UP)


def _payment_mode_code(payment_method: str) -> int:
    return _PAYMENT_MODE_MAP.get((payment_method or "").strip().upper(), _DEFAULT_PAYMENT_MODE)


def _format_datetime(value: dt.datetime) -> str:
    """"YYYY-MM-DD HH:MM:SS" - independently reimplemented in the same
    format app/api/fbr_client.py uses, not imported from it."""
    return (value or dt.datetime.utcnow()).strftime("%Y-%m-%d %H:%M:%S")


def _split_buyer_identity(cnic_ntn: str) -> tuple[str | None, str | None]:
    """SpCustomer stores one combined CNIC/NTN field (see
    spare_parts/db/models.py SpCustomer.cnic_ntn) rather than separate
    columns. An NTN is at most 9 digits; a CNIC is 13. Treat an all-digit
    value of NTN length as an NTN, anything longer (truncated to 13) as
    a CNIC - mirrors the length rules app/api/fbr_client.py applies to
    BuyerNTN/BuyerCNIC, independently reimplemented."""
    digits = "".join(ch for ch in (cnic_ntn or "") if ch.isdigit())
    if not digits:
        return None, None
    if len(digits) <= 9:
        return digits, None
    return None, digits[:13]


def _sign_payload(payload: dict, secret_key: str) -> str:
    """HMAC-SHA256 over the sorted-keys, compact JSON form of the
    payload, hex-uppercase - the same algorithm app/api/fbr_client.py
    uses, independently reimplemented (not imported from it). Called
    BEFORE the "Signature" key itself is added, so the signature never
    signs itself."""
    payload_str = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hmac.new(secret_key.encode("utf-8"), payload_str.encode("utf-8"), hashlib.sha256).hexdigest().upper()


def build_sale_payload(db: Session, sale: SpSale) -> dict:
    """Builds an FBR-submission-style payload dict for one POSTED
    spare-parts sale. Pure data transformation - does not send anything
    anywhere, and nothing calls this automatically; it must be invoked
    explicitly (e.g. from a future UI action) when a payload is wanted.

    Raises SparePartsValidationError if the sale isn't POSTED (a
    CANCELLED sale has nothing to submit)."""
    if sale.status != "POSTED":
        raise SparePartsValidationError(
            f"Only a POSTED sale can have an FBR payload built (sale {sale.sale_no} is {sale.status})."
        )

    settings = settings_service.get_settings(db)
    env_settings = settings_service.get_fbr_environment(db, settings.fbr_environment)

    pos_id_raw = (env_settings.pos_id or "").strip()
    pos_id: int | str = int(pos_id_raw) if pos_id_raw.isdigit() else pos_id_raw

    usin = sale.sale_no or (env_settings.usin or "")

    customer = sale.customer
    buyer_ntn, buyer_cnic = _split_buyer_identity(customer.cnic_ntn if customer else "")

    subtotal = Decimal(str(sale.subtotal or 0))
    tax_amount = _round2(sale.tax_amount)
    discount = _round2(sale.discount)
    tax_percent = Decimal(str(sale.tax_percent or 0))

    items = []
    total_quantity = Decimal("0")
    for item in sale.items:
        line_value = _round2(item.line_total)
        # Header tax is one amount for the whole sale (SpSale.tax_amount)
        # - this module doesn't track tax per line - so it's apportioned
        # here by each line's share of the subtotal, giving the Items[]
        # array a sensible TaxCharged per row without inventing a
        # per-part tax rate this module has no data for.
        item_tax = (
            _round2(line_value / subtotal * tax_amount) if subtotal > 0 else Decimal("0.00")
        )
        part = item.part
        items.append({
            "ItemCode": part.part_no if part else str(item.part_id),
            "ItemName": part.name if part else "",
            "Quantity": float(item.qty or 0),
            "PCTCode": DEFAULT_PCT_CODE,
            "TaxRate": float(tax_percent),
            "SaleValue": float(line_value),
            "TotalAmount": float(line_value + item_tax),
            "TaxCharged": float(item_tax),
            "Discount": float(_round2(item.discount)),
            "FurtherTax": 0.0,
            "InvoiceType": _INVOICE_TYPE_NEW,
            "RefUSIN": None,
        })
        total_quantity += Decimal(str(item.qty or 0))

    payload = {
        "InvoiceNumber": "",
        "POSID": pos_id,
        "USIN": usin,
        "RefUSIN": None,
        "DateTime": _format_datetime(sale.sale_date),
        "BuyerNTN": buyer_ntn,
        "BuyerCNIC": buyer_cnic,
        "BuyerName": (customer.name if customer else "") or "Walk-in Customer",
        "BuyerPhoneNumber": (customer.phone if customer else None) or None,
        "TotalSaleValue": float(_round2(subtotal)),
        "TotalTaxCharged": float(tax_amount),
        "TotalQuantity": float(total_quantity),
        "Discount": float(discount),
        "FurtherTax": 0.0,
        "TotalBillAmount": float(_round2(sale.total)),
        "PaymentMode": _payment_mode_code(sale.payment_method),
        "InvoiceType": _INVOICE_TYPE_NEW,
        "Items": items,
    }

    if env_settings.secret_key:
        payload["Signature"] = _sign_payload(payload, env_settings.secret_key)

    return payload


def validate_payload(payload: dict) -> list[str]:
    """Checks the payload against the same required-field/shape rules
    app/api/fbr_client.py's own _validate_payload() enforces
    (independently reimplemented, not imported). Returns a list of
    problem descriptions - empty means the payload looks submittable."""
    errors: list[str] = []

    for field in ("POSID", "USIN", "DateTime", "Items", "TotalBillAmount", "PaymentMode", "InvoiceType"):
        if payload.get(field) in (None, "", []):
            errors.append(f"Missing required field: {field}")

    if not isinstance(payload.get("POSID"), int):
        errors.append("POSID must be an integer - check that POS ID is set and numeric in FBR settings.")

    items = payload.get("Items") or []
    if not items:
        errors.append("At least one item is required.")

    total_bill_amount = payload.get("TotalBillAmount")
    if total_bill_amount is not None and total_bill_amount <= 0:
        errors.append("TotalBillAmount must be greater than zero.")

    if payload.get("PaymentMode") not in _VALID_PAYMENT_MODES:
        errors.append(f"PaymentMode must be one of {_VALID_PAYMENT_MODES}.")

    buyer_ntn = payload.get("BuyerNTN")
    if buyer_ntn and len(str(buyer_ntn)) > 9:
        errors.append("BuyerNTN must be at most 9 characters.")
    buyer_cnic = payload.get("BuyerCNIC")
    if buyer_cnic and len(str(buyer_cnic)) > 13:
        errors.append("BuyerCNIC must be at most 13 characters.")

    for idx, item in enumerate(items, start=1):
        if not item.get("ItemCode"):
            errors.append(f"Item {idx}: missing ItemCode.")
        if not item.get("ItemName"):
            errors.append(f"Item {idx}: missing ItemName.")
        if not item.get("Quantity") or item.get("Quantity") <= 0:
            errors.append(f"Item {idx}: Quantity must be greater than zero.")
        pct_code = item.get("PCTCode")
        if not pct_code or len(str(pct_code)) != 8:
            errors.append(f"Item {idx}: PCTCode must be exactly 8 characters.")
        if item.get("TaxRate") is None:
            errors.append(f"Item {idx}: missing TaxRate.")
        if item.get("InvoiceType") not in _VALID_INVOICE_TYPES:
            errors.append(f"Item {idx}: InvoiceType must be one of {_VALID_INVOICE_TYPES}.")

    return errors
