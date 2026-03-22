import asyncio
import logging
import threading
from PyQt6.QtCore import QThread, pyqtSignal, QObject
from whatsplay_pro.bot.whatsapp_client import WhatsAppClient
from whatsplay_pro.bot.message_queue import outgoing_queue, QueuedMessage
from whatsplay_pro.core.signals import signals
from whatsplay_pro.ai.chatbot import ai_orchestrator

logger = logging.getLogger(__name__)

class WhatsAppWorker(QThread):
    """Background worker for the WhatsApp client event loop."""
    
    def __init__(self, headless: bool = True):
        super().__init__()
        self.headless = headless
        self.client: Optional[WhatsAppClient] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._is_running = True

    def run(self):
        """Entry point for the background thread."""
        logger.info("WhatsApp background thread STARTED.")
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        
        # Initialize client
        self.client = WhatsAppClient(headless=self.headless)
        
        # Connect client events to orchestrators/signals
        self.client.add_handler("on_message", self._handle_incoming_message)
        
        # Run startup and process queues
        self._loop.run_until_complete(self.client.start())
        
        # Run the main task processor loop
        self._loop.run_until_complete(self._main_loop())
        
        logger.info("WhatsApp background thread SHUTTING DOWN.")
        self._loop.run_until_complete(self.client.stop())
        self._loop.close()

    async def _main_loop(self):
        """Background loop to process outgoing messages and AI auto-replies."""
        while self._is_running:
            try:
                # 1. Check for Outgoing Messages from GUI/Campaigns
                if outgoing_queue.qsize() > 0:
                    msg_task: QueuedMessage = await outgoing_queue.get()
                    success = await self.client.send_message(msg_task.chat_id, msg_task.content)
                    if success:
                        outgoing_queue.task_done()
                    else:
                        # Retry logic if needed
                        logger.warning(f"Failed to send to {msg_task.chat_id}. Retry logic pending...")
                
                # 2. Heartbeat/Monitoring
                await asyncio.sleep(1) # Yield control
                
            except Exception as e:
                logger.error(f"Main processing loop error: {e}")
                await asyncio.sleep(2)

    async def _handle_incoming_message(self, msg_data: dict):
        """Process incoming messages and trigger AI orchestrator."""
        chat_id = msg_data.get('chat_id')
        content = msg_data.get('content')
        
        # 1. Emit GUI signal for real-time feed
        signals.new_message_received.emit(msg_data)
        
        # 2. Check for AI Auto-Reply
        if ai_orchestrator.is_enabled:
            response = await ai_orchestrator.process_incoming(chat_id, content)
            if response:
                await outgoing_queue.put(chat_id, response, priority=5) # Priority reply

    def stop(self):
        """Safe shutdown of the background worker."""
        self._is_running = False
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
        self.wait()
