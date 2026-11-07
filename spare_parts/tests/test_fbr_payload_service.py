"""Unit tests for spare_parts.services.fbr_payload_service.

Also asserts this module's independence from the main app's FBR/invoice
code - see test_fbr_payload_service_is_independent_of_app_fbr_code below.
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from spare_parts.db.base import SpareBase
from spare_parts.db import models  # noqa: F401
from spare_parts.errors import SparePartsValidationError
from spare_parts.services import (
    customers_service,
    fbr_payload_service,
    parts_service,
    sales_service,
    settings_service,
    stock_service,
)


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SpareBase.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def part(db_session):
    p = parts_service.create_part(db_session, part_no="HD-1", name="Brake Pad", retail_price=100)
    stock_service.add_ledger_entry(db_session, part_id=p.id, qty_in=50, reference_type="OPENING")
    db_session.commit()
    return p


@pytest.fixture()
def part2(db_session):
    p = parts_service.create_part(db_session, part_no="F-2", name="Oil Filter", retail_price=50)
    stock_service.add_ledger_entry(db_session, part_id=p.id, qty_in=50, reference_type="OPENING")
    db_session.commit()
    return p


def _make_sale(db_session, part, customer_id=None, qty=2, unit_price=100, tax_percent=10,
                discount=0, payment_method="Cash"):
    return sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=customer_id,
        items=[dict(part_id=part.id, qty_entered=qty, unit_price=unit_price, discount=discount)],
        tax_percent=tax_percent, paid=9999, payment_method=payment_method,
    )


# --- Basic payload shape ---------------------------------------------------

def test_build_sale_payload_basic_shape(db_session, part):
    sale = _make_sale(db_session, part)
    payload = fbr_payload_service.build_sale_payload(db_session, sale)

    assert payload["USIN"] == sale.sale_no
    assert payload["InvoiceNumber"] == ""
    assert payload["RefUSIN"] is None
    assert payload["InvoiceType"] == 1
    assert isinstance(payload["DateTime"], str)
    assert len(payload["Items"]) == 1
    assert payload["TotalBillAmount"] == float(sale.total)
    assert payload["TotalSaleValue"] == float(sale.subtotal)
    assert payload["TotalTaxCharged"] == float(sale.tax_amount)


def test_build_sale_payload_item_fields(db_session, part):
    sale = _make_sale(db_session, part, qty=3, unit_price=100)
    payload = fbr_payload_service.build_sale_payload(db_session, sale)
    item = payload["Items"][0]

    assert item["ItemCode"] == "HD-1"
    assert item["ItemName"] == "Brake Pad"
    assert item["Quantity"] == 3
    assert item["SaleValue"] == 300.0
    assert item["PCTCode"] == fbr_payload_service.DEFAULT_PCT_CODE
    assert len(item["PCTCode"]) == 8
    assert item["InvoiceType"] == 1
    assert item["RefUSIN"] is None
    assert item["FurtherTax"] == 0.0


def test_build_sale_payload_multiple_items_tax_apportioned(db_session, part, part2):
    sale = sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=None,
        items=[
            dict(part_id=part.id, qty_entered=2, unit_price=100),   # 200
            dict(part_id=part2.id, qty_entered=1, unit_price=50),   # 50
        ],
        tax_percent=10, paid=9999,
    )
    payload = fbr_payload_service.build_sale_payload(db_session, sale)
    items = payload["Items"]
    assert len(items) == 2
    # 200/250 share and 50/250 share of the 25.00 total tax.
    assert items[0]["TaxCharged"] == pytest.approx(20.0, abs=0.01)
    assert items[1]["TaxCharged"] == pytest.approx(5.0, abs=0.01)
    assert payload["TotalTaxCharged"] == float(sale.tax_amount)


# --- Buyer identity ----------------------------------------------------

def test_build_sale_payload_walk_in_has_no_buyer_identity(db_session, part):
    sale = _make_sale(db_session, part, customer_id=None)
    payload = fbr_payload_service.build_sale_payload(db_session, sale)
    assert payload["BuyerNTN"] is None
    assert payload["BuyerCNIC"] is None
    assert payload["BuyerName"] == "Walk-in Customer"
    assert payload["BuyerPhoneNumber"] is None


def test_build_sale_payload_customer_with_ntn(db_session, part):
    customer = customers_service.create_customer(
        db_session, name="ACME Garage", type="RETAIL", phone="0300-1234567", cnic_ntn="123456789",
    )
    sale = _make_sale(db_session, part, customer_id=customer.id)
    payload = fbr_payload_service.build_sale_payload(db_session, sale)
    assert payload["BuyerName"] == "ACME Garage"
    assert payload["BuyerNTN"] == "123456789"
    assert payload["BuyerCNIC"] is None
    assert payload["BuyerPhoneNumber"] == "0300-1234567"


def test_build_sale_payload_customer_with_cnic(db_session, part):
    customer = customers_service.create_customer(
        db_session, name="Jane Doe", type="RETAIL", cnic_ntn="35202-1234567-1",
    )
    sale = _make_sale(db_session, part, customer_id=customer.id)
    payload = fbr_payload_service.build_sale_payload(db_session, sale)
    assert payload["BuyerCNIC"] == "3520212345671"
    assert payload["BuyerNTN"] is None


def test_build_sale_payload_customer_with_no_cnic_ntn(db_session, part):
    customer = customers_service.create_customer(db_session, name="No ID Customer", type="RETAIL")
    sale = _make_sale(db_session, part, customer_id=customer.id)
    payload = fbr_payload_service.build_sale_payload(db_session, sale)
    assert payload["BuyerNTN"] is None
    assert payload["BuyerCNIC"] is None
    assert payload["BuyerName"] == "No ID Customer"


# --- Payment mode mapping -------------------------------------------------

@pytest.mark.parametrize("method,expected_code", [
    ("Cash", 1), ("Card", 2), ("Bank Transfer", 5), ("Credit", 5),
    ("Something Unrecognized", 1),
])
def test_build_sale_payload_payment_mode_mapping(db_session, part, method, expected_code):
    sale = _make_sale(db_session, part, payment_method=method)
    payload = fbr_payload_service.build_sale_payload(db_session, sale)
    assert payload["PaymentMode"] == expected_code


# --- FBR configuration from spare_parts' own settings ----------------------

def test_build_sale_payload_uses_spare_parts_own_fbr_settings(db_session, part):
    settings_service.update_settings(db_session, fbr_environment="PRODUCTION")
    settings_service.save_fbr_environment(db_session, "PRODUCTION", pos_id="966416", usin="FALLBACK-USIN")
    sale = _make_sale(db_session, part)
    payload = fbr_payload_service.build_sale_payload(db_session, sale)
    assert payload["POSID"] == 966416
    assert isinstance(payload["POSID"], int)
    # USIN prefers the sale's own number over the settings fallback.
    assert payload["USIN"] == sale.sale_no


def test_build_sale_payload_usin_falls_back_to_settings_when_no_sale_no(db_session, part):
    # Not realistically reachable via create_sale (always assigns a
    # sale_no), but confirms the fallback branch works if sale_no is blank.
    settings_service.save_fbr_environment(db_session, "SANDBOX", usin="FALLBACK-USIN")
    sale = _make_sale(db_session, part)
    sale.sale_no = ""
    payload = fbr_payload_service.build_sale_payload(db_session, sale)
    assert payload["USIN"] == "FALLBACK-USIN"


def test_build_sale_payload_switching_environment_changes_pos_id(db_session, part):
    settings_service.save_fbr_environment(db_session, "SANDBOX", pos_id="111111")
    settings_service.save_fbr_environment(db_session, "PRODUCTION", pos_id="222222")
    sale = _make_sale(db_session, part)

    settings_service.update_settings(db_session, fbr_environment="SANDBOX")
    payload_sandbox = fbr_payload_service.build_sale_payload(db_session, sale)
    assert payload_sandbox["POSID"] == 111111

    settings_service.update_settings(db_session, fbr_environment="PRODUCTION")
    payload_prod = fbr_payload_service.build_sale_payload(db_session, sale)
    assert payload_prod["POSID"] == 222222


def test_build_sale_payload_pos_id_non_numeric_stays_string(db_session, part):
    settings_service.save_fbr_environment(db_session, "SANDBOX", pos_id="ABC123")
    sale = _make_sale(db_session, part)
    payload = fbr_payload_service.build_sale_payload(db_session, sale)
    assert payload["POSID"] == "ABC123"


# --- Signature ---------------------------------------------------------

def test_build_sale_payload_no_signature_without_secret_key(db_session, part):
    sale = _make_sale(db_session, part)
    payload = fbr_payload_service.build_sale_payload(db_session, sale)
    assert "Signature" not in payload


def test_build_sale_payload_signature_present_with_secret_key(db_session, part):
    settings_service.save_fbr_environment(db_session, "SANDBOX", secret_key="my-secret")
    sale = _make_sale(db_session, part)
    payload = fbr_payload_service.build_sale_payload(db_session, sale)
    assert "Signature" in payload
    assert len(payload["Signature"]) == 64  # SHA256 hex digest length
    assert payload["Signature"] == payload["Signature"].upper()


def test_build_sale_payload_signature_deterministic_for_same_data(db_session, part):
    settings_service.save_fbr_environment(db_session, "SANDBOX", secret_key="my-secret")
    sale = _make_sale(db_session, part)
    payload1 = fbr_payload_service.build_sale_payload(db_session, sale)
    payload2 = fbr_payload_service.build_sale_payload(db_session, sale)
    assert payload1["Signature"] == payload2["Signature"]


def test_build_sale_payload_signature_changes_with_different_secret(db_session, part):
    sale = _make_sale(db_session, part)
    settings_service.save_fbr_environment(db_session, "SANDBOX", secret_key="secret-one")
    payload1 = fbr_payload_service.build_sale_payload(db_session, sale)
    settings_service.save_fbr_environment(db_session, "SANDBOX", secret_key="secret-two")
    payload2 = fbr_payload_service.build_sale_payload(db_session, sale)
    assert payload1["Signature"] != payload2["Signature"]


# --- Non-POSTED sale ----------------------------------------------------

def test_build_sale_payload_rejects_cancelled_sale(db_session, part):
    sale = _make_sale(db_session, part)
    sales_service.cancel_sale(db_session, sale.id)
    with pytest.raises(SparePartsValidationError):
        fbr_payload_service.build_sale_payload(db_session, sale)


# --- validate_payload ----------------------------------------------------

def test_validate_payload_accepts_well_formed_payload(db_session, part):
    sale = _make_sale(db_session, part)
    payload = fbr_payload_service.build_sale_payload(db_session, sale)
    settings_service.save_fbr_environment(db_session, "SANDBOX", pos_id="966416")
    payload = fbr_payload_service.build_sale_payload(db_session, sale)
    assert fbr_payload_service.validate_payload(payload) == []


def test_validate_payload_flags_missing_pos_id(db_session, part):
    sale = _make_sale(db_session, part)
    payload = fbr_payload_service.build_sale_payload(db_session, sale)
    errors = fbr_payload_service.validate_payload(payload)
    assert any("POSID" in e for e in errors)


def test_validate_payload_flags_empty_items():
    payload = {
        "POSID": 1, "USIN": "X", "DateTime": "2026-01-01 00:00:00", "Items": [],
        "TotalBillAmount": 100, "PaymentMode": 1, "InvoiceType": 1,
    }
    errors = fbr_payload_service.validate_payload(payload)
    assert any("item" in e.lower() for e in errors)


def test_validate_payload_flags_invalid_payment_mode():
    payload = {
        "POSID": 1, "USIN": "X", "DateTime": "2026-01-01 00:00:00",
        "Items": [{"ItemCode": "A", "ItemName": "A", "Quantity": 1, "PCTCode": "11001010",
                    "TaxRate": 0, "InvoiceType": 1}],
        "TotalBillAmount": 100, "PaymentMode": 99, "InvoiceType": 1,
    }
    errors = fbr_payload_service.validate_payload(payload)
    assert any("PaymentMode" in e for e in errors)


def test_validate_payload_flags_bad_pct_code_length():
    payload = {
        "POSID": 1, "USIN": "X", "DateTime": "2026-01-01 00:00:00",
        "Items": [{"ItemCode": "A", "ItemName": "A", "Quantity": 1, "PCTCode": "123",
                    "TaxRate": 0, "InvoiceType": 1}],
        "TotalBillAmount": 100, "PaymentMode": 1, "InvoiceType": 1,
    }
    errors = fbr_payload_service.validate_payload(payload)
    assert any("PCTCode" in e for e in errors)


# --- Independence from the main app's FBR/invoice code ---------------------

def test_fbr_payload_service_is_independent_of_app_fbr_code():
    import inspect
    from spare_parts.services import fbr_payload_service as module
    source = inspect.getsource(module)
    for forbidden in ("app.api.fbr_client", "app.services.invoice_service", "app.db.models"):
        # Only comments/docstrings may mention these names (checked
        # above by the author, re-checked here) - no "import" line.
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")) and forbidden in stripped:
                pytest.fail(f"Found forbidden import referencing {forbidden!r}: {stripped!r}")
