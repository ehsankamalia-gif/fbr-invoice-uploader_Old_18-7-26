"""Shared exception types for the Spare Parts module's service layer.

One canonical SparePartsValidationError, imported by every service
(parts, suppliers, purchases, and later sales/payments/adjustments) so UI
code can catch exactly one exception type regardless of which service
raised it. Previously parts_service and suppliers_service each defined
their own same-named-but-distinct class, which would have silently let a
suppliers_service error slip past a `except SparePartsValidationError`
written against parts_service's class, or vice versa.
"""
from __future__ import annotations


class SparePartsValidationError(ValueError):
    """Raised for any caller-facing validation failure (duplicate
    part_no, blank required field, insufficient stock, etc.) - UI code
    catches this specifically to show an inline error instead of a
    generic failure."""
