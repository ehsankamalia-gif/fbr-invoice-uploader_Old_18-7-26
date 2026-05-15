
import logging
import threading
import queue
import time
from typing import Optional, Dict, Any
from playwright.sync_api import sync_playwright, Page, BrowserContext
from config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(settings.LOG_DIR / "dms_automation.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


class DMSAutomator:
    def __init__(self):
        self.is_running = False
        self.playwright = None
        self.browser = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.thread: Optional[threading.Thread] = None
        self.task_queue = queue.Queue()
        self.result_queue = queue.Queue()

    def start(self):
        """Start the browser automation in a background thread"""
        if self.is_running:
            logger.warning("Automator is already running")
            return

        self.is_running = True
        self.thread = threading.Thread(target=self._run_browser, daemon=True)
        self.thread.start()
        logger.info("DMS Automator started in background thread")

    def stop(self):
        """Stop the browser automation"""
        self.is_running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        if self.context:
            try:
                self.context.close()
            except:
                pass
        if self.playwright:
            try:
                self.playwright.stop()
            except:
                pass
        logger.info("DMS Automator stopped")

    def execute_task(self, task_func):
        """Execute a task in the browser thread and return the result"""
        if not self.is_running:
            raise RuntimeError("Automator is not running. Call start() first.")

        self.task_queue.put(task_func)
        result = self.result_queue.get()
        if isinstance(result, Exception):
            raise result
        return result

    def _run_browser(self):
        """Main browser loop that runs in the background thread"""
        try:
            with sync_playwright() as p:
                self.playwright = p

                logger.info(f"Launching browser with profile at {settings.BROWSER_PROFILE_DIR}")

                # Enhanced browser launch options to bypass detection
                self.context = p.chromium.launch_persistent_context(
                    user_data_dir=str(settings.BROWSER_PROFILE_DIR),
                    headless=settings.HEADLESS_MODE,
                    channel="chrome",
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--start-maximized",
                        "--ignore-certificate-errors",
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-infobars",
                        "--window-position=0,0",
                        "--ignore-certifcate-errors",
                        "--ignore-certifcate-errors-spki-list",
                        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    ],
                    no_viewport=True,
                    ignore_https_errors=True
                )

                if self.context.pages:
                    self.page = self.context.pages[0]
                else:
                    self.page = self.context.new_page()

                # Stealth initialization script
                self.page.add_init_script("""
                    // Hide automation properties
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    window.chrome = { runtime: {} };
                    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                """)

                logger.info("Browser launched successfully")

                while self.is_running:
                    try:
                        if not self.task_queue.empty():
                            task = self.task_queue.get_nowait()
                            try:
                                result = task(self.page)
                                self.result_queue.put(result)
                            except Exception as e:
                                logger.error(f"Task execution failed: {e}")
                                self.result_queue.put(e)

                        if self.context.pages:
                            self.context.pages[-1].wait_for_timeout(100)
                        else:
                            time.sleep(0.1)

                    except queue.Empty:
                        time.sleep(0.1)
                    except Exception as e:
                        logger.error(f"Browser loop error: {e}")
                        time.sleep(0.1)

        except Exception as e:
            logger.error(f"Browser startup failed: {e}")
        finally:
            self.is_running = False

    def login(self):
        """Login to DMS portal"""
        def _login_task(page: Page):
            logger.info(f"Navigating to {settings.DMS_PORTAL_URL}")
            page.goto(settings.DMS_PORTAL_URL, timeout=60000)
            page.wait_for_load_state("networkidle", timeout=30000)

            if settings.DMS_USERNAME and settings.DMS_PASSWORD:
                logger.info("Attempting to auto-fill login credentials")

                username_selectors = [
                    "input[name='username']", "input[name*='user']", "#username", "#user",
                    "input[type='text']", "input[placeholder*='User']", "input[placeholder*='user']"
                ]
                password_selectors = [
                    "input[name='password']", "input[name*='pass']", "#password", "#pass",
                    "input[type='password']", "input[placeholder*='Password']", "input[placeholder*='password']"
                ]

                username_field = None
                for sel in username_selectors:
                    try:
                        if page.locator(sel).is_visible(timeout=2000):
                            username_field = sel
                            break
                    except:
                        continue

                password_field = None
                for sel in password_selectors:
                    try:
                        if page.locator(sel).is_visible(timeout=2000):
                            password_field = sel
                            break
                    except:
                        continue

                if username_field:
                    page.fill(username_field, settings.DMS_USERNAME)
                    logger.info("Username filled")

                if password_field:
                    page.fill(password_field, settings.DMS_PASSWORD)
                    logger.info("Password filled")

                logger.info("Login fields populated. Please complete login manually if needed.")

            return True

        return self.execute_task(_login_task)

    def wait_for_login(self, timeout: int = 300):
        """Wait for the user to complete login manually"""
        def _wait_task(page: Page):
            logger.info(f"Waiting up to {timeout}s for login to complete...")
            
            # Indicators that we are logged in (common logout or dashboard elements)
            logged_in_indicators = [
                "a[href*='logout']", 
                "button[id*='logout']", 
                "i.fa-sign-out", 
                ".user-profile",
                "text=Dashboard",
                "text=Welcome"
            ]
            
            start_time = time.time()
            while time.time() - start_time < timeout:
                # Check if URL has changed from login page
                current_url = page.url.lower()
                if "login" not in current_url and "auth" not in current_url:
                    logger.info(f"Login detected via URL change: {current_url}")
                    return True
                
                # Check for logged-in elements
                for selector in logged_in_indicators:
                    try:
                        if page.locator(selector).is_visible(timeout=500):
                            logger.info(f"Login detected via selector: {selector}")
                            
                            # Check for the "OK" modal after login
                            self._dismiss_welcome_modal(page)
                            
                            # Navigate to Job Cards menu
                            self._navigate_to_job_cards(page)
                            
                            return True
                    except:
                        continue
                
                page.wait_for_timeout(1000)
            
            logger.warning("Login wait timed out.")
            return False

        return self.execute_task(_wait_task)

    def _get_all_frames(self, page: Page):
        """Helper to get all frames on the page, including the main page"""
        return [page] + page.frames

    def _smart_click(self, frame, locator):
        """Perform a robust click using multiple techniques: coordinate-based, JS, and standard"""
        try:
            # Technique 1: Scroll and move mouse to center of element
            box = locator.bounding_box()
            if box:
                center_x = box['x'] + box['width'] / 2
                center_y = box['y'] + box['height'] / 2
                
                # Move mouse to element (triggers hover events)
                self.page.mouse.move(center_x, center_y)
                self.page.wait_for_timeout(100)
                
                # Click the specific coordinates
                self.page.mouse.click(center_x, center_y)
                logger.info(f"Performed coordinate-based click at {center_x}, {center_y}")
                return True
            
            # Technique 2: Standard Force Click
            locator.click(force=True, timeout=2000)
            return True
        except Exception as e:
            logger.debug(f"Smart click failed: {e}")
            
            # Technique 3: JavaScript Dispatch Click (last resort)
            try:
                frame.evaluate("el => el.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}))", locator.element_handle())
                return True
            except:
                return False

    def _dismiss_welcome_modal(self, page: Page):
        """Helper to persistently click OK on the welcome modal using multiple methods across all frames"""
        logger.info("Starting persistent modal dismissal across all frames...")
        
        ok_selectors = [
            "//button[contains(text(), 'OK')]",
            "button:has-text('OK')",
            ".swal2-confirm",
            "button.btn-primary",
            "text=OK"
        ]

        for attempt in range(5):
            logger.info(f"Modal dismissal attempt {attempt + 1}/5...")
            
            for frame in self._get_all_frames(page):
                try:
                    # Try clicking each selector using smart click
                    for selector in ok_selectors:
                        try:
                            locator = frame.locator(selector).first
                            if locator.is_visible(timeout=200):
                                logger.info(f"Found modal button via {selector}. Clicking...")
                                self._smart_click(frame, locator)
                                page.wait_for_timeout(500)
                        except: continue
                    
                    # Also try global Enter
                    page.keyboard.press("Enter")
                except: continue
            
            # Check visibility across frames
            modal_visible = False
            for frame in self._get_all_frames(page):
                try:
                    modal_indicators = [".modal-backdrop", ".modal-content", ".swal2-container", "div[role='dialog']"]
                    for ind in modal_indicators:
                        if frame.locator(ind).is_visible(timeout=200):
                            modal_visible = True
                            break
                except: continue
            
            if not modal_visible:
                logger.info("Modal dismissed successfully.")
                page.wait_for_timeout(1000)
                return True
                
            page.wait_for_timeout(1000)

        return True

    def _navigate_to_job_cards(self, page: Page):
        """Helper to click on the Job Cards menu on the left sidebar (frame-aware)"""
        logger.info("Attempting to navigate to Job Cards menu...")
        
        job_card_selectors = [
            "//span[contains(text(), 'Job Cards')]",
            "//a[contains(., 'Job Cards')]",
            "li:has-text('Job Cards')",
            "text=Job Cards",
            ".sidebar-menu a:has-text('Job Cards')",
            "//i[contains(@class, 'fa-id-card')]/following-sibling::span[contains(text(), 'Job Cards')]"
        ]
        
        for frame in self._get_all_frames(page):
            for selector in job_card_selectors:
                try:
                    locator = frame.locator(selector).first
                    if locator.is_visible(timeout=500):
                        logger.info(f"Job Cards menu found in frame via {selector}. Clicking...")
                        
                        # Check if menu needs expanding (if it has a parent treeview)
                        try:
                            parent_li = locator.locator("xpath=ancestor::li").first
                            if "treeview" in (parent_li.get_attribute("class") or ""):
                                logger.info("Detected expandable menu, ensuring it is open...")
                                self._smart_click(frame, parent_li)
                                page.wait_for_timeout(500)
                        except: pass

                        self._smart_click(frame, locator)
                        page.wait_for_timeout(2000)
                        return True
                except:
                    continue
        
        logger.warning("Could not find Job Cards menu on the sidebar.")
        return False

    def fill_vehicle_details(self, frame_number: str, engine_number: str):
        """Fill frame number and engine number into the portal with aggressive detection across frames"""
        def _fill_task(page: Page):
            # 1. Final check to dismiss any lingering modals or popups
            self._dismiss_welcome_modal(page)
            
            logger.info(f"Attempting to fill details - Frame: {frame_number}, Engine: {engine_number}")

            # 2. Aggressive field detection with visual highlighting across all frames
            def find_and_fill(selectors, value, field_name):
                logger.info(f"Searching for {field_name} field across all frames...")
                for frame in self._get_all_frames(page):
                    for selector in selectors:
                        try:
                            locator = frame.locator(selector).first
                            if locator.is_visible(timeout=500):
                                logger.info(f"Found {field_name} in frame via: {selector}")
                                
                                # Visual feedback: Highlight the field
                                frame.evaluate(f"el => el.style.border = '3px solid #e67e22'", locator.element_handle())
                                
                                locator.scroll_into_view_if_needed()
                                locator.click(force=True)
                                page.keyboard.press("Control+A")
                                page.keyboard.press("Backspace")
                                locator.fill(value)
                                return True
                        except: continue
                return False

            frame_selectors = [
                "input[name*='chassis']", "input[name*='frame']", 
                "input[placeholder*='Chassis']", "input[placeholder*='Frame']",
                "//label[contains(text(), 'Chassis')]/following::input",
                "//label[contains(text(), 'Frame')]/following::input",
                "#chassis_no", "#frame_no"
            ]

            engine_selectors = [
                "input[name*='engine']", "input[placeholder*='Engine']",
                "//label[contains(text(), 'Engine')]/following::input",
                "#engine_no"
            ]

            # Try to fill both fields
            frame_filled = find_and_fill(frame_selectors, frame_number, "Chassis/Frame")
            page.wait_for_timeout(500)
            engine_filled = find_and_fill(engine_selectors, engine_number, "Engine")

            # Final JS fallback across frames
            if not frame_filled or not engine_filled:
                for frame in self._get_all_frames(page):
                    try:
                        frame.evaluate(f"""(f, e) => {{
                            const inputs = Array.from(document.querySelectorAll('input'));
                            const fIn = inputs.find(i => i.name.toLowerCase().includes('chassis') || i.placeholder.toLowerCase().includes('chassis'));
                            const eIn = inputs.find(i => i.name.toLowerCase().includes('engine') || i.placeholder.toLowerCase().includes('engine'));
                            if (fIn) {{ fIn.value = f; fIn.dispatchEvent(new Event('input', {{ bubbles: true }})); }}
                            if (eIn) {{ eIn.value = e; eIn.dispatchEvent(new Event('input', {{ bubbles: true }})); }}
                        }}""", frame_number, engine_number)
                    except: continue

            return {"success": frame_filled or engine_filled}

        return self.execute_task(_fill_task)

    def navigate_to(self, url: str):
        """Navigate to a specific URL"""
        def _navigate_task(page: Page):
            logger.info(f"Navigating to {url}")
            page.goto(url, timeout=60000)
            page.wait_for_load_state("networkidle", timeout=30000)
            return True

        return self.execute_task(_navigate_task)
