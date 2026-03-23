import logging
import requests
import base64
import socket
import uuid
import time
from typing import List, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_result, RetryError
from app.db.models import SMSQueue, SMSStatus, SMSConfiguration
from app.db.session import SessionLocal
import datetime as dt
from android_sms_gateway import APIClient, Message
from android_sms_gateway.domain import TextMessage

logger = logging.getLogger(__name__)

class SMSService:
    def __init__(self):
        # Connection pooling
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "FBR-Uploader/2.0 (Clean Architecture)"})

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
        
        logger.info(f"[TX:{tx_id}] --- Starting SMS Send to {phone_number} at {protocol}://{ip}:{port} ---")
        
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
            result = sock.connect_ex((ip, int(port)))
            sock.close()
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
            "phoneNumbers": [phone_number],
            "textMessage": {"text": msg_content}
        }

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
        
        try:
            # 1. Define Common Payload fields
            payload_base = {
                "to": phone_number, "mobile": phone_number, "recipient": phone_number, "number": phone_number, "receiver": phone_number,
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
            config = db.query(SMSConfiguration).first()
            if not config or not config.is_enabled:
                return

            pending_items = db.query(SMSQueue).filter(SMSQueue.status == SMSStatus.PENDING).all()
            for item in pending_items:
                item.status = SMSStatus.SENDING
                db.commit()

                success = False
                error_msg = ""

                # 1. Handle SMS Channel
                if not config.is_enabled:
                    error_msg = "SMS Notifications are disabled."
                elif config.gateway_type == 'CLOUD' and config.api_url:
                    success, error_msg = self.send_sms_via_cloud(
                        config.api_url,
                        item.phone_number,
                        item.message,
                        config.api_key,
                        config.cloud_username,
                        config.cloud_password
                    )
                elif config.gateway_ip:
                    success, error_msg = self.send_sms_via_wifi(
                        config.gateway_ip, 
                        config.gateway_port, 
                        item.phone_number, 
                        item.message,
                        config.api_key,
                        config.gateway_username,
                        config.gateway_password,
                        use_https=config.use_https
                    )
                else:
                    error_msg = "SMS Gateway not configured properly."
                
                if success:
                    item.status = SMSStatus.SENT
                    item.sent_at = dt.datetime.utcnow()
                    logger.info(f"[QUEUE] {item.channel} {item.id} successfully sent to {item.phone_number}")
                else:
                    item.retry_count += 1
                    item.error_message = error_msg
                    if item.retry_count >= 3:
                        item.status = SMSStatus.FAILED
                        logger.error(f"[QUEUE] {item.channel} {item.id} FAILED permanently after {item.retry_count} attempts: {error_msg}")
                    else:
                        item.status = SMSStatus.PENDING # Retry later
                        logger.warning(f"[QUEUE] {item.channel} {item.id} failed attempt {item.retry_count}. Retrying later. Error: {error_msg}")
                
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

        customer_name = invoice.customer.name if invoice.customer else "Customer"
        phone = invoice.customer.phone if invoice.customer else None
        
        if not phone:
            logger.warning(f"No phone number for customer in invoice {invoice.invoice_number}")
            return

        message = config.invoice_template.format(
            customer=customer_name,
            invoice_no=invoice.invoice_number,
            amount=invoice.total_amount,
            fbr_id=invoice.fbr_invoice_number or "Pending"
        )

        # Queue SMS if enabled
        if config.is_enabled:
            new_sms = SMSQueue(
                phone_number=phone,
                message=message,
                invoice_id=invoice.id,
                channel="SMS"
            )
            db.add(new_sms)
            
        db.commit()

sms_service = SMSService()
