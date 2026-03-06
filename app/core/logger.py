import logging
import sys
import os
from pathlib import Path
from app.core.config import settings

# Create logs directory
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

class Logger:
    def __init__(self, name: str, log_file: str = "app.log"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(settings.LOG_LEVEL)
        
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        
        # File Handler
        file_handler = logging.FileHandler(log_dir / log_file)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
        
        # Stream Handler (Console)
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        self.logger.addHandler(stream_handler)

    def info(self, msg: str, *args, **kwargs):
        self.logger.info(msg, *args, **kwargs)
    
    def error(self, msg: str, *args, **kwargs):
        self.logger.error(msg, *args, **kwargs)
        
    def warning(self, msg: str, *args, **kwargs):
        self.logger.warning(msg, *args, **kwargs)
        
    def debug(self, msg: str, *args, **kwargs):
        self.logger.debug(msg, *args, **kwargs)
    
    def exception(self, msg: str, *args, **kwargs):
        self.logger.exception(msg, *args, **kwargs)

# Create global logger instance
logger = Logger(settings.APP_NAME)
