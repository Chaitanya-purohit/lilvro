"""Turn normalized student text into a fast, tool-aware Codex response."""

from __future__ import annotations

import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import requests
from dotenv import load_dotenv

from mastery import MasteryBook
from math_renderer import render_math
from modes import (
    MistakeState,
    ModeGuidance,
    TeachbackState,
    guide_mistake,
    guide_teachback,
    guide_walkthrough,
    maybe_stop_modes,
    sync_session_from_modes,
)
from persona import flavor_for_tool, persona_base_prompt
from tools import (
    Mode,
    SessionState,
    Tool,
    TurnDecision,
    apply_decision,
    build_instructions,
    collect_signals,
    route_turn,
)

load_dotenv()

RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5-codex"
DEFAULT_MAX_OUTPUT_TOKENS = 140
HISTORY_TURNS = 6
MAX_RETRIES = 2

DISTRESS_FALLBACK = (
    "Hey, I'm really glad you told me. I'm just a study buddy, so please talk to "
    "a trusted adult or caregiver about how you're feeling right away. I can stay "
    "with an easy STEM warm-up later if you want."
)

OFF_TOPIC_FALLBACK = (
    "I'm only here for STEM study stuff, so let's skip that. Want a quick puzzle "
    "on fractions, forces, or atoms instead?"
)

NETWORK_FALLBACK = (
    "My brain glitched for a second. Want to try the next tiny step together anyway?"
)


class AgentError(RuntimeError):
    """Raised when the agent cannot produce a response."""


@dataclass(slots=True)
class AgentReply:
    """Structured real-time turn result."""

    text: str
    tool: Tool
    support_tool: Tool | None
    mode: Mode
    reason: str
    adjust: bool
    phase: str
    topic: str | None
    mastery: float
    session: dict[str, object]
    local_only: bool = False


@dataclass
class PlannedTurn:
    decision: TurnDecision
    guidance: ModeGuidance
    signals_summary: str
    frustration: bool = False
    engagement: bool = False


@dataclass
class AgentRuntime:
    """Mutable session brain shared across voice turns."""

    session: SessionState
    teachback: TeachbackState
    mistake: MistakeState
    mastery: MasteryBook = field(default_factory=MasteryBook)
    history: deque[dict[str, str]] = field(
        default_factory=lambda: deque(maxlen=HISTORY_TURNS * 2)
    )

    @classmethod
    def fresh(cls) -> AgentRuntime:
        return cls(SessionState(), TeachbackState(), MistakeState())

    def remember(self, role: str, text: str) -> None:
        self.history.append({"role": role, "content": text})


def _extract_output_text(payload: dict[str, Any]) -> str:
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


def _history_input(runtime: AgentRuntime, user_text: str) -> list[dict[str, str]]:
    messages = list(runtime.history)
    messages.append({"role": "user", "content": user_text})
    return messages


def _polish_speech(text: str) -> str:
    """Make model output safer for TTS."""
    spoken = render_math(text)
    spoken = spoken.replace("\n", " ")
    while "  " in spoken:
        spoken = spoken.replace("  ", " ")
    return spoken.strip()


def _update_mastery(runtime: AgentRuntime, planned: PlannedTurn) -> float:
    decision = planned.decision
    guidance = planned.guidance
    topic = decision.topic or runtime.session.topic
    return runtime.mastery.note_turn(
        topic=topic,
        engagement=planned.engagement or guidance.phase == "celebrate",
        frustration=planned.frustration,
        teachback_strong=guidance.phase == "concept_check",
        teachback_gap=guidance.phase in {"intentional_miss", "scaffold"},
        mistake_catch=guidance.phase == "caught",
        mistake_miss=guidance.phase in {"hint", "reveal"},
    )


def _local_reply(decision: TurnDecision) -> str | None:
    if decision.reason == "distress_signal":
        return DISTRESS_FALLBACK
    if decision.reason == "off_topic_redirect":
        return OFF_TOPIC_FALLBACK
    return None


def plan_turn(
    normalized_text: str, runtime: AgentRuntime | None = None
) -> tuple[PlannedTurn, AgentRuntime]:
    """Local-only planning for a turn: tool, mode, and prompt overlays."""
    runtime = runtime or AgentRuntime.fresh()
    signals = collect_signals(normalized_text)
    decision = route_turn(normalized_text, runtime.session)
    maybe_stop_modes(decision, teachback=runtime.teachback, mistake=runtime.mistake)

    if decision.mode == Mode.TEACHBACK:
        guidance = guide_teachback(normalized_text, runtime.teachback, decision=decision)
    elif decision.mode == Mode.MISTAKE:
        guidance = guide_mistake(normalized_text, runtime.mistake, decision=decision)
    else:
        guidance = guide_walkthrough(normalized_text, runtime.session, decision=decision)

    apply_decision(runtime.session, decision, signals)
    sync_session_from_modes(
        runtime.session,
        teachback=runtime.teachback,
        mistake=runtime.mistake,
        phase=guidance.phase,
    )
    summary = (
        f"frustration={signals.frustration} distress={signals.distress} "
        f"disengaged={signals.disengaged} engagement={signals.engagement} "
        f"words={signals.word_count}"
    )
    return (
        PlannedTurn(
            decision,
            guidance,
            summary,
            frustration=bool(signals.frustration or signals.distress),
            engagement=bool(signals.engagement),
        ),
        runtime,
    )


def _call_codex(
    *,
    instructions: str,
    runtime: AgentRuntime,
    user_text: str,
    api_key: str,
    model: str,
    max_output_tokens: int,
    timeout: float,
) -> str:
    body: dict[str, Any] = {
        "model": model,
        "instructions": instructions,
        "input": _history_input(runtime, user_text),
        "max_output_tokens": max_output_tokens,
    }
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = requests.post(
                RESPONSES_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=timeout,
            )
            response.raise_for_status()
            return _extract_output_text(response.json())
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_error = exc
            time.sleep(0.15 * (attempt + 1))
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            if status in {429, 500, 502, 503, 504} and attempt < MAX_RETRIES:
                last_error = exc
                time.sleep(0.2 * (attempt + 1))
                continue
            detail = None
            try:
                if exc.response is not None:
                    detail = exc.response.json().get("error", {}).get("message")
            except (ValueError, AttributeError):
                detail = None
            raise AgentError(detail or f"Codex request failed ({status}).") from exc
    raise AgentError(f"Codex unavailable ({last_error}).")


def respond(
    normalized_text: str,
    *,
    runtime: AgentRuntime | None = None,
    planned: PlannedTurn | None = None,
    api_key: str | None = None,
    model: str | None = None,
    timeout: float = 18.0,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
) -> AgentReply:
    """Route tools/modes locally, then ask Codex for a spoken reply."""
    normalized_text = normalized_text.strip()
    if not normalized_text:
        raise ValueError("normalized_text cannot be empty")

    if planned is None:
        planned, runtime = plan_turn(normalized_text, runtime)
    elif runtime is None:
        runtime = AgentRuntime.fresh()

    decision = planned.decision
    guidance = planned.guidance
    mastery_score = _update_mastery(runtime, planned)
    topic = decision.topic or runtime.session.topic

    local = _local_reply(decision)
    if local is not None:
        text = _polish_speech(local)
        runtime.remember("user", normalized_text)
        runtime.remember("assistant", text)
        return AgentReply(
            text=text,
            tool=decision.primary_tool,
            support_tool=decision.support_tool,
            mode=decision.mode,
            reason=decision.reason,
            adjust=decision.adjust,
            phase=guidance.phase,
            topic=topic,
            mastery=mastery_score,
            session=runtime.session.snapshot(),
            local_only=True,
        )

    extra = [
        guidance.prompt_addendum,
        flavor_for_tool(decision.primary_tool.value),
        runtime.mastery.coaching_line(topic),
    ]
    instructions = build_instructions(
        decision,
        base_prompt=persona_base_prompt(),
        extra=extra,
        session=runtime.session,
    )

    api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise AgentError("OPENAI_API_KEY is not set.")

    tokens = max_output_tokens
    if decision.adjust or decision.primary_tool in {
        Tool.MOTIVATION,
        Tool.MENTAL_HEALTH,
        Tool.ENTERTAINMENT,
    }:
        tokens = min(tokens, 100)

    try:
        raw = _call_codex(
            instructions=instructions,
            runtime=runtime,
            user_text=normalized_text,
            api_key=api_key,
            model=model or os.getenv("CODEX_MODEL", DEFAULT_MODEL),
            max_output_tokens=tokens,
            timeout=timeout,
        )
        text = _polish_speech(raw)
        local_only = False
    except AgentError:
        # Keep the voice loop alive if the model blips.
        text = _polish_speech(NETWORK_FALLBACK)
        local_only = True

    runtime.remember("user", normalized_text)
    runtime.remember("assistant", text)

    snapshot = runtime.session.snapshot()
    snapshot["mastery"] = runtime.mastery.snapshot()

    return AgentReply(
        text=text,
        tool=decision.primary_tool,
        support_tool=decision.support_tool,
        mode=decision.mode,
        reason=decision.reason,
        adjust=decision.adjust,
        phase=guidance.phase,
        topic=topic,
        mastery=mastery_score,
        session=snapshot,
        local_only=local_only,
    )


def main() -> None:
    runtime = AgentRuntime.fresh()
    print("lilvro agent ready.")
    print("Modes: walkthrough | teachback | mistake")
    print("Tools: teaching | motivation | advising | mental_health | entertainment")
    print("Type 'quit' to exit. Prefix with 'plan:' to dry-run routing only.\n")
    while True:
        normalized_text = input("You: ").strip()
        if not normalized_text:
            continue
        if normalized_text.lower() in {"quit", "exit", "q"}:
            break

        dry_run = False
        if normalized_text.lower().startswith("plan:"):
            dry_run = True
            normalized_text = normalized_text[5:].strip()
            if not normalized_text:
                continue

        planned, runtime = plan_turn(normalized_text, runtime)
        decision, guidance = planned.decision, planned.guidance
        mastery = runtime.mastery.get(decision.topic or runtime.session.topic)
        print(
            f"[plan] tool={decision.primary_tool.value}"
            f" support={decision.support_tool.value if decision.support_tool else '-'}"
            f" mode={decision.mode.value}"
            f" phase={guidance.phase}"
            f" reason={decision.reason}"
            f" adjust={decision.adjust}"
            f" topic={decision.topic or '-'}"
            f" mastery={mastery:.2f}"
            f" | {planned.signals_summary}"
        )
        if dry_run:
            # Dry-run still updates mastery lightly via a shadow note for demos.
            _update_mastery(runtime, planned)
            continue
        try:
            reply = respond(normalized_text, runtime=runtime, planned=planned)
        except AgentError as exc:
            print(f"Agent error: {exc}")
            continue
        tag = "local" if reply.local_only else "codex"
        print(f"Agent ({tag}): {reply.text}\n")


if __name__ == "__main__":
    main()
