"""Live submission of a Spare Parts sale's FBR payload to FBR's POS
Integration endpoint.

Kept separate from fbr_payload_service.py on purpose: that module only
ever builds a payload dict and explicitly makes no network calls (its
own test suite assumes zero network side effects). This module owns
the impure part - the actual HTTP POST and persisting the outcome.

Independent implementation, same as fbr_payload_service.py:
- Imports nothing from app.api.fbr_client, app.services.invoice_service,
  or any app.db.models table.
- Uses only this module's own settings (settings_service.get_settings /
  get_fbr_environment) for the POS ID / Auth Token / API Base URL /
  environment selection.
- Never touches, calls, or is called by the main app's invoice upload
  path - see spare_parts/__init__.py.
"""
from __future__ import annotations

import datetime as dt
import json

import requests
from sqlalchemy.orm import Session
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from spare_parts.db.models import SpSale
from spare_parts.errors import SparePartsValidationError
from spare_parts.services import fbr_payload_service, sales_service, settings_service
from spare_parts.logging_config import get_logger

logger = get_logger(__name__)

STATUS_NOT_SUBMITTED = "NOT_SUBMITTED"
STATUS_SUBMITTED = "SUBMITTED"
STATUS_FAILED = "FAILED"

_SUCCESS_CODE = "100"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type(requests.RequestException),
    reraise=True,
)
def _post_to_fbr(url: str, payload: dict, auth_token: str, verify_ssl: bool) -> requests.Response:
    headers = {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    response = requests.post(url, json=payload, headers=headers, timeout=(10, 60), verify=verify_ssl)
    response.raise_for_status()
    return response


def _mark_failed(db: Session, sale: SpSale, error_message: str, raw_response: str | None = None) -> None:
    sale.fbr_submission_status = STATUS_FAILED
    sale.fbr_last_error = error_message
    sale.fbr_last_response = raw_response
    sale.fbr_submitted_at = dt.datetime.utcnow()
    db.commit()


def submit_sale_to_fbr(db: Session, sale_id: int, *, force: bool = False) -> SpSale:
    """Builds, validates, and actually POSTs the FBR payload for one
    POSTED sale to the currently-selected environment's POS endpoint,
    then persists the outcome on that same sp_sales row (only the
    LATEST attempt is kept, not a full history).

    force=False (default) refuses to resubmit a sale already marked
    SUBMITTED - callers should catch the resulting SparePartsValidationError,
    confirm with the user, and retry with force=True if they want to
    resubmit anyway.

    Raises SparePartsValidationError for every caller-facing failure
    (sale not found, not POSTED, already submitted, payload validation
    errors, missing FBR configuration, FBR rejection, network failure)
    so UI code only ever needs one except clause."""
    sale = sales_service.get_sale(db, sale_id)
    if not sale:
        raise SparePartsValidationError(f"Sale id={sale_id} not found.")

    if sale.fbr_submission_status == STATUS_SUBMITTED and not force:
        raise SparePartsValidationError(
            f"Sale {sale.sale_no} was already submitted to FBR "
            f"(Invoice Number: {sale.fbr_invoice_number}). Confirm to resubmit."
        )

    # Check FBR configuration before building a payload that embeds it
    # (a blank POS ID would otherwise surface as a confusing payload
    # validation error instead of this clear "not configured" message).
    settings = settings_service.get_settings(db)
    env_settings = settings_service.get_fbr_environment(db, settings.fbr_environment)

    api_base_url = (env_settings.api_base_url or "").strip()
    pos_id = (env_settings.pos_id or "").strip()
    auth_token = (env_settings.auth_token or "").strip()
    if not pos_id or not auth_token or not api_base_url:
        raise SparePartsValidationError(
            f"FBR is not configured for the {settings.fbr_environment} environment "
            "(missing POS ID, Auth Token, and/or API Base URL). Configure it on the "
            "Spare Parts Settings page first."
        )
    if not api_base_url.lower().startswith("http"):
        raise SparePartsValidationError(
            f"API Base URL for {settings.fbr_environment} doesn't look like a valid URL: {api_base_url!r}"
        )

    # build_sale_payload itself rejects a non-POSTED sale.
    payload = fbr_payload_service.build_sale_payload(db, sale)

    errors = fbr_payload_service.validate_payload(payload)
    if errors:
        raise SparePartsValidationError("Payload is not valid for FBR submission: " + "; ".join(errors))

    is_production = (settings.fbr_environment or "").upper() == "PRODUCTION"

    try:
        http_response = _post_to_fbr(api_base_url, payload, auth_token, verify_ssl=is_production)
    except requests.RequestException as e:
        logger.error(f"FBR submission network failure for sale {sale.sale_no}: {e}", exc_info=True)
        response_text = getattr(getattr(e, "response", None), "text", None)
        _mark_failed(db, sale, f"Could not reach FBR: {e}", response_text)
        raise SparePartsValidationError(f"Could not reach FBR: {e}")

    try:
        response_json = http_response.json()
    except ValueError:
        logger.error(f"FBR returned a non-JSON response for sale {sale.sale_no}: {http_response.text[:500]}")
        _mark_failed(db, sale, "FBR returned an unexpected (non-JSON) response.", http_response.text[:2000])
        raise SparePartsValidationError("FBR returned an unexpected (non-JSON) response.")

    code = str(response_json.get("Code"))
    if code == _SUCCESS_CODE:
        sale.fbr_submission_status = STATUS_SUBMITTED
        sale.fbr_invoice_number = response_json.get("InvoiceNumber") or sale.fbr_invoice_number
        sale.fbr_submitted_at = dt.datetime.utcnow()
        sale.fbr_last_error = None
        sale.fbr_last_response = json.dumps(response_json)
        db.commit()
        db.refresh(sale)
        logger.info(f"Sale {sale.sale_no} submitted to FBR - invoice number {sale.fbr_invoice_number}.")
        return sale

    error_message = response_json.get("Response") or f"Unexpected FBR response: {response_json}"
    _mark_failed(db, sale, str(error_message), json.dumps(response_json))
    logger.warning(f"FBR rejected sale {sale.sale_no}: {error_message}")
    raise SparePartsValidationError(f"FBR rejected the submission: {error_message}")
