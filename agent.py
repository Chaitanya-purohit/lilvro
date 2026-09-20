"""Turn normalized student text into a voice-friendly Codex response."""

import os
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

RESPONSES_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openrouter/free"

_BASE_SYSTEM = """
You are a friendly STEM study partner for children ages 8 to 14.

The student's message has already been normalized, so mathematical notation is
intentional. Help the student reason through one step at a time instead of
immediately giving the final answer. Keep responses concise and conversational.
Ask one useful question at a time.

Your response will be spoken aloud. Use natural spoken math rather than
Markdown, LaTeX, code blocks, tables, or visual formatting.
Never give the final answer directly.

HONESTY — CRITICAL RULES:
- If you are not certain about a fact, concept, or calculation, say so explicitly: "I'm not sure about that one, let's look at it together" or "That's a great question — I want to make sure I get this right for you."
- Never guess or make up an answer to appear helpful. A confident wrong explanation is worse than admitting uncertainty.
- Do not fill gaps in your knowledge with plausible-sounding but unverified content.

ANSWER VERIFICATION — CRITICAL RULES:
- Before responding to any student answer, silently compute the correct answer yourself first.
- If the student's answer does NOT match your computed answer, it is WRONG. Do NOT say "yes", "correct", "right", "exactly", "great", "good job", "that's it", or any affirmative word about the answer. This rule has NO exceptions.
- If the answer is WRONG: respond with a warm redirect only — e.g. "Hmm, not quite, let's try that again" or "Close! Double-check that step." Never confirm and never hint that they were right.
- If the answer is RIGHT: confirm it briefly and move to the next step.
- When unsure whether the answer is correct, say "Let's double-check that together" rather than confirming.
- Sycophancy is forbidden. Saying "yes" to a wrong answer is a critical failure.
""".strip()

_MODES = {
    "walkthrough": (
        "Guide the student step by step with leading questions. "
        "Never reveal the answer outright."
    ),
    "teach_back": (
        "The student will explain a concept to you. Ask concept-check questions. "
        "If they explain something poorly, pretend to misunderstand it so they sharpen their explanation."
    ),
    "quiz": (
        "Explain a concept but include exactly one deliberate mistake. "
        "Wait for the student to identify it. Give a hint if they miss it. "
        "Confirm and explain when they find it."
    ),
}

_MOOD_NOTES = {
    "frustrated":  "The student sounds frustrated. Be extra warm, slow down, and simplify.",
    "confused":    "The student sounds confused. Try a different angle or a simple analogy.",
    "disengaged":  "The student sounds disengaged. Add a surprising fact or fun angle to pull them back in.",
    "confident":   "The student sounds confident. Push a little harder and introduce the next idea.",
    "neutral":     "",
}


class AgentError(RuntimeError):
    """Raised when the agent cannot produce a response."""


def _build_system(mode: str, mood: str) -> str:
    mode_note = _MODES.get(mode, _MODES["walkthrough"])
    mood_note = _MOOD_NOTES.get(mood, "")
    system = _BASE_SYSTEM + f"\n\nMode: {mode_note}"
    if mood_note:
        system += f"\n\nMood note: {mood_note}"
    return system


def _extract_output_text(payload: dict[str, Any]) -> str:
    """Extract assistant text from an OpenRouter chat completions payload."""
    try:
        msg = payload["choices"][0]["message"]
        text = (msg.get("content") or "").strip()
        if text:
            return text
    except (KeyError, IndexError):
        pass
    raise AgentError("OpenRouter returned no text.")


def respond(
    normalized_text: str,
    history: list[dict] | None = None,
    mood: str = "neutral",
    mode: str = "walkthrough",
    *,
    api_key: str | None = None,
    model: str | None = None,
    timeout: float = 30.0,
) -> tuple[str, list[dict]]:
    """
    Return a spoken response for normalized student input.

    Args:
        normalized_text: Student input (from speech_normalizer.normalize())
        history:         Conversation so far — list of {"role": ..., "content": ...}
        mood:            "neutral" | "frustrated" | "confused" | "confident" | "disengaged"
        mode:            "walkthrough" | "teach_back" | "quiz"

    Returns:
        (response_text, updated_history)

    Raises:
        ValueError: if the utterance is empty (caller should not speak yet)
    """
    normalized_text = normalized_text.strip()
    if not normalized_text:
        raise ValueError("normalized_text cannot be empty — wait until the student finishes speaking")

    # Soft guard: do not invent a reply from pure hesitation noise.
    lowered = normalized_text.lower().strip(".,!? ")
    if lowered in {"um", "uh", "erm", "hmm", "hm", "ah", "oh", "mm", "mmm"}:
        raise ValueError("utterance is filler only — keep listening")

    api_key = api_key or os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise AgentError("OPENROUTER_API_KEY is not set.")

    history = list(history or [])
    history.append({"role": "user", "content": normalized_text})

    # Prepend system message to conversation history
    messages = [{"role": "system", "content": _build_system(mode, mood)}] + [
        {"role": msg["role"], "content": msg["content"]}
        for msg in history
    ]

    response = requests.post(
        RESPONSES_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model or os.getenv("CODEX_MODEL", DEFAULT_MODEL),
            "messages": messages,
            "max_tokens": 500,
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
        raise AgentError(detail or f"OpenRouter request failed ({response.status_code}).") from exc

    reply = _extract_output_text(response.json())
    if not reply.strip():
        raise AgentError("Codex returned empty text — not speaking yet.")
    history.append({"role": "assistant", "content": reply})
    return reply, history


def detect_mode(text: str, current_mode: str) -> str:
    """Switch mode based on student wake phrases."""
    lower = text.lower()
    if any(p in lower for p in ["quiz mode", "quiz me", "test me", "find the mistake"]):
        return "quiz"
    if any(p in lower for p in ["teach back", "let me explain", "i'll explain", "teach you"]):
        return "teach_back"
    if any(p in lower for p in ["help me", "walk me through", "walkthrough", "explain this"]):
        return "walkthrough"
    return current_mode


if __name__ == "__main__":
    print("agent.py terminal test — type to chat, Ctrl+C to quit")
    print("Switch modes: 'quiz mode' | 'teach back' | 'help me'\n")
    history = []
    mode = "walkthrough"
    while True:
        try:
            user_input = input("You: ").strip()
            if not user_input:
                continue
            mode = detect_mode(user_input, mode)
            print(f"  [mode: {mode}]")
            response, history = respond(user_input, history, mode=mode)
            print(f"Agent: {response}\n")
        except KeyboardInterrupt:
            print("\nDone.")
            break
