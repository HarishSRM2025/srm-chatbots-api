"""Server-side Gemini Developer API integration."""

import logging
from urllib.parse import quote

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class GeminiError(Exception):
    """Raised when Gemini cannot provide a user-facing response."""


def generate_response(
    prompt: str,
    model: str | None = None,
    timeout: int = 120,
) -> str:
    api_key = settings.GEMINI_API_KEY.strip()
    if not api_key or api_key.startswith("gen-lang-client-"):
        raise GeminiError("Set GEMINI_API_KEY to an API key from Google AI Studio.")

    # Existing agents can still contain local model names before migration.
    selected_model = (model or "").removeprefix("models/")
    if not selected_model.startswith("gemini-") or selected_model == "gemini-2.5-flash-lite":
        selected_model = settings.GEMINI_MODEL.removeprefix("models/")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{quote(selected_model, safe='')}:generateContent"
    )
    try:
        response = requests.post(
            url,
            headers={"x-goog-api-key": api_key},
            json={"contents": [{"role": "user", "parts": [{"text": prompt}]}]},
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        # Log only metadata: request exceptions may contain credentials or content.
        status_code = exc.response.status_code if exc.response is not None else None
        logger.warning("Gemini request failed: model=%s status=%s type=%s",
                       selected_model, status_code, type(exc).__name__)
        raise GeminiError("The Gemini service is unavailable. Please try again later.") from exc
    except ValueError as exc:
        raise GeminiError("Gemini returned an invalid response.") from exc

    try:
        candidate = data["candidates"][0]
        if candidate.get("finishReason") not in ("STOP", "MAX_TOKENS"):
            raise GeminiError("Gemini returned no usable response.")
        parts = candidate["content"]["parts"]
        text = "".join(
            part["text"] for part in parts
            if "text" in part and not part.get("thought", False)
        ).strip()
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise GeminiError("Gemini returned an invalid or empty response.") from exc

    if not text:
        raise GeminiError("Gemini returned no user-facing response.")
    return text
