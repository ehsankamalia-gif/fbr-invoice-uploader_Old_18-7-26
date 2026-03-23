import requests
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

class EvolutionAPIClient:
    def __init__(self):
        self.session = requests.Session()
        # Support both casing for apikey header as different versions of Evolution API might expect different ones
        self.session.headers.update({
            "apikey": settings.EVOLUTION_API_KEY,
            "apiKey": settings.EVOLUTION_API_KEY
        })

    def get_connection_state(self):
        try:
            response = self.session.get(
                f"{settings.EVOLUTION_API_URL}/instance/connectionState/{settings.EVOLUTION_INSTANCE_NAME}",
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}

    def get_qr_code(self):
        """Fetch the current QR code from the instance."""
        try:
            response = self.session.get(
                f"{settings.EVOLUTION_API_URL}/instance/connect/{settings.EVOLUTION_INSTANCE_NAME}",
                timeout=15
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}

    def send_text(self, number: str, text: str):
        """Send a plain text message via the instance with comprehensive delivery logic."""
        # 1. Advanced Sanitization & Validation
        clean_number = "".join(filter(str.isdigit, number))
        
        if clean_number.startswith("0"):
            clean_number = "92" + clean_number[1:]
        elif len(clean_number) == 10 and clean_number.startswith("3"):
            clean_number = "92" + clean_number

        # Final check: Must be 12 digits for Pakistan (92XXXXXXXXXX)
        if len(clean_number) != 12 or not clean_number.startswith("92"):
            logger.error(f"Validation Failed: '{clean_number}' is not a valid Pakistan WhatsApp number format.")
            return False, f"Invalid format: {clean_number}. Expected 12 digits starting with 92."

        try:
            # Evolution API - Required Structure: textMessage
            payload = {
                "number": clean_number,
                "textMessage": {
                    "text": text
                },
                "options": {
                    "delay": 1200,
                    "presence": "composing",
                    "linkPreview": False
                }
            }
            
            logger.info(f"Delivery Pipeline [INIT]: {clean_number}")
            response = self.session.post(
                f"{settings.EVOLUTION_API_URL}/message/sendText/{settings.EVOLUTION_INSTANCE_NAME}",
                json=payload,
                timeout=25
            )
            
            # 2. Response Code & Error Analysis
            if not response.ok:
                resp_data = {}
                try: resp_data = response.json()
                except: pass
                
                error_msg = resp_data.get("response", {}).get("message", str(resp_data))
                
                # Check for Account/Policy Restrictions
                if "blocked" in str(error_msg).lower():
                    return False, "Account Restricted: Number blocked by WhatsApp policy."
                
                # Check for Number Existence
                if response.status_code == 400 and ("exists" in str(resp_data) or "not found" in str(resp_data).lower()):
                    return False, f"Delivery Failed: Number {clean_number} is not registered on WhatsApp."

                # Fallback Delivery Attempt (Minimal structure if property missing error persists)
                logger.warning(f"Primary Delivery Failed ({response.status_code}). Executing Fallback...")
                fallback_payload = {
                    "number": clean_number,
                    "textMessage": {"text": text}
                }
                response = self.session.post(
                    f"{settings.EVOLUTION_API_URL}/message/sendText/{settings.EVOLUTION_INSTANCE_NAME}",
                    json=fallback_payload,
                    timeout=25
                )

            response.raise_for_status()
            logger.info(f"Delivery Pipeline [SUCCESS]: {clean_number}")
            return True, response.json()

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                return False, "Auth Failure: Evolution API Key is invalid or expired."
            if e.response.status_code == 404:
                return False, "Infrastructure Error: Evolution Instance 'whatapps2' not found."
            return False, f"Server Error ({e.response.status_code}): {e.response.text}"
        except requests.exceptions.ConnectionError:
            return False, "Network Error: Could not connect to Evolution API server."
        except Exception as e:
            logger.error(f"Delivery Pipeline [CRITICAL]: {str(e)}")
            return False, f"Unexpected Error: {str(e)}"

    def logout_instance(self):
        """Force logout the instance."""
        try:
            response = self.session.delete(
                f"{settings.EVOLUTION_API_URL}/instance/logout/{settings.EVOLUTION_INSTANCE_NAME}",
                timeout=15
            )
            response.raise_for_status()
            return True, response.json()
        except requests.exceptions.RequestException as e:
            return False, str(e)

    def check_number_exists(self, number: str):
        """Check if a number is registered on WhatsApp."""
        # Sanitization logic matching send_text
        clean_number = "".join(filter(str.isdigit, number))
        if clean_number.startswith("0"):
            clean_number = "92" + clean_number[1:]
        elif len(clean_number) == 10 and clean_number.startswith("3"):
            clean_number = "92" + clean_number

        if len(clean_number) != 12 or not clean_number.startswith("92"):
            return False, f"Invalid format: {clean_number}"

        try:
            payload = {"numbers": [clean_number]}
            response = self.session.post(
                f"{settings.EVOLUTION_API_URL}/chat/whatsappNumbers/{settings.EVOLUTION_INSTANCE_NAME}",
                json=payload,
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            
            # Evolution API returns a list of objects with exists property
            if isinstance(data, list) and len(data) > 0:
                result = data[0]
                if result.get("exists"):
                    return True, result
                else:
                    return False, "This number is not on WhatsApp"
            
            return False, "Could not verify number status"

        except Exception as e:
            logger.error(f"Number Validation Failed: {str(e)}")
            return False, f"Validation Error: {str(e)}"
