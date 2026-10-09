import logging
import sys

def setup_logger(name: str = "data_collector", debug_mode: bool = False) -> logging.Logger:
    """Configures and returns a logger instance with standardized formatting."""
    logger = logging.getLogger(name)
    level = logging.DEBUG if debug_mode else logging.INFO
    logger.setLevel(level)
    
    # If handler is already configured, clear it first (avoids duplicates on re-init)
    if logger.handlers:
        logger.handlers.clear()
        
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - [%(levelname)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    
    # Avoid duplicating logs if parent loggers exist
    logger.propagate = False
    
    return logger

# Default logger instance
logger = setup_logger()
