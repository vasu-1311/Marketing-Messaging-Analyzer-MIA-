import os
import re
import time
from typing import Any, Dict, Optional, List

from dotenv import load_dotenv
import google.generativeai as genai

from config.settings import AppSettings
from config.logging_config import logger
from utils.exceptions import LLMServiceError

# --- Init env + settings ---
load_dotenv()
SETTINGS = AppSettings()

DEFAULT_MAX_RETRIES = 3
DEFAULT_GEMINI_MODEL = "gemini-1.5-flash"

_client_configured = False


def _configure_client() -> None:
    """
    Configure the google-generativeai client using GEMINI_API_KEY / GOOGLE_API_KEY.
    """
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY / GOOGLE_API_KEY is not set.")
        raise LLMServiceError(
            "Missing API key. Set GEMINI_API_KEY or GOOGLE_API_KEY in your environment or .env file."
        )

    try:
        genai.configure(api_key=api_key)
        logger.info("google-generativeai client configured successfully.")
    except Exception as e:
        logger.exception("Failed to configure google-generativeai: %s", e)
        raise LLMServiceError(
            "Failed to configure google-generativeai. "
            "Check your API key and library installation."
        ) from e


def _ensure_client() -> None:
    global _client_configured
    if not _client_configured:
        _configure_client()
        _client_configured = True


def _extract_text_from_response(response: Any) -> str:
    """
    Robustly extract text from a google-generativeai response object without using response.text.

    Strategy:
    - Iterate response.candidates[*].content.parts[*].text
    - Concatenate text from all parts
    - If nothing found, inspect finish_reason and prompt_feedback
    """
    collected: List[str] = []

    try:
        candidates = getattr(response, "candidates", None) or []
        for cand in candidates:
            finish_reason = getattr(cand, "finish_reason", None)
            logger.debug("Candidate finish_reason: %s", finish_reason)

            content = getattr(cand, "content", None)
            if not content:
                continue
            parts = getattr(content, "parts", None) or []
            for part in parts:
                t = getattr(part, "text", None)
                if t:
                    collected.append(t)
    except Exception:
        logger.debug("Error while extracting text from candidates.", exc_info=True)

    raw_text = " ".join(collected).strip()

    if not raw_text:
        # Try to detect safety blocking
        prompt_feedback = getattr(response, "prompt_feedback", None)
        block_reason = getattr(prompt_feedback, "block_reason", None) if prompt_feedback else None

        if block_reason:
            raise LLMServiceError(
                f"AI response was blocked by safety filters (reason: {block_reason}). "
                "Try a different URL or less sensitive content."
            )

        # If we reach here, the API technically responded but gave no usable text
        raise LLMServiceError(
            "AI did not return any usable text (no content parts). "
            "This can happen if the model was interrupted, blocked, or misconfigured."
        )

    return raw_text


def _call_gemini_api(prompt: str) -> str:
    """
    Call Gemini via google-generativeai and return the raw text response.
    We do NOT ask for JSON; we parse a strict text template ourselves.
    """
    _ensure_client()

    max_retries = getattr(SETTINGS, "gemini_max_retries", DEFAULT_MAX_RETRIES)
    model_name = getattr(SETTINGS, "gemini_model", DEFAULT_GEMINI_MODEL)

    logger.debug("Using model %s (max_retries=%d)", model_name, max_retries)

    model = genai.GenerativeModel(model_name)

    last_error: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.debug("Calling Gemini (attempt %d)...", attempt)

            response = model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.2,
                    "max_output_tokens": 512,
                },
            )

            raw_text = _extract_text_from_response(response)
            logger.debug("Raw Gemini response (truncated): %s", raw_text[:500])

            return raw_text

        except LLMServiceError:
            # Already user-facing and clean, just bubble up
            raise

        except Exception as e:
            last_error = e
            logger.exception("Unexpected error while calling Gemini: %s", e)

            # Simple retry on transient-ish errors
            msg = str(e).lower()
            if ("unavailable" in msg or "internal" in msg or "deadline" in msg) and attempt < max_retries:
                wait = 2**(attempt - 1)
                logger.info("Transient error; retrying in %d seconds...", wait)
                time.sleep(wait)
                continue

            raise LLMServiceError(
                f"Unexpected error during Gemini call: {type(e).__name__}: {e}"
            ) from e

    # If for some reason we exhaust retries
    raise LLMServiceError(
        f"Gemini call failed after {max_retries} attempts. Last error: {last_error!r}"
    )


def _parse_insights_text(text: str) -> Dict[str, Any]:
    """
    Parse the model's text into a structured dict.

    Expected format (we enforce this in the prompt):

    HOOK_SCORE: 82
    HOOK_SCORE_JUSTIFICATION: ...
    AUDIENCE_PERSONA: ...
    AUDIENCE_PERSONA_JUSTIFICATION: ...
    CONVERSION_KILLERS:
    1) phrase text | reason text
    2) another phrase | another reason
    3) third phrase | third reason
    """
    text = text.strip()
    if not text:
        raise LLMServiceError("AI returned an empty analysis. Cannot parse.")

    def grab(pattern: str, name: str, default: Optional[str] = None) -> str:
        m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if not m:
            if default is not None:
                return default
            raise LLMServiceError(f"Missing '{name}' in AI response. Response was:\n\n{text[:400]}")
        return m.group(1).strip()

    hook_score_str = grab(r"HOOK_SCORE:\s*([0-9]{1,3})", "HOOK_SCORE", default="0")
    try:
        hook_score = max(0, min(100, int(hook_score_str)))
    except ValueError:
        hook_score = 0

    hook_just = grab(
        r"HOOK_SCORE_JUSTIFICATION:\s*(.+)",
        "HOOK_SCORE_JUSTIFICATION",
        default="",
    )

    persona = grab(
        r"AUDIENCE_PERSONA:\s*(.+)",
        "AUDIENCE_PERSONA",
        default="Unknown audience",
    )

    persona_just = grab(
        r"AUDIENCE_PERSONA_JUSTIFICATION:\s*(.+)",
        "AUDIENCE_PERSONA_JUSTIFICATION",
        default="",
    )

    # Conversion killers block
    killers_block_match = re.search(
        r"CONVERSION_KILLERS:\s*(.+)", text, re.IGNORECASE | re.DOTALL
    )
    killers_block = killers_block_match.group(1).strip() if killers_block_match else ""

    killers: list[Dict[str, str]] = []
    if killers_block:
        # Lines like: "1) phrase text | reason text"
        for line in killers_block.splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^\s*\d+[\).\-\:]\s*(.+)$", line)
            if not m:
                continue
            body = m.group(1).strip()
            # Split into phrase | reason
            if "|" in body:
                phrase, reason = [part.strip() for part in body.split("|", 1)]
            else:
                phrase, reason = body, ""
            if phrase:
                killers.append({"phrase": phrase, "reason": reason})

    # Ensure exactly 3 items (pad or trim)
    while len(killers) < 3:
        killers.append(
            {
                "phrase": "",
                "reason": "",
            }
        )
    if len(killers) > 3:
        killers = killers[:3]

    result: Dict[str, Any] = {
        "hook_score": hook_score,
        "hook_score_justification": hook_just,
        "audience_persona": persona,
        "audience_persona_justification": persona_just,
        "conversion_killers": killers,
    }

    logger.debug("Parsed insights dict from AI text: %s", result)
    return result


def _fallback_local_analysis(hook_text: str, full_text: str) -> Dict[str, Any]:
    """
    Fallback heuristic analysis when Gemini doesn't return usable text.

    This is NOT true LLM output. It's a cheap local heuristic so the app still works.
    """
    logger.warning("Using local fallback analysis (Gemini unavailable).")

    hook = hook_text or ""
    full = full_text or ""
    hook_lower = hook.lower()
    full_lower = full.lower()

    # Very dumb hook score heuristic
    length = len(hook.strip())
    score = 30
    if length > 20:
        score += 15
    if length > 60:
        score += 15
    power_words = ["best", "ultimate", "guide", "free", "step-by-step", "proven"]
    if any(w in hook_lower for w in power_words):
        score += 10
    if "?" in hook:
        score += 5
    score = max(10, min(95, score))

    # Audience persona heuristic
    if any(k in full_lower for k in ["developer", "javascript", "react", "frontend"]):
        persona = "Web developers exploring technical content."
    elif any(k in full_lower for k in ["marketing", "brand", "campaign", "conversion"]):
        persona = "Marketing professionals focused on improving conversions."
    elif any(k in full_lower for k in ["ecommerce", "shop", "cart", "checkout"]):
        persona = "E-commerce store owners or managers."
    else:
        persona = "General online audience interested in this topic."

    persona_just = "Heuristic guess based on keywords detected in the page content."

    # Conversion killers: pick some common jargon if present
    jargon_terms = [
  "synergy",
  "low-hanging fruit",
  "think outside the box",
  "circle back",
  "touch base",
  "bandwidth",
  "core competencies",
  "actionable items",
  "robust",
  "cutting-edge",
  "game changer",
  "next-generation",
  "state-of-the-art",
  "best-in-class",
  "viral",
  "data-driven",
  "holistic",
  "mission-critical",
  "game-changing",
  "customizable",
  "scalable",
  "disruptive",
  "value-add",
  "bleeding-edge",
  "rockstar",       # e.g. in “rockstar engineer”
  "ninja",          # e.g. “ninja developer”
  "virtually",
  "leverage",
  "bandwidth",
  "action plan",
  "action item",
  "deep dive",
  "core competency",
  "win-win",
  "optimization",
  "think outside the box",
  "let’s circle back",
  "touch base"
]
    killers: list[Dict[str, str]] = []
    for term in jargon_terms:
        if term in full_lower:
            killers.append(
                {
                    "phrase": term,
                    "reason": "Jargon can confuse readers; consider using simpler, concrete language.",
                }
            )
    # If we have fewer than 3, pad with generic suggestions
    while len(killers) < 3:
        killers.append(
            {
                "phrase": "",
                "reason": "",
            }
        )
    killers = killers[:3]

    return {
        "hook_score": score,
        "hook_score_justification": "Score estimated using a simple heuristic (length, power words, punctuation).",
        "audience_persona": persona,
        "audience_persona_justification": persona_just,
        "conversion_killers": killers,
        "fallback_used": True,
    }


def analyze_marketing_insights(hook_text: str, full_text: str) -> Dict[str, Any]:
    """
    Public function used by app.py.

    Normal path:
      - Calls Gemini
      - Parses strict text template into a structured dict

    Fallback path:
      - If Gemini fails or returns no usable text, generate a local heuristic analysis.

    Returns a dict with:
    - hook_score
    - hook_score_justification
    - audience_persona
    - audience_persona_justification
    - conversion_killers (list of {phrase, reason})
    - hook_text_used
    - full_text_used
    - fallback_used (optional, bool)
    - llm_error (optional, str) if fallback was triggered
    """
    logger.info("Generating marketing insights prompt.")

    prompt = f"""
You are a world-class Senior Marketing Analyst and Copywriter.

Your task is to analyze a web page's messaging.

IMPORTANT INSTRUCTIONS (FOLLOW EXACTLY):
- Do NOT return JSON.
- Do NOT use Markdown.
- Do NOT add extra commentary before or after the result.
- You MUST respond ONLY using the following plain text template and nothing else:

HOOK_SCORE: <integer 0-100>
HOOK_SCORE_JUSTIFICATION: <one concise sentence>
AUDIENCE_PERSONA: <one concise sentence describing the specific target audience>
AUDIENCE_PERSONA_JUSTIFICATION: <one concise sentence>
CONVERSION_KILLERS:
1) <confusing or harmful phrase from the content> | <short reason why it's bad or how to improve>
2) <confusing or harmful phrase from the content> | <short reason>
3) <confusing or harmful phrase from the content> | <short reason>

Rules:
- "HOOK_SCORE" is based ONLY on the hook text (headline + first paragraph).
- "CONVERSION_KILLERS" must be EXACTLY 3 items.
- Each conversion killer must reference a concrete phrase from the content.

--- HOOK TEXT (headline + opening paragraph) ---
{hook_text}

--- FULL PAGE TEXT (context for persona and jargon) ---
{full_text}

Now respond using ONLY the template described above.
Do not include any explanations, JSON, or Markdown.
"""

    try:
        raw_response = _call_gemini_api(prompt)
        insights = _parse_insights_text(raw_response)
        insights["fallback_used"] = False
    except LLMServiceError as e:
        # Gemini failed or was blocked → use local fallback
        logger.error("Gemini failed; using fallback analysis. Error: %s", e)
        insights = _fallback_local_analysis(hook_text, full_text)
        insights["llm_error"] = str(e)

    # Attach original inputs for app display / debugging
    insights["hook_text_used"] = hook_text
    insights["full_text_used"] = full_text

    return insights
