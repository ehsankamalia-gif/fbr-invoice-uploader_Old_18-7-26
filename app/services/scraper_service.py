import logging
import sys
import threading
import time
from typing import List, Dict, Optional
from app.services.form_capture_service import FormCaptureService

logger = logging.getLogger(__name__)

class HondaScraper:
    def __init__(self):
        self.capture_service = FormCaptureService()

    def start_browser(self, headless=False):
        """Ensures the browser instance is running via FormCaptureService."""
        if not self.capture_service.is_running:
            self.capture_service.start_capture_session()

    def close(self):
        # We generally don't close the shared browser service
        pass

    def login(self, url: str, username: str = None, password: str = None):
        """Navigates to the URL and performs auto-login using the shared browser."""
        def login_task(page):
            # Same logic as before, adapted for 'page' argument
            from app.core.config import settings

            max_retries = 2
            for attempt in range(max_retries):
                try:
                    logger.info(f"Navigating to {url} (Attempt {attempt+1}/{max_retries})...")
                    page.goto(url, timeout=30000)
                    break 
                except Exception as e:
                    logger.warning(f"Navigation error on attempt {attempt+1}: {e}")
                    if attempt == max_retries - 1:
                        raise e
                    time.sleep(2)

            try:
                # Apply layout fixes immediately after navigation
                self._apply_layout_fixes(page)
                
                # Wait for the page to be stable
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except:
                    pass 
                    
                found_user_selector = None
                found_pass_selector = None
                
                # Strategy A: Precise Placeholders
                try:
                    if page.get_by_placeholder("Enter Dealer Code").is_visible():
                        logger.info("Found 'Enter Dealer Code' field.")
                        page.get_by_placeholder("Enter Dealer Code").fill(username)
                        found_user_selector = "placeholder='Enter Dealer Code'"
                    
                    if page.get_by_placeholder("Enter Password").is_visible():
                        logger.info("Found 'Enter Password' field.")
                        page.get_by_placeholder("Enter Password").fill(password)
                        found_pass_selector = "placeholder='Enter Password'"
                except Exception as e:
                    logger.warning(f"Placeholder strategy failed: {e}")

                # Strategy B: CSS Selectors (Fallback)
                if not found_user_selector:
                    user_selectors = [
                        "input[name='username']", "input[name*='user']", "#username", "#user",
                        "input[type='text']"
                    ]
                    for sel in user_selectors:
                        if page.is_visible(sel):
                            page.fill(sel, username)
                            found_user_selector = sel
                            break
                
                if not found_pass_selector:
                    pass_selectors = [
                        "input[name='password']", "input[name*='pass']", "#password", "#pass",
                        "input[type='password']"
                    ]
                    for sel in pass_selectors:
                        if page.is_visible(sel):
                            page.fill(sel, password)
                            found_pass_selector = sel
                            break

                if not found_user_selector or not found_pass_selector:
                    logger.warning(f"Could not identify all login fields.")
                    return

                # Focus CAPTCHA
                captcha_selectors = ["input[placeholder='Type the Confirm Text']", "input[name*='captcha']", "input[name*='code']"]
                for cap in captcha_selectors:
                     try:
                        if page.is_visible(cap):
                            logger.info("CAPTCHA detected. Focusing field for user...")
                            page.focus(cap)
                            break
                     except: continue

                logger.info("Login fields populated.")

            except Exception as e:
                logger.error(f"Auto-login process failed: {e}")
                # We raise exception so the caller knows it failed
                raise e

        # Execute the task
        try:
            self.capture_service.execute_task(login_task)
        except Exception as e:
             logger.warning(f"Auto-login could not complete: {e}. Please login manually.")

    def _apply_layout_fixes(self, page):
        pass

    def trigger_bookmark_dialog(self):
        def task(page):
            page.bring_to_front()
            modifier = "Meta" if sys.platform == "darwin" else "Control"
            page.keyboard.press(f"{modifier}+d")
        self.capture_service.execute_task(task)

    def scrape_current_page(self, page_num: int = 1) -> List[Dict]:
        def task(page):
            return self._scrape_page_logic(page, page_num)
        return self.capture_service.execute_task(task)

    def _scrape_page_logic(self, page, page_num):
        # Logic extracted from scrape_current_page
        try:
            page.wait_for_selector("table", timeout=5000)
        except:
            pass 

        data = []
        rows = page.query_selector_all("tbody tr")
        if not rows:
            rows = page.query_selector_all("tr")
            if rows:
                rows = rows[1:]

        for row in rows:
            cells = row.query_selector_all("td")
            if len(cells) < 7:
                continue 
            
            try:
                p_order = cells[1].inner_text().strip()
                model = cells[3].inner_text().strip()
                color = cells[4].inner_text().strip()
                engine = cells[5].inner_text().strip()
                chassis = cells[6].inner_text().strip()
                status_text = cells[7].inner_text().strip()

                status = "IN_STOCK"
                if "sold" in status_text.lower():
                    status = "SOLD"

                item = {
                    "purchase_order": p_order,
                    "model_code": model,
                    "color_code": color,
                    "engine_number": engine,
                    "chassis_number": chassis,
                    "status": status,
                    "page_number": page_num
                }
                
                if engine and chassis:
                    data.append(item)
            except Exception as e:
                logger.warning(f"Error parsing row: {e}")
                continue
            
        return data

    def detect_total_pages(self) -> Optional[int]:
        def task(page):
            try:
                result = page.evaluate(r"""() => {
                    const allElements = document.querySelectorAll('*');
                    for (const el of allElements) {
                        if (el.innerText && el.innerText.length < 50 && el.innerText.match(/of\s+(\d+)/i)) {
                             const match = el.innerText.match(/of\s+(\d+)/i);
                             if (match) {
                                     const num = parseInt(match[1]);
                                     const text = el.textContent.toLowerCase();
                                     if (text.includes('page')) return num;
                                     if (text.includes('item') || text.includes('record') || text.includes('entry')) continue; 
                                     if (num < 100) return num;
                                 }
                            }
                        }
                    return null;
                }""")
                if result:
                    logger.info(f"Detected total pages from UI: {result}")
                return result
            except:
                return None
        return self.capture_service.execute_task(task)

    def scrape_all_pages(self, max_pages=10, status_callback=None, retry_count=3, delay=1.0) -> List[Dict]:
        """
        Scrapes multiple pages. 
        WARNING: This blocks the caller if executed synchronously.
        Best called from a background thread.
        """
        def task(page):
            accumulated_data = []
            seen_keys = set()
            
            # Detect total pages
            total_pages = None
            try:
                # We can call the logic directly since we have 'page'
                # But detect_total_pages is defined as a method that calls execute_task.
                # We shouldn't call self.detect_total_pages() from within a task!
                # It would try to queue another task and deadlock.
                # So we need to duplicate logic or structure it better.
                # I'll just skip detection or use a simpler check here.
                pass
            except: pass
            
            total_str = ""
            
            for page_num in range(1, max_pages + 1):
                if status_callback:
                    status_callback(f"Scraping Page {page_num}{total_str}... (Items: {len(accumulated_data)})")
                    
                logger.info(f"Starting scrape for page {page_num}")
                
                first_cell_text = self._get_first_cell_text(page)
                old_row_count = 0
                try:
                    old_row_count = len(page.query_selector_all("tbody tr"))
                except: pass
                
                page_data = []
                for attempt in range(retry_count):
                    try:
                        page_data = self._scrape_page_logic(page, page_num)
                        if page_data:
                            break 
                        else:
                            if status_callback:
                                status_callback(f"Page {page_num}{total_str}: Retrying ({attempt+1}/{retry_count})...")
                            if attempt < retry_count - 1:
                                time.sleep(2)
                    except Exception as e:
                        logger.error(f"Error scraping page {page_num}: {e}")

                if page_data:
                    new_items = 0
                    for item in page_data:
                        key = (item.get("purchase_order", ""), item.get("chassis_number", ""), item.get("engine_number", ""))
                        if key not in seen_keys:
                            seen_keys.add(key)
                            accumulated_data.append(item)
                            new_items += 1
                    
                    if status_callback:
                        status_callback(f"Page {page_num}{total_str} Done. Added {new_items}. Total: {len(accumulated_data)}")

                    if new_items == 0 and len(page_data) > 0:
                        if status_callback:
                            status_callback(f"Stopping: No new data on Page {page_num}.")
                        return accumulated_data 
                else:
                    if status_callback:
                        status_callback(f"Page {page_num}{total_str} Failed/Empty. Continuing...")
                    logger.info(f"Page {page_num} is empty. Assuming end of list.")
                    break
                
                if page_num >= max_pages:
                    break
                
                if status_callback:
                    status_callback(f"Page {page_num}{total_str}: Navigating to next...")
                    
                if not self._go_to_next_page(page, current_page_num=page_num):
                    logger.info("No next page found or reached end.")
                    break
                
                if delay > 0:
                    time.sleep(delay)
                    
                if status_callback:
                    status_callback(f"Page {page_num + 1}{total_str}: Waiting for load...")
                
                self._wait_for_table_update(page, old_text=first_cell_text, old_row_count=old_row_count)
                    
            return accumulated_data

        return self.capture_service.execute_task(task)

    def _get_first_cell_text(self, page) -> str:
        try:
            cell = page.query_selector("tbody tr:first-child td:nth-child(2)") 
            if cell:
                return cell.inner_text().strip()
        except:
            pass
        return ""

    def _wait_for_table_update(self, page, old_text: str, old_row_count: int = 0) -> bool:
        try:
            old_text_safe = old_text.replace("'", "\\'")
            page.wait_for_function(
                f"""() => {{
                    let firstRow = document.querySelector('tbody tr');
                    if (!firstRow) {{
                        const rows = document.querySelectorAll('tr');
                        if (rows.length > 1) firstRow = rows[1]; 
                    }}
                    if (!firstRow) return false;
                    const cell = firstRow.querySelector('td:nth-child(2)');
                    const currentText = cell ? cell.innerText.trim() : '';
                    let rowCount = document.querySelectorAll('tbody tr').length;
                    if (rowCount === 0) {{
                        rowCount = Math.max(0, document.querySelectorAll('tr').length - 1);
                    }}
                    return (currentText !== '{old_text_safe}') || (rowCount > {old_row_count});
                }}""",
                timeout=10000 
            )
            page.wait_for_timeout(500) 
            return True
        except Exception as e:
            page.wait_for_timeout(2000)
            return False

    def _go_to_next_page(self, page, current_page_num: int = None) -> bool:
        next_page = current_page_num + 1 if current_page_num else 2
        
        # 1. STRATEGY: Input Field
        try:
            inputs = page.query_selector_all('input[type="text"], input[type="number"], input:not([type])')
            for inp in inputs:
                if not inp.is_visible(): continue
                val = inp.input_value()
                if val and val.strip() == str(current_page_num):
                    box = inp.bounding_box()
                    if box and box['width'] > 150: continue 
                    try:
                        inp.click() 
                        inp.fill(str(next_page))
                        inp.press("Enter")
                        page.wait_for_timeout(200)
                        inp.press("Tab") 
                        return True
                    except: pass
        except: pass

        # 2. STRATEGY: Dropdown (Select)
        try:
            selects = page.query_selector_all('select')
            for select in selects:
                if not select.is_visible(): continue
                val = select.input_value()
                if val == str(current_page_num):
                     try:
                        select.select_option(str(next_page))
                        return True
                     except: pass
        except: pass
        
        # 3. STRATEGY: Next Button/Icon
        try:
            candidates = [
                "button[title='Next Page']", "a[title='Next Page']", 
                "button[aria-label='Next Page']", 
                ".k-pager-nav.k-pager-last", ".next", ".next-page", 
                "xpath=//a[contains(text(), 'Next')]", 
                "xpath=//button[contains(text(), 'Next')]",
                "xpath=//span[contains(@class, 'icon-next')]/.."
            ]
            for sel in candidates:
                if page.is_visible(sel):
                    page.click(sel)
                    return True
        except: pass
        
        # 4. STRATEGY: Page Number Links
        try:
            link = page.get_by_role("link", name=str(next_page), exact=True)
            if link.is_visible():
                link.click()
                return True
            
            btn = page.get_by_role("button", name=str(next_page), exact=True)
            if btn.is_visible():
                btn.click()
                return True
        except: pass

        return False
