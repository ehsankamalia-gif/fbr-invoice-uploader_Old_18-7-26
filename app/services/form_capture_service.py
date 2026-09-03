import json
import time
import threading
import os
import logging
import queue
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright, Page
from app.services.captured_form_processor import CapturedFormProcessor
from app.services.settings_service import settings_service

# Configure logging with a dedicated logger so it works regardless of import order
_capture_logger = logging.getLogger("form_capture_service")
_capture_logger.setLevel(logging.DEBUG)
# Remove any existing handlers to avoid duplicates
_capture_logger.handlers.clear()
# Add file handler
_capture_fh = logging.FileHandler('capture_debug.log', mode='a', encoding='utf-8')
_capture_fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
_capture_logger.addHandler(_capture_fh)
# Also add a stream handler for console visibility
_capture_sh = logging.StreamHandler()
_capture_sh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
_capture_logger.addHandler(_capture_sh)

# Log startup immediately
_capture_logger.info("FormCaptureService module loaded")

class FormCaptureService:
    _instance = None
    _lock = threading.RLock()  # RLock to allow re-entrant locking (e.g. clear_data -> _save_data)

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(FormCaptureService, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        self.config_path = Path("capture_config.json")
        self.output_file = Path("captured_forms.json")
        self.is_running = False
        self.browser = None
        self.playwright = None
        self.context = None
        self.page = None
        self.thread = None
        self.session_data = {}
        self.pending_action = None # For thread-safe navigation
        self.pending_url = None
        self.task_queue = queue.Queue()
        self.on_data_captured = None # Callback for listeners (e.g. main_window)
        
        # Batch processing configuration
        self.batch_size = 5  # Number of field changes before saving
        self.current_batch = 0
        
        self.load_config()
        self.processor = CapturedFormProcessor(self.config)
        self._ensure_output_file()
        _capture_logger.info(f"Output file path: {self.output_file.absolute()}")
        self._initialized = True

    def _ensure_output_file(self):
        """Creates the output file with empty structure if not exists"""
        if not self.output_file.exists():
            try:
                with open(self.output_file, 'w') as f:
                    json.dump({"pages": {}}, f, indent=2)
            except Exception as e:
                print(f"Error creating output file: {e}")

    def load_config(self):
        if self.config_path.exists():
            with open(self.config_path, 'r') as f:
                self.config = json.load(f)
        else:
            self.config = {
                "target_domains": ["dealers.ahlportal.com"],
                "exclude_selectors": ["input[type='password']"],
                "debounce_ms": 300,
                "output_file": "captured_forms.json"
            }
            # Save default config
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)

        # Pull Honda Portal credentials from SettingsService
        try:
            from app.core.config import settings
            username = settings.HONDA_PORTAL_USERNAME
            password = settings.HONDA_PORTAL_PASSWORD
            
            if username or password:
                if "login_config" not in self.config:
                    self.config["login_config"] = {}
                
                # Update if they are empty in the config
                if not self.config["login_config"].get("dealer_code"):
                    self.config["login_config"]["dealer_code"] = username
                if not self.config["login_config"].get("password"):
                    self.config["login_config"]["password"] = password
        except Exception as e:
            _capture_logger.error(f"Failed to load credentials from settings_service: {e}")

        if "output_file" in self.config:
            self.output_file = Path(self.config["output_file"])

        # Sync processor mapping with latest config (if processor exists)
        if hasattr(self, 'processor') and self.processor:
            self.processor.mapping = self.config.get("field_mapping", {})

        # Push login config to runtime if a page is active
        try:
            if self.page:
                login_cfg = self.config.get("login_config", {})
                self.page.evaluate(f"window.__fbrLoginConfig = {json.dumps(login_cfg)};")
                try:
                    self.page.evaluate("if (window.tryPrefillLogin) { window.tryPrefillLogin(); }")
                except Exception:
                    pass
        except Exception as e:
            _capture_logger.error(f"Failed to push login config to runtime: {e}")

    def start_capture_session(self, url=None):
        if self.is_running:
            return
        
        self.is_running = True
        self.load_config() # Refresh config and credentials
        
        # Load existing data to preserve history
        if self.output_file.exists():
            try:
                with open(self.output_file, 'r') as f:
                    self.session_data = json.load(f)
            except:
                self.session_data = {"pages": {}}
        else:
            self.session_data = {"pages": {}}
            
        if "pages" not in self.session_data:
            self.session_data["pages"] = {}
        
        self.thread = threading.Thread(target=self._run_browser, args=(url,), daemon=True)
        self.thread.start()

    def launch_browser(self, url=None):
        """Alias for start_capture_session for compatibility"""
        return self.start_capture_session(url)

    def stop_capture_session(self):
        self.is_running = False
        if self.browser:
            try:
                self.browser.close()
            except:
                pass
        if self.playwright:
            try:
                self.playwright.stop()
            except:
                pass
        
        self.browser = None
        self.playwright = None
        self.context = None
        self.page = None

    def clear_session_data(self):
        """Clears in-memory session data and the output file"""
        with self._lock:
            self.session_data = {"pages": {}}
            self._save_data()
            self.current_batch = 0
            _capture_logger.info("Session data cleared by user request.")

    def execute_task(self, callback):
        """
        Executes a callback in the browser thread.
        Callback receives (page) as argument.
        Returns the result of the callback.
        """
        if not self.is_running:
            self.start_capture_session()
            # Allow some time for thread start
            time.sleep(1)
            
        result_queue = queue.Queue()
        self.task_queue.put((callback, result_queue))
        
        result = result_queue.get()
        if isinstance(result, Exception):
            raise result
        return result

    def _run_browser(self, start_url):
        self.start_url = start_url
        try:
            with sync_playwright() as p:
                self.playwright = p
                
                # Path for persistent browser data (history, passwords, etc.)
                user_data_dir = Path("browser_profile")
                user_data_dir.mkdir(exist_ok=True)
                
                _capture_logger.info(f"Launching persistent browser context at {user_data_dir.absolute()}")
                
                # Launch persistent context to preserve history and passwords
                # Using channel="chrome" to use the actual Chrome browser if installed
                self.context = p.chromium.launch_persistent_context(
                    user_data_dir=str(user_data_dir.absolute()),
                    channel="chrome", # Use actual Chrome browser
                    headless=False,
                    args=[
                        "--disable-blink-features=AutomationControlled", # Help bypass bot detection
                        "--start-maximized"
                    ],
                    no_viewport=True # Allow window to be maximized
                )
                
                self.browser = self.context.browser # Note: browser might be None for persistent context
                
                # Expose binding to Python
                self.context.expose_binding("py_capture", self._handle_captured_data)
                
                # Add init script to inject listener on every page
                self.context.add_init_script(self._get_injection_script())
                
                # If there are already pages (sometimes persistent context starts with one), use the first one
                if self.context.pages:
                    self.page = self.context.pages[0]
                else:
                    self.page = self.context.new_page()
                
                # Listen to console logs for debugging
                self.page.on("console", lambda msg: _capture_logger.debug(f"Browser Console: {msg.text}"))
                
                # Handle new pages (popups)
                def handle_page(new_p):
                    _capture_logger.info(f"New page detected: {new_p.url}")
                    new_p.on("console", lambda msg: _capture_logger.debug(f"Page Console: {msg.text}"))
                
                self.context.on("page", handle_page)
                
                if start_url:
                    _capture_logger.info(f"Navigating to {start_url}")
                    
                    # RETRY LOGIC for Navigation
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            self.page.goto(start_url, timeout=30000)
                            break # Success
                        except Exception as e:
                            _capture_logger.warning(f"Navigation failed (attempt {attempt+1}/{max_retries}): {e}")
                            if attempt < max_retries - 1:
                                sleep_time = 2 ** (attempt + 1) # Exponential backoff: 2, 4, 8 sec
                                _capture_logger.info(f"Retrying navigation in {sleep_time}s...")
                                time.sleep(sleep_time)
                            else:
                                _capture_logger.error(f"Navigation failed after {max_retries} attempts. Aborting session.")
                                raise e
                
                # ATTEMPT LOGIN PREFILL (Only if data exists in settings)
                try:
                    login_config = self.config.get("login_config", {})
                    dealer_code = login_config.get("dealer_code")
                    password = login_config.get("password")
                    
                    if dealer_code and password:
                        user_sel = login_config.get("username_selector", "#txt_dealer_code")
                        pass_sel = login_config.get("password_selector", "#txt_password")
                        
                        # Wait briefly for login fields
                        try:
                            self.page.wait_for_selector(user_sel, timeout=3000)
                            # Only fill if the field is empty (to respect browser's saved passwords)
                            current_val = self.page.input_value(user_sel)
                            if not current_val:
                                _capture_logger.info("Login fields detected and empty. Attempting to prefill...")
                                self.page.fill(user_sel, dealer_code)
                                self.page.fill(pass_sel, password)
                                _capture_logger.info("Login fields prefilled successfully.")
                            else:
                                _capture_logger.info("Login fields already contain data (possibly from saved passwords). Skipping prefill.")
                        except:
                            pass
                except Exception as e:
                    _capture_logger.error(f"Error during login prefill check: {e}")
                
                # Keep the browser open until stopped
                while self.is_running:
                    try:
                        # Process Task Queue
                        try:
                            while not self.task_queue.empty():
                                task, result_q = self.task_queue.get_nowait()
                                try:
                                    res = task(self.page)
                                    result_q.put(res)
                                except Exception as task_ex:
                                    result_q.put(task_ex)
                        except queue.Empty:
                            pass

                        # Check pending actions
                        if self.pending_action:
                            try:
                                action = self.pending_action
                                self.pending_action = None # Clear immediately
                                if action == 'reload':
                                    _capture_logger.info("Executing scheduled reload...")
                                    self.page.reload()
                                elif action == 'goto_start' and self.pending_url:
                                    _capture_logger.info(f"Executing scheduled navigation to {self.pending_url}...")
                                    self.page.goto(self.pending_url)
                                    self.pending_url = None
                            except Exception as nav_ex:
                                _capture_logger.error(f"Error executing pending action: {nav_ex}")

                        # Check if any page is still open
                        pages = self.context.pages
                        if len(pages) > 0:
                            try:
                                # Use the last page (active) to pump the event loop
                                # Reduced timeout to make browser more responsive
                                pages[-1].wait_for_timeout(100) 
                            except Exception:
                                # If page closes during wait, fallback to short sleep
                                time.sleep(0.3)
                        else:
                            _capture_logger.info("All pages closed, stopping session.")
                            break
                    except Exception as e:
                        _capture_logger.error(f"Browser loop error: {e}")
                        break
                        
        except Exception as e:
            _capture_logger.error(f"Playwright error: {e}")
        finally:
            self.is_running = False

    def _handle_captured_data(self, source, data):
        """Callback for window.py_capture(data)"""
        try:
            # DEBUG RAW DATA - Only log to console, not to file
            _capture_logger.debug(f"Captured Data Received: {data}")
            
            # Check for Form Submission
            if data.get("type") == "form_submission":
                _capture_logger.info("Form Submission Event Detected!")
                
                # MERGE FORCED CAPTURE DATA
                forced_data = data.get("forced_capture", {})
                if forced_data:
                    _capture_logger.info(f"Merging {len(forced_data)} forced capture fields...")
                    page_url = data.get("url", "unknown_url")
                    
                    with self._lock:
                        if page_url not in self.session_data["pages"]:
                            self.session_data["pages"][page_url] = {"fields": {}}
                        
                        for selector, value in forced_data.items():
                            self.session_data["pages"][page_url]["fields"][selector] = {
                                "value": value,
                                "timestamp": time.time(),
                                "type": "forced"
                            }
                        
                        # Save merged state for debugging
                        self._save_data()

                    # METRIC: Check capture completeness for dashboard
                    eng_present = 1 if forced_data.get("#txt_engine_no") else 0
                    col_present = 1 if forced_data.get("#txt_color") else 0
                    mod_present = 1 if forced_data.get("#txt_model") else 0
<<<<<<< HEAD
                    chassis_present = 1 if forced_data.get("#txt_chassis_no") else 0
                    logging.info(f"METRIC:CAPTURE_QUALITY:chassis={chassis_present},engine={eng_present},color={col_present},model={mod_present}")

                # Log forced_data keys to help diagnose missing fields
                if forced_data:
                    forced_keys = list(forced_data.keys())
                    logging.info(f"Forced capture keys: {forced_keys}")
                    # Check specifically for chassis number
                    chassis_val = forced_data.get("#txt_chassis_no") or forced_data.get("txt_chassis_no") or ""
                    if not chassis_val:
                        logging.warning("Chassis number (#txt_chassis_no) is MISSING in forced capture data!")
                        # Try to find chassis in _debug_all_inputs
                        debug_inputs = forced_data.get("_debug_all_inputs", {})
                        if isinstance(debug_inputs, dict):
                            for k, v in debug_inputs.items():
                                if 'chassis' in k.lower() or 'frame' in k.lower():
                                    logging.info(f"Found chassis-like field in debug inputs: {k} = {v}")

                with self._lock:
                    success = self.processor.process_submission(self.session_data)
                
=======
                    _capture_logger.info(f"METRIC:CAPTURE_QUALITY:engine={eng_present},color={col_present},model={mod_present}")

                success = self.processor.process_submission(forced_data)
>>>>>>> 0d07d35b60c68e1d566c6d3058a8141acd945221
                if success:
                    _capture_logger.info("Invoice saved successfully. Clearing session data.")
                    
                    # Notify listener if registered
                    if self.on_data_captured:
                        try:
                            with self._lock:
                                # Pass the captured chassis to allow lookup
                                chassis = self.session_data.get("pages", {}).get(data.get("url"), {}).get("fields", {}).get("#txt_chassis_no", {}).get("value")
                                # If not found in current page, try searching all pages
                                if not chassis:
                                    for url, page in self.session_data.get("pages", {}).items():
                                        chassis = page.get("fields", {}).get("#txt_chassis_no", {}).get("value")
                                        if chassis: break
                            
                            _capture_logger.info(f"Triggering on_data_captured callback with chassis: {chassis}")
                            self.on_data_captured(chassis)
                        except Exception as cb_ex:
                            _capture_logger.error(f"Error in on_data_captured callback: {cb_ex}")

<<<<<<< HEAD
                    with self._lock:
                        self.clear_session_data()
                else:
                    logging.warning("process_submission returned False - data was NOT saved to database")
                    # Log what data was available for debugging
                    with self._lock:
                        available_pages = list(self.session_data.get("pages", {}).keys())
                        logging.warning(f"Available pages in session_data: {available_pages}")
                        for url_key in available_pages:
                            fields = self.session_data.get("pages", {}).get(url_key, {}).get("fields", {})
                            field_keys = list(fields.keys())
                            logging.warning(f"  Page '{url_key}' has fields: {field_keys}")
=======
                    self.clear_session_data()
                else:
                    _capture_logger.error(f"FAILED to save captured data to database. Session data keys: {list(self.session_data.get('pages', {}).keys())}")
                    # Try to log the chassis number for debugging
                    for url, page in self.session_data.get("pages", {}).items():
                        chassis_val = page.get("fields", {}).get("#txt_chassis_no", {}).get("value", "")
                        if chassis_val:
                            _capture_logger.error(f"FAILED save for chassis: {chassis_val}")
                            break
>>>>>>> 0d07d35b60c68e1d566c6d3058a8141acd945221
                    
                # Always save after form submission
                with self._lock:
                    self._save_data()
                    self.current_batch = 0
                
<<<<<<< HEAD
                logging.info("Submission captured. Waiting for next action.")
                        
                return

            # For individual field capture, use lock
            with self._lock:
                # Robust Page URL retrieval
                page_url = "unknown_url"
                try:
                    if hasattr(source, "page") and source.page:
                        page_url = source.page.url
                    elif isinstance(source, dict) and "page" in source:
                        page_url = source["page"].url
                    elif self.page:
                        page_url = self.page.url
                except Exception as e:
                    logging.error(f"Error getting page URL (using fallback): {e}")
=======
                _capture_logger.info("Submission captured. Waiting for next action.")
                # Removed forced reload to allow validation checks on page

                        
                return

            # Robust Page URL retrieval
            page_url = "unknown_url"
            try:
                if hasattr(source, "page") and source.page:
                    page_url = source.page.url
                elif isinstance(source, dict) and "page" in source:
                    page_url = source["page"].url
                elif self.page:
                    page_url = self.page.url
            except Exception as e:
                _capture_logger.error(f"Error getting page URL (using fallback): {e}")
>>>>>>> 0d07d35b60c68e1d566c6d3058a8141acd945221

                # Initialize page entry if not exists
                if page_url not in self.session_data["pages"]:
                    self.session_data["pages"][page_url] = {
                        "last_updated": time.time(),
                        "fields": {}
                    }
                
<<<<<<< HEAD
                # Update data
                selector = data.get("selector")
                if selector:
                    self.session_data["pages"][page_url]["fields"][selector] = data
                    self.session_data["pages"][page_url]["last_updated"] = time.time()
                    
                    self.current_batch += 1
                    
                    if self.current_batch >= self.batch_size:
                        logging.debug(f"Data updated in memory for {page_url}. Batch size {self.batch_size} reached. Saving data...")
                        self._save_data()
                        self.current_batch = 0
                    else:
                        logging.debug(f"Data updated in memory for {page_url}. Batch size {self.current_batch}/{self.batch_size}")
                else:
                    logging.warning(f"No selector in captured data: {data}")
                
        except Exception as e:
            logging.error(f"Error handling captured data: {e}", exc_info=True)
=======
                self.current_batch += 1
                
                if self.current_batch >= self.batch_size:
                    _capture_logger.debug(f"Data updated in memory for {page_url}. Batch size {self.batch_size} reached. Saving data...")
                    self._save_data()
                    self.current_batch = 0
                else:
                    _capture_logger.debug(f"Data updated in memory for {page_url}. Batch size {self.current_batch}/{self.batch_size}")
            else:
                _capture_logger.warning(f"No selector in captured data: {data}")
                
        except Exception as e:
            _capture_logger.error(f"Error handling captured data: {e}")
>>>>>>> 0d07d35b60c68e1d566c6d3058a8141acd945221

    def _save_data(self):
        """Persist data to JSON file"""
        with self._lock:
            try:
                # Ensure directory exists
                self.output_file.parent.mkdir(parents=True, exist_ok=True)
                
                # Write to temporary file first to avoid corruption
                temp_file = self.output_file.with_suffix('.tmp')
                with open(temp_file, 'w') as f:
                    json.dump(self.session_data, f)
                    f.flush()
                    os.fsync(f.fileno())
                
                # Atomic replace
                if self.output_file.exists():
                    os.replace(temp_file, self.output_file)
                else:
                    temp_file.rename(self.output_file)
                
                _capture_logger.debug("File saved successfully.")
                
            except Exception as e:
                _capture_logger.error(f"Error saving data: {e}")


    def _get_injection_script(self):
        """Returns the JavaScript code to inject"""
        debounce_ms = self.config.get("debounce_ms", 300)
        exclude_selectors = json.dumps(self.config.get("exclude_selectors", []))
        include_selectors = json.dumps(self.config.get("include_selectors", []))
        submit_selector = self.config.get("submit_selector", "button[type='submit']")
        
        embedded_login_config = json.dumps(self.config.get("login_config", {}))

        return f"""
        (function() {{
            const DEBOUNCE_MS = {debounce_ms};
            const EXCLUDE_SELECTORS = {exclude_selectors};
            const INCLUDE_SELECTORS = {include_selectors};
            const SUBMIT_SELECTOR = "{submit_selector}";
            const EMBEDDED_LOGIN_CONFIG = {embedded_login_config};
            const LOGIN_CONFIG = window.__fbrLoginConfig || EMBEDDED_LOGIN_CONFIG || {{}};
            
            let timeouts = {{}};

            function tryPrefillLogin() {{
                try {{
                    if (!LOGIN_CONFIG) return false;
                    const userSel = LOGIN_CONFIG.username_selector || '#txt_dealer_code';
                    const passSel = LOGIN_CONFIG.password_selector || '#txt_password';
                    const dealer = LOGIN_CONFIG.dealer_code || '';
                    const pass = LOGIN_CONFIG.password || '';
                    if (!dealer || !pass) return false;

                    let u = null;
                    let p = null;

                    // Primary: configured selectors
                    try {{ u = document.querySelector(userSel); }} catch(e){{}}
                    try {{ p = document.querySelector(passSel); }} catch(e){{}}

                    // Fallback: find by placeholder/name/id heuristics
                    if (!u) {{
                        const inputs = Array.from(document.querySelectorAll('input, textarea'));
                        u = inputs.find(el => {{
                            const ph = (el.getAttribute('placeholder') || '').toLowerCase();
                            const nm = (el.name || '').toLowerCase();
                            const id = (el.id || '').toLowerCase();
                            return ph.includes('dealer') || nm.includes('dealer') || id.includes('dealer');
                        }});
                    }}
                    if (!p) {{
                        const inputs = Array.from(document.querySelectorAll('input, textarea'));
                        p = inputs.find(el => {{
                            const ph = (el.getAttribute('placeholder') || '').toLowerCase();
                            const nm = (el.name || '').toLowerCase();
                            const id = (el.id || '').toLowerCase();
                            return (el.type && el.type.toLowerCase() === 'password') || ph.includes('password') || nm.includes('password') || id.includes('password');
                        }});
                    }}

                    if (u && p) {{
                        u.value = dealer;
                        p.value = pass;
                        try {{ u.dispatchEvent(new Event('input', {{ bubbles: true }})); }} catch(e){{}}
                        try {{ p.dispatchEvent(new Event('input', {{ bubbles: true }})); }} catch(e){{}}
                        return true;
                    }}
                }} catch (e) {{
                    console.error('Prefill error', e);
                }}
                return false;
            }}

            // Attempt login prefill only once after a short delay
            try {{ window.tryPrefillLogin = tryPrefillLogin; }} catch(e){{}}
            setTimeout(() => {{
                tryPrefillLogin();
            }}, 1500); // Wait for page to fully load before attempting prefill

            // Optimized selector generation - uses id directly if available
            function getCssSelector(el) {{
                if (!(el instanceof Element)) return;
                
                // If element has an id, use that directly
                if (el.id) {{
                    return '#' + el.id;
                }}
                
                // Fallback to tag name with class
                let selector = el.nodeName.toLowerCase();
                if (el.className) {{
                    selector += '.' + el.className.split(' ').join('.');
                }}
                
                return selector;
            }}

            function isExcluded(el) {{
                if (!el || !(el instanceof Element)) return false;
                return EXCLUDE_SELECTORS.some(sel => el.matches(sel));
            }}

            function isIncluded(el) {{
                if (!el || !(el instanceof Element)) return false;
                // If whitelist is empty, allow everything (unless excluded)
                if (INCLUDE_SELECTORS.length === 0) return true;
                
                // Check if element matches any selector in the whitelist
                return INCLUDE_SELECTORS.some(sel => el.matches(sel));
            }}

            function capture(el, eventType) {{
                try {{
                    if (!el || !(el instanceof Element)) return;
                    
                    // Priority 1: Exclusions always win
                    if (isExcluded(el)) {{
                         return;
                    }}
                    
                    // Priority 2: Whitelist check
                    if (!isIncluded(el)) {{
                         return;
                    }}
                    
                    const selector = getCssSelector(el);
                    if (!selector) return;
                    
                    let value = el.value;
                    if (el.type === 'checkbox' || el.type === 'radio') {{
                        value = el.checked;
                    }} else if (el.tagName === 'SELECT') {{
                        value = Array.from(el.selectedOptions).map(opt => opt.value).join(',');
                    }}
                    
                    // Fallback: If value is undefined, try text content (for spans, divs like Select2)
                    if (value === undefined || value === null) {{
                        value = el.innerText || el.textContent || "";
                    }}
    
                    const data = {{
                        selector: selector,
                        value: value,
                        type: el.type || el.tagName.toLowerCase(),
                        timestamp: Date.now() / 1000
                    }};
                    
                    // Send to Python
                    if (window.py_capture) {{
                        window.py_capture(data);
                        // console.log("Sent to Python:", data);
                    }} else {{
                        console.error("py_capture binding not found!");
                    }}
                    
                    // Visual Feedback (Safe) - Green border + badge
                    try {{
                        el.setAttribute('data-captured', 'true');
                        // Add a small checkmark badge next to the field for visibility
                        if (!el.parentElement.querySelector('.fbr-captured-badge')) {{
                            const badge = document.createElement('span');
                            badge.className = 'fbr-captured-badge';
                            badge.innerText = '✓';
                            badge.title = 'FBR Capture: ' + (el.id || selector);
                            el.parentElement.appendChild(badge);
                        }}
                    }} catch(e) {{}}
                    
                }} catch (e) {{
                    console.error("Error in capture function:", e);
                }}
            }}

            // Debounce wrapper
            function debouncedCapture(el, eventType) {{
                const selector = getCssSelector(el);
                if (timeouts[selector]) clearTimeout(timeouts[selector]);
                
                timeouts[selector] = setTimeout(() => {{
                    capture(el, eventType);
                }}, DEBOUNCE_MS);
            }}

            // Event Listeners
            ['input', 'change'].forEach(event => {{
                document.addEventListener(event, (e) => {{
                    try {{
                        if (!e.target || !(e.target instanceof Element)) return;

                        if (e.target.matches('input, textarea, select') || isIncluded(e.target)) {{
                            if (event === 'input') {{
                                debouncedCapture(e.target, event);
                            }} else {{
                                capture(e.target, event);
                            }}
                        }}
                    }} catch (err) {{
                        // console.error("Error in event listener:", err);
                    }}
                }}, true);
            }});

            // SUBMIT DETECTION: Listen for submit events
            document.addEventListener('submit', function(e) {{
                // Check if the submitter was a search button
                if (e.submitter) {{
                    const text = e.submitter.innerText.toLowerCase();
                    if (text.includes('search') || text.includes('find') || text.includes('filter') || text.includes('load')) {{
                        console.log("Ignored submit from search button:", e.submitter);
                        return;
                    }}
                }}
                handleSubmit("form_submit_event");
            }}, true);
            
            // SUBMIT DETECTION: Listen for clicks on submit-like buttons
            document.addEventListener('click', function(e) {{
                // Check if target or parent is a submit button
                let el = e.target;
                // Walk up to find button if clicked on icon inside
                while (el && el !== document.body) {{
                    if (el.tagName === 'BUTTON' || (el.tagName === 'INPUT' && el.type === 'submit')) {{
                        // Check if it's a submit button
                        const text = el.innerText.toLowerCase();
                        if ((el.type === 'submit' || el.classList.contains('btn-primary') || el.classList.contains('submit') || text.includes('save') || text.includes('submit')) && !text.includes('search') && !text.includes('find') && !text.includes('filter') && !text.includes('load')) {{
                             // Delay slightly to allow validation scripts to run first
                             setTimeout(() => handleSubmit("button_click"), 100);
                        }}
                        break;
                    }}
                    el = el.parentElement;
                }}
            }}, true);

            // SUBMIT DETECTION: Also handle configured SUBMIT_SELECTOR directly
            if (SUBMIT_SELECTOR && SUBMIT_SELECTOR !== "button[type='submit']") {{
                document.addEventListener('click', function(e) {{
                    let el = e.target;
                    while (el && el !== document.body) {{
                        try {{ if (el.matches(SUBMIT_SELECTOR)) {{ setTimeout(() => handleSubmit("config_selector"), 100); return; }} }} catch(e2) {{}}
                        el = el.parentElement;
                    }}
                }}, true);
            }}
            
            // Mutation Observer for complex widgets (like Select2 containers)
            if (typeof MutationObserver !== 'undefined') {{
                const observer = new MutationObserver((mutations) => {{
                    // Process mutations in batches and debounce
                    clearTimeout(window.__mutationTimeout);
                    window.__mutationTimeout = setTimeout(() => {{
                        mutations.forEach((mutation) => {{
                            // Ignore our own visual feedback changes to avoid infinite loops
                            if (mutation.type === 'attributes' && (mutation.attributeName === 'style' || mutation.attributeName === 'data-captured' || mutation.attributeName === 'class')) {{
                                return;
                            }}

                            let target = mutation.target;
                            if (target.nodeType === 3) target = target.parentElement; // Text node -> Parent
                            
                            if (target && isIncluded(target)) {{
                                debouncedCapture(target, 'mutation');
                            }}
                        }});
                    }}, 100); // Debounce mutations by 100ms
                }});
                
                // Only observe if body exists (wait for load usually, but this script injects after load)
                if (document.body) {{
                    observer.observe(document.body, {{ 
                        subtree: true, 
                        childList: true, 
                        characterData: true,
                        attributes: true,
                    }});
                }}
            }}

            // -----------------------------------------------------------
            // JQUERY / SELECT2 HOOKS
            // -----------------------------------------------------------
            if (typeof jQuery !== 'undefined') {{
                try {{
                    // Hook into Select2 events globally
                    jQuery(document).on('select2:select change', 'select', function(e) {{
                        if (isIncluded(this)) {{
                            console.log("jQuery Change detected:", this);
                            capture(this, 'jquery_change');
                        }}
                    }});
                    console.log("FBR Capture: jQuery hooks initialized");
                }} catch(e) {{
                    console.error("FBR Capture: jQuery hook error", e);
                }}
            }}

            // -----------------------------------------------------------
            // ACTIVE POLLING (Safety Net for missed events)
            // -----------------------------------------------------------
            const previousValues = {{}};

            function getElementValue(el) {{
                let val = el.value;
                if (el.type === 'checkbox' || el.type === 'radio') {{
                    val = el.checked;
                }} else if (el.tagName === 'SELECT') {{
                    val = Array.from(el.selectedOptions).map(opt => opt.value).join(',');
                }} else if (val === undefined || val === null) {{
                    val = (el.innerText || el.textContent || "").trim();
                }}
                return val;
            }}

            // NEW: Label-based extraction for read-only fields
            const LABEL_STRATEGIES = [
                {{ label: "Full Name", selector: "#txt_full_name" }},
                {{ label: "Father / Husband Name", selector: "#txt_father_name" }}
            ];

            function captureByLabels() {{
                LABEL_STRATEGIES.forEach(strategy => {{
                    // 1. Skip if primary selector exists in DOM
                    if (document.querySelector(strategy.selector)) return;
                    
                    // 2. Find label using XPath
                    // Use robust XPath to find text nodes containing the label
                    const xpath = `//*[text()[contains(., '${{strategy.label}}')]]`;
                    try {{
                        const result = document.evaluate(xpath, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
                        
                        for (let i = 0; i < result.snapshotLength; i++) {{
                            const el = result.snapshotItem(i);
                            
                            // Determine potential value element container
                            let valueEl = null;
                            let method = "unknown";

                            // Strategy A: Direct Next Sibling (e.g., <div>Label</div><div>Value</div>)
                            if (el.nextElementSibling) {{
                                valueEl = el.nextElementSibling;
                                method = "sibling";
                            }}
                            
                            // Strategy B: Parent TD Sibling (e.g., <td>Label</td><td>Value</td>)
                            // If direct sibling didn't yield a value or wasn't suitable, try stepping up to TD
                            if (!valueEl || (valueEl.tagName === 'BR' || valueEl.tagName === 'HR')) {{
                                const parentTd = el.closest('td');
                                if (parentTd) {{
                                    valueEl = parentTd.nextElementSibling;
                                    method = "parent_td_sibling";
                                }}
                            }}

                            // Strategy C: Table Row Cell Index (for nested structures or complex tables)
                            if (!valueEl) {{
                                const parentRow = el.closest('tr');
                                if (parentRow) {{
                                    const cells = Array.from(parentRow.cells);
                                    // Find which cell contains our label element
                                    const idx = cells.findIndex(c => c === el || c.contains(el));
                                    if (idx !== -1 && idx + 1 < cells.length) {{
                                        valueEl = cells[idx + 1];
                                        method = "row_cell_index";
                                    }}
                                }}
                            }}
                            
                            if (valueEl) {{
                                let val = "";
                                // Check for value property first (inputs, selects)
                                if (valueEl.value !== undefined && valueEl.value !== "") {{
                                    val = valueEl.value;
                                }} else {{
                                    val = (valueEl.innerText || valueEl.textContent || "").trim();
                                }}
                                
                                // If val is empty, check if valueEl contains an input/select/textarea
                                if (!val && valueEl.children.length > 0) {{
                                    const input = valueEl.querySelector('input, select, textarea');
                                    if (input) {{
                                         if (input.value !== undefined && input.value !== "") {{
                                             val = input.value;
                                         }}
                                    }}
                                }}
                                
                                // Clean up common separators if they were captured
                                if (val.startsWith(":")) val = val.substring(1).trim();
                                
                                if (val && val.length > 1) {{
                                    // Capture it!
                                    const data = {{
                                        selector: strategy.selector, // Masquerade as the expected selector
                                        value: val,
                                        type: 'label_inference',
                                        method: method,
                                        label_found: strategy.label,
                                        timestamp: Date.now() / 1000
                                    }};
                                    
                                    // Check if value is new
                                    if (previousValues[strategy.selector] !== val) {{
                                        console.log(`[Label Inference] MATCH: '${{strategy.label}}' -> '${{val}}' via ${{method}}`);
                                        if (window.py_capture) window.py_capture(data);
                                        previousValues[strategy.selector] = val;
                                        
                                        // Visual feedback restored
                                        try {{
                                            valueEl.setAttribute('data-captured', 'true');
                                            valueEl.title = `Captured as ${{strategy.label}}`;
                                        }} catch(e) {{}}
                                    }}
                                    return; // Stop after first valid match
                                }}
                            }}
                        }}
                    }} catch(e) {{
                        console.error("Error in captureByLabels", e);
                    }}
                }});
            }}

            function pollWhitelistedElements() {{
                // 1. Standard Selectors
                INCLUDE_SELECTORS.forEach(selector => {{
                    const els = document.querySelectorAll(selector);
                    els.forEach(el => {{
                        const val = getElementValue(el);

                        // Unique key for tracking
                        const key = selector; 
                        
                        if (previousValues[key] !== val) {{
                            // Value changed!
                            if (previousValues[key] !== undefined) {{ // Don't fire on initial load unless you want to
                                console.log(`Polling detected change in ${{selector}}`);
                                capture(el, 'poll');
                            }}
                            previousValues[key] = val;
                        }}
                    }});
                }});
                
                // 2. Label Inference
                captureByLabels();
            }}
            
            // Poll every 10 seconds - Optimized for reduced overhead
            setInterval(pollWhitelistedElements, 10000);

            // Initial Capture of whitelisted elements (Fix for static TD elements)
            setTimeout(() => {{
                console.log("Running initial capture for whitelisted elements...");
                INCLUDE_SELECTORS.forEach(selector => {{
                    const els = document.querySelectorAll(selector);
                    els.forEach(el => {{
                        // Capture immediately to ensure static data (like TD) is grabbed
                        capture(el, 'initial_load');
                        
                        // Update polling cache
                        const val = getElementValue(el);
                        const key = selector; 
                        previousValues[key] = val;
                    }});
                }});
            }}, 1000);

            // -----------------------------------------------------------
            // SUBMIT DETECTION
            // -----------------------------------------------------------
            function handleSubmit(source) {{
                console.log("Submit detected via " + source);
                
                // Visual Feedback
                const overlay = document.getElementById('fbr-debug-overlay');
                if (overlay) {{
                    overlay.innerText = "Checking Validation...";
                    overlay.style.backgroundColor = "rgba(241, 196, 15, 0.9)"; // Yellow
                }}

                // Wait for validation to trigger (50ms) - Ultra fast
                setTimeout(() => {{
                    // CHECK FOR VALIDATION ERRORS
                    let hasErrors = false;
                    
                    // Common error selectors
                    const errorSelectors = [
                        '.error', '.text-danger', '.invalid-feedback', '.alert-danger', 
                        '.input-validation-error', '.field-validation-error',
                        'span[style*="color: red"]', 'div[style*="color: red"]'
                    ];
                    
                    // 1. Check for error elements
                    errorSelectors.forEach(sel => {{
                        const errs = document.querySelectorAll(sel);
                        errs.forEach(el => {{
                            // Check if visible and has content
                            const text = el.innerText.trim();
                            if (el.offsetParent !== null && text.length > 0) {{
                                // Ignore simple asterisks (required field indicators)
                                if (text === '*' || text === ': *' || text === '* :' || text.length < 2) return;
                                
                                hasErrors = true;
                                console.log("Validation Error Found:", el);
                            }}
                        }});
                    }});

                    // 2. Check for inputs with error classes or styles
                    const inputErrorSelectors = ['.is-invalid', '.error'];
                    inputErrorSelectors.forEach(sel => {{
                        const errs = document.querySelectorAll('input' + sel + ', select' + sel + ', textarea' + sel);
                        if (errs.length > 0) hasErrors = true;
                    }});
                    
                    // 3. Check HTML5 invalid state
                    const invalidEls = document.querySelectorAll(':invalid');
                    if (invalidEls.length > 0) {{
                        hasErrors = true;
                        console.log("HTML5 Invalid Elements:", invalidEls);
                    }}
                    
                    if (hasErrors) {{
                        console.log("Validation errors detected, but proceeding with capture for debugging...");
                        if (overlay) {{
                            overlay.innerText = "Validation Errors (Proceeding...)";
                            overlay.style.backgroundColor = "rgba(230, 126, 34, 0.9)"; // Orange
                        }}
                    }} else {{
                        if (overlay) {{
                            overlay.innerText = "Processing Submission...";
                            overlay.style.backgroundColor = "rgba(46, 204, 113, 0.9)"; // Green
                        }}
                    }}

                    // FORCE CAPTURE ALL FIELDS
                    const currentData = {{}};
                
                // 1. Capture by Whitelist
                INCLUDE_SELECTORS.forEach(selector => {{
                    try {{
                        const els = document.querySelectorAll(selector);
                        if (els.length === 0) {{
                             console.warn("FBR Capture: Whitelisted selector NOT FOUND during submit:", selector);
                        }} else {{
                             console.log("FBR Capture: Whitelisted selector FOUND during submit:", selector, "Count:", els.length);
                        }}
    
                        els.forEach(el => {{
                            try {{
                                let val = el.value;
                                if (el.type === 'checkbox' || el.type === 'radio') {{
                                    val = el.checked;
                                }} else if (el.tagName === 'SELECT') {{
                                    // Handle Select2
                                    if (typeof jQuery !== 'undefined' && jQuery(el).data('select2')) {{
                                        val = jQuery(el).val();
                                    }} else {{
                                        val = Array.from(el.selectedOptions).map(opt => opt.value).join(',');
                                    }}
                                }} else if (val === undefined || val === null || val === '') {{
                                    val = el.innerText || el.textContent || "";
                                }}
                                
                                // Use ID if available for the key, else selector
                                const key = el.id ? '#' + el.id : selector;
                                currentData[key] = val;
                                console.log("FBR Capture: Captured Value for", key, ":", val);
                            }} catch (elemErr) {{
                                console.error("FBR Capture: Error extracting element for " + selector, elemErr);
                            }}
                        }});
                    }} catch (selErr) {{
                        console.error("FBR Capture: Error querying selector " + selector, selErr);
                    }}
                }});

                // 2. FALLBACK: Text-based capture for Name/Father when they appear as labels
                function grabText(labelPatterns) {{
                    // Priority order: Labels/Bold first, then spans/cells, then paragraphs, then divs
                    const prioritySelectors = ['label', 'b', 'strong', 'th', 'span', 'td', 'p', 'div'];
                    const IGNORED_VALUES = ['submit', 'save', 'cancel', 'update', 'login', 'reset', 'back', 'next', 'search', 'print'];
                    
                    for (let selector of prioritySelectors) {{
                        const els = document.querySelectorAll(selector);
                        for (let el of els) {{
                            const text = (el.innerText || "").trim();
                            // Optimization: Skip if text is too long (likely a container) or too short
                            if (text.length > 200 || text.length < 3) continue;

                            // Check if this element matches one of our patterns (case-insensitive)
                            const match = labelPatterns.some(p => text.toLowerCase().includes(p.toLowerCase()));
                            
                            if (match) {{
                                // Found the label! Now look for the value.
                                
                                // OPTIMIZATION: Check if the text is JUST the label (with optional colon)
                                const isJustLabel = labelPatterns.some(p => {{
                                    const r = new RegExp("^\\\\s*" + p + "\\\\s*[:|-]?\\\\s*$", "i");
                                    return r.test(text);
                                }});

                                // Strategy 1: Text content of the same element (e.g. "Name: John")
                                if (!isJustLabel) {{
                                    for (let p of labelPatterns) {{
                                        const regex = new RegExp(".*" + p + "\\\\s*[:|-]?\\\\s*", "i");
                                        if (text.match(regex)) {{
                                            const val = text.replace(regex, "").trim();
                                            // Validate value
                                            if (val.length > 1 && !val.startsWith("*") && !val.includes(":") && !IGNORED_VALUES.includes(val.toLowerCase())) {{
                                                console.log("grabText Strategy 1 SUCCESS. Val:", val);
                                                return val;
                                            }}
                                        }}
                                    }}
                                }}

                                // Strategy 2: Next Sibling
                                let next = el.nextElementSibling;
                                if (next) {{
                                    const val = (next.innerText || next.value || "").trim();
                                    if (val && val.length > 1 && !IGNORED_VALUES.includes(val.toLowerCase())) return val;
                                }}
                                
                                // Strategy 3: Parent's Next Sibling
                                const parent = el.parentElement;
                                if (parent) {{
                                    let parentNext = parent.nextElementSibling;
                                    if (parentNext) {{
                                         const val = (parentNext.innerText || parentNext.value || "").trim();
                                         if (val && val.length > 1 && !IGNORED_VALUES.includes(val.toLowerCase())) return val;
                                    }}
                                    
                                    // Strategy 4: Cell index matching
                                    if (parent.tagName === 'TD' || parent.tagName === 'TH') {{
                                        const row = parent.parentElement;
                                        if (row && row.tagName === 'TR') {{
                                            const cells = Array.from(row.children);
                                            const idx = cells.indexOf(parent);
                                            if (idx !== -1 && cells[idx+1]) {{
                                                const val = (cells[idx+1].innerText || cells[idx+1].value || "").trim();
                                                if (val && val.length > 1 && !IGNORED_VALUES.includes(val.toLowerCase())) return val;
                                            }}
                                        }}
                                    }}
                                }}
                            }}
                        }}
                    }}
                    return null;
                }}

                // Explicitly check for Name and Father Name if missing
                const nameFromFallback = grabText([
                    'Full Name', 
                    'Name', 
                    'Customer Name',
                    'Buyer Name'
                ]);
                if (!currentData['#txt_full_name'] && nameFromFallback) {{
                    currentData['#txt_full_name'] = nameFromFallback;
                    console.log("FBR Capture: Recovered Full Name via text fallback:", nameFromFallback);
                }}

                const fatherFromFallback = grabText([
                    'Father / Husband Name',
                    'Father Name',
                    'Husband Name',
                    'Father'
                ]);
                if (!currentData['#txt_father_name'] && fatherFromFallback) {{
                    currentData['#txt_father_name'] = fatherFromFallback;
                    console.log("FBR Capture: Recovered Father Name via text fallback:", fatherFromFallback);
                }}

                // 3. DIAGNOSTIC: Capture ALL inputs as fallback
                const debugInputs = {{}};
                try {{
                    document.querySelectorAll('input, select, textarea').forEach(el => {{
                        if (el.id) debugInputs[el.id] = el.value;
                        else debugInputs[el.name] = el.value;
                    }});
                }} catch(e) {{}}
                currentData['_debug_all_inputs'] = debugInputs;

                // Explicitly check for Chassis Number if missing
                const chassisFromFallback = grabText([
                    'Chassis No',
                    'Chassis Number',
                    'Chassis #',
                    'Frame No',
                    'Frame Number',
                    'Frame #',
                    'VIN',
                    'Chassis'
                ]);
                if (!currentData['#txt_chassis_no']) {{
                     const chassisKey = Object.keys(debugInputs || {{}}).find(k => k.toLowerCase().includes('chassis') || k.toLowerCase().includes('frame') || k.toLowerCase().includes('vin'));
                     if (chassisKey) currentData['#txt_chassis_no'] = debugInputs[chassisKey];
                }}

                if (!currentData['#txt_chassis_no'] && chassisFromFallback) {{
                    currentData['#txt_chassis_no'] = chassisFromFallback;
                    console.log("FBR Capture: Recovered Chassis Number via text fallback:", chassisFromFallback);
                }}

                // Explicitly check for Engine Number if missing (Added Fix)
                const engineFromFallback = grabText([
                    'Engine No',
                    'Engine Number',
                    'Engine #',
                    'Eng No',
                    'Eng #',
                    'Engine'
                ]);
                // Try to find if engine number is in a key that looks like engine
                if (!currentData['#txt_engine_no']) {{
                     // Check debug inputs for any engine-like key
                     const engineKey = Object.keys(debugInputs || {{}}).find(k => k.toLowerCase().includes('engine'));
                     if (engineKey) currentData['#txt_engine_no'] = debugInputs[engineKey];
                }}

                if (!currentData['#txt_engine_no'] && engineFromFallback) {{
                    currentData['#txt_engine_no'] = engineFromFallback;
                    console.log("FBR Capture: Recovered Engine Number via text fallback:", engineFromFallback);
                }}

                // Explicitly check for Model if missing
                const modelFromFallback = grabText([
                    'Model',
                    'Model Name',
                    'Vehicle Model',
                    'Product',
                    'Make/Model'
                ]);

                // Try to find if model is in a key that looks like model
                if (!currentData['#txt_model']) {{
                     const modelKey = Object.keys(debugInputs || {{}}).find(k => k.toLowerCase().includes('model'));
                     if (modelKey) currentData['#txt_model'] = debugInputs[modelKey];
                }}

                if (!currentData['#txt_model'] && modelFromFallback) {{
                    currentData['#txt_model'] = modelFromFallback;
                    console.log("FBR Capture: Recovered Model via text fallback:", modelFromFallback);
                }}

                // Explicitly check for Color if missing
                const colorFromFallback = grabText([
                    'Color',
                    'Vehicle Color',
                    'Body Color',
                    'Colour'
                ]);

                // Try to find if color is in a key that looks like color
                if (!currentData['#txt_color']) {{
                     const colorKey = Object.keys(debugInputs || {{}}).find(k => k.toLowerCase().includes('color'));
                     if (colorKey) currentData['#txt_color'] = debugInputs[colorKey];
                }}

                if (!currentData['#txt_color'] && colorFromFallback) {{
                    currentData['#txt_color'] = colorFromFallback;
                    console.log("FBR Capture: Recovered Color via text fallback:", colorFromFallback);
                }}

                // VALIDATION & CLEANUP
                function validateData(data) {{
                    try {{
                        // Engine No Validation - Only reject if clearly a button/label text
                        if (data['#txt_engine_no']) {{
                            let en = data['#txt_engine_no'];
                            // Use exact match for common button texts to avoid rejecting valid data
                            if (/^(submit|save|cancel|search|reset|print|back|next|login|logout|update|delete)$/i.test(en.trim())) {{
                                console.warn("FBR Capture: Invalid Engine No rejected:", en);
                                delete data['#txt_engine_no'];
                            }}
                        }}
                        
                        // Color Validation - Only reject if clearly a button/label text
                        if (data['#txt_color']) {{
                            let c = data['#txt_color'];
                            if (/^(submit|save|cancel|search|reset|print|back|next|login|logout|update|delete)$/i.test(c.trim())) {{
                                 console.warn("FBR Capture: Invalid Color rejected:", c);
                                 delete data['#txt_color'];
                            }}
                        }}
                        
                        // Model Validation - Only reject if clearly a button/label text
                        if (data['#txt_model']) {{
                            let m = data['#txt_model'];
                            if (/^(submit|save|cancel|search|reset|print|back|next|login|logout|update|delete)$/i.test(m.trim())) {{
                                 console.warn("FBR Capture: Invalid Model rejected:", m);
                                 delete data['#txt_model'];
                            }}
                        }}
                    }} catch (e) {{
                        console.error("FBR Capture: Validation error", e);
                    }}
                }}
                
                validateData(currentData);

                if (window.py_capture) {{
                    window.py_capture({{
                        type: 'form_submission',
                        source: source,
                        url: window.location.href,
                        timestamp: Date.now() / 1000,
                        forced_capture: currentData
                    }});
                }}
            }}, 1000);
        }}

            // -----------------------------------------------------------
            // LAYOUT & UI HELPERS
            // -----------------------------------------------------------
            function injectStyles() {{
                const styleId = 'fbr-capture-styles';
                if (document.getElementById(styleId)) return;
                
                const style = document.createElement('style');
                style.id = styleId;
                style.textContent = `
                     [data-captured="true"] {{
                         border: 2px solid #2ecc71 !important;
                         outline: 2px solid #2ecc71 !important;
                         outline-offset: 1px;
                         background-color: rgba(46, 204, 113, 0.1) !important;
                         box-shadow: 0 0 5px rgba(46, 204, 113, 0.5);
                         transition: all 0.3s ease;
                     }}
                     /* Select2 Support */
                     select[data-captured="true"] + .select2-container .select2-selection,
                     .select2-container [data-captured="true"] {{
                         border: 2px solid #2ecc71 !important;
                         background-color: rgba(46, 204, 113, 0.1) !important;
                         box-shadow: 0 0 5px rgba(46, 204, 113, 0.5);
                     }}
                     /* Captured badge on labels */
                     .fbr-captured-badge {{
                         display: inline-block;
                         margin-left: 4px;
                         color: #2ecc71;
                         font-weight: bold;
                         font-size: 12px;
                     }}
                 `;
                document.head.appendChild(style);
            }}

            function forceLayout() {{
                // No-op: Layout forcing removed to restore default CSS
            }}

            function addManualTrigger() {{
                // No-op: Manual trigger button removed
            }}

            function initOverlay() {{
                injectStyles();
                if (document.getElementById('fbr-debug-overlay')) return;
                
                const overlay = document.createElement('div');
                overlay.id = 'fbr-debug-overlay';
                overlay.style.position = 'fixed';
                overlay.style.top = '10px';
                overlay.style.right = '10px';
                overlay.style.zIndex = '999999';
                overlay.style.backgroundColor = 'rgba(0, 0, 0, 0.7)';
                overlay.style.color = 'white';
                overlay.style.padding = '10px 20px';
                overlay.style.borderRadius = '5px';
                overlay.style.fontFamily = 'Arial, sans-serif';
                overlay.style.fontSize = '14px';
                overlay.style.pointerEvents = 'none';
                overlay.style.transition = 'background-color 0.3s';
                overlay.innerText = 'FBR Capture Active';
                document.body.appendChild(overlay);
            }}
            
            // Call it
            if (document.readyState === 'loading') {{
                document.addEventListener('DOMContentLoaded', function() {{
                    addManualTrigger();
                    forceLayout();
                    initOverlay();
                }});
            }} else {{
                addManualTrigger();
                forceLayout();
                initOverlay();
            }}
            
            console.log("Form Capture Injector Loaded - Listening for events");
        }})();
        """

form_capture_service = FormCaptureService()
