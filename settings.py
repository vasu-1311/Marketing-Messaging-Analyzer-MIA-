import os
import logging
from dotenv import load_dotenv

# Global defaults
LLM_MODEL_NAME = "gemini-2.5-flash"
MAX_RETRIES = 5
DEFAULT_LOG_LEVEL = logging.INFO
LOG_FILE_PATH = "mia.log"
LLM_TIMEOUT_SECONDS = 30
MAX_CONTENT_CHARS = 10000  # Max content length to send to LLM


class AppSettings:
    """
    Centralized configuration manager using the Singleton pattern to ensure
    environment variables are loaded only once.
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AppSettings, cls).__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not self._initialized:
            # Load .env eagerly so direct imports also see env vars
            load_dotenv()

            self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

            # Optional overrides for LLM behavior
            self.gemini_model = os.getenv("GEMINI_MODEL", LLM_MODEL_NAME)
            self.gemini_max_retries = int(os.getenv("GEMINI_MAX_RETRIES", MAX_RETRIES))

            # Logging overrides
            self.log_level = os.getenv("LOG_LEVEL", "INFO").upper()
            self.log_file_path = os.getenv("LOG_FILE_PATH", LOG_FILE_PATH)

            AppSettings._initialized = True

    def load_env(self) -> None:
        """
        Reloads environment variables from the .env file and refreshes attributes.
        Safe to call multiple times.
        """
        load_dotenv()
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        self.gemini_model = os.getenv("GEMINI_MODEL", LLM_MODEL_NAME)
        self.gemini_max_retries = int(os.getenv("GEMINI_MAX_RETRIES", MAX_RETRIES))
        self.log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        self.log_file_path = os.getenv("LOG_FILE_PATH", LOG_FILE_PATH)


# Singleton instance for global access (if you ever want to import `settings`)
settings = AppSettings()
