import threading
import time

from app.services.settings_service import settings_service, should_regenerate_invoice_number


def test_settings_change_notifies_subscribers_within_time_limit(tmp_path):
    original_env_path = settings_service.env_path
    settings_service.env_path = tmp_path / ".env"
    token = None
    received = {}
    fired = threading.Event()
    try:
        token = settings_service.subscribe(lambda event: (received.update(event), fired.set()))
        start = time.monotonic()
        settings_service.save_environment(
            env="SANDBOX",
            base_url="https://notify.test",
            pos_id="123",
            usin="EHS",
            token="tok",
            secret_key="sek",
            tax_rate="18.0",
            pct_code="8711.2010",
            invoice_type="Standard",
            discount="0.0",
            item_code="MOTO",
            item_name="Motorcycle",
            business_name="Ehsan Trader",
        )
        assert fired.wait(0.5)
        assert (time.monotonic() - start) < 0.5
        assert received.get("type") == "fbr_settings_saved"
        assert int(received.get("revision") or 0) > 0
        env_settings = settings_service.get_environment("SANDBOX")
        assert env_settings.get("base_url") == "https://notify.test"
        assert env_settings.get("pos_id") == "123"
        assert env_settings.get("usin") == "EHS"
    finally:
        if token:
            settings_service.unsubscribe(token)
        settings_service.env_path = original_env_path


def test_active_environment_change_notifies_subscribers_within_time_limit(tmp_path):
    original_env_path = settings_service.env_path
    settings_service.env_path = tmp_path / ".env"
    token = None
    fired = threading.Event()
    received = {}
    try:
        token = settings_service.subscribe(lambda event: (received.update(event), fired.set()))
        start = time.monotonic()
        settings_service.set_active_environment("SANDBOX")
        assert fired.wait(0.5)
        assert (time.monotonic() - start) < 0.5
        assert received.get("type") == "fbr_active_environment_changed"
        assert received.get("environment") == "SANDBOX"
        assert int(received.get("revision") or 0) > 0
    finally:
        if token:
            settings_service.unsubscribe(token)
        settings_service.env_path = original_env_path


def test_should_regenerate_invoice_number_rules():
    assert should_regenerate_invoice_number("", "EHS", ["usin"]) is True
    assert should_regenerate_invoice_number("ERROR", "EHS", ["usin"]) is True
    assert should_regenerate_invoice_number("EHS-0001", "EHS", ["usin"]) is True
    assert should_regenerate_invoice_number("ABC-0001", "EHS", ["usin"]) is False
    assert should_regenerate_invoice_number("EHS-0001", "EHS", []) is False
