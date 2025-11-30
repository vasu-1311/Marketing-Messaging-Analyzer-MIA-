import requests
from bs4 import BeautifulSoup

from config.logging_config import logger
from utils.exceptions import ScrapingError, ContentExtractionError


def _fetch_html(url: str) -> requests.Response:
    """Handles the HTTP request and checks for status."""
    logger.debug("Attempting to fetch URL: %s", url)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        )
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        logger.info("Successfully fetched content. Status: %s", response.status_code)
        logger.debug("Raw HTML payload size: %d bytes.", len(response.content))
        return response
    except requests.exceptions.HTTPError as e:
        logger.error("HTTP Error while fetching URL: %s", e, exc_info=True)
        raise ScrapingError(f"HTTP Error {e.response.status_code}: {e.response.reason}") from e
    except requests.exceptions.RequestException as e:
        logger.error("Network/Connection failure: %s", e, exc_info=True)
        raise ScrapingError(f"Request failed (Connection or Timeout): {type(e).__name__}") from e


def _clean_and_extract(html_content: bytes) -> tuple[str, str]:
    """Cleans HTML and extracts full text and hook text."""
    soup = BeautifulSoup(html_content, "html.parser")

    # 1. Clean the HTML (remove nav bars, scripts, styles, etc.)
    logger.debug("Starting HTML sanitization: removing boilerplate elements.")
    for element in soup(["script", "style", "nav", "footer", "header", "aside", "form", "meta", "img"]):
        element.decompose()

    main_content = soup.find("body")
    if not main_content:
        logger.warning("Could not locate the main <body> tag.")
        raise ContentExtractionError("Could not find main content (body tag).")

    raw_text = main_content.get_text(separator=" ", strip=True)
    logger.debug("Full text extracted. Character count: %d", len(raw_text))

    # 2. Extract Hook Content (H1 + First Paragraph)
    hook_text = ""

    h1 = soup.find("h1")
    if h1:
        hook_text += h1.get_text(strip=True) + " "

    first_p = soup.find("p")
    if first_p:
        hook_text += first_p.get_text(strip=True)

    hook_text = hook_text.strip()
    logger.debug("Hook text extracted: %s...", hook_text[:50])

    if len(raw_text) < 50:
        logger.warning("Extracted full text is unusually short (%d chars).", len(raw_text))
        raise ContentExtractionError("Extracted content is too brief for analysis.")

    return raw_text, hook_text


def scrape_website_content(url: str) -> dict:
    """
    Orchestrates the scraping flow: fetch, clean, and extract.
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url  # Attempt to fix common user input error

    try:
        response = _fetch_html(url)
        full_text, hook_text = _clean_and_extract(response.content)

        logger.info("Content scraping and cleaning finalized.")

        return {
            "full_text": full_text,
            "hook_text": hook_text,
        }

    except (ScrapingError, ContentExtractionError):
        # Re-raise custom errors for the orchestrator to handle gracefully
        raise
    except Exception as e:
        logger.critical("Unexpected error in scraping service: %s", e, exc_info=True)
        raise ScrapingError(f"Unexpected internal scraping failure: {type(e).__name__}") from e
