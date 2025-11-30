import streamlit as st
import os

# Import the production-grade modules
from config.settings import AppSettings
from config.logging_config import logger
from services.llm_service import analyze_marketing_insights
from services.web_scraper import scrape_website_content
from utils.exceptions import MiaException, ScrapingError, LLMServiceError

# Initialize logging immediately using the Singleton pattern
logger.info("Application starting up.")

# --- Initialization and Configuration Check ---
SETTINGS = AppSettings()
SETTINGS.load_env()
API_KEY_PRESENT = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))

# --- Helper Methods ---


@st.cache_data(show_spinner=False)
def orchestrate_analysis_flow(url: str):
    """
    Coordinates the scraping and AI analysis steps.
    This function is cached to prevent re-running on every Streamlit interaction.
    """
    logger.info("Starting orchestration flow for analysis.")

    # 1. Scraping Step
    try:
        scrape_results = scrape_website_content(url)
        full_text = scrape_results["full_text"]
        hook_text = scrape_results["hook_text"]

        if not full_text or len(full_text.strip()) < 50:
            raise ScrapingError("Extracted content was empty or too short after cleaning.")

        st.success("Content fetched and cleaned successfully.")

    except MiaException as e:
        # Catch custom, predictable errors (e.g., HTTP 404, parsing failure)
        error_message = f"Scraping Error: {e}"
        logger.error(error_message, exc_info=True)
        return {"error": error_message}
    except Exception as e:
        # Catch unexpected errors (e.g., memory, system issues)
        error_message = f"An unexpected system error occurred during scraping: {type(e).__name__}"
        logger.critical(error_message, exc_info=True)
        return {"error": error_message}

    # 2. AI Analysis Step
    with st.spinner("Analyzing messaging strategy (this might take a few seconds)..."):
        try:
            analysis_results = analyze_marketing_insights(hook_text, full_text)
            st.success("AI Analysis Complete!")
            return analysis_results

        except LLMServiceError as e:
            # Catch LLM specific errors (e.g., API key, rate limit, parsing)
            error_message = f"AI Analysis Error: {e}"
            logger.error(error_message, exc_info=True)
            return {"error": error_message}
        except Exception as e:
            # Catch unexpected system errors during AI call
            error_message = f"An unexpected system error occurred during AI analysis: {type(e).__name__}"
            logger.critical(error_message, exc_info=True)
            return {"error": error_message}


def display_results(results: dict):
    """Formats and displays the structured analysis results to the user."""

    if not isinstance(results, dict):
        st.error("Invalid results object returned from analysis.")
        return

    if "error" in results:
        st.error(results["error"])
        st.warning("Analysis could not be completed due to the error above.")
        return

    st.header("Key Messaging Insights")

    # Fallback indicator (if Gemini failed and local heuristics were used)
    if results.get("fallback_used"):
        st.warning(
            "Gemini did not return a usable response. "
            "Showing a local heuristic analysis instead of real model output."
        )
        llm_error = results.get("llm_error")
        if llm_error:
            st.caption(f"Underlying LLM error: {llm_error}")

    # Display Analyzed Hook Text
    hook_text = results.get("hook_text_used") or results.get("hook_text") or "N/A"
    st.subheader("Analyzed Hook Text")
    st.code(hook_text, language="markdown")
    st.caption("This is the headline and first paragraph the AI scored.")

    # 1. Hook Score
    raw_hook_score = results.get("hook_score", 0)
    try:
        hook_score = int(float(raw_hook_score))
    except Exception:
        hook_score = 0

    st.subheader("1. Hook Score")
    st.metric(
        label="Opening Compellingness (Headline + First Paragraph)",
        value=f"{hook_score}%",
    )
    if hook_score < 50:
        st.info("The opening hook needs significant work to grab visitor attention quickly.")
    elif hook_score < 80:
        st.info("The hook is decent, but it could be punchier or clearer. Room for improvement!")
    else:
        st.info("Excellent hook! The opening is highly compelling and right on target.")

    # 2. Audience Persona
    persona = results.get("audience_persona", "N/A")
    st.subheader("2. Target Audience Persona")
    st.markdown(f"**Prediction:** *{persona}*")
    st.caption("This prediction helps us verify if the tone and vocabulary match the intended reader.")

    # 3. Conversion Killers
    killers = results.get("conversion_killers")
    st.subheader("3. Conversion Killers (Friction Points)")

    if isinstance(killers, list) and killers:
        st.warning("Heads up! These phrases might confuse or lose customers:")

        for i, killer in enumerate(killers, start=1):
            # Case 1: killer is an object with phrase + reason
            if isinstance(killer, dict):
                phrase = (killer.get("phrase") or "").strip()
                reason = (killer.get("reason") or "").strip()

                # Skip totally empty rows
                if not phrase and not reason:
                    continue

                st.markdown(f"**{i}.** `{phrase or 'N/A'}`")
                if reason:
                    st.markdown(f"_{reason}_")

            # Case 2: killer is a plain string
            else:
                text = str(killer).strip()
                if not text:
                    continue
                st.markdown(f"**{i}.** `{text}`")

    elif isinstance(killers, dict):
        # Single dict case: show it as one item
        phrase = (killers.get("phrase") or "").strip()
        reason = (killers.get("reason") or "").strip()
        if phrase or reason:
            st.warning("Heads up! Potential friction point found:")
            st.markdown(f"`{phrase or 'N/A'}`")
            if reason:
                st.markdown(f"_{reason}_")
        else:
            st.info("Nice! No obvious jargon or confusing phrases were found. Clear messaging!")

    elif isinstance(killers, str) and killers.strip():
        st.warning("Heads up! Potential friction point found:")
        st.markdown(f"`{killers.strip()}`")

    else:
        st.info("Nice! No obvious jargon or confusing phrases were found. Clear messaging!")

# --- Building the Interface ---
st.set_page_config(
    page_title="Marketing Messaging Analyzer",
    layout="centered",
)

st.title("Marketing Messaging Analyzer")
st.markdown(
    "Enter a public website URL below to extract core content and generate marketing insights using AI."
)

# API Key Check UI
if not API_KEY_PRESENT:
    st.error("GEMINI_API_KEY / GOOGLE_API_KEY environment variable not found.")
    st.warning(
        "Create a `.env` file in your project folder with `GEMINI_API_KEY='YOUR_KEY_HERE'` "
        "or `GOOGLE_API_KEY='YOUR_KEY_HERE'`, or set it in your deployment environment secrets."
    )

url_input = st.text_input(
    "Website URL (e.g., https://www.google.com)",
    placeholder="https://www.yourcompanyblog.com/post-title",
)

# Initialize Session State for results persistence
if "analysis_results" not in st.session_state:
    st.session_state["analysis_results"] = None

if st.button("Analyze Messaging", type="primary"):
    if not API_KEY_PRESENT:
        st.error("API Key is missing. Cannot proceed with AI analysis.")
    elif not url_input:
        st.error("Please enter a valid URL.")
    else:
        # Clear cache for the new run
        try:
            orchestrate_analysis_flow.clear()
        except Exception:
            logger.debug("Failed to clear orchestrate_analysis_flow cache.", exc_info=True)

        # Call the cached orchestrator function
        st.session_state["analysis_results"] = orchestrate_analysis_flow(url_input)

        # Display results immediately after analysis
        if st.session_state["analysis_results"]:
            display_results(st.session_state["analysis_results"])

# If results are already in session state (e.g., after a rerun), display them
elif st.session_state.get("analysis_results"):
    display_results(st.session_state["analysis_results"])
