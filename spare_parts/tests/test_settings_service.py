"""Unit tests for spare_parts.services.settings_service."""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from spare_parts.db.base import SpareBase
from spare_parts.db import models  # noqa: F401 - registers tables on SpareBase.metadata
from spare_parts.services import settings_service


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SpareBase.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()
    engine.dispose()


def test_get_settings_creates_default_row(db_session):
    settings = settings_service.get_settings(db_session)
    assert settings.id == 1
    assert settings.allow_negative_stock is False
    assert settings.default_tax_percent == Decimal("0")
    assert settings.purchase_no_prefix == "PO-"
    assert settings.wholesale_no_prefix == "WS-"
    assert settings.retail_no_prefix == "RT-"
    assert settings.fbr_environment == "SANDBOX"


def test_get_settings_returns_same_row_on_repeat_calls(db_session):
    first = settings_service.get_settings(db_session)
    second = settings_service.get_settings(db_session)
    assert first.id == second.id == 1


def test_update_settings_general_fields(db_session):
    updated = settings_service.update_settings(
        db_session,
        allow_negative_stock=True,
        default_tax_percent="17.5",
        purchase_no_prefix="PUR-",
        wholesale_no_prefix="WHL-",
        retail_no_prefix="RTL-",
    )
    assert updated.allow_negative_stock is True
    assert updated.default_tax_percent == Decimal("17.5")
    assert updated.purchase_no_prefix == "PUR-"
    assert updated.wholesale_no_prefix == "WHL-"
    assert updated.retail_no_prefix == "RTL-"


def test_update_settings_ignores_blank_purchase_no_prefix(db_session):
    settings_service.update_settings(db_session, purchase_no_prefix="CUSTOM-")
    updated = settings_service.update_settings(db_session, purchase_no_prefix="")
    assert updated.purchase_no_prefix == "CUSTOM-"


def test_update_settings_ignores_blank_wholesale_no_prefix(db_session):
    settings_service.update_settings(db_session, wholesale_no_prefix="WHL-")
    updated = settings_service.update_settings(db_session, wholesale_no_prefix="")
    assert updated.wholesale_no_prefix == "WHL-"


def test_update_settings_ignores_blank_retail_no_prefix(db_session):
    settings_service.update_settings(db_session, retail_no_prefix="RTL-")
    updated = settings_service.update_settings(db_session, retail_no_prefix="")
    assert updated.retail_no_prefix == "RTL-"


# --- fbr_environment pointer (which environment is selected) -------------

def test_update_settings_fbr_environment_uppercased(db_session):
    updated = settings_service.update_settings(db_session, fbr_environment="production")
    assert updated.fbr_environment == "PRODUCTION"


def test_update_settings_fbr_environment_ignores_blank(db_session):
    settings_service.update_settings(db_session, fbr_environment="PRODUCTION")
    updated = settings_service.update_settings(db_session, fbr_environment="")
    assert updated.fbr_environment == "PRODUCTION"


# --- per-environment FBR API/security fields (this module's own, separate
# from invoice FBR config) - one row per environment, so switching
# Environment in the UI actually swaps the values shown ---------------------

def test_get_fbr_environment_creates_empty_row(db_session):
    row = settings_service.get_fbr_environment(db_session, "SANDBOX")
    assert row.environment == "SANDBOX"
    assert row.api_base_url is None
    assert row.pos_id is None
    assert row.usin is None
    assert row.auth_token is None
    assert row.secret_key is None


def test_get_fbr_environment_normalizes_case_and_defaults_unknown_to_sandbox(db_session):
    row = settings_service.get_fbr_environment(db_session, "production")
    assert row.environment == "PRODUCTION"
    row2 = settings_service.get_fbr_environment(db_session, "not-a-real-env")
    assert row2.environment == "SANDBOX"


def test_save_fbr_environment_fields(db_session):
    updated = settings_service.save_fbr_environment(
        db_session,
        "PRODUCTION",
        api_base_url="https://esp.fbr.gov.pk:8244/FBR/v1/api/Live/PostData",
        pos_id="966416",
        usin="RE",
        auth_token="token-abc",
        secret_key="secret-xyz",
    )
    assert updated.environment == "PRODUCTION"
    assert updated.api_base_url == "https://esp.fbr.gov.pk:8244/FBR/v1/api/Live/PostData"
    assert updated.pos_id == "966416"
    assert updated.usin == "RE"
    assert updated.auth_token == "token-abc"
    assert updated.secret_key == "secret-xyz"


def test_save_fbr_environment_fields_strip_whitespace(db_session):
    updated = settings_service.save_fbr_environment(db_session, "SANDBOX", pos_id="  966416  ")
    assert updated.pos_id == "966416"


def test_save_fbr_environment_fields_can_be_cleared(db_session):
    settings_service.save_fbr_environment(db_session, "SANDBOX", auth_token="token-abc")
    cleared = settings_service.save_fbr_environment(db_session, "SANDBOX", auth_token="")
    assert cleared.auth_token is None


def test_save_fbr_environment_fields_independent_of_each_other(db_session):
    settings_service.save_fbr_environment(db_session, "SANDBOX", pos_id="966416")
    updated = settings_service.save_fbr_environment(db_session, "SANDBOX", usin="RE")
    assert updated.pos_id == "966416"
    assert updated.usin == "RE"


def test_sandbox_and_production_environments_are_independent(db_session):
    """The actual bug being fixed: switching Environment must show that
    environment's OWN values, not one shared set."""
    settings_service.save_fbr_environment(
        db_session, "SANDBOX", api_base_url="https://sandbox.example/api", pos_id="111111",
    )
    settings_service.save_fbr_environment(
        db_session, "PRODUCTION", api_base_url="https://prod.example/api", pos_id="222222",
    )
    sandbox = settings_service.get_fbr_environment(db_session, "SANDBOX")
    production = settings_service.get_fbr_environment(db_session, "PRODUCTION")
    assert sandbox.api_base_url == "https://sandbox.example/api"
    assert sandbox.pos_id == "111111"
    assert production.api_base_url == "https://prod.example/api"
    assert production.pos_id == "222222"


def test_saving_one_environment_does_not_touch_the_other(db_session):
    settings_service.save_fbr_environment(db_session, "SANDBOX", pos_id="111111")
    settings_service.save_fbr_environment(db_session, "PRODUCTION", pos_id="222222")
    settings_service.save_fbr_environment(db_session, "SANDBOX", pos_id="999999")
    assert settings_service.get_fbr_environment(db_session, "SANDBOX").pos_id == "999999"
    assert settings_service.get_fbr_environment(db_session, "PRODUCTION").pos_id == "222222"
