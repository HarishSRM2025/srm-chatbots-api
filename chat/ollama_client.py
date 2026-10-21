
import re

import requests
from django.conf import settings


class OllamaError(Exception):
    """Raised when the local Ollama service fails."""


def generate_response(
    prompt: str,
    model: str | None = None,
    timeout: int = 120,
) -> str:
    """Generate a user-facing response using the local Ollama model."""

    ollama_url = getattr(
        settings,
        "OLLAMA_BASE_URL",
        "http://localhost:11434",
    )
    selected_model = model or getattr(
        settings,
        "OLLAMA_MODEL",
        "qwen3:4b",
    )

    try:
        response = requests.post(
            f"{ollama_url.rstrip('/')}/api/generate",
            json={
                "model": selected_model,
                "prompt": prompt,
                "stream": False,
                "think": False,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()

    except requests.RequestException as exc:
        raise OllamaError(
            "Could not connect to the local Ollama service."
        ) from exc
    except ValueError as exc:
        raise OllamaError(
            "Ollama returned an invalid response."
        ) from exc

        if not isinstance(generated_text, str):
            raise OllamaError("Ollama returned an invalid response.")

    generated_text = data.get("response", "")

    if not isinstance(generated_text, str):
        raise OllamaError("Ollama returned an invalid response.")

    # Handle responses with a missing opening <think> tag.
    if re.search(r"</think\s*>", generated_text, flags=re.IGNORECASE):
        generated_text = re.split(
            r"</think\s*>",
            generated_text,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[1]

    # Remove any remaining complete reasoning blocks.
    generated_text = re.sub(
        r"<think\b[^>]*>.*?</think\s*>",
        "",
        generated_text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Remove an unclosed reasoning block.
    generated_text = re.sub(
        r"<think\b[^>]*>.*$",
        "",
        generated_text,
        flags=re.IGNORECASE | re.DOTALL,
    ).strip()

    if not generated_text:
        raise OllamaError(
            "Ollama returned no user-facing response."
        )

    return generated_text

    if not isinstance(generated_text, str):
        raise OllamaError("Ollama returned an invalid response.")

    # Remove complete reasoning blocks.
    generated_text = re.sub(
        r"<think\b[^>]*>.*?</think\s*>",
        "",
        generated_text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # If a reasoning block is unclosed, discard it rather than expose it.
    generated_text = re.sub(
        r"<think\b[^>]*>.*$",
        "",
        generated_text,
        flags=re.IGNORECASE | re.DOTALL,
    ).strip()

    if not generated_text:
        raise OllamaError(
            "Ollama returned no user-facing response."
        )

    return generated_text
