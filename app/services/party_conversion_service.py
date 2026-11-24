"""Dealer <-> Customer conversion.

A "party" is a row in the `customers` table; its `type` is INDIVIDUAL (a
customer) or DEALER. Converting changes that one row in place - same ID, name,
CNIC/NTN and contact details - so no duplicate party is ever created.

Invoices are never touched: each invoice carries its own `invoice_party_type`
snapshot taken when it was created (see InvoiceService.create_invoice), so
everything saved before a conversion stays a dealer invoice and everything saved
after is a customer invoice.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from sqlalchemy.orm import Session

from app.db import session as db_session
from app.db.models import Customer, CustomerType, PartyTypeHistory, pk_now
from app.utils.string_utils import normalize_business_name

logger = logging.getLogger(__name__)

DEALER = CustomerType.DEALER.value
CUSTOMER = CustomerType.INDIVIDUAL.value


class PartyConversionError(ValueError):
    """A conversion that was refused for a business reason (not a DB failure)."""


def _norm(value: Any) -> str:
    return str(getattr(value, "value", value) or "").upper()


def convert_party(
    party_id: int,
    new_type: str,
    changed_by: Optional[str] = None,
    session_factory: Optional[Callable[[], Session]] = None,
    business_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Converts one party to `new_type` ('DEALER' or 'INDIVIDUAL') atomically.

    One transaction: lock the party row, update its type and
    converted_to_customer_at, write a party_type_history row, commit. Any error
    rolls the whole thing back and is re-raised.

    Raises PartyConversionError if the party doesn't exist, is deleted, or is
    already of `new_type`.
    """
    new_type = _norm(new_type)
    if new_type not in (DEALER, CUSTOMER):
        raise PartyConversionError(f"Unknown party type: {new_type!r}")

    factory = session_factory or db_session.SessionLocal
    db = factory()
    try:
        # FOR UPDATE serialises concurrent conversions of the same party on
        # MySQL (it is a no-op on SQLite, which locks the whole file anyway).
        party = (
            db.query(Customer)
            .filter(Customer.id == party_id)
            .with_for_update()
            .one_or_none()
        )
        if party is None or party.is_deleted:
            raise PartyConversionError("This record no longer exists.")

        old_type = _norm(party.type) or CUSTOMER
        if old_type == new_type:
            label = "dealer" if new_type == DEALER else "customer"
            raise PartyConversionError(f"{party.name} is already a {label}.")

        if new_type == DEALER:
            bn = (business_name or party.business_name or "").strip()
            if not bn:
                raise PartyConversionError(
                    "A business name is required before a customer can be made a dealer."
                )
            norm = normalize_business_name(bn)
            clash = (
                db.query(Customer.id)
                .filter(Customer.normalized_business_name == norm, Customer.id != party.id)
                .first()
            )
            if clash:
                raise PartyConversionError(
                    f"Business name '{bn}' is already used by another record."
                )
            party.business_name = bn.upper()
            party.normalized_business_name = norm

        now = pk_now()
        party.type = new_type
        party.converted_to_customer_at = now if new_type == CUSTOMER else None
        db.add(
            PartyTypeHistory(
                party_id=party.id,
                old_type=old_type,
                new_type=new_type,
                changed_at=now,
                changed_by=(changed_by or "system")[:100],
            )
        )
        db.commit()
        logger.info(
            "AUDIT: party %s converted %s -> %s by %s",
            party_id, old_type, new_type, changed_by or "system",
        )
        return {
            "party_id": party_id,
            "name": party.name,
            "old_type": old_type,
            "new_type": new_type,
            "changed_at": now,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def convert_dealer_to_customer(party_id: int, changed_by: Optional[str] = None, **kw) -> Dict[str, Any]:
    return convert_party(party_id, CUSTOMER, changed_by, **kw)


def convert_customer_to_dealer(party_id: int, changed_by: Optional[str] = None, **kw) -> Dict[str, Any]:
    return convert_party(party_id, DEALER, changed_by, **kw)
