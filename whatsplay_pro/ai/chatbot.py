from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import logging
import asyncio
from whatsplay_pro.core.config import Config
from whatsplay_pro.core.signals import signals

logger = logging.getLogger(__name__)

class BaseAIProvider(ABC):
    """Abstract interface for pluggable AI chatbot backends."""
    
    @abstractmethod
    async def generate_response(self, chat_id: str, message: str, context: List[Dict[str, str]] = None) -> str:
        """Process incoming message and return a context-aware response."""
        pass

class OpenAIProvider(BaseAIProvider):
    """OpenAI API implementation for context-aware chatbot responses."""
    
    def __init__(self, api_key: str, model: str = "gpt-4-turbo"):
        self.api_key = api_key
        self.model = model
        self._client = None # Lazy-init OpenAI client if library is installed
        
    async def generate_response(self, chat_id: str, message: str, context: List[Dict[str, str]] = None) -> str:
        """Generate response via OpenAI API."""
        try:
            # Simulation for architectural demonstration
            logger.info(f"AI Thinking: {message[:20]}...")
            signals.ai_thinking.emit(chat_id)
            
            # Simulate network latency
            await asyncio.sleep(2)
            
            response = f"Simulated AI Response for: {message[:10]}..."
            signals.ai_replied.emit(chat_id, response)
            return response
            
        except Exception as e:
            logger.error(f"OpenAI Generation Error: {e}")
            return "Simulated Fallback: Error occurred."

class RuleBasedChatbot(BaseAIProvider):
    """Fallback rule-based chatbot for simple keyword responses."""
    
    def __init__(self, rules: Dict[str, str] = None):
        self.rules = rules or {
            "hello": "Hello! I am the WhatsPlay AI Bot. How can I assist you?",
            "help": "You can type 'hello' or ask a question.",
            "status": "I am online and ready to help!"
        }
        
    async def generate_response(self, chat_id: str, message: str, context: List[Dict[str, str]] = None) -> str:
        """Return keyword-matched response or generic fallback."""
        msg_lower = message.lower()
        for kw, resp in self.rules.items():
            if kw in msg_lower:
                return resp
        return "I'm not sure about that. Try typing 'help'."

class ChatbotOrchestrator:
    """Central AI management for auto-replies and context handling."""
    
    def __init__(self, provider: BaseAIProvider = None):
        self.provider = provider or RuleBasedChatbot()
        self.is_enabled = False
        self.chat_contexts: Dict[str, List[Dict[str, str]]] = {}

    def set_provider(self, provider: BaseAIProvider):
        """Switch AI provider at runtime."""
        self.provider = provider
        logger.info(f"AI Provider switched to: {type(provider).__name__}")

    async def process_incoming(self, chat_id: str, message: str) -> Optional[str]:
        """Orchestrate auto-reply logic with context tracking and humanized delay."""
        if not self.is_enabled:
            return None
            
        # Update context
        if chat_id not in self.chat_contexts:
            self.chat_contexts[chat_id] = []
        self.chat_contexts[chat_id].append({"role": "user", "content": message})
        
        # Human-like delay simulation
        delay = Config.AUTO_REPLY_DELAY
        logger.debug(f"AI will reply to {chat_id} after {delay}s delay...")
        await asyncio.sleep(delay)
        
        # Generate and log response
        response = await self.provider.generate_response(
            chat_id, message, self.chat_contexts[chat_id]
        )
        
        # Update context with assistant response
        self.chat_contexts[chat_id].append({"role": "assistant", "content": response})
        
        # Truncate context for token limits if needed
        if len(self.chat_contexts[chat_id]) > 10:
            self.chat_contexts[chat_id] = self.chat_contexts[chat_id][-10:]
            
        return response

# Global orchestrator singleton instance
ai_orchestrator = ChatbotOrchestrator()
