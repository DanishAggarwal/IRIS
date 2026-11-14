"""Thin Gemini Embedding Provider for IRIS.

Generates 768-dimensional embeddings using Google's Gemini Embedding API
via the official google-genai SDK.

Configured via environment variables:
    GEMINI_API_KEY
    GEMINI_EMBEDDING_MODEL (default: gemini-embedding-001)
    GEMINI_EMBEDDING_DIM   (default: 768)

Exposes:
    embed_documents(texts, batch_size=10) -> list[list[float]]
    embed_query(query) -> list[float]
"""

import logging
import os
import re
import time
from typing import Optional, Sequence

from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai import errors

from database.repository import validate_embedding, DEFAULT_EMBEDDING_DIM

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-embedding-001"
DEFAULT_BATCH_SIZE = 10
_MAX_RETRIES = 5
_BACKOFF_BASE_SECONDS = 2


def _extract_retry_delay(exc: Exception) -> Optional[float]:
    """Extract server-requested retryDelay in seconds from quota/rate-limit error if present."""
    msg = str(exc)
    m = re.search(r"retryDelay['\"]?\s*:\s*['\"]?(\d+(?:\.\d+)?)s?", msg)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    m2 = re.search(r"retry in (\d+(?:\.\d+)?)s", msg, re.IGNORECASE)
    if m2:
        try:
            return float(m2.group(1))
        except ValueError:
            pass
    return None


def get_embedding_config() -> tuple[str, int]:
    """Return configured model identifier and output dimension."""
    model = os.getenv("GEMINI_EMBEDDING_MODEL", DEFAULT_MODEL).strip()
    dim_str = os.getenv("GEMINI_EMBEDDING_DIM", str(DEFAULT_EMBEDDING_DIM)).strip()
    try:
        dim = int(dim_str)
    except ValueError:
        dim = DEFAULT_EMBEDDING_DIM
    return model, dim


def _get_client() -> genai.Client:
    """Instantiate GenAI Client using GEMINI_API_KEY from environment."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or not api_key.strip():
        raise EnvironmentError(
            "GEMINI_API_KEY is not set. Add it to your .env file."
        )
    return genai.Client(api_key=api_key.strip())


def _is_transient_error(exc: Exception) -> bool:
    """Determine whether an error is transient (rate limit 429 or 5xx server error)."""
    if isinstance(exc, errors.ServerError):
        return True
    if isinstance(exc, errors.ClientError):
        code = getattr(exc, "code", None)
        if code == 429:
            return True
        msg = str(exc).lower()
        if "429" in msg or "resource_exhausted" in msg or "rate limit" in msg:
            return True
    return False


def _call_embed_content(
    client: genai.Client,
    model: str,
    contents: str | list[str],
    task_type: str,
    dimension: int,
) -> list[list[float]]:
    """Execute API call with bounded retries and exponential backoff."""
    config = types.EmbedContentConfig(
        task_type=task_type,
        output_dimensionality=dimension,
    )

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = client.models.embed_content(
                model=model,
                contents=contents,
                config=config,
            )
            if not resp or not resp.embeddings:
                raise ValueError("API returned empty embeddings response")

            results: list[list[float]] = []
            for idx, item in enumerate(resp.embeddings):
                values = getattr(item, "values", None)
                if values is None:
                    raise ValueError(f"Embedding item at index {idx} missing 'values'")
                clean = validate_embedding(values, expected_dim=dimension)
                results.append(clean)

            return results

        except Exception as exc:
            if _is_transient_error(exc) and attempt < _MAX_RETRIES:
                server_delay = _extract_retry_delay(exc)
                if server_delay is not None:
                    sleep_sec = server_delay + 2.0
                else:
                    sleep_sec = _BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))

                logger.warning(
                    "Transient error on attempt %d/%d. Backing off for %.1fs (server delay hint: %s). Error type: %s",
                    attempt,
                    _MAX_RETRIES,
                    sleep_sec,
                    server_delay,
                    type(exc).__name__,
                )
                time.sleep(sleep_sec)
            else:
                logger.error(
                    "Embedding API call failed on attempt %d/%d: %s",
                    attempt,
                    _MAX_RETRIES,
                    type(exc).__name__,
                )
                raise


def embed_documents(
    texts: Sequence[str],
    batch_size: int = DEFAULT_BATCH_SIZE,
    client: Optional[genai.Client] = None,
) -> list[list[float]]:
    """Generate embeddings for document chunks using RETRIEVAL_DOCUMENT.

    Args:
        texts: Sequence of document chunk text strings.
        batch_size: Number of texts per API batch call (default: 10).
        client: Optional preconfigured GenAI client (for testing/mocking).

    Returns:
        List of 768-dimensional float vectors matching the order of input texts.

    Raises:
        ValueError: If input texts list is empty or any item is blank.
        EnvironmentError: If GEMINI_API_KEY is not set.
    """
    if not texts:
        return []

    for i, t in enumerate(texts):
        if not isinstance(t, str) or not t.strip():
            raise ValueError(f"Text item at index {i} is empty or non-string")

    if client is None:
        client = _get_client()

    model, dimension = get_embedding_config()
    all_embeddings: list[list[float]] = []

    # Process in batches
    for i in range(0, len(texts), batch_size):
        batch = list(texts[i : i + batch_size])
        batch_embeddings = _call_embed_content(
            client=client,
            model=model,
            contents=batch,
            task_type="RETRIEVAL_DOCUMENT",
            dimension=dimension,
        )
        all_embeddings.extend(batch_embeddings)

    return all_embeddings


def embed_query(
    query: str,
    client: Optional[genai.Client] = None,
) -> list[float]:
    """Generate embedding for a search query using RETRIEVAL_QUERY.

    Args:
        query: Query string.
        client: Optional preconfigured GenAI client.

    Returns:
        768-dimensional float vector.

    Raises:
        ValueError: If query is empty or non-string.
        EnvironmentError: If GEMINI_API_KEY is not set.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Query string cannot be empty or non-string")

    if client is None:
        client = _get_client()

    model, dimension = get_embedding_config()
    results = _call_embed_content(
        client=client,
        model=model,
        contents=query.strip(),
        task_type="RETRIEVAL_QUERY",
        dimension=dimension,
    )
    return results[0]
