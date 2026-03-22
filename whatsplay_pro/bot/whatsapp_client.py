import asyncio
import logging
import time
import os
import base64
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List
from playwright.async_api import async_playwright, Playwright, BrowserContext, Page, Error as PlaywrightError
from whatsplay_pro.core.config import Config
from whatsplay_pro.core.signals import signals
from whatsplay_pro.bot.message_queue import outgoing_queue, QueuedMessage

logger = logging.getLogger(__name__)

class WhatsAppClient:
    """Robust Playwright-based WhatsApp Web client (WhatsPlay Wrapper)."""
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.playwright: Optional[Playwright] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._is_running = False
        self._is_ready = False
        self._qr_captured = False
        self._event_handlers: Dict[str, List[Callable]] = {
            "on_message": [],
            "on_ready": [],
            "on_auth": [],
            "on_disconnected": []
        }
        
        # Anti-ban safety
        self._last_send_time = 0
        self._message_delay_min = Config.MIN_DELAY
        self._message_delay_max = Config.MAX_DELAY

    def add_handler(self, event_name: str, handler: Callable):
        """Register a callback for specific events."""
        if event_name in self._event_handlers:
            self._event_handlers[event_name].append(handler)

    async def _emit(self, event_name: str, *args, **kwargs):
        """Trigger registered event handlers."""
        if event_name in self._event_handlers:
            for handler in self._event_handlers[event_name]:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(*args, **kwargs)
                    else:
                        handler(*args, **kwargs)
                except Exception as e:
                    logger.error(f"Error in handler {handler.__name__} for {event_name}: {e}")

    async def start(self):
        """Initialize Playwright and launch the browser."""
        if self._is_running:
            return
            
        logger.info("Starting WhatsApp Client Initialization...")
        signals.wa_starting.emit()
        self._is_running = True
        
        try:
            self.playwright = await async_playwright().start()
            
            # Use LocalProfileAuth simulation via persistent context
            self.context = await self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(Config.WHATSAPP_SESSION_DIR),
                headless=self.headless,
                viewport={'width': 1280, 'height': 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled'
                ]
            )
            
            self.page = await self.context.new_page()
            
            # Start monitoring
            asyncio.create_task(self._monitor_status())
            
            # Navigate to WhatsApp
            logger.info("Navigating to web.whatsapp.com...")
            await self.page.goto("https://web.whatsapp.com", wait_until="commit", timeout=60000)
            
            # Inject monitoring scripts and event listeners
            await self._setup_listeners()
            
        except Exception as e:
            logger.error(f"Failed to start WhatsApp client: {e}")
            self._is_running = False
            signals.wa_error.emit(str(e))

    async def _setup_listeners(self):
        """Setup page-level listeners for messages and state changes."""
        # This is a simplified version of WhatsPlay logic
        # In a real system, we'd inject JS to hook into the WhatsApp internal stores
        pass

    async def _monitor_status(self):
        """Background loop to check for QR, connectivity, and session status."""
        logger.info("Monitoring session status...")
        
        while self._is_running:
            try:
                if not self.page or self.page.is_closed():
                    break
                    
                # 1. Check for QR Code
                qr_canvas = await self.page.query_selector("canvas[aria-label='Scan me!']")
                if qr_canvas and not self._is_ready:
                    qr_data = await qr_canvas.screenshot()
                    qr_b64 = base64.b64encode(qr_data).decode('utf-8')
                    signals.wa_auth_required.emit(qr_b64)
                    await self._emit("on_auth", qr_b64)
                    await asyncio.sleep(5) # Poll QR every 5s
                    continue
                
                # 2. Check for Chat List (Logged In)
                chat_list = await self.page.query_selector("div[data-testid='chat-list']")
                if chat_list and not self._is_ready:
                    logger.info("WhatsApp Web is READY and CONNECTED.")
                    self._is_ready = True
                    signals.wa_ready.emit()
                    await self._emit("on_ready")
                
                # 3. Check for Incoming Messages (Simplified Polling)
                if self._is_ready:
                    await self._poll_incoming_messages()
                
            except Exception as e:
                logger.debug(f"Monitor loop error (expected during startup/shutdown): {e}")
                
            await asyncio.sleep(3)

    async def _poll_incoming_messages(self):
        """Simplified logic to find unread chats and process messages."""
        # Real WhatsPlay 1.9.8 would use internal hooks, we'll simulate with selectors
        unread_selector = "span[aria-label*='unread message']"
        unreads = await self.page.query_selector_all(unread_selector)
        
        if unreads:
            logger.info(f"Found {len(unreads)} unread chats. Processing...")
            # Logic to click and read messages would go here
            # For each message: signals.new_message_received.emit(msg_data)

    async def send_message(self, chat_id: str, message: str) -> bool:
        """Send a text message to a chat ID (phone number with @c.us or @g.us)."""
        if not self._is_ready:
            return False
            
        try:
            # Simulate human behavior: random delay
            import random
            delay = random.uniform(self._message_delay_min, self._message_delay_max)
            logger.info(f"Anti-ban safety: waiting {delay:.2f}s before sending to {chat_id}")
            await asyncio.sleep(delay)
            
            # Simple navigation send (more robust ways exist in WhatsPlay)
            send_url = f"https://web.whatsapp.com/send?phone={chat_id.split('@')[0]}&text={message}"
            await self.page.goto(send_url, wait_until="commit")
            
            send_btn = await self.page.wait_for_selector("span[data-icon='send']", timeout=30000)
            if send_btn:
                await send_btn.click()
                logger.info(f"Message sent to {chat_id}")
                signals.message_sent.emit({"chat_id": chat_id, "status": "success"})
                return True
                
        except Exception as e:
            logger.error(f"Failed to send message to {chat_id}: {e}")
            signals.message_sent.emit({"chat_id": chat_id, "status": "failed", "error": str(e)})
            
        return False

    async def stop(self):
        """Graceful shutdown of the client."""
        logger.info("Stopping WhatsApp Client...")
        self._is_running = False
        self._is_ready = False
        
        if self.context:
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()
        
        logger.info("WhatsApp Client SHUTDOWN COMPLETE.")
        signals.wa_disconnected.emit("Manual shutdown")
