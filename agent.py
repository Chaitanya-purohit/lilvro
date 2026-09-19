"""Turn normalized student text into a voice-friendly Codex response."""

import os
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5-codex"
SYSTEM_PROMPT = """
You are a friendly STEM study partner for children ages 8 to 14.

The student's message has already been normalized, so mathematical notation is
intentional. Help the student reason through one step at a time instead of
immediately giving the final answer. Keep responses concise and conversational.
Ask one useful question at a time.

Your response will be spoken aloud. Use natural spoken math rather than
Markdown, LaTeX, code blocks, tables, or visual formatting.
""".strip()


class AgentError(RuntimeError):
    """Raised when the agent cannot produce a response."""


def _extract_output_text(payload: dict[str, Any]) -> str:
    """Extract assistant text from an OpenAI Responses API payload."""
    if isinstance(payload.get("output_text"), str):
        text = payload["output_text"].strip()
        if text:
            return text

    parts: list[str] = []
    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                parts.append(content["text"])

    text = "\n".join(parts).strip()
    if not text:
        raise AgentError("Codex returned no text.")
    return text


def respond(
    normalized_text: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
    timeout: float = 30.0,
) -> str:
    """Return a spoken-response draft for normalized student input."""
    normalized_text = normalized_text.strip()
    if not normalized_text:
        raise ValueError("normalized_text cannot be empty")

    api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise AgentError("OPENAI_API_KEY is not set.")

    response = requests.post(
        RESPONSES_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model or os.getenv("CODEX_MODEL", DEFAULT_MODEL),
            "instructions": SYSTEM_PROMPT,
            "input": normalized_text,
        },
        timeout=timeout,
    )

    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        try:
            detail = response.json().get("error", {}).get("message")
        except (ValueError, AttributeError):
            detail = None
        raise AgentError(detail or f"Codex request failed ({response.status_code}).") from exc

    return _extract_output_text(response.json())


def main() -> None:
    normalized_text = input("Normalized text: ")
    print(respond(normalized_text))


if __name__ == "__main__":
    main()
