import asyncio
import logging
from typing import Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass(order=True)
class QueuedMessage:
    """Structure for a message waiting to be sent."""
    priority: int
    chat_id: str
    content: str
    media_path: str = None
    created_at: datetime = field(default_factory=datetime.now)
    retry_count: int = 0
    max_retries: int = 3
    
class MessageQueue:
    """Thread-safe queue for managing outgoing messages with priority support."""
    
    def __init__(self):
        self._queue = asyncio.PriorityQueue()
        self._pending_tasks: List[QueuedMessage] = []

    async def put(self, chat_id: str, content: str, media_path: str = None, priority: int = 10):
        """Add a message to the outgoing queue."""
        msg = QueuedMessage(
            priority=priority,
            chat_id=chat_id,
            content=content,
            media_path=media_path
        )
        await self._queue.put(msg)
        logger.debug(f"Message queued for {chat_id}: {content[:30]}...")

    async def get(self) -> QueuedMessage:
        """Get the next message to be sent."""
        return await self._queue.get()

    def task_done(self):
        """Mark a task as completed."""
        self._queue.task_done()

    def qsize(self) -> int:
        """Return the current size of the queue."""
        return self._queue.qsize()

# Global outgoing queue instance
outgoing_queue = MessageQueue()
