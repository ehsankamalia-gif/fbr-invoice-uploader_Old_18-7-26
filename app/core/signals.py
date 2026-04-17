from PyQt6.QtCore import QObject, pyqtSignal

class BookingSignals(QObject):
    """Centralized signals for booking state management."""
    # Signal emitted when a booking is created or its status changes (e.g., delivered)
    # Arguments: model_name (str), new_count (int)
    booking_updated = pyqtSignal(str, int)
    
    # Signal emitted when a booking is created
    booking_created = pyqtSignal(str) # model_name
    
    # Signal emitted when a booking is delivered
    booking_delivered = pyqtSignal(str) # model_name
    
    # Signal to refresh all booking-related UI components
    refresh_all_bookings = pyqtSignal()

# Global singleton instance
booking_signals = BookingSignals()
