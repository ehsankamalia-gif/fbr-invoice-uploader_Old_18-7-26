import logging
import time
import psutil
import os
from datetime import datetime
from typing import Dict, Any

# Create a specialized logger for updates and performance
update_logger = logging.getLogger("update_monitor")
update_logger.setLevel(logging.INFO)

# Ensure a dedicated log file for monitoring
if not update_logger.handlers:
    fh = logging.FileHandler("system_monitor.log")
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    update_logger.addHandler(fh)

class SystemMonitor:
    """
    Monitors system performance and tracks update-related events.
    """
    
    @staticmethod
    def log_update_event(event_type: str, details: str):
        """Logs a specific update-related event."""
        update_logger.info(f"[UPDATE_EVENT] Type: {event_type} | Details: {details}")

    @staticmethod
    def get_performance_snapshot() -> Dict[str, Any]:
        """Captures a snapshot of current system performance."""
        process = psutil.Process(os.getpid())
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "cpu_percent": psutil.cpu_percent(interval=None),
            "memory_usage_mb": process.memory_info().rss / (1024 * 1024),
            "thread_count": process.num_threads(),
            "disk_usage_percent": psutil.disk_usage('/').percent
        }
        update_logger.info(f"[PERF_SNAPSHOT] {snapshot}")
        return snapshot

    @classmethod
    def monitor_operation(cls, operation_name: str):
        """Decorator to monitor the performance impact of a function."""
        def decorator(func):
            def wrapper(*args, **kwargs):
                cls.log_update_event("OP_START", f"Starting operation: {operation_name}")
                start_perf = cls.get_performance_snapshot()
                start_time = time.time()
                
                try:
                    result = func(*args, **kwargs)
                    duration = time.time() - start_time
                    cls.log_update_event("OP_SUCCESS", f"Operation {operation_name} completed in {duration:.2f}s")
                    return result
                except Exception as e:
                    cls.log_update_event("OP_FAILURE", f"Operation {operation_name} failed: {str(e)}")
                    raise
                finally:
                    cls.get_performance_snapshot()
            return wrapper
        return decorator
