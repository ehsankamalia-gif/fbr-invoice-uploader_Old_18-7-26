"""Small helpers shared across the Spare Parts module's own service
layer. Internal to this module only - not imported by, and never
imports, anything outside spare_parts/ (see spare_parts/__init__.py)."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from spare_parts.errors import SparePartsValidationError


def to_decimal(value, field_name: str) -> Decimal:
    """Coerces a UI/service input to Decimal, raising the module's
    standard validation error (not a raw Decimal exception) on anything
    that isn't a valid number."""
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except InvalidOperation:
        raise SparePartsValidationError(f"{field_name} must be a valid number.")


# FBR InvoiceType codes a spare-parts SALE can be sent with. Debit/Credit
# notes (2, 3, 12) are deliberately not offered: they must reference an
# original invoice (RefUSIN), which a counter sale doesn't carry.
INVOICE_TYPE_NEW = 1
INVOICE_TYPE_3RD_SCHEDULE_NEW = 11
SALE_INVOICE_TYPES = (
    (INVOICE_TYPE_NEW, "1 - New (Standard)"),
    (INVOICE_TYPE_3RD_SCHEDULE_NEW, "11 - 3rd Schedule New"),
)
# What the sale counter pre-selects for a new sale.
DEFAULT_SALE_INVOICE_TYPE = INVOICE_TYPE_3RD_SCHEDULE_NEW


def normalize_invoice_type(value) -> int | None:
    """None (not chosen) stays None; otherwise must be one of the offered
    FBR codes."""
    if value is None or value == "":
        return None
    try:
        code = int(value)
    except (TypeError, ValueError):
        raise SparePartsValidationError("Invoice type must be a valid FBR code.")
    if code not in {c for c, _ in SALE_INVOICE_TYPES}:
        raise SparePartsValidationError(
            f"Invoice type {code} is not available for a sale "
            f"(choose one of {[c for c, _ in SALE_INVOICE_TYPES]})."
        )
    return code
