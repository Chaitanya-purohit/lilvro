"""Andy-agent orchestrator: plan locally, reply with Codex, polish for speech.

Public flow:
    runtime = AgentRuntime.fresh()
    reply = runtime.turn(normalized_text)   # cohesive one-call API
"""

from __future__ import annotations

import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import requests
from dotenv import load_dotenv

from contracts import Mode, ModeGuidance, SessionState, Tool, TurnDecision
from mastery import MasteryBook
from math_renderer import render_math
from modes import (
    MistakeState,
    TeachbackState,
    guide_for_decision,
    maybe_stop_modes,
    sync_session_from_modes,
)
from persona import flavor_for_tool, local_fallback, persona_base_prompt
from tools import (
    apply_decision,
    build_instructions,
    collect_signals,
    route_turn,
)
from voice_ux import (
    HardwareCue,
    TranscriptEvent,
    VoiceIntent,
    VoiceUxAction,
    VoiceUxState,
    begin_turn_cues,
    enrich_bilingual,
    handle_transcript_confidence,
    handle_voice_ux,
    hardware_payload,
)

load_dotenv()

RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5-codex"
DEFAULT_MAX_OUTPUT_TOKENS = 140
HISTORY_TURNS = 6
MAX_RETRIES = 2


class AgentError(RuntimeError):
    """Raised when the agent cannot produce a response."""


@dataclass(slots=True)
class AgentReply:
    """Structured real-time turn result for the voice pipeline."""

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
    voice_intent: str = VoiceIntent.NONE.value
    stop_tts: bool = False
    thinking_filler: str | None = None
    hardware: dict[str, object] | None = None


@dataclass
class PlannedTurn:
    decision: TurnDecision
    guidance: ModeGuidance
    signals_summary: str
    frustration: bool = False
    engagement: bool = False
    voice_action: VoiceUxAction | None = None


@dataclass
class AgentRuntime:
    """Mutable session brain shared across voice turns."""

    session: SessionState
    teachback: TeachbackState
    mistake: MistakeState
    mastery: MasteryBook = field(default_factory=MasteryBook)
    voice: VoiceUxState = field(default_factory=VoiceUxState)
    history: deque[dict[str, str]] = field(
        default_factory=lambda: deque(maxlen=HISTORY_TURNS * 2)
    )

    @classmethod
    def fresh(cls) -> AgentRuntime:
        return cls(SessionState(), TeachbackState(), MistakeState())

    def remember(self, role: str, text: str) -> None:
        self.history.append({"role": role, "content": text})
        if role == "assistant":
            self.voice.remember_agent(text)
        elif role == "user":
            self.voice.remember_user(text)

    def snapshot(self) -> dict[str, object]:
        data = self.session.snapshot()
        data["mastery"] = self.mastery.snapshot()
        data["teachback_active"] = self.teachback.active
        data["mistake_active"] = self.mistake.active
        data["voice_ux"] = self.voice.snapshot()
        return data

    def ingest_transcript(
        self, text: str, *, confidence: float = 1.0, is_final: bool = True
    ) -> VoiceUxAction | None:
        """STT confidence gate — call before turn() when confidence is known."""
        event = TranscriptEvent(text=text, confidence=confidence, is_final=is_final)
        return handle_transcript_confidence(self.voice, event)

    def plan(self, normalized_text: str) -> PlannedTurn:
        planned, _ = plan_turn(normalized_text, self)
        return planned

    def turn(
        self,
        normalized_text: str,
        *,
        plan_only: bool = False,
        confidence: float | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 18.0,
        max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    ) -> AgentReply | PlannedTurn:
        """One cohesive entrypoint for the voice pipeline."""
        normalized_text = normalized_text.strip()
        if not normalized_text:
            raise ValueError("normalized_text cannot be empty")

        # Confidence-aware re-ask (when STT provides a score).
        if confidence is not None:
            reask = self.ingest_transcript(
                normalized_text, confidence=confidence, is_final=True
            )
            if reask is not None:
                if plan_only:
                    return _ux_planned(self, reask)
                text = _polish_speech(reask.speak or "")
                self.remember("user", normalized_text)
                self.remember("assistant", text)
                return AgentReply(
                    text=text,
                    tool=Tool.TEACHING,
                    support_tool=None,
                    mode=self.session.mode,
                    reason="stt_uncertain",
                    adjust=True,
                    phase="redirect",
                    topic=self.session.topic,
                    mastery=self.mastery.get(self.session.topic),
                    session=self.snapshot(),
                    local_only=True,
                    voice_intent=reask.intent.value,
                    stop_tts=False,
                    hardware=hardware_payload(reask.hardware)
                    if reask.hardware
                    else None,
                )

        # Conversation UX (barge-in, pause, repeat, bookmarks, persona, …)
        ux = handle_voice_ux(normalized_text, self.voice, topic=self.session.topic)
        if ux.handled:
            if plan_only:
                return _ux_planned(self, ux)
            text = _polish_speech(ux.speak or "")
            self.remember("user", normalized_text)
            if text:
                self.remember("assistant", text)
            return AgentReply(
                text=text,
                tool=Tool.TEACHING,
                support_tool=None,
                mode=self.session.mode,
                reason=f"voice_ux:{ux.intent.value}",
                adjust=False,
                phase="idle",
                topic=self.session.topic,
                mastery=self.mastery.get(self.session.topic),
                session=self.snapshot(),
                local_only=True,
                voice_intent=ux.intent.value,
                stop_tts=ux.stop_tts,
                hardware=hardware_payload(ux.hardware) if ux.hardware else None,
            )

        planned = self.plan(normalized_text)
        if plan_only:
            _update_mastery(self, planned)
            return planned

        cues = begin_turn_cues(self.voice)
        reply = respond(
            normalized_text,
            runtime=self,
            planned=planned,
            api_key=api_key,
            model=model,
            timeout=timeout,
            max_output_tokens=max_output_tokens,
        )
        reply.thinking_filler = cues["filler"]
        reply.hardware = cues["hardware"]
        return reply


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
    spoken = render_math(text)
    spoken = spoken.replace("\n", " ")
    while "  " in spoken:
        spoken = spoken.replace("  ", " ")
    return spoken.strip()


def _update_mastery(runtime: AgentRuntime, planned: PlannedTurn) -> float:
    topic = planned.decision.topic or runtime.session.topic
    return runtime.mastery.note_from_guidance(
        topic=topic,
        guidance=planned.guidance,
        frustration=planned.frustration,
        engagement=planned.engagement,
    )


def _make_reply(
    *,
    text: str,
    planned: PlannedTurn,
    runtime: AgentRuntime,
    mastery_score: float,
    local_only: bool,
    voice_intent: str = VoiceIntent.NONE.value,
    stop_tts: bool = False,
    thinking_filler: str | None = None,
    hardware: dict[str, object] | None = None,
) -> AgentReply:
    decision = planned.decision
    topic = decision.topic or runtime.session.topic
    return AgentReply(
        text=text,
        tool=decision.primary_tool,
        support_tool=decision.support_tool,
        mode=decision.mode,
        reason=decision.reason,
        adjust=decision.adjust,
        phase=planned.guidance.phase_value,
        topic=topic,
        mastery=mastery_score,
        session=runtime.snapshot(),
        local_only=local_only,
        voice_intent=voice_intent,
        stop_tts=stop_tts,
        thinking_filler=thinking_filler,
        hardware=hardware,
    )


def _ux_planned(runtime: AgentRuntime, ux: VoiceUxAction) -> PlannedTurn:
    """Build a non-mutating planned turn for UX-only dry runs."""
    from contracts import ModeGuidance, Phase

    return PlannedTurn(
        decision=TurnDecision(
            primary_tool=Tool.TEACHING,
            support_tool=None,
            mode=runtime.session.mode,
            reason=f"voice_ux:{ux.intent.value}",
            topic=runtime.session.topic,
        ),
        guidance=ModeGuidance(runtime.session.mode, Phase.IDLE, ""),
        signals_summary="voice_ux",
        voice_action=ux,
    )


def plan_turn(
    normalized_text: str, runtime: AgentRuntime | None = None
) -> tuple[PlannedTurn, AgentRuntime]:
    """Local-only planning for a turn: tool, mode, and prompt overlays."""
    runtime = runtime or AgentRuntime.fresh()
    signals = collect_signals(normalized_text)
    decision = route_turn(normalized_text, runtime.session)
    maybe_stop_modes(decision, teachback=runtime.teachback, mistake=runtime.mistake)
    guidance = guide_for_decision(
        normalized_text,
        decision=decision,
        session=runtime.session,
        teachback=runtime.teachback,
        mistake=runtime.mistake,
        signals=signals,
    )
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
    planned = PlannedTurn(
        decision,
        guidance,
        summary,
        frustration=signals.is_frustrated,
        engagement=signals.is_engaged,
    )
    return planned, runtime


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

    mastery_score = _update_mastery(runtime, planned)
    decision = planned.decision

    local = local_fallback(decision.reason)
    if local is not None:
        text = _polish_speech(local)
        text = enrich_bilingual(text, runtime.voice.stt.language)
        runtime.remember("user", normalized_text)
        runtime.remember("assistant", text)
        return _make_reply(
            text=text,
            planned=planned,
            runtime=runtime,
            mastery_score=mastery_score,
            local_only=True,
            hardware=hardware_payload(HardwareCue.SPEAKING),
        )

    instructions = build_instructions(
        decision,
        base_prompt=persona_base_prompt(),
        extra=[
            planned.guidance.prompt_addendum,
            flavor_for_tool(decision.primary_tool),
            runtime.voice.persona_flavor(),
            runtime.mastery.coaching_line(decision.topic or runtime.session.topic),
        ],
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
        text = enrich_bilingual(_polish_speech(raw), runtime.voice.stt.language)
        local_only = False
    except AgentError:
        text = _polish_speech(local_fallback("network_error") or "Let's try that again.")
        local_only = True

    runtime.remember("user", normalized_text)
    runtime.remember("assistant", text)
    return _make_reply(
        text=text,
        planned=planned,
        runtime=runtime,
        mastery_score=mastery_score,
        local_only=local_only,
        thinking_filler=begin_turn_cues(runtime.voice)["filler"],
        hardware=hardware_payload(HardwareCue.SPEAKING),
    )


def main() -> None:
    runtime = AgentRuntime.fresh()
    print("lilvro andy-agent ready.")
    print("Voice UX: pause, repeat slower, another way, bookmark, personas, whisper mic")
    print("Modes: walkthrough | teachback | mistake")
    print("Tools: teaching | motivation | advising | mental_health | entertainment")
    print("Type 'quit' to exit. Prefix with 'plan:' to dry-run routing only.\n")
    while True:
        normalized_text = input("You: ").strip()
        if not normalized_text:
            continue
        if normalized_text.lower() in {"quit", "exit", "q"}:
            break

        plan_only = False
        if normalized_text.lower().startswith("plan:"):
            plan_only = True
            normalized_text = normalized_text[5:].strip()
            if not normalized_text:
                continue

        result = runtime.turn(normalized_text, plan_only=plan_only)
        if isinstance(result, PlannedTurn):
            decision, guidance = result.decision, result.guidance
            mastery = runtime.mastery.get(decision.topic or runtime.session.topic)
            print(
                f"[plan] tool={decision.primary_tool.value}"
                f" support={decision.support_tool.value if decision.support_tool else '-'}"
                f" mode={decision.mode.value}"
                f" phase={guidance.phase_value}"
                f" reason={decision.reason}"
                f" adjust={decision.adjust}"
                f" topic={decision.topic or '-'}"
                f" mastery={mastery:.2f}"
                f" | {result.signals_summary}"
            )
            continue

        reply = result
        print(
            f"[plan] tool={reply.tool.value}"
            f" mode={reply.mode.value}"
            f" phase={reply.phase}"
            f" reason={reply.reason}"
            f" mastery={reply.mastery:.2f}"
        )
        tag = "local" if reply.local_only else "codex"
        print(f"Agent ({tag}): {reply.text}\n")


if __name__ == "__main__":
    main()
