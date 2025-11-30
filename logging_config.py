import logging
import os
import re

# --- 1. Initialize the Logger Instance FIRST ---
logger = logging.getLogger("App")

# --- Redaction Patterns ---

REDACTION_PATTERNS = [
    # 1. Redact the GEMINI API Key (specific, case-insensitive match)
    re.compile(r"(api_key|API_KEY|gemini|GEMINI_API_KEY)='?([A-Za-z0-9-_]+)'?"),

    # 2. Redact HTTP/HTTPS URLs that might leak PII or specific resource names
    re.compile(r"https?:\/\/[^\s\(\)]*"),

    # 3. Redact the content of data fields in log messages (e.g., full_text in JSON logs)
    re.compile(r"(Text Payload|full_text|hook_text)[:=\s].*?(\s|$)"),

    # 4. Redact the full user prompt sent to the model (often logged in debug)
    re.compile(r"Sending prompt to Gemini:\n---.*?---", re.DOTALL),
]


class SensitiveDataFilter(logging.Filter):
    """
    A log filter to redact the GEMINI_API_KEY and other sensitive data
    from log messages if the log level is not DEBUG.
    DEBUG logs stay unredacted for easier diagnosis.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.INFO:
            message = record.getMessage()

            api_key = os.getenv("GEMINI_API_KEY")
            if api_key:
                message = message.replace(api_key, "[REDACTED_API_KEY]")

            for pattern in REDACTION_PATTERNS:
                if pattern is REDACTION_PATTERNS[0]:
                    message = pattern.sub(r"\1='[REDACTED_KEY]'", message)
                else:
                    message = pattern.sub(r"[...REDACTED...]", message)

            # Update record so all handlers get the redacted version
            record.msg = message
            record.args = ()

        return True


def setup_logging() -> None:
    """
    Configures the application's logging system.
    Uses LOG_LEVEL env var if set, otherwise defaults to INFO.
    """
    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Apply the sensitive data filter to all existing handlers
    for handler in logging.root.handlers:
        handler.addFilter(SensitiveDataFilter())

    logger.info("Logging configured at level: %s", log_level_name)


# --- Initialize Logging on import ---
setup_logging()
