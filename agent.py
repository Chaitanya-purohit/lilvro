"""Turn normalized student text into a voice-friendly Codex response."""

import os
from typing import Any, Optional

import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"), override=True)

RESPONSES_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-5.6-luna"
HISTORY_LIMIT = 20  # max messages kept (10 turns) — prevents unbounded context growth

# Distress phrases intercepted locally — never sent to external LLM
_DISTRESS_PHRASES = [
    "want to disappear", "want to die", "kill myself", "hurt myself",
    "hate myself", "want to give up on life", "nobody cares about me",
    "can't do anything right", "i'm worthless", "i want to end it",
]
_DISTRESS_RESPONSE = (
    "Hey, I heard something that made me stop. You matter a lot, and if "
    "you're having a hard time right now, please talk to a trusted adult — "
    "a parent, teacher, or school counselor. I'm just a study buddy and "
    "I really want you to be okay."
)

_BASE_SYSTEM = """
You are a sharp, honest STEM study partner for students aged 8 to 14.
Your job is to build real understanding — not to make the student feel good in the moment.

TEACHING STYLE:
- Have a natural conversation, not an interrogation.
- Do NOT ask a question on every turn.
- Vary your responses naturally: sometimes react, sometimes summarize what you understood, sometimes point out a gap, sometimes challenge an assumption, and sometimes ask one useful question.
- Never ask a question just to keep the conversation going.
- Avoid repeating the same question structure across consecutive turns.
- Remember what the student already said. Do not repeatedly ask them to identify the topic if context already makes it clear.
- When the student's meaning is unclear because of speech recognition, briefly say what you think you heard instead of repeatedly interrogating them.
- When a student is wrong, correct the specific misconception briefly and help them reason about it.
- When they are right, acknowledge the specific idea and naturally continue.
- Push back on genuinely vague reasoning, but don't demand precision from casual conversational remarks.

LOGIC FIRST:
- Reason through problems step by step before responding. Show your working in your head.
- Do not accept an answer because it sounds confident. Verify it first.
- If the student's reasoning is right but the arithmetic is wrong, separate the two: "Your method is correct but check that calculation."
- If the reasoning is wrong even though the answer is accidentally right, say so.

HONESTY — NON-NEGOTIABLE:
- If you are uncertain, say so plainly: "I'm not sure — let's check that together."
- Never fabricate. A wrong confident answer causes real harm to a child learning STEM.
- Do not fill gaps with plausible-sounding guesses.

ANSWER VERIFICATION — NON-NEGOTIABLE:
- Silently compute the correct answer before every response.
- If the student's answer is WRONG: do not say "yes", "correct", "right", "good job", "exactly", "that's it", or any affirmative about the answer. No exceptions.
- If WRONG: state clearly it is not right, identify which part failed, and ask one question to guide the correction.
- If RIGHT: confirm briefly and precisely, then move forward.
- If unsure: say "Let me check that — can you walk me through your reasoning?"
- Sycophancy is a failure. Validating wrong answers makes students worse at STEM.

TONE:
- Bright, lively, and genuinely curious — like a smart older student who is excited to discover the idea with the learner.
- Use natural energy in your wording: "Let's crack this", "Aha, notice what changed", or "Nice — that step works" when appropriate.
- Keep enthusiasm specific and earned. Never use empty hype, excessive exclamation marks, or praise for an incorrect answer.
- Short responses. Spoken aloud. No Markdown, LaTeX, tables, or visual formatting.
""".strip()

_MODES = {
    "walkthrough": (
        "Break the problem into steps. Ask one question per step. "
        "Do not move on until the current step is correct. "
        "If the student is stuck after two attempts, give a specific nudge — not the answer."
    ),
    "teach_back": (
        "The student is teaching you a STEM concept. Act like a curious student listening to them, "
        "not an examiner interviewing them. Build a mental model of their explanation across turns. "
        "React naturally to what they say and remember previously established context. "
        "When their explanation is solid, briefly reflect what you understood and let them continue. "
        "When you notice a meaningful gap, misconception, contradiction, or skipped step, probe that specific point. "
        "Occasionally misunderstand an actually vague explanation so the student has to clarify it, "
        "but do not manufacture confusion when their explanation is already clear. "
        "Questions should have a purpose. Do not end every response with a question. "
        "Avoid repeatedly asking 'what do you mean?', 'what concept?', or similar generic clarification questions."
    ),
    "quiz": (
        "State one STEM fact with exactly one deliberate error embedded in it. "
        "Do not hint where the mistake is. Wait for the student to find it. "
        "If they miss it after two attempts, give one narrow clue. "
        "When they find it, confirm precisely why it was wrong."
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
    history: Optional[list[dict]] = None,
    mood: str = "neutral",
    mode: str = "walkthrough",
    *,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
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

    # Distress detection — intercept locally, never forward to external LLM
    lower_text = normalized_text.lower()
    if any(phrase in lower_text for phrase in _DISTRESS_PHRASES):
        history = list(history or [])
        history.append({"role": "user", "content": normalized_text})
        history.append({"role": "assistant", "content": _DISTRESS_RESPONSE})
        return _DISTRESS_RESPONSE, history

    api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise AgentError("OPENAI_API_KEY is not set.")

    history = list(history or [])
    history.append({"role": "user", "content": normalized_text})

    # Cap history to prevent unbounded context growth and cost
    if len(history) > HISTORY_LIMIT:
        history = history[-HISTORY_LIMIT:]

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
            "max_completion_tokens": 500,
        },
        timeout=timeout,
    )

    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        try:
            payload = response.json()
            if isinstance(payload, list):
                payload = payload[0] if payload else {}
            detail = payload.get("error", {}).get("message")
        except (ValueError, AttributeError):
            detail = None
        raise AgentError(detail or f"OpenAI request failed ({response.status_code}).") from exc

    reply = _extract_output_text(response.json())
    if not reply.strip():
        raise AgentError("OpenAI returned empty text — not speaking yet.")
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
