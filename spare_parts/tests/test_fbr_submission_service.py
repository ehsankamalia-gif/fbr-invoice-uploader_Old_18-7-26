"""Unit tests for spare_parts.services.fbr_submission_service.

Every test patches requests.post - an autouse fixture defaults it to
raise if any test forgets to, so nothing here can ever reach FBR's
real network. Also asserts this module's independence from the main
app's FBR/invoice code.
"""
from __future__ import annotations

import json

import pytest
import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from spare_parts.db.base import SpareBase
from spare_parts.db import models  # noqa: F401
from spare_parts.errors import SparePartsValidationError
from spare_parts.services import (
    fbr_submission_service,
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


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    """Every test must explicitly patch requests.post - if one forgets,
    this fails loudly instead of silently reaching the real network."""
    def _unexpected_call(*args, **kwargs):
        raise AssertionError("A test called the REAL requests.post() without patching it first.")
    monkeypatch.setattr(fbr_submission_service.requests, "post", _unexpected_call)


@pytest.fixture()
def part(db_session):
    p = parts_service.create_part(db_session, part_no="HD-1", name="Brake Pad", retail_price=100)
    stock_service.add_ledger_entry(db_session, part_id=p.id, qty_in=50, reference_type="OPENING")
    db_session.commit()
    return p


def _make_sale(db_session, part, qty=2, unit_price=100, tax_percent=10):
    return sales_service.create_sale(
        db_session, sale_type="RETAIL", customer_id=None,
        items=[dict(part_id=part.id, qty_entered=qty, unit_price=unit_price)],
        tax_percent=tax_percent, paid=9999,
    )


def _configure_sandbox(db_session, pos_id="966416", auth_token="test-token", url="https://sandbox.example/post"):
    settings_service.update_settings(db_session, fbr_environment="SANDBOX")
    settings_service.save_fbr_environment(
        db_session, "SANDBOX", pos_id=pos_id, auth_token=auth_token, api_base_url=url,
    )


class _FakeResponse:
    """Minimal stand-in for requests.Response - just what _post_to_fbr uses."""

    def __init__(self, json_body=None, status_code=200, text=None, raise_json_error=False):
        self._json_body = json_body
        self.status_code = status_code
        self.text = text if text is not None else json.dumps(json_body or {})
        self._raise_json_error = raise_json_error

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error", response=self)

    def json(self):
        if self._raise_json_error:
            raise ValueError("not JSON")
        return self._json_body


def _patch_post(monkeypatch, fn):
    monkeypatch.setattr(fbr_submission_service.requests, "post", fn)


def _counting_post(monkeypatch, response_or_fn):
    calls = []

    def _fn(url, json=None, headers=None, timeout=None, verify=None):
        calls.append(dict(url=url, json=json, headers=headers, timeout=timeout, verify=verify))
        if callable(response_or_fn):
            return response_or_fn(len(calls))
        return response_or_fn

    _patch_post(monkeypatch, _fn)
    return calls


# --- success / rejection / network failure --------------------------------

def test_submit_sale_to_fbr_success(db_session, part, monkeypatch):
    _configure_sandbox(db_session)
    sale = _make_sale(db_session, part)
    calls = _counting_post(
        monkeypatch, _FakeResponse({"Code": "100", "InvoiceNumber": "FBR-INV-001", "Response": "OK"}),
    )

    result = fbr_submission_service.submit_sale_to_fbr(db_session, sale.id)

    assert result.fbr_submission_status == fbr_submission_service.STATUS_SUBMITTED
    assert result.fbr_invoice_number == "FBR-INV-001"
    assert result.fbr_last_error is None
    assert result.fbr_submitted_at is not None
    assert len(calls) == 1


def test_submit_sale_to_fbr_rejected(db_session, part, monkeypatch):
    _configure_sandbox(db_session)
    sale = _make_sale(db_session, part)
    _counting_post(monkeypatch, _FakeResponse({"Code": "01", "Response": "Invalid POS ID"}))

    with pytest.raises(SparePartsValidationError, match="Invalid POS ID"):
        fbr_submission_service.submit_sale_to_fbr(db_session, sale.id)

    db_session.refresh(sale)
    assert sale.fbr_submission_status == fbr_submission_service.STATUS_FAILED
    assert "Invalid POS ID" in sale.fbr_last_error


def test_submit_sale_to_fbr_network_failure(db_session, part, monkeypatch):
    _configure_sandbox(db_session)
    sale = _make_sale(db_session, part)

    def _raise(*a, **k):
        raise requests.ConnectionError("Could not connect")

    _patch_post(monkeypatch, _raise)

    with pytest.raises(SparePartsValidationError, match="Could not reach FBR"):
        fbr_submission_service.submit_sale_to_fbr(db_session, sale.id)

    db_session.refresh(sale)
    assert sale.fbr_submission_status == fbr_submission_service.STATUS_FAILED
    assert "Could not reach FBR" in sale.fbr_last_error


def test_submit_sale_to_fbr_malformed_response(db_session, part, monkeypatch):
    _configure_sandbox(db_session)
    sale = _make_sale(db_session, part)
    _counting_post(monkeypatch, _FakeResponse(raise_json_error=True, text="<html>not json</html>"))

    with pytest.raises(SparePartsValidationError, match="unexpected"):
        fbr_submission_service.submit_sale_to_fbr(db_session, sale.id)

    db_session.refresh(sale)
    assert sale.fbr_submission_status == fbr_submission_service.STATUS_FAILED


# --- pre-flight guard ----------------------------------------------------

def test_submit_sale_to_fbr_refuses_without_pos_config(db_session, part, monkeypatch):
    # No _configure_sandbox() call - settings/environment row exist but are blank.
    sale = _make_sale(db_session, part)
    calls = _counting_post(monkeypatch, _FakeResponse({"Code": "100"}))

    with pytest.raises(SparePartsValidationError, match="not configured"):
        fbr_submission_service.submit_sale_to_fbr(db_session, sale.id)

    assert calls == [], "requests.post must never be called when FBR config is incomplete"


def test_submit_sale_to_fbr_refuses_bad_url(db_session, part, monkeypatch):
    _configure_sandbox(db_session, url="not-a-url")
    sale = _make_sale(db_session, part)
    calls = _counting_post(monkeypatch, _FakeResponse({"Code": "100"}))

    with pytest.raises(SparePartsValidationError, match="valid URL"):
        fbr_submission_service.submit_sale_to_fbr(db_session, sale.id)

    assert calls == []


# --- cancelled sale ---------------------------------------------------------

def test_submit_sale_to_fbr_rejects_cancelled_sale(db_session, part, monkeypatch):
    _configure_sandbox(db_session)
    sale = _make_sale(db_session, part)
    sales_service.cancel_sale(db_session, sale.id)
    calls = _counting_post(monkeypatch, _FakeResponse({"Code": "100"}))

    with pytest.raises(SparePartsValidationError):
        fbr_submission_service.submit_sale_to_fbr(db_session, sale.id)

    assert calls == []


def test_submit_sale_to_fbr_sale_not_found(db_session, monkeypatch):
    with pytest.raises(SparePartsValidationError, match="not found"):
        fbr_submission_service.submit_sale_to_fbr(db_session, 999999)


# --- resubmission guard ----------------------------------------------------

def test_submit_sale_to_fbr_refuses_resubmit_without_force(db_session, part, monkeypatch):
    _configure_sandbox(db_session)
    sale = _make_sale(db_session, part)
    calls = _counting_post(monkeypatch, _FakeResponse({"Code": "100", "InvoiceNumber": "FBR-INV-002"}))
    fbr_submission_service.submit_sale_to_fbr(db_session, sale.id)
    assert len(calls) == 1

    with pytest.raises(SparePartsValidationError, match="already submitted"):
        fbr_submission_service.submit_sale_to_fbr(db_session, sale.id)
    assert len(calls) == 1  # no second HTTP call


def test_submit_sale_to_fbr_resubmits_with_force(db_session, part, monkeypatch):
    _configure_sandbox(db_session)
    sale = _make_sale(db_session, part)
    calls = _counting_post(monkeypatch, _FakeResponse({"Code": "100", "InvoiceNumber": "FBR-INV-003"}))
    fbr_submission_service.submit_sale_to_fbr(db_session, sale.id)

    result = fbr_submission_service.submit_sale_to_fbr(db_session, sale.id, force=True)
    assert len(calls) == 2
    assert result.fbr_submission_status == fbr_submission_service.STATUS_SUBMITTED


# --- transport details -----------------------------------------------------

def test_submit_sale_to_fbr_sends_bearer_header_and_environment_url(db_session, part, monkeypatch):
    _configure_sandbox(db_session, pos_id="123456", auth_token="my-sandbox-token", url="https://sandbox.example/post")
    sale = _make_sale(db_session, part)
    calls = _counting_post(monkeypatch, _FakeResponse({"Code": "100", "InvoiceNumber": "X"}))

    fbr_submission_service.submit_sale_to_fbr(db_session, sale.id)

    assert len(calls) == 1
    call = calls[0]
    assert call["url"] == "https://sandbox.example/post"
    assert call["headers"]["Authorization"] == "Bearer my-sandbox-token"
    assert call["verify"] is False  # SANDBOX -> verify=False


def test_submit_sale_to_fbr_production_uses_ssl_verify_and_its_own_url(db_session, part, monkeypatch):
    settings_service.save_fbr_environment(
        db_session, "PRODUCTION", pos_id="999999", auth_token="prod-token", api_base_url="https://prod.example/post",
    )
    settings_service.update_settings(db_session, fbr_environment="PRODUCTION")
    sale = _make_sale(db_session, part)
    calls = _counting_post(monkeypatch, _FakeResponse({"Code": "100", "InvoiceNumber": "X"}))

    fbr_submission_service.submit_sale_to_fbr(db_session, sale.id)

    call = calls[0]
    assert call["url"] == "https://prod.example/post"
    assert call["headers"]["Authorization"] == "Bearer prod-token"
    assert call["verify"] is True


# --- retry behavior ----------------------------------------------------

def test_submit_sale_to_fbr_retries_then_succeeds(db_session, part, monkeypatch):
    # Avoid real sleeping between retry attempts.
    monkeypatch.setattr(fbr_submission_service, "_post_to_fbr", fbr_submission_service._post_to_fbr.retry_with(
        wait=None
    ))
    _configure_sandbox(db_session)
    sale = _make_sale(db_session, part)

    def _flaky(count):
        if count < 3:
            raise requests.ConnectionError("transient failure")
        return _FakeResponse({"Code": "100", "InvoiceNumber": "FBR-RETRY-OK"})

    calls = _counting_post(monkeypatch, _flaky)

    result = fbr_submission_service.submit_sale_to_fbr(db_session, sale.id)

    assert len(calls) == 3
    assert result.fbr_submission_status == fbr_submission_service.STATUS_SUBMITTED
    assert result.fbr_invoice_number == "FBR-RETRY-OK"


# --- independence from the main app's FBR/invoice code ---------------------

def test_fbr_submission_service_is_independent_of_app_fbr_code():
    import inspect
    source = inspect.getsource(fbr_submission_service)
    for forbidden in ("app.api.fbr_client", "app.services.invoice_service", "app.db.models"):
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")) and forbidden in stripped:
                pytest.fail(f"Found forbidden import referencing {forbidden!r}: {stripped!r}")
