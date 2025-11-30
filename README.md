# Marketing Insights Analyzer (MIA)

The Marketing Insights Analyzer is a production-grade Python application built using Streamlit and the Google Gemini API. It analyzes public website content to provide actionable marketing metrics: **Hook Score**, **Audience Persona**, and **Conversion Killers**.

## Features

- **Secure Configuration:** Uses `python-dotenv` for API key management, never exposing secrets in code.
- **Production Observability:** Implements a robust Python logging system with a custom filter to ensure sensitive data is hidden from operational console logs (`INFO` level) but retained in forensic file logs (`DEBUG` level).
- **Modular Architecture:** Clear separation of concerns into configuration, services, and utilities for maintainability and testing.
- **Reliable Scraping:** Uses `requests` and `beautifulsoup4` for fetching and cleaning HTML content, handling network errors and common website boilerplate.
- **Resilient AI Analysis:** Employs exponential backoff/retry logic for API calls and enforces structured JSON output using a strict JSON schema.

## Setup and Installation

### 1. Prerequisites

- Python 3.8+
- A valid Gemini API Key

### 2. Environment Setup

1. **Clone the repository:**

    ```bash
    git clone <repository-url>
    cd mia
    ```

2. **Create a virtual environment (recommended):**

    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: .\venv\Scripts\activate
    ```

3. **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

4. **Configure API Key:**

    Create a file named `.env` in the root directory and add your key:

    ```text
    # .env
    GEMINI_API_KEY='YOUR_KEY_HERE'
    ```

### 3. Running the Application

From the project root:

```bash
streamlit run app.py
