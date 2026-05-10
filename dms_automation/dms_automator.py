
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

                self.context = p.chromium.launch_persistent_context(
                    user_data_dir=str(settings.BROWSER_PROFILE_DIR),
                    headless=settings.HEADLESS_MODE,
                    channel="chrome",
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--start-maximized"
                    ],
                    no_viewport=True
                )

                if self.context.pages:
                    self.page = self.context.pages[0]
                else:
                    self.page = self.context.new_page()

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

    def fill_vehicle_details(self, frame_number: str, engine_number: str):
        """Fill frame number and engine number into the portal"""
        def _fill_task(page: Page):
            logger.info(f"Filling vehicle details - Frame: {frame_number}, Engine: {engine_number}")

            frame_selectors = [
                "input[name*='frame']", "input[name*='chassis']", "#frame", "#chassis",
                "input[placeholder*='Frame']", "input[placeholder*='frame']",
                "input[placeholder*='Chassis']", "input[placeholder*='chassis']"
            ]

            engine_selectors = [
                "input[name*='engine']", "#engine",
                "input[placeholder*='Engine']", "input[placeholder*='engine']"
            ]

            frame_field = None
            for sel in frame_selectors:
                try:
                    if page.locator(sel).is_visible(timeout=2000):
                        frame_field = sel
                        break
                except:
                    continue

            engine_field = None
            for sel in engine_selectors:
                try:
                    if page.locator(sel).is_visible(timeout=2000):
                        engine_field = sel
                        break
                except:
                    continue

            result = {
                "frame_field_found": frame_field is not None,
                "engine_field_found": engine_field is not None,
                "frame_number_filled": False,
                "engine_number_filled": False
            }

            if frame_field:
                page.fill(frame_field, frame_number)
                result["frame_number_filled"] = True
                logger.info(f"Frame number filled: {frame_number}")

            if engine_field:
                page.fill(engine_field, engine_number)
                result["engine_number_filled"] = True
                logger.info(f"Engine number filled: {engine_number}")

            if not result["frame_field_found"] or not result["engine_field_found"]:
                logger.warning("Could not find one or more fields. Please navigate to the correct page.")

            return result

        return self.execute_task(_fill_task)

    def navigate_to(self, url: str):
        """Navigate to a specific URL"""
        def _navigate_task(page: Page):
            logger.info(f"Navigating to {url}")
            page.goto(url, timeout=60000)
            page.wait_for_load_state("networkidle", timeout=30000)
            return True

        return self.execute_task(_navigate_task)
