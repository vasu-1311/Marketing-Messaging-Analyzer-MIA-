class MiaException(Exception):
    """Base exception for the Marketing Insights Analyzer application."""
    pass


class ScrapingError(MiaException):
    """Raised for network, HTTP, or connectivity issues during scraping."""
    pass


class ContentExtractionError(MiaException):
    """Raised for issues during HTML parsing/cleaning or when content is missing/too short."""
    pass


class LLMServiceError(MiaException):
    """Raised for all Gemini API interaction errors (API key, rate limit, invalid response, etc.)."""
    pass
