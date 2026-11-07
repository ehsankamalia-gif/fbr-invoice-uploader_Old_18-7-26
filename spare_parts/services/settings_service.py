"""Module-level settings (single row, id=1) plus this module's own
per-environment FBR API/security settings (one row per SANDBOX/
PRODUCTION in sp_fbr_environments - see SpFbrEnvironment)."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from spare_parts.db.models import SpFbrEnvironment, SpSettings

_SETTINGS_ID = 1
_VALID_FBR_ENVIRONMENTS = ("SANDBOX", "PRODUCTION")
_VALID_RECEIPT_PAPER_FORMATS = ("A4", "THERMAL_80MM", "THERMAL_58MM")


def get_settings(db: Session) -> SpSettings:
    settings = db.query(SpSettings).filter(SpSettings.id == _SETTINGS_ID).first()
    if settings is None:
        settings = SpSettings(
            id=_SETTINGS_ID,
            allow_negative_stock=False,
            default_tax_percent=Decimal("0"),
            purchase_no_prefix="PO-",
            fbr_environment="SANDBOX",
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def update_settings(db: Session, **fields) -> SpSettings:
    settings = get_settings(db)
    if "allow_negative_stock" in fields:
        settings.allow_negative_stock = bool(fields["allow_negative_stock"])
    if "default_tax_percent" in fields and fields["default_tax_percent"] is not None:
        settings.default_tax_percent = Decimal(str(fields["default_tax_percent"]))
    if "purchase_no_prefix" in fields and fields["purchase_no_prefix"]:
        settings.purchase_no_prefix = str(fields["purchase_no_prefix"]).strip()
    if "wholesale_no_prefix" in fields and fields["wholesale_no_prefix"]:
        settings.wholesale_no_prefix = str(fields["wholesale_no_prefix"]).strip()
    if "retail_no_prefix" in fields and fields["retail_no_prefix"]:
        settings.retail_no_prefix = str(fields["retail_no_prefix"]).strip()
    # Which FBR environment is currently selected - the actual API/
    # security values for each environment live in sp_fbr_environments
    # (see get_fbr_environment/save_fbr_environment below), not here.
    if "fbr_environment" in fields and fields["fbr_environment"]:
        settings.fbr_environment = str(fields["fbr_environment"]).strip().upper()
    if "receipt_paper_format" in fields and fields["receipt_paper_format"]:
        value = str(fields["receipt_paper_format"]).strip().upper()
        if value in _VALID_RECEIPT_PAPER_FORMATS:
            settings.receipt_paper_format = value
    if "stock_take_no_prefix" in fields and fields["stock_take_no_prefix"]:
        settings.stock_take_no_prefix = str(fields["stock_take_no_prefix"]).strip()
    if "quotation_no_prefix" in fields and fields["quotation_no_prefix"]:
        settings.quotation_no_prefix = str(fields["quotation_no_prefix"]).strip()
    db.commit()
    db.refresh(settings)
    return settings


def get_fbr_environment(db: Session, environment: str) -> SpFbrEnvironment:
    """This module's own FBR API/security settings for ONE environment
    (SANDBOX or PRODUCTION) - get-or-create, so switching the Environment
    dropdown always has real (if empty) values to load. Stored only for
    spare_parts' own use; never read by the invoice-upload/FBR
    submission code - see spare_parts/__init__.py."""
    environment = (environment or "SANDBOX").strip().upper()
    if environment not in _VALID_FBR_ENVIRONMENTS:
        environment = "SANDBOX"
    row = db.query(SpFbrEnvironment).filter(SpFbrEnvironment.environment == environment).first()
    if row is None:
        row = SpFbrEnvironment(environment=environment)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def save_fbr_environment(db: Session, environment: str, **fields) -> SpFbrEnvironment:
    """Saves API Base URL/POS ID/USIN/Auth Token/Secret Key for ONE
    environment, leaving every other environment's own row untouched -
    this is what makes switching the Environment dropdown show different
    values per environment, instead of one shared set regardless of
    which is selected. Blank clears a field."""
    row = get_fbr_environment(db, environment)
    for field_name in ("api_base_url", "pos_id", "usin", "auth_token", "secret_key"):
        if field_name in fields:
            value = fields[field_name]
            setattr(row, field_name, str(value).strip() or None if value is not None else None)
    db.commit()
    db.refresh(row)
    return row
