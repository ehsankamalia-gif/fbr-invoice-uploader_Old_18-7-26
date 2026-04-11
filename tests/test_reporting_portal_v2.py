import os

import pytest
from fastapi.testclient import TestClient


os.environ["REPORTING_DISABLE_SCHEDULER"] = "1"


def _client():
    from reporting.main import app

    return TestClient(app)


def test_dashboard_pages_render():
    client = _client()
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert "Reporting Portal" in r.text

    r = client.get("/builder")
    assert r.status_code == 200
    assert "Template Builder" in r.text

    r = client.get("/schedules")
    assert r.status_code == 200
    assert "Scheduled Reports" in r.text


def test_templates_crud_roundtrip():
    client = _client()
    headers = {"X-User-Role": "admin"}

    r = client.get("/api/templates", headers=headers)
    assert r.status_code == 200
    existing = r.json()["items"]

    payload = {"name": "Test Template API", "description": "x", "definition": {"version": 1, "widgets": []}}
    r = client.post("/api/templates", headers=headers, json=payload)
    assert r.status_code == 200
    tid = r.json()["id"]

    r = client.get(f"/api/templates/{tid}", headers=headers)
    assert r.status_code == 200
    assert r.json()["name"] == "Test Template API"

    r = client.put(
        f"/api/templates/{tid}",
        headers=headers,
        json={"name": "Test Template API v2", "description": "y", "definition": {"version": 1, "widgets": [{"type": "kpi", "metric": "total_invoices", "title": "Total"}]}},
    )
    assert r.status_code == 200

    r = client.get(f"/api/templates/{tid}", headers=headers)
    assert r.status_code == 200
    assert r.json()["name"] == "Test Template API v2"

    r = client.get("/api/templates", headers=headers)
    assert r.status_code == 200
    names = [x["name"] for x in r.json()["items"]]
    assert "Test Template API v2" in names


@pytest.mark.parametrize("fmt,expected_type", [
    ("csv", "text/csv"),
    ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ("pdf", "application/pdf"),
    ("pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
])
def test_exports_return_expected_content_type(fmt, expected_type):
    client = _client()
    headers = {"X-User-Role": "admin"}
    r = client.get("/api/templates", headers=headers)
    assert r.status_code == 200
    tid = r.json()["items"][0]["id"]

    r = client.get(f"/export/{fmt}?template_id={tid}&status=ALL", headers=headers)
    assert r.status_code == 200
    assert expected_type in r.headers.get("content-type", "")


def test_legacy_invoices_csv_endpoint():
    client = _client()
    headers = {"X-User-Role": "sales"}
    r = client.get("/invoices.csv", headers=headers)
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
