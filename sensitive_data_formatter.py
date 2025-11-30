import logging
import os

# --- Custom Log Filter for Sensitive Data ---

class SensitiveDataFilter(logging.Filter):
    """
    A log filter to redact the GEMINI_API_KEY from log messages 
    if the log level is not DEBUG.
    """
    def filter(self, record):
        # We only apply redaction if the log level is INFO or higher (not DEBUG)
        if record.levelno >= logging.INFO:
            api_key = os.getenv("GEMINI_API_KEY")
            if api_key:
                # Replace the full API key with a truncated version for security
                redacted_key = api_key[:4] + '...' + api_key[-4:]
                record.msg = record.msg.replace(api_key, f"REDACTED_API_KEY({redacted_key})")
        return True

# --- Main Logging Configuration ---

def setup_logging():
    """
    Configures the application's logging system.
    """
    # 1. Get the desired logging level (DEBUG is verbose, INFO is standard)
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    
    # 2. Configure the root logger
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 3. Apply the sensitive data filter
    # This filter will be applied to the main StreamHandler by default in Streamlit/Python environments
    for handler in logging.root.handlers:
        handler.addFilter(SensitiveDataFilter())
        
    logging.info(f"Logging configured at level: {log_level}")

# --- Initialize Logging on import ---
setup_logging()

# Provide an accessor for other modules
logger = logging.getLogger("App")