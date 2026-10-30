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
