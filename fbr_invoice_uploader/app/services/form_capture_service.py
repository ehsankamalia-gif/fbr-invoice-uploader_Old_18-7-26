import json
import time
import threading
import os
import logging
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright, Page
from app.services.captured_form_processor import CapturedFormProcessor

# Configure logging
logging.basicConfig(
    filename='capture_debug.log',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class FormCaptureService:
    _instance = None
    _lock = threading.Lock()

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
        
        self.load_config()
        self.processor = CapturedFormProcessor(self.config)
        self._ensure_output_file()
        logging.info(f"Output file path: {self.output_file.absolute()}")
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
                "target_domains": [],
                "exclude_selectors": ["input[type='password']"],
                "debounce_ms": 300,
                "output_file": "captured_forms.json"
            }
            # Save default config
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)

        if "output_file" in self.config:
            self.output_file = Path(self.config["output_file"])

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
            logging.error(f"Failed to push login config to runtime: {e}")

    def start_capture_session(self, url=None):
        if self.is_running:
            return
        
        self.is_running = True
        
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
            logging.info("Session data cleared by user request.")

    def _run_browser(self, start_url):
        self.start_url = start_url
        try:
            with sync_playwright() as p:
                self.playwright = p
                self.browser = p.chromium.launch(headless=False)
                self.context = self.browser.new_context()
                
                # Expose binding to Python
                self.context.expose_binding("py_capture", self._handle_captured_data)
                
                # Add init script to inject listener on every page
                self.context.add_init_script(self._get_injection_script())
                
                self.page = self.context.new_page()
                
                # Listen to console logs for debugging
                self.page.on("console", lambda msg: logging.debug(f"Browser Console: {msg.text}"))
                
                # Handle new pages (popups)
                def handle_page(page):
                    logging.info(f"New page detected: {page.url}")
                    page.on("console", lambda msg: logging.debug(f"Page Console: {msg.text}"))
                
                self.context.on("page", handle_page)
                
                if start_url:
                    logging.info(f"Navigating to {start_url}")
                    self.page.goto(start_url)
                    
                    # ATTEMPT LOGIN PREFILL
                    try:
                        login_config = self.config.get("login_config", {})
                        dealer_code = login_config.get("dealer_code")
                        password = login_config.get("password")
                        
                        if dealer_code and password:
                            user_sel = login_config.get("username_selector", "#txt_dealer_code")
                            pass_sel = login_config.get("password_selector", "#txt_password")
                            
                            # Check if selectors exist on page (wait briefly)
                            try:
                                # Wait up to 3s for login fields
                                self.page.wait_for_selector(user_sel, timeout=3000)
                                logging.info("Login fields detected. Attempting to prefill...")
                                
                                self.page.fill(user_sel, dealer_code)
                                self.page.fill(pass_sel, password)
                                logging.info("Login fields prefilled successfully.")
                            except:
                                logging.info("Login fields not found on start page. Skipping prefill.")
                    except Exception as e:
                        logging.error(f"Error during login prefill: {e}")
                
                # Keep the browser open until stopped
                while self.is_running:
                    try:
                        # Check pending actions
                        if self.pending_action:
                            try:
                                action = self.pending_action
                                self.pending_action = None # Clear immediately
                                if action == 'reload':
                                    logging.info("Executing scheduled reload...")
                                    self.page.reload()
                                elif action == 'goto_start' and self.pending_url:
                                    logging.info(f"Executing scheduled navigation to {self.pending_url}...")
                                    self.page.goto(self.pending_url)
                                    self.pending_url = None
                            except Exception as nav_ex:
                                logging.error(f"Error executing pending action: {nav_ex}")

                        # Check if any page is still open
                        pages = self.context.pages
                        if len(pages) > 0:
                            try:
                                # Use the last page (active) to pump the event loop
                                pages[-1].wait_for_timeout(1000)
                            except Exception:
                                # If page closes during wait, fallback to short sleep
                                time.sleep(0.5)
                        else:
                            logging.info("All pages closed, stopping session.")
                            break
                    except Exception as e:
                        print(f"Browser loop error: {e}")
                        break
                        
        except Exception as e:
            print(f"Playwright error: {e}")
        finally:
            self.is_running = False

    def _handle_captured_data(self, source, data):
        """Callback for window.py_capture(data)"""
        try:
            # DEBUG RAW DATA
            try:
                with open("save_debug.txt", "a") as f:
                    f.write(f"RAW DATA: {data}\n")
            except:
                pass

            logging.info(f"Captured Data Received: {data}")
            
            # Check for Form Submission
            if data.get("type") == "form_submission":
                logging.info("Form Submission Event Detected!")
                
                # MERGE FORCED CAPTURE DATA
                forced_data = data.get("forced_capture", {})
                if forced_data:
                    logging.info(f"Merging {len(forced_data)} forced capture fields...")
                    page_url = data.get("url", "unknown_url")
                    
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

                success = self.processor.process_submission(self.session_data)
                if success:
                    logging.info("Invoice saved successfully. Clearing session data.")
                    self.clear_session_data()
                    
                    logging.info("Submission captured. Waiting for next action.")
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
                logging.error(f"Error getting page URL (using fallback): {e}")

            # Initialize page entry if not exists
            if page_url not in self.session_data["pages"]:
                self.session_data["pages"][page_url] = {
                    "last_updated": time.time(),
                    "fields": {}
                }
            
            # Update data
            selector = data.get("selector")
            if selector:
                self.session_data["pages"][page_url]["fields"][selector] = data
                self.session_data["pages"][page_url]["last_updated"] = time.time()
                
                logging.info(f"Data updated in memory for {page_url}. Calling _save_data()...")
                self._save_data()
            else:
                logging.warning(f"No selector in captured data: {data}")
                
        except Exception as e:
            logging.error(f"Error handling captured data: {e}")

    def _save_data(self):
        """Persist data to JSON file"""
        try:
            # Direct debug write
            try:
                with open("save_debug.txt", "a") as dbg:
                    dbg.write(f"{datetime.now()}: Attempting save. Pages: {len(self.session_data.get('pages', {}))}\n")
            except:
                pass

            logging.info(f"Saving data to {self.output_file}")
            
            # Ensure directory exists
            self.output_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Write to temporary file first to avoid corruption
            temp_file = self.output_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(self.session_data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            
            # Atomic rename
            if temp_file.exists():
                if self.output_file.exists():
                    self.output_file.unlink()
                temp_file.rename(self.output_file)
                logging.info("File saved successfully via atomic rename.")
                
        except Exception as e:
            msg = f"Error saving data: {e}"
            print(msg)
            logging.error(msg)
            # Fallback
            try:
                with open("save_error.txt", "a") as err:
                    err.write(f"{datetime.now()}: {msg}\n")
            except:
                pass

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
                        // u.setAttribute('data-prefilled', 'true');
                        // p.setAttribute('data-prefilled', 'true');
                        // Visual feedback removed
                        /*
                        const overlay = document.getElementById('fbr-debug-overlay');
                        if (overlay) {{
                            overlay.innerText = 'Login Prefilled';
                            overlay.style.backgroundColor = 'rgba(46, 204, 113, 0.9)';
                        }}
                        */
                        return true;
                    }}
                }} catch (e) {{
                    console.error('Prefill error', e);
                }}
                return false;
            }}

            // Attempt immediately and on mutations
            try {{ window.tryPrefillLogin = tryPrefillLogin; }} catch(e){{}}
            let __prefillDone = false;
            function ensurePrefillLoop() {{
                let attempts = 0;
                const maxAttempts = 12; // ~6 seconds
                const timer = setInterval(() => {{
                    if (tryPrefillLogin()) {{
                        __prefillDone = true;
                        clearInterval(timer);
                    }} else {{
                        attempts++;
                        if (attempts >= maxAttempts) clearInterval(timer);
                    }}
                }}, 500);
            }}
            ensurePrefillLoop();
            if (typeof MutationObserver !== 'undefined') {{
                const mo = new MutationObserver(() => {{ tryPrefillLogin(); }});
                if (document.body) mo.observe(document.body, {{ subtree: true, childList: true }});
            }}

            function getCssSelector(el) {{
                if (!(el instanceof Element)) return;
                
                let path = [];
                while (el.nodeType === Node.ELEMENT_NODE) {{
                    let selector = el.nodeName.toLowerCase();
                    if (el.id) {{
                        selector += '#' + el.id;
                        path.unshift(selector);
                        break;
                    }} else {{
                        let sib = el, nth = 1;
                        while (sib = sib.previousElementSibling) {{
                            if (sib.nodeName.toLowerCase() == selector)
                                nth++;
                        }}
                        if (nth != 1)
                            selector += ":nth-of-type("+nth+")";
                    }}
                    path.unshift(selector);
                    el = el.parentNode;
                }}
                return path.join(" > ");
            }}

            function isExcluded(el) {{
                return EXCLUDE_SELECTORS.some(sel => el.matches(sel));
            }}

            function isIncluded(el) {{
                // If whitelist is empty, allow everything (unless excluded)
                if (INCLUDE_SELECTORS.length === 0) return true;
                
                // Check if element matches any selector in the whitelist
                return INCLUDE_SELECTORS.some(sel => el.matches(sel));
            }}

            function capture(el, eventType) {{
                if (!el) return;
                
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
                
                console.log("Capturing:", data);

                // Visual Feedback
                try {{
                    el.style.outline = '2px solid #2ecc71'; // Green
                    el.style.boxShadow = '0 0 5px #2ecc71';
                    el.setAttribute('data-captured', 'true');
                }} catch(e) {{}}

                // Send to Python
                if (window.py_capture) {{
                    window.py_capture(data);
                }} else {{
                    console.error("py_capture binding not found!");
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
            ['input', 'change', 'blur', 'focusout', 'click'].forEach(event => {{
                document.addEventListener(event, (e) => {{
                    if (e.target.matches('input, textarea, select') || isIncluded(e.target)) {{
                        // For immediate feedback on change/blur, skip debounce or use short one
                        if (event === 'input') {{
                            debouncedCapture(e.target, event);
                        }} else {{
                            capture(e.target, event);
                        }}
                    }}
                }}, true);
            }});
            
            // Mutation Observer for complex widgets (like Select2 containers)
            if (typeof MutationObserver !== 'undefined') {{
                const observer = new MutationObserver((mutations) => {{
                    mutations.forEach((mutation) => {{
                        let target = mutation.target;
                        if (target.nodeType === 3) target = target.parentElement; // Text node -> Parent
                        
                        if (target && isIncluded(target)) {{
                            debouncedCapture(target, 'mutation');
                        }}
                    }});
                }});
                
                // Only observe if body exists (wait for load usually, but this script injects after load)
                if (document.body) {{
                    observer.observe(document.body, {{ 
                        subtree: true, 
                        childList: true, 
                        characterData: true,
                        attributes: true
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

            function pollWhitelistedElements() {{
                INCLUDE_SELECTORS.forEach(selector => {{
                    const els = document.querySelectorAll(selector);
                    els.forEach(el => {{
                        let val = el.value;
                        if (el.type === 'checkbox' || el.type === 'radio') {{
                            val = el.checked;
                        }} else if (el.tagName === 'SELECT') {{
                            val = Array.from(el.selectedOptions).map(opt => opt.value).join(',');
                        }} else if (val === undefined || val === null) {{
                            val = el.innerText || el.textContent || "";
                        }}

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
            }}
            
            // Poll every 2 seconds
            setInterval(pollWhitelistedElements, 2000);

            // -----------------------------------------------------------
            // SUBMIT DETECTION
            // -----------------------------------------------------------
            function handleSubmit(source) {{
                console.log("Submit detected via " + source);
                
                // Visual Feedback
                /*
                const overlay = document.getElementById('fbr-debug-overlay');
                if (overlay) {{
                    overlay.innerText = "Checking Validation...";
                    overlay.style.backgroundColor = "rgba(241, 196, 15, 0.9)"; // Yellow
                }}
                */

                // Wait for validation to trigger (1000ms)
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
                            if (el.offsetParent !== null && el.innerText.trim().length > 0) {{
                                hasErrors = true;
                                console.log("Validation Error Found:", el);
                                // Highlight
                                // try {{ el.style.border = '2px solid red'; }} catch(e){{}}
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
                        console.log("Validation errors found; continuing to capture state.");
                        /*
                        if (overlay) {{
                            overlay.innerText = "Validation Errors Found - Capturing State";
                            overlay.style.backgroundColor = "rgba(231, 76, 60, 0.9)";
                        }}
                        */
                    }}

                    /*
                    if (overlay) {{
                        overlay.innerText = "Processing Submission...";
                        overlay.style.backgroundColor = "rgba(46, 204, 113, 0.9)";
                    }}
                    */

                    // FORCE CAPTURE ALL FIELDS
                    const currentData = {{}};
                
                // 1. Capture by Whitelist
                INCLUDE_SELECTORS.forEach(selector => {{
                    const els = document.querySelectorAll(selector);
                    els.forEach(el => {{
                        let val = el.value;
                        if (el.type === 'checkbox' || el.type === 'radio') {{
                            val = el.checked;
                        }} else if (el.tagName === 'SELECT') {{
                            val = Array.from(el.selectedOptions).map(opt => opt.value).join(',');
                        }} else if (val === undefined || val === null) {{
                            val = el.innerText || el.textContent || "";
                        }}
                        
                        // Use ID if available for the key, else selector
                        const key = el.id ? '#' + el.id : selector;
                        currentData[key] = val;
                    }});
                }});

                // 2. DIAGNOSTIC: Capture ALL inputs on page to debug missing fields
                const debugInputs = {{}};
                document.querySelectorAll('input, select, textarea').forEach(el => {{
                    if (el.id) debugInputs[el.id] = el.value;
                    else debugInputs[el.name] = el.value;
                }});
                currentData['_debug_all_inputs'] = debugInputs;

                function grabText(selectors) {{
                    for (let i = 0; i < selectors.length; i++) {{
                        const els = document.querySelectorAll(selectors[i]);
                        for (let j = 0; j < els.length; j++) {{
                            const el = els[j];
                            let val = (el.innerText || el.textContent || '').trim();
                            if (val) {{
                                return val;
                            }}
                        }}
                    }}
                    return '';
                }}

                const nameFromFallback = grabText([
                    '#lbl_full_name',
                    '#lblCustomerName',
                    'span[id*="full_name"]',
                    'div[id*="full_name"]',
                    'span[id*="cust_name"]',
                    'div[id*="cust_name"]'
                ]);
                if (!currentData['#txt_full_name'] && nameFromFallback) {{
                    currentData['#txt_full_name'] = nameFromFallback;
                }}

                const fatherFromFallback = grabText([
                    '#lbl_father_name',
                    '#lblFatherName',
                    'span[id*="father_name"]',
                    'div[id*="father_name"]',
                    'span[id*="father"]',
                    'div[id*="father"]'
                ]);
                if (!currentData['#txt_father_name'] && fatherFromFallback) {{
                    currentData['#txt_father_name'] = fatherFromFallback;
                }}

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

            // ADD MANUAL TRIGGER BUTTON
            function addManualTrigger() {{
                // No-op: Manual trigger button removed
            }}
            
            // Call it
            if (document.readyState === 'loading') {{
                document.addEventListener('DOMContentLoaded', addManualTrigger);
            }} else {{
                addManualTrigger();
            }}

            document.addEventListener('click', function(e) {{
                // DEBUG CLICK
                console.log("Clicked:", e.target);
                
                // Check if it matches submit selector OR is a generic save button
                const isSubmit = e.target.matches(SUBMIT_SELECTOR) || e.target.closest(SUBMIT_SELECTOR);
                
                // Backup check for "Save" text if selector fails
                const isSaveBtn = (e.target.innerText && e.target.innerText.toLowerCase().includes('save')) || 
                                  (e.target.value && e.target.value.toLowerCase().includes('save'));

                if (isSubmit || isSaveBtn) {{
                    console.log("Save action detected!");
                    handleSubmit('click');
                }}
            }}, true);

            // -----------------------------------------------------------
            // DEBUG OVERLAY
            // -----------------------------------------------------------
            function initOverlay() {{
                // No-op: Debug overlay removed
            }}

            if (document.readyState === 'loading') {{
                document.addEventListener('DOMContentLoaded', initOverlay);
            }} else {{
                initOverlay();
            }}

            function forceLayout() {{
                // No-op: Layout forcing removed to restore default CSS
            }}
            
            if (document.readyState === 'loading') {{
                document.addEventListener('DOMContentLoaded', forceLayout);
            }} else {{
                forceLayout();
            }}
            
            console.log("Form Capture Injector Loaded - Listening for events");
        }})();
        """

form_capture_service = FormCaptureService()
