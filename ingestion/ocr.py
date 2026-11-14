"""Thin Gemini OCR provider for IRIS.

Sends a rendered page image to Gemini and returns a faithful verbatim
transcription. Application code must call extract_page() — never
the Gemini SDK directly.

Models are read from environment variables so they can be changed
without touching code:
  GEMINI_OCR_MODEL_PRIMARY   (default: gemini-3.5-flash-lite)
  GEMINI_OCR_MODEL_FALLBACK  (default: gemini-3.1-flash-lite)
"""

import base64
import logging
import os
import time
from typing import Optional

import google.generativeai as genai

logger = logging.getLogger(__name__)

# Pipeline version — bump when prompt or processing logic changes
EXTRACTION_VERSION = "ocr-v1"

# Prompt instructs the model to transcribe faithfully, not summarise.
_OCR_PROMPT = (
    "You are a faithful transcription engine. "
    "Transcribe every word visible on this page exactly as it appears, "
    "preserving the original structure, headings, tables, bullet points and numbering. "
    "Do not summarise, paraphrase, add explanations or omit any content. "
    "If a word or passage is unreadable, write [illegible] in its place. "
    "If the page has no readable text or is blank, output [empty]. "
    "Output only the transcribed text — no commentary, no markdown code fences."
)

_MAX_RETRIES = 3
_BACKOFF_BASE_SECONDS = 2


def _get_models() -> tuple[str, str]:
    primary = os.getenv("GEMINI_OCR_MODEL_PRIMARY", "gemini-3.5-flash-lite")
    fallback = os.getenv("GEMINI_OCR_MODEL_FALLBACK", "gemini-3.1-flash-lite")
    return primary, fallback


def _configure_client() -> None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY is not set. Add it to your .env file."
        )
    genai.configure(api_key=api_key)


def _call_model(model_name: str, image_bytes: bytes) -> str:
    """Send image bytes to the named Gemini model and return the text response."""
    model = genai.GenerativeModel(
        model_name=model_name,
        generation_config=genai.types.GenerationConfig(
            temperature=0,
            candidate_count=1,
        ),
    )
    image_part = {
        "mime_type": "image/png",
        "data": base64.b64encode(image_bytes).decode("utf-8"),
    }
    response = model.generate_content([_OCR_PROMPT, image_part])
    try:
        return response.text or ""
    except (ValueError, AttributeError):
        # Candidate has no text parts (e.g. empty or blank page)
        if hasattr(response, "candidates") and response.candidates:
            candidate = response.candidates[0]
            parts = getattr(candidate.content, "parts", [])
            return "".join(getattr(p, "text", "") for p in parts if hasattr(p, "text"))
        return ""


def extract_page(
    image_bytes: bytes,
    page_number: int,
    *,
    primary_model: Optional[str] = None,
    fallback_model: Optional[str] = None,
) -> dict:
    """OCR a single page image using Gemini with automatic fallback.

    Args:
        image_bytes:    PNG bytes of the rendered page.
        page_number:    1-indexed page number (used only for logging).
        primary_model:  Override for GEMINI_OCR_MODEL_PRIMARY env var.
        fallback_model: Override for GEMINI_OCR_MODEL_FALLBACK env var.

    Returns:
        dict with keys:
          "text"        (str)   — transcribed text, or "" on failure
          "model_used"  (str | None)
          "status"      (str)   — "success" | "failed"
          "error"       (str | None)
    """
    _configure_client()

    env_primary, env_fallback = _get_models()
    primary = primary_model or env_primary
    fallback = fallback_model or env_fallback

    def _attempt(model_name: str) -> tuple[bool, str, Optional[str]]:
        """Try up to _MAX_RETRIES times on rate-limit errors."""
        last_error: Optional[str] = None
        for attempt in range(_MAX_RETRIES):
            try:
                text = _call_model(model_name, image_bytes)
                return True, text, None
            except Exception as exc:
                err_str = str(exc)
                is_rate_limit = (
                    "429" in err_str
                    or "quota" in err_str.lower()
                    or "rate" in err_str.lower()
                )
                if is_rate_limit and attempt < _MAX_RETRIES - 1:
                    wait = _BACKOFF_BASE_SECONDS ** (attempt + 1)
                    logger.warning(
                        "Page %d: rate limit on %s, retrying in %ds (attempt %d/%d)",
                        page_number, model_name, wait, attempt + 1, _MAX_RETRIES,
                    )
                    time.sleep(wait)
                    last_error = err_str
                else:
                    last_error = err_str
                    break
        return False, "", last_error

    # Try primary model first
    logger.info("Page %d: OCR with primary model %s", page_number, primary)
    ok, text, error = _attempt(primary)
    if ok:
        return {"text": text, "model_used": primary, "status": "success", "error": None}

    # Fall back to secondary model
    logger.warning(
        "Page %d: primary model %s failed (%s), trying fallback %s",
        page_number, primary, error, fallback,
    )
    ok, text, error = _attempt(fallback)
    if ok:
        return {"text": text, "model_used": fallback, "status": "success", "error": None}

    logger.error("Page %d: both models failed. Last error: %s", page_number, error)
    return {"text": "", "model_used": None, "status": "failed", "error": error}
