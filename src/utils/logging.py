"""
Centralized logging configuration.

This module provides consistent logging setup across the application.
"""

import logging
import os
from typing import Optional
from pydantic import BaseModel

class LogConfig(BaseModel):
    """Logging configuration."""
    level: str = os.getenv("LOG_LEVEL", "INFO").upper()
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    date_format: str = "%Y-%m-%d %H:%M:%S"
    file_path: Optional[str] = os.getenv("LOG_FILE")

def setup_logger(name: str) -> logging.Logger:
    """
    Set up a logger with consistent configuration.

    Args:
        name: Name of the logger (usually __name__)

    Returns:
        logging.Logger: Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Avoid adding handlers if they already exist
    if not logger.handlers:
        config = LogConfig()
        
        # Set log level
        logger.setLevel(config.level)
        
        # Create console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(config.level)
        
        # Create formatter
        formatter = logging.Formatter(
            fmt=config.format,
            datefmt=config.date_format
        )
        console_handler.setFormatter(formatter)
        
        # Add console handler
        logger.addHandler(console_handler)
        
        # Add file handler if configured
        if config.file_path:
            file_handler = logging.FileHandler(config.file_path)
            file_handler.setLevel(config.level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
    
    return logger 