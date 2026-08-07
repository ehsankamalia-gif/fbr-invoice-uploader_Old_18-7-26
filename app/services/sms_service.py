import logging
import re
import requests
import base64
import socket
import uuid
import time
import threading
from typing import List, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_result, RetryError
from app.db.models import SMSQueue, SMSStatus, SMSConfiguration
from app.db.session import SessionLocal
import datetime as dt
from sqlalchemy import or_
from android_sms_gateway import APIClient, Message
from android_sms_gateway.domain import TextMessage

logger = logging.getLogger(__name__)


def normalize_pk_mobile(phone_number: Optional[str]) -> str:
    """Normalize a Pakistan mobile phone number for Android SMS gateway compatibility.

    Accepts formats like:
      03001234567, 0300-123-4567, 0300 123 4567,
      +923001234567, 923001234567, 00923001234567,
      3001234567 (7-10 digits assumed to be missing 03 prefix)
    Returns the canonical 11-digit format: 03XXXXXXXXX.

    Use `format_phone_for_gateway()` if you need the 923/E.164 variant that
    Android SMS gateway HTTP APIs typically require.
    """
    if not phone_number:
        return ""

    raw = str(phone_number).strip()
    digits = re.sub(r"\D", "", raw)

    if not digits:
        return raw

    if len(digits) == 11 and digits.startswith("03"):
        return digits

    if len(digits) == 12 and digits.startswith("923"):
        return "0" + digits[2:]

    if len(digits) == 14 and digits.startswith("00923"):
        return "0" + digits[4:]

    if len(digits) == 10 and digits.startswith("3"):
        return "0" + digits

    if 7 <= len(digits) <= 9 and not digits.startswith("0"):
        return "03" + digits[-9:]

    return raw


def format_phone_for_gateway(phone_number: Optional[str]) -> str:
    """Convert a phone number to the format MOST likely to be accepted by Android
    SMS gateway HTTP APIs.

    Most gateway apps (including the official android_sms_gateway server running on
    the phone that listens on /message, /sms, or /send endpoints) reject the local
    03XXXXXXXXX Pakistan format and require a country-code prefixed variant without
    the leading zero.

    Strategy:
      - Valid PK mobile number (after normalize_pk_mobile returns 03XXXXXXXXX) -> 923XXXXXXXXX
      - Numbers with + kept (e.g. landline) -> strip + but keep digits
      - Everything else -> keep digits only (no spaces, dashes, etc.)
    """
    if not phone_number:
        return ""

    normalized = normalize_pk_mobile(phone_number)
    digits = re.sub(r"\D", "", normalized)

    # Valid Pakistan mobile: convert 03XXXXXXXXX -> 923XXXXXXXXX (gateway-standard format)
    if len(digits) == 11 and digits.startswith("03"):
        return "92" + digits[1:]

    return digits if digits else normalized


class SMSService:
    def __init__(self):
        # Connection pooling
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "FBR-Uploader/2.0 (Clean Architecture)"})
        self._stop_event = threading.Event()
        self._scheduler_thread: Optional[threading.Thread] = None

    def send_sms_via_wifi(self, ip: str, port: str, phone_number: str, msg_content: str, 
                          api_key: Optional[str] = None, 
                          username: Optional[str] = None, 
                          password: Optional[str] = None,
                          use_https: bool = False,
                          total_timeout: float = 30.0) -> tuple[bool, str]:
        """
        Sends an SMS using official gateway protocol with connection pooling and fast discovery.
        Includes transaction tracking and robust error handling.
        """
        tx_id = str(uuid.uuid4())[:8]
        start_time = time.time()
        protocol = "https" if use_https else "http"
        
        # Normalize Pakistan mobile number before sending (critical for Android SMS gateway)
        # We keep a normalized record for logs, then produce the gateway-standard 923/E.164
        # format which all Android HTTP SMS gateway endpoints expect.
        phone_number = normalize_pk_mobile(phone_number)
        if not phone_number:
            return False, "Phone number is empty after normalization."
        gateway_phone = format_phone_for_gateway(phone_number)
        if not gateway_phone:
            return False, "Phone number is empty after gateway formatting."

        # Sanitize IP/Hostname: remove protocol prefixes and handle accidental port inclusion
        ip = (ip or "").strip()
        if "://" in ip:
            ip = ip.split("://")[-1]
        if ":" in ip:
            # If user entered 192.168.1.10:8080, we extract the IP and potentially use that port if not specified
            parts = ip.split(":")
            ip = parts[0]
            if not port or port == "8080":
                port = parts[1]
        
        # Remove any trailing slashes or spaces
        ip = ip.replace("/", "").strip()

        logger.info(f"[TX:{tx_id}] --- Starting SMS Send to {phone_number} at {protocol}://{ip}:{port} ---")
        
        if not ip:
            return False, "Gateway IP/Hostname is empty after sanitization."
        
        def check_timeout():
            if time.time() - start_time > total_timeout:
                raise TimeoutError(f"Total time limit ({total_timeout}s) reached for SMS transaction.")

        # 0. Fast Connectivity Check (Socket Test)
        try:
            logger.info(f"[TX:{tx_id}] Connection check: Testing {ip}:{port}")
            # Increase timeout for public IP / high-latency networks
            sock_timeout = 5.0 if "." in ip and not ip.startswith(("192.", "10.", "172.16.")) else 2.5
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(sock_timeout)
            
            try:
                p_int = int(port or "8080")
            except ValueError:
                return False, f"Invalid port: {port}. Please use a numeric port (e.g., 8080)."

            try:
                result = sock.connect_ex((ip, p_int))
                sock.close()
            except socket.gaierror:
                return False, f"Invalid Gateway IP or Hostname: '{ip}'. Please ensure it is a correct IP address or domain name without 'http://'."
            except Exception as e:
                return False, f"Socket error: {str(e)}"
            if result != 0:
                reason = "Port closed or unreachable" if result == 10061 else f"Error code {result}"
                return False, f"Unreachable: {ip}:{port} ({reason}). Check gateway connectivity."
        except Exception as e:
            return False, f"Connection error: {str(e)}"

        # 1. Prepare Authentication & Payload
        headers = {"Content-Type": "application/json"}
        if username and password:
            auth_str = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {auth_str}"
        elif api_key:
            headers["Authorization"] = f"Bearer {api_key}"
            headers["X-API-KEY"] = api_key
        
        payload = {
            "phoneNumbers": [gateway_phone],
            "textMessage": {"text": msg_content}
        }

        # Also log the raw -> normalized -> gateway mapping for debugging
        logger.info(f"[TX:{tx_id}] Phone normalised: original={phone_number!r}, gateway_fmt={gateway_phone!r}")

        # 2. Try Official & Quick Protocols with Tenacity Retries
        last_error = "All prioritized endpoints and protocols failed."
        
        # Prepare attempts
        protocols_to_try = [protocol]
        if protocol == "https": protocols_to_try.append("http")
        else: protocols_to_try.append("https")
        
        # Add simpler endpoint variants for basic Android SMS Gateways
        endpoints = ["/message", "/sms", "/send", "/api/send", "/api/v1/sms", "/"]

        for proto in protocols_to_try:
            for ep in endpoints:
                url = f"{proto}://{ip}:{port}{ep}"
                
                @retry(
                    stop=stop_after_attempt(2),
                    wait=wait_exponential(multiplier=1, min=1, max=3),
                    retry=retry_if_result(lambda x: x[0] is False),
                    reraise=False
                )
                def single_sms_attempt():
                    try:
                        check_timeout()
                        logger.info(f"[TX:{tx_id}] Probing SMS endpoint: {url}")
                        
                        # Some gateways expect different payload formats
                        # Try the standard one first, then a flat one
                        try:
                            response = self.session.post(url, json=payload, headers=headers, timeout=6.0)
                        except:
                            return False, "Request failed"

                        if response.status_code in [200, 201, 202]:
                            resp_text = response.text.lower()
                            if "<html" not in resp_text:
                                return True, f"Success: {response.status_code}"
                        
                        # Retry with flat payload for simpler gateways
                        flat_payload = {
                            "to": phone_number,
                            "message": msg_content
                        }
                        response = self.session.post(url, json=flat_payload, headers=headers, timeout=6.0)
                        if response.status_code in [200, 201, 202]:
                             return True, f"Success: {response.status_code} (Flat Payload)"

                        return False, f"Status {response.status_code}: {response.text[:100]}"
                    except Exception as e:
                        return False, f"Error: {str(e)}"

                try:
                    success, msg = single_sms_attempt()
                    if success:
                        logger.info(f"[TX:{tx_id}] Result: {msg} in {time.time() - start_time:.2f}s")
                        return True, msg
                    last_error = msg
                except: continue

        return False, f"SMS Error: {last_error}"

    def send_sms_via_cloud(self, api_url: str, phone_number: str, msg_content: str,
                           api_key: Optional[str] = None,
                           username: Optional[str] = None,
                           password: Optional[str] = None) -> tuple[bool, str]:
        """
        Sends an SMS via a Cloud Server Gateway using an adaptive multi-profile approach.
        Tries different authentication and payload methods until one succeeds.
        """
        tx_id = str(uuid.uuid4())[:8]
        logger.info(f"[CLOUD:{tx_id}] Attempting to send to {phone_number} via {api_url}")

        # Normalize Pakistan mobile number before sending, then produce the gateway-friendly
        # 923/E.164 format. Also expose both formats so the "catch-all" payload_base can
        # contain every format the remote server might expect.
        phone_number = normalize_pk_mobile(phone_number)
        if not phone_number:
            return False, "Phone number is empty after normalization."
        gateway_phone = format_phone_for_gateway(phone_number)
        e164_with_plus = "+" + gateway_phone if gateway_phone and not gateway_phone.startswith("+") else gateway_phone

        try:
            # 1. Define Common Payload fields (send multiple field names + formats because
            #    every cloud gateway uses different fields and number formats)
            payload_base = {
                "to": gateway_phone,
                "mobile": gateway_phone,
                "recipient": gateway_phone,
                "number": gateway_phone,
                "receiver": gateway_phone,
                "phone": gateway_phone,
                "phone_number": gateway_phone,
                # Also include E.164 +923... variant for international gateways
                "to_e164": e164_with_plus,
                "mobile_e164": e164_with_plus,
                # Include local 03 format as fallback for Pakistan-local API servers
                "to_local": phone_number,
                "mobile_local": phone_number,
                "message": msg_content, "msg": msg_content, "text": msg_content, "body": msg_content,
                "sender": "FBR-SYSTEM", "from": "FBR-SYSTEM"
            }

            # 2. Define Auth Profiles to try
            auth_profiles = []
            
            # Profile A: API Key Headers
            if api_key:
                auth_profiles.append({
                    "name": "API Key Headers",
                    "headers": {"Authorization": f"Bearer {api_key}", "X-API-KEY": api_key},
                    "params": {"api_key": api_key, "apikey": api_key}
                })

            # Profile B: Basic Auth + Custom Headers
            if username and password:
                auth_str = base64.b64encode(f"{username}:{password}".encode()).decode()
                auth_profiles.append({
                    "name": "Basic Auth + Headers",
                    "headers": {"Authorization": f"Basic {auth_str}", "X-USERNAME": username, "X-PASSWORD": password},
                    "params": {}
                })
                
                # Profile C: Credentials in Query Params (Common in Pakistan/Local APIs)
                auth_profiles.append({
                    "name": "Query Param Auth",
                    "headers": {},
                    "params": {
                        "username": username, "user": username, "u": username,
                        "password": password, "pass": password, "p": password, "pwd": password
                    }
                })

            # If no credentials provided, try one anonymous profile
            if not auth_profiles:
                auth_profiles.append({"name": "Anonymous", "headers": {}, "params": {}})

            last_error = "No compatible auth profile found."

            # 3. Iteratively try profiles with different HTTP methods
            for profile in auth_profiles:
                logger.info(f"[CLOUD:{tx_id}] Trying Auth Profile: {profile['name']}")
                
                current_headers = {"User-Agent": "FBR-Uploader/2.0"}
                current_headers.update(profile["headers"])
                
                current_params = profile["params"].copy()
                
                # Try POST JSON, GET, and POST Form for each auth profile
                methods = [
                    ("POST", "json"),
                    ("GET", "params"),
                    ("POST", "data")
                ]

                for method, target in methods:
                    try:
                        full_payload = payload_base.copy()
                        
                        if method == "POST":
                            if target == "json":
                                response = self.session.post(api_url, json=full_payload, params=current_params, headers=current_headers, timeout=12.0)
                            else: # Form data
                                response = self.session.post(api_url, data=full_payload, params=current_params, headers=current_headers, timeout=12.0)
                        else: # GET
                            full_payload.update(current_params)
                            response = self.session.get(api_url, params=full_payload, headers=current_headers, timeout=12.0)

                        # Inspect Response
                        status = response.status_code
                        body = response.text.lower()
                        
                        # 200 OK is only success if body doesn't contain error keywords
                        if status in [200, 201, 202]:
                            auth_errors = ["invalid", "error", "failed", "unauthorized", "wrong", "denied", "mismatch"]
                            if not any(err in body for err in auth_errors):
                                return True, f"Cloud Success ({profile['name']} via {method})"
                            else:
                                last_error = f"Server rejected credentials or message: {response.text}"
                                logger.warning(f"[CLOUD:{tx_id}] {profile['name']} {method} returned 200 but body contains error: {response.text}")
                        elif status in [401, 403]:
                            last_error = f"Authentication Failed (Status {status}): {response.text}"
                        else:
                            last_error = f"Server Error (Status {status}): {response.text}"

                    except Exception as e:
                        logger.warning(f"[CLOUD:{tx_id}] {profile['name']} {method} failed: {e}")
                        last_error = f"Connection failed: {str(e)}"

            return False, last_error
                
        except Exception as e:
            logger.error(f"[CLOUD:{tx_id}] Critical Failure: {e}")
            return False, f"Cloud connection failed: {str(e)}"

    def process_queue(self):
        """Processes the SMS queue using the configured gateway type."""
        db = SessionLocal()
        try:
            # Get config
            config = db.query(SMSConfiguration).filter(SMSConfiguration.is_enabled == True).first()
            if not config:
                return

            now = dt.datetime.utcnow()
            pending_items = (
                db.query(SMSQueue)
                .filter(SMSQueue.channel == "SMS")
                .filter(SMSQueue.status.in_([SMSStatus.PENDING, SMSStatus.FAILED, SMSStatus.SCHEDULED]))
                .filter(or_(SMSQueue.next_retry_at.is_(None), SMSQueue.next_retry_at <= now))
                .filter(SMSQueue.retry_count < SMSQueue.max_retries)
                .order_by(SMSQueue.id.asc())
                .limit(25)
                .all()
            )
            for item in pending_items:
                # Pre-normalize the phone number so even legacy DB records (bad formats
                # stored before the normalize_pk_mobile() function existed) get corrected
                # before dispatch to the gateway.  This specifically fixes the "invalid
                # phone number" error when old bookings stored e.g. 0300123456 or +923
                # without local formatting.
                if item.phone_number:
                    normalized = normalize_pk_mobile(item.phone_number)
                    if normalized and normalized != item.phone_number:
                        item.phone_number = normalized
                        db.commit()

                item.status = SMSStatus.SENDING
                db.commit()

                success = False
                error_msg = ""

                # 1. Handle SMS Channel
                if (config.gateway_type or "").upper() == 'CLOUD' and config.api_url:
                    success, error_msg = self.send_sms_via_cloud(
                        (config.api_url or "").strip(),
                        (item.phone_number or "").strip(),
                        (item.message or "").strip(),
                        (config.api_key or None),
                        (config.cloud_username or None),
                        (config.cloud_password or None)
                    )
                elif config.gateway_ip:
                    success, error_msg = self.send_sms_via_wifi(
                        (config.gateway_ip or "").strip(),
                        (config.gateway_port or "8080"),
                        (item.phone_number or "").strip(),
                        (item.message or "").strip(),
                        (config.api_key or None),
                        (config.gateway_username or None),
                        (config.gateway_password or None),
                        use_https=bool(getattr(config, "use_https", False))
                    )
                else:
                    error_msg = "SMS Gateway not configured properly."
                
                if success:
                    item.status = SMSStatus.SENT
                    item.sent_at = dt.datetime.utcnow()
                    item.error_message = None
                    item.next_retry_at = None
                    logger.info(f"[QUEUE] {item.channel} {item.id} successfully sent to {item.phone_number}")
                else:
                    item.retry_count = int(item.retry_count or 0) + 1
                    item.error_message = (error_msg or "Unknown error")[:255]
                    history = item.retry_history or []
                    history.append({"ts": dt.datetime.utcnow().isoformat(), "attempt": int(item.retry_count), "error": item.error_message})
                    item.retry_history = history

                    if int(item.retry_count) >= int(item.max_retries or 3):
                        item.status = SMSStatus.FAILED
                        item.next_retry_at = None
                        logger.error(f"[QUEUE] {item.channel} {item.id} FAILED permanently after {item.retry_count} attempts: {item.error_message}")
                    else:
                        item.status = SMSStatus.PENDING
                        backoff = min(3600, 30 * (2 ** max(0, int(item.retry_count) - 1)))
                        item.next_retry_at = dt.datetime.utcnow() + dt.timedelta(seconds=backoff)
                        logger.warning(f"[QUEUE] {item.channel} {item.id} failed attempt {item.retry_count}. Retrying at {item.next_retry_at}. Error: {item.error_message}")
                
                db.commit()
        except Exception as e:
            logger.error(f"Error processing SMS queue: {e}")
            db.rollback()
        finally:
            db.close()

    def queue_invoice_sms(self, db, invoice):
        """Queues SMS for a new invoice."""
        config = db.query(SMSConfiguration).first()
        if not config:
            return

        if not bool(getattr(config, "is_enabled", False)):
            return
        if not bool(getattr(config, "invoice_sms_enabled", True)):
            return

        customer_name = invoice.customer.name if invoice.customer else "Customer"
        raw_phone = invoice.customer.phone if invoice.customer else None
        phone = normalize_pk_mobile(raw_phone) if raw_phone else None
        
        if not phone:
            logger.warning(f"No valid phone number for customer in invoice {invoice.invoice_number} (raw={raw_phone!r})")
            return

        message = config.invoice_template.format(
            customer=customer_name,
            invoice_no=invoice.invoice_number,
            amount=invoice.total_amount,
            fbr_id=invoice.fbr_invoice_number or "Pending"
        )

        new_sms = SMSQueue(
            phone_number=phone,
            message=message,
            invoice_id=invoice.id,
            channel="SMS"
        )
        db.add(new_sms)
        db.commit()

    def queue_spare_ledger_sms(self, db, transaction):
        """Queues SMS for a new spare ledger transaction."""
        config = db.query(SMSConfiguration).first()
        if not config:
            return

        if not bool(getattr(config, "is_enabled", False)):
            return

        # Determine if it's credit or debit BEFORE reading the owner phone, so we can skip early if disabled
        is_credit = transaction.trans_type == "CREDIT"
        if is_credit:
            if not bool(getattr(config, "spare_credit_sms_enabled", True)):
                return
        else:
            if not bool(getattr(config, "spare_debit_sms_enabled", True)):
                return

        owner_phone = normalize_pk_mobile(getattr(config, "owner_phone_number", None))
        if not owner_phone:
            logger.warning("No owner phone number configured in SMS settings")
            return

        amount = transaction.amount
        source = "Hard Cash" if transaction.cash_type == "HARD_CASH" else "Bank"
        if not is_credit:
            source = "SP Order"

        if is_credit:
            template = config.spare_ledger_credit_template
        else:
            template = config.spare_ledger_debit_template

        if not template:
            if is_credit:
                template = "Spare Ledger: Credit received of Rs. {amount} via {source}. Reference: {reference}. Description: {description}. Balance: Rs. {balance}"
            else:
                template = "Spare Ledger: Debit/Order of Rs. {amount} via {source}. Reference: {reference}. Description: {description}. Balance: Rs. {balance}"

        # Compute current spare ledger running balance AFTER the current transaction is applied.
        # MUST EXACTLY match the UI CURRENT BALANCE card calculation in main_window._reload_spare_ledger
        # which EXCLUDES any rows whose description starts with "Advance Booking -".
        # UI formula (see main_window.py lines 10846-10850, 10875-10895, 10959-10967):
        #   all_rows WHERE description IS NULL OR description NOT LIKE "Advance Booking -%"
        #   running_balance = sum(CREDIT amounts) - sum(DEBIT amounts) over those rows.
        try:
            from app.db.models import SpareLedgerTransaction
            from sqlalchemy import func, and_, or_

            ledger_exclusion_filter = or_(
                SpareLedgerTransaction.description.is_(None),
                ~SpareLedgerTransaction.description.like("Advance Booking -%"),
            )

            sum_credit = (
                db.query(func.coalesce(func.sum(SpareLedgerTransaction.amount), 0.0))
                .filter(
                    and_(
                        SpareLedgerTransaction.trans_type == "CREDIT",
                        ledger_exclusion_filter,
                    )
                )
                .scalar()
                or 0.0
            )
            sum_debit = (
                db.query(func.coalesce(func.sum(SpareLedgerTransaction.amount), 0.0))
                .filter(
                    and_(
                        SpareLedgerTransaction.trans_type == "DEBIT",
                        ledger_exclusion_filter,
                    )
                )
                .scalar()
                or 0.0
            )

            # Make sure current transaction effect is included even if not flushed yet,
            # BUT only if it, too, passes the same Advance Booking exclusion filter the UI uses.
            current_id = getattr(transaction, "id", None)
            current_desc = getattr(transaction, "description", None)
            is_booking_row = (
                isinstance(current_desc, str)
                and current_desc.startswith("Advance Booking -")
            )
            current_amount = float(transaction.amount or 0.0) if not is_booking_row else 0.0

            if current_id is None:
                # Not flushed: manually add the current transaction's contribution (if not booking).
                if is_credit:
                    sum_credit += current_amount
                else:
                    sum_debit += current_amount
            else:
                # Flushed - check whether DB aggregate already accounted for it.
                if is_credit:
                    included = (
                        db.query(func.count(SpareLedgerTransaction.id))
                        .filter(
                            SpareLedgerTransaction.id == int(current_id),
                            SpareLedgerTransaction.trans_type == "CREDIT",
                            ledger_exclusion_filter,
                        )
                        .scalar()
                        or 0
                    )
                    if int(included) < 1 and not is_booking_row:
                        sum_credit += current_amount
                else:
                    included = (
                        db.query(func.count(SpareLedgerTransaction.id))
                        .filter(
                            SpareLedgerTransaction.id == int(current_id),
                            SpareLedgerTransaction.trans_type == "DEBIT",
                            ledger_exclusion_filter,
                        )
                        .scalar()
                        or 0
                    )
                    if int(included) < 1 and not is_booking_row:
                        sum_debit += current_amount

            current_balance = float(sum_credit or 0.0) - float(sum_debit or 0.0)
        except Exception as e:
            logger.error(f"Failed to compute spare ledger balance for SMS: {e}", exc_info=True)
            # Fallback to signed transaction delta so balance still gives directional info.
            current_balance = (float(transaction.amount or 0.0) if is_credit else (-1.0 * float(transaction.amount or 0.0)))

        # Build template values dict with a "missing returns empty string" default so
        # older/customized templates without {balance} (or any new placeholder) don't crash.
        from collections import defaultdict

        _d = {
            "amount": amount,
            "source": source,
            "reference": transaction.reference_number or "N/A",
            "description": transaction.description or "N/A",
            "balance": f"{current_balance:,.2f}",
        }
        safe_values = defaultdict(lambda: "")
        safe_values.update(_d)

        message = template.format_map(safe_values)

        new_sms = SMSQueue(
            phone_number=owner_phone,
            message=message,
            channel="SMS"
        )
        db.add(new_sms)
        db.flush()

        # Spare ledger notifications should go out immediately, just like booking SMS,
        # instead of waiting only for a later queue tick.
        success = False
        result_msg = ""
        try:
            if (config.gateway_type or "").upper() == "CLOUD" and config.api_url:
                success, result_msg = self.send_sms_via_cloud(
                    (config.api_url or "").strip(),
                    owner_phone,
                    message,
                    (config.api_key or None),
                    (config.cloud_username or None),
                    (config.cloud_password or None),
                )
            elif config.gateway_ip:
                success, result_msg = self.send_sms_via_wifi(
                    (config.gateway_ip or "").strip(),
                    (config.gateway_port or "8080"),
                    owner_phone,
                    message,
                    (config.api_key or None),
                    (config.gateway_username or None),
                    (config.gateway_password or None),
                    use_https=bool(getattr(config, "use_https", False)),
                )
            else:
                result_msg = "SMS Gateway not configured properly."
        except Exception as e:
            result_msg = str(e)

        if success:
            new_sms.status = SMSStatus.SENT
            new_sms.sent_at = dt.datetime.utcnow()
            new_sms.error_message = None
        elif result_msg:
            new_sms.status = SMSStatus.FAILED
            new_sms.error_message = str(result_msg)[:255]
        db.commit()

    def _is_feature_enabled(self, db, feature_flag_attr: str) -> bool:
        """Return True only if (a) master SMS is enabled AND (b) the specific per-feature flag is True or missing.

        If the config row is missing, returns False (safer than sending SMS without explicit config).
        Falls back to True for the specific feature flag to preserve behaviour for legacy installs without the columns.
        """
        try:
            config = db.query(SMSConfiguration).first()
        except Exception as e:
            logger.warning(f"_is_feature_enabled: could not read SMSConfiguration: {e}")
            return False
        if config is None:
            return False
        if not bool(getattr(config, "is_enabled", False)):
            return False
        return bool(getattr(config, feature_flag_attr, True))

    def _resolve_template(self, db, template_attr: str, fallback: str) -> str:
        """Return template from DB SMSConfiguration row, or the fallback if missing / empty."""
        try:
            cfg = db.query(SMSConfiguration).first()
            if cfg is None:
                return fallback
            tmpl = getattr(cfg, template_attr, None)
            return tmpl if tmpl else fallback
        except Exception:
            return fallback

    def _get_phone_for_customer(self, db, customer_id: int, fallback_phone=None) -> Optional[str]:
        """Fetch customer's phone number by ID and normalize it."""
        try:
            from app.db.models import Customer
            cust = db.query(Customer).filter(Customer.id == int(customer_id)).first()
            if cust and getattr(cust, "phone", None):
                return normalize_pk_mobile(cust.phone)
        except Exception:
            pass
        if fallback_phone:
            return normalize_pk_mobile(fallback_phone)
        return None

    def _queue_template_sms(self, db, phone: Optional[str], message: str, reference_type=None, reference_id=None, recipient_name=None):
        """Queue an SMS if SMS is enabled; does nothing if config doesn't exist / is disabled.

        reference_type / reference_id are accepted for logging/forward-compat but NOT passed to
        SMSQueue (which doesn't have those columns). They're written to the debug log only).
        """
        try:
            config = db.query(SMSConfiguration).first()
        except Exception:
            config = None
        if config is None or not bool(getattr(config, "is_enabled", False)):
            return
        p = normalize_pk_mobile(phone)
        if not p:
            logger.warning(f"SMS queued but no valid phone number (message={message!r})")
            return
        payload = dict(
            phone_number=p,
            message=message,
            channel="SMS"
        )
        if recipient_name:
            payload["recipient_name"] = str(recipient_name)[:100]
        try:
            new_sms = SMSQueue(**payload)
            db.add(new_sms)
            logger.info(
                f"Queued SMS to {p} ({recipient_name or 'n/a'})"
                + (f" [{reference_type}#{reference_id}" if reference_type else "")
            )
        except Exception as e:
            logger.error(f"Failed to queue SMS to {p}: {e}", exc_info=True)

    def queue_credit_sale_sms(self, db, sale_id: int, items, advance_payment: float,
                              customer_id: int, fallback_phone=None):
        """Queue one SMS per chassis in a newly-created credit sale (BuyerLedger SALE debit entries)."""
        try:
            if not self._is_feature_enabled(db, "credit_sale_payment_sms_enabled"):
                return
            phone = self._get_phone_for_customer(db, customer_id, fallback_phone)
            if not phone:
                logger.warning(f"No phone for buyer/customer {customer_id} in credit sale {sale_id}")
                return
            tmpl = self._resolve_template(
                db, "credit_sale_template",
                "Dear {customer}, credit sale of {model} (Chassis: {chassis}) is confirmed. Credit: Rs. {credit_price}. Advance: Rs. {advance}. Balance: Rs. {balance}."
            )
            try:
                from app.db.models import Customer
                cust = db.query(Customer).filter(Customer.id == int(customer_id)).first()
                customer_name = cust.name if cust else f"Customer #{customer_id}"
            except Exception:
                customer_name = f"Customer #{customer_id}"

            total_credit = 0.0
            if items:
                total_credit = sum(float(getattr(it, "credit_price", 0.0) or 0.0) for it in items)
            running_balance = total_credit - float(advance_payment or 0.0)

            try:
                from app.db.models import CreditSaleItem
                sale_items = list(items)
                if sale_items and isinstance(sale_items[0], CreditSaleItem):
                    # Model instances - send per-chassis detail SMS if >1 items else aggregate
                    if len(sale_items) > 1:
                        per_item_balance = total_credit - float(advance_payment or 0.0)
                        for item in sale_items:
                            msg = tmpl.format(
                                customer=customer_name,
                                model=getattr(item, "model", "Unknown"),
                                chassis=getattr(item, "chassis_number", "N/A"),
                                credit_price=float(getattr(item, "credit_price", 0.0) or 0.0),
                                advance=float(advance_payment or 0.0),
                                balance=per_item_balance
                            )
                            self._queue_template_sms(db, phone, msg, reference_type="CREDIT_SALE", reference_id=int(sale_id))
                    else:
                        item = sale_items[0] if sale_items else None
                        msg = tmpl.format(
                            customer=customer_name,
                            model=getattr(item, "model", "Unknown") if item else "Unknown",
                            chassis=getattr(item, "chassis_number", "N/A") if item else "N/A",
                            credit_price=total_credit,
                            advance=float(advance_payment or 0.0),
                            balance=running_balance
                        )
                        self._queue_template_sms(db, phone, msg, reference_type="CREDIT_SALE", reference_id=int(sale_id))
                else:
                    # items are plain dicts
                    if len(items) > 1:
                        for item in items:
                            msg = tmpl.format(
                                customer=customer_name,
                                model=item.get("model", "Unknown"),
                                chassis=item.get("chassis_number", "N/A"),
                                credit_price=float(item.get("credit_price", 0.0) or 0.0),
                                advance=float(advance_payment or 0.0),
                                balance=running_balance
                            )
                            self._queue_template_sms(db, phone, msg, reference_type="CREDIT_SALE", reference_id=int(sale_id))
                    else:
                        item = items[0] if items else {}
                        msg = tmpl.format(
                            customer=customer_name,
                            model=item.get("model", "Unknown"),
                            chassis=item.get("chassis_number", "N/A"),
                            credit_price=total_credit,
                            advance=float(advance_payment or 0.0),
                            balance=running_balance
                        )
                        self._queue_template_sms(db, phone, msg, reference_type="CREDIT_SALE", reference_id=int(sale_id))
            except Exception as e:
                logger.error(f"queue_credit_sale_sms failed for sale {sale_id}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"queue_credit_sale_sms outer failed: {e}", exc_info=True)

    def queue_credit_payment_sms(self, db, payment_id: int, buyer_id: int, amount: float,
                                  penalty_amount: float, discount_amount: float, new_balance: float):
        """Queue SMS when a BuyerLedger PAYMENT (installment receive) is created."""
        try:
            if not self._is_feature_enabled(db, "credit_sale_payment_sms_enabled"):
                return
            phone = self._get_phone_for_customer(db, buyer_id, None)
            if not phone:
                logger.warning(f"No phone for buyer {buyer_id} in credit payment {payment_id}")
                return
            tmpl = self._resolve_template(
                db, "credit_payment_template",
                "Dear {customer}, installment of Rs. {amount} received. Penalty: Rs. {penalty}. Discount: Rs. {discount}. Remaining balance: Rs. {balance}."
            )
            try:
                from app.db.models import Customer
                cust = db.query(Customer).filter(Customer.id == int(buyer_id)).first()
                customer_name = cust.name if cust else f"Customer #{buyer_id}"
            except Exception:
                customer_name = f"Customer #{buyer_id}"
            msg = tmpl.format(
                customer=customer_name,
                amount=float(amount or 0.0),
                penalty=float(penalty_amount or 0.0),
                discount=float(discount_amount or 0.0),
                balance=float(new_balance if new_balance is not None else 0.0)
            )
            self._queue_template_sms(db, phone, msg, reference_type="CREDIT_PAYMENT", reference_id=int(payment_id))
        except Exception as e:
            logger.error(f"queue_credit_payment_sms failed for payment {payment_id}: {e}", exc_info=True)

    def queue_finance_sale_sms(self, db, sale, customer_id: int, fallback_phone=None):
        """Queue SMS when a new FinanceCreditSale account is created."""
        try:
            if not self._is_feature_enabled(db, "finance_sale_installment_sms_enabled"):
                return
            from app.db.models import FinanceCreditSale, Customer
            phone = self._get_phone_for_customer(db, customer_id, fallback_phone)
            if not phone:
                logger.warning(f"No phone for finance customer {customer_id} in finance sale {getattr(sale, 'id', None)}")
                return
            tmpl = self._resolve_template(
                db, "finance_sale_template",
                "Dear {customer}, finance account {sale_id} for {model} (Chassis: {chassis}) is confirmed. Finance: Rs. {credit_price}. Down: Rs. {down}. Balance: Rs. {balance}."
            )
            try:
                cust = db.query(Customer).filter(Customer.id == int(customer_id)).first()
                customer_name = cust.name if cust else f"Customer #{customer_id}"
            except Exception:
                customer_name = f"Customer #{customer_id}"
            msg = tmpl.format(
                customer=customer_name,
                sale_id=getattr(sale, "sale_id", "N/A"),
                model=getattr(sale, "model", "Unknown"),
                chassis=getattr(sale, "chassis_no", "N/A"),
                credit_price=float(getattr(sale, "credit_price", 0.0) or 0.0),
                down=float(getattr(sale, "down_payment", 0.0) or 0.0),
                balance=float(getattr(sale, "remaining_balance", getattr(sale, "credit_price", 0.0)) or 0.0)
            )
            self._queue_template_sms(db, phone, msg, reference_type="FINANCE_SALE", reference_id=int(getattr(sale, "id", 0)))
        except Exception as e:
            logger.error(f"queue_finance_sale_sms failed: {e}", exc_info=True)

    def queue_finance_installment_sms(self, db, installment, sale, customer_id: int):
        """Queue SMS when a FinanceInstallment is received against a finance account."""
        try:
            if not self._is_feature_enabled(db, "finance_sale_installment_sms_enabled"):
                return
            from app.db.models import Customer
            phone = self._get_phone_for_customer(db, customer_id, None)
            if not phone:
                logger.warning(f"No phone for finance customer {customer_id} in installment {getattr(installment, 'id', None)}")
                return
            tmpl = self._resolve_template(
                db, "finance_installment_template",
                "Dear {customer}, installment of Rs. {amount} received for {sale_id}. New balance: Rs. {balance}."
            )
            try:
                cust = db.query(Customer).filter(Customer.id == int(customer_id)).first()
                customer_name = cust.name if cust else f"Customer #{customer_id}"
            except Exception:
                customer_name = f"Customer #{customer_id}"
            msg = tmpl.format(
                customer=customer_name,
                amount=float(getattr(installment, "paid_amount", 0.0) or 0.0),
                sale_id=getattr(sale, "sale_id", "N/A") if sale else "N/A",
                balance=float(getattr(sale, "remaining_balance", 0.0) or 0.0) if sale else 0.0
            )
            self._queue_template_sms(db, phone, msg, reference_type="FINANCE_INSTALLMENT", reference_id=int(getattr(installment, "id", 0)))
        except Exception as e:
            logger.error(f"queue_finance_installment_sms failed: {e}", exc_info=True)

    def start_scheduler(self) -> None:
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            return
        self._stop_event.clear()
        self._scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self._scheduler_thread.start()
        logger.info("SMS scheduler started.")

    def stop_scheduler(self) -> None:
        self._stop_event.set()
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            self._scheduler_thread.join(timeout=2)
        try:
            self.session.close()
        except Exception:
            pass
        logger.info("SMS scheduler stopped.")

    def _run_scheduler(self) -> None:
        while not self._stop_event.is_set():
            delay = 5
            db = SessionLocal()
            try:
                config = db.query(SMSConfiguration).filter(SMSConfiguration.is_enabled == True).first()
                if config:
                    delay = int(getattr(config, "delay_seconds", 5) or 5)
            except Exception as e:
                logger.error(f"SMS scheduler config read failed: {e}", exc_info=True)
            finally:
                db.close()

            try:
                self.process_queue()
            except Exception as e:
                logger.error(f"SMS scheduler tick failed: {e}", exc_info=True)

            time.sleep(max(1, int(delay)))

sms_service = SMSService()
