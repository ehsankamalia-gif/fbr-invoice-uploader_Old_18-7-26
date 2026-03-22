from PyQt6.QtCore import QObject, pyqtSignal
from typing import Any, Dict

class AppSignals(QObject):
    """Centralized PyQt signals for the entire application."""
    
    # WhatsApp Connection Signals
    wa_starting = pyqtSignal()
    wa_auth_required = pyqtSignal(str) # QR Data (base64)
    wa_ready = pyqtSignal()
    wa_disconnected = pyqtSignal(str) # Reason
    wa_error = pyqtSignal(str) # Error Message
    
    # Message Signals
    new_message_received = pyqtSignal(dict) # Message Data
    message_sent = pyqtSignal(dict) # Sent Status Data
    
    # Bulk Messaging Signals
    bulk_progress = pyqtSignal(int, int, str) # current, total, status
    bulk_completed = pyqtSignal(dict) # Summary
    
    # AI Signals
    ai_status_changed = pyqtSignal(bool) # Enabled/Disabled
    ai_thinking = pyqtSignal(str) # Chat ID
    ai_replied = pyqtSignal(str, str) # Chat ID, Response
    
    # Generic Notification
    notify = pyqtSignal(str, str) # Type (success, error, info), Message
    
    # Logging Dashboard Signal
    log_message = pyqtSignal(str, str) # Level, Message

# Global singleton signals instance
signals = AppSignals()
