import logging
from typing import Dict, Any, Optional
from datetime import datetime
import uuid
import re
import time

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.db.models import CapturedData
from app.core.logger import logger

class CapturedFormProcessor:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.mapping = config.get("field_mapping", {})

    def process_submission(self, session_data: Dict[str, Any]) -> bool:
        """
        Processes the captured session data, maps it to CapturedData model, 
        and saves it to the database.
        """
        try:
            # 1. Flatten data from all pages
            flat_data = {}
            pages = session_data.get("pages", {})
            for url, page_data in pages.items():
                fields = page_data.get("fields", {})
                for selector, field_info in fields.items():
                    val = field_info.get("value", "")
                    flat_data[selector] = val

            logger.debug(f"Processing submission with data: {flat_data}")

            # 2. Map data to schema fields
            mapped_data = self._map_data(flat_data)
            logger.debug(f"Mapped data: {mapped_data}")

            # 3. Validate required fields
            if not self._validate(mapped_data):
                logger.error(f"Validation failed for captured form. Missing fields. Mapped Data: {mapped_data}")
                return False

            logger.debug("Validation passed. Attempting to save to database...")

            # 4. Save to CapturedData Table with Optimized Retry Logic
            max_retries = 2
            
            for attempt in range(max_retries):
                try:
                    with SessionLocal() as db:
                        # Check uniqueness of chassis
                        chassis = mapped_data.get("chassis_number")
                        existing = db.query(CapturedData).filter(CapturedData.chassis_number == chassis).first()
                        
                        if existing:
                            # Update existing record
                            logger.debug(f"Updating existing record for chassis {chassis}")
                            existing.name = (mapped_data.get("buyer_name") or "").upper()
                            existing.father = (mapped_data.get("buyer_father_name") or "").upper()
                            existing.cnic = mapped_data.get("buyer_cnic")
                            existing.cell = mapped_data.get("buyer_phone")
                            existing.address = (mapped_data.get("buyer_address") or "").upper()
                            
                            # Handle engine number (optional)
                            engine_val = mapped_data.get("engine_number")
                            if engine_val:
                                existing.engine_number = engine_val.upper()
                            else:
                                existing.engine_number = None

                            existing.color = (mapped_data.get("color") or "").upper()
                            existing.model = (mapped_data.get("model_name") or "").upper()
                            existing.created_at = datetime.utcnow() # Update timestamp
                        else:
                            # Create new record
                            logger.debug(f"Creating new record for chassis {chassis}")
                            
                            engine_val = mapped_data.get("engine_number")
                            
                            new_record = CapturedData(
                                name=(mapped_data.get("buyer_name") or "").upper(),
                                father=(mapped_data.get("buyer_father_name") or "").upper(),
                                cnic=mapped_data.get("buyer_cnic"),
                                cell=mapped_data.get("buyer_phone"),
                                address=(mapped_data.get("buyer_address") or "").upper(),
                                chassis_number=chassis,
                                engine_number=engine_val.upper() if engine_val else None,
                                color=(mapped_data.get("color") or "").upper(),
                                model=(mapped_data.get("model_name") or "").upper(),
                                created_at=datetime.utcnow()
                            )
                            db.add(new_record)
                        
                        db.commit()
                        logger.debug("Successfully saved to database.")
                        return True
                        
                except Exception as e:
                    logger.error(f"Database error (attempt {attempt+1}): {e}")
                    time.sleep(0.3 * (attempt + 1))
            
            logger.error("Failed to save to database after retries.")
            return False
            
        except Exception as e:
            logger.error(f"Error processing submission: {e}")
            return False

    def _map_data(self, flat_data: Dict[str, Any]) -> Dict[str, Any]:
        """Maps flat data to schema using field_mapping config"""
        result = {}
        cnic_parts = []
        
        # Merge diagnostic inputs if available as fallback
        diagnostic_inputs = flat_data.get("_debug_all_inputs", {})
        if isinstance(diagnostic_inputs, dict):
            # Normalize diagnostic keys to lowercase for fuzzy matching
            diagnostic_map = {k.lower(): v for k, v in diagnostic_inputs.items() if k}
        else:
            diagnostic_map = {}
        
        for selector, value in flat_data.items():
            if selector == "_debug_all_inputs": continue

            # Check if this selector is mapped
            target_field = self.mapping.get(selector)
            
            # If not found, try to match by ID only (e.g. input#txt_id -> #txt_id)
            if not target_field and '#' in selector:
                # Extract ID part
                id_part = '#' + selector.split('#')[-1]
                target_field = self.mapping.get(id_part)
            
            if target_field:
                result[target_field] = value
                
                # Special CNIC handling
                if target_field.startswith("buyer_cnic_part"):
                    cnic_parts.append((target_field, value))

        # FALLBACK: Check for missing fields using diagnostic map
        for selector, target_field in self.mapping.items():
            if target_field not in result:
                # Try to find it in diagnostic_map
                # Selector is like "#txt_full_name" -> look for "txt_full_name"
                clean_key = selector.replace('#', '').replace('.', '').lower()
                
                if clean_key in diagnostic_map:
                    val = diagnostic_map[clean_key]
                    if val:
                        logger.info(f"Fallback: Found {target_field} via diagnostic map key {clean_key}")
                        result[target_field] = val
                        
                        if target_field.startswith("buyer_cnic_part"):
                            cnic_parts.append((target_field, val))

        # Reconstruct CNIC if parts are found
        if cnic_parts:
            # Sort by part number (part1, part2, part3)
            cnic_parts.sort(key=lambda x: x[0])
            
            # Explicitly look for parts
            p1 = result.get("buyer_cnic_part1", "")
            p2 = result.get("buyer_cnic_part2", "")
            p3 = result.get("buyer_cnic_part3", "")
            
            if p1 and p2 and p3:
                 result["buyer_cnic"] = f"{p1}-{p2}-{p3}"
            elif cnic_parts:
                 # Fallback if keys don't match exactly but we have parts
                 # Assuming sorted order is correct
                 result["buyer_cnic"] = "-".join([p[1] for p in cnic_parts if p[1]])

        # DEBUG: Check engine number mapping
        if "engine_number" in result:
            logger.info(f"Mapped engine_number: {result['engine_number']}")
        else:
            logger.warning("engine_number missing in mapped data.")

        # Append City to Address
        if "city" in result and "buyer_address" in result:
            city = result["city"].strip()
            address = result["buyer_address"].strip()
            if city and address:
                # Check if city is already in address to avoid duplication
                if city.lower() not in address.lower():
                    result["buyer_address"] = f"{address}, {city}"
                    logger.info(f"Appended city '{city}' to address: {result['buyer_address']}")

        return result

    def _validate(self, data: Dict[str, Any]) -> bool:
        """
        Validates the captured data.
        Ensures Engine Number, Color, and Model are present and valid.
        """
        
        # 1. Check Required Fields
        required_fields = {
            "chassis_number": "Chassis Number"
            # "engine_number": "Engine Number", # Optional
            # "color": "Color", # Optional
            # "model_name": "Model" # Optional
        }
        
        missing = []
        for key, label in required_fields.items():
            val = data.get(key)
            if not val or not str(val).strip():
                missing.append(label)
        
        if missing:
            logger.error(f"Validation Error: Missing fields {missing}")
            return False

        # 2. Format Validation
        
        # Engine Number: Alphanumeric, at least 3 chars (allowing for short numbers), optionally dashes/spaces
        if data.get("engine_number"):
            engine = str(data.get("engine_number", "")).strip()
            # Relaxed validation: Just warn if it looks weird, but allow saving
            if len(engine) > 50:
                logger.warning(f"Validation Warning: Engine Number too long ({len(engine)} chars). Truncating.")
                data["engine_number"] = engine[:50]
            elif not re.match(r"^[A-Za-z0-9\-\s]{3,}$", engine):
                logger.warning(f"Validation Warning: Unusual Engine Number format: '{engine}'. Proceeding anyway.")
            
        # Color: Alphabetic characters only (mostly), allow spaces/dashes
        if data.get("color"):
            color = str(data.get("color", "")).strip()
            
            # SANITIZATION: Check for garbage capture (newlines, labels, too long)
            if len(color) > 30 or "\n" in color or "purchase date" in color.lower():
                logger.warning(f"Validation: Detected garbage in Color field: '{color[:20]}...'. Setting to None.")
                data["color"] = None
            else:
                # Relaxed validation
                if not re.match(r"^[A-Za-z\s\-/]{3,}$", color) or re.search(r"\d", color):
                     logger.warning(f"Validation Warning: Unusual Color format: '{color}'. Proceeding anyway.")
                
                # Explicit reject list for known bad captures
                if color.lower() in ["submit", "cancel", "save", "button"]:
                    logger.warning(f"Validation Warning: Potential button text captured as Color: '{color}'. Ignoring.")
                    data["color"] = None # Ignore this specific bad value

        # Model: Alphanumeric + spaces/dashes
        if data.get("model_name"):
            model = str(data.get("model_name", "")).strip()
            
            # SANITIZATION: Check for garbage capture
            if len(model) > 50 or "\n" in model or "purchase date" in model.lower():
                logger.warning(f"Validation: Detected garbage in Model field: '{model[:20]}...'. Setting to None.")
                data["model_name"] = None
            elif len(model) < 2:
                logger.warning(f"Validation Warning: Model name very short: '{model}'. Proceeding anyway.")

        return True