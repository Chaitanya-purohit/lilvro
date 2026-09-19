"""Mood detection and response strategy for the Lilvro learning agent."""

from __future__ import annotations

import re
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


class MoodState(str, Enum):
	FRUSTRATED = "frustrated"
	DISENGAGED = "disengaged"
	CONFUSED = "confused"
	CONFIDENT = "confident"
	NEUTRAL = "neutral"


class MoodAction(str, Enum):
	SIMPLIFY = "simplify"
	REFRAME = "reframe"
	BACKTRACK = "backtrack"
	EXTEND = "extend"
	CONTINUE = "continue"


@dataclass(frozen=True)
class MoodResponse:
	state: MoodState
	action: MoodAction
	instructions: str
	encouragement: str


_MOOD_PATTERNS: dict[MoodState, tuple[str, ...]] = {
	MoodState.FRUSTRATED: (
		r"\b(?:this is|it's) (?:too )?hard\b",
		r"\bi (?:don't|do not) get it\b",
		r"\bconfus(?:ed|ing)\b",
		r"\bthis makes no sense\b",
		r"\bugh\b",
		r"\b(?:can't|cannot) do this\b",
	),
	MoodState.DISENGAGED: (
		r"\b(?:this is|it's) boring\b",
		r"\bi(?:'m| am) bored\b",
		r"\bwhatever\b",
		r"\bi don't want to do this\b",
		r"\bcan we do something else\b",
	),
	MoodState.CONFUSED: (
		r"\bwhat do you mean\b",
		r"\bwhy\b.*\b(?:that|this)\b",
		r"\bhow did you get that\b",
		r"\bwhich step\b",
		r"\bi(?:'m| am) confused\b",
	),
	MoodState.CONFIDENT: (
		r"\bi got it\b",
		r"\bthat makes sense\b",
		r"\bthat was easy\b",
		r"\bi know how\b",
		r"\bmy answer is\b",
		r"\bi think the answer is\b",
	),
}


_RESPONSE_POLICIES = {
	MoodState.FRUSTRATED: MoodResponse(
		MoodState.FRUSTRATED,
		MoodAction.SIMPLIFY,
		"Slow down. Use shorter sentences, explain one idea at a time, and offer a simpler example.",
		"That is okay. This is a tricky step, so let's take it one piece at a time.",
	),
	MoodState.DISENGAGED: MoodResponse(
		MoodState.DISENGAGED,
		MoodAction.REFRAME,
		"Make the concept concrete and interesting with a short real-world STEM connection or a safe interactive challenge.",
		"Let's connect this to something surprising and see if we can make it more interesting.",
	),
	MoodState.CONFUSED: MoodResponse(
		MoodState.CONFUSED,
		MoodAction.BACKTRACK,
		"Back up to the last clear step, explain the idea using a different example, and ask one gentle check-in question.",
		"No problem. Let's try that step in a different way.",
	),
	MoodState.CONFIDENT: MoodResponse(
		MoodState.CONFIDENT,
		MoodAction.EXTEND,
		"Acknowledge the correct reasoning, then offer a slightly harder related problem without skipping the student's explanation.",
		"Nice work. You have the idea, so let's try the next challenge.",
	),
	MoodState.NEUTRAL: MoodResponse(
		MoodState.NEUTRAL,
		MoodAction.CONTINUE,
		"Continue at the current difficulty and ask a concise check-in question when useful.",
		"Let's keep going.",
	),
}


def detect_mood(text: str) -> MoodState:
	"""Infer a mood from a student utterance using local phrase patterns."""
	if not isinstance(text, str):
		raise TypeError("text must be a string")

	for mood in (
		MoodState.FRUSTRATED,
		MoodState.DISENGAGED,
		MoodState.CONFUSED,
		MoodState.CONFIDENT,
	):
		if any(re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL) for pattern in _MOOD_PATTERNS[mood]):
			return mood
	return MoodState.NEUTRAL


def response_for_mood(mood: MoodState | str) -> MoodResponse:
	"""Return the response strategy for a detected mood."""
	try:
		state = mood if isinstance(mood, MoodState) else MoodState(mood)
	except ValueError as error:
		raise ValueError(f"unknown mood: {mood}") from error
	return _RESPONSE_POLICIES[state]


def choose_response_strategy(text: str) -> MoodResponse:
	"""Detect a student's mood and return the matching teaching strategy."""
	return response_for_mood(detect_mood(text))


_AI_MOOD_PROMPT = """Classify the student's emotional state for a child-friendly STEM tutor.
Return only valid JSON with exactly these keys:
{{"mood":"frustrated|disengaged|confused|confident|neutral","confidence":0.0}}

Use frustrated when the student expresses difficulty or discouragement.
Use disengaged when the student is bored or wants to stop.
Use confused when the student asks for clarification.
Use confident when the student shows understanding or readiness for a challenge.
Use neutral when no mood is clear. Never include a response to the student.

Student message: {message}"""


def choose_response_strategy_with_ai(
	text: str,
	classifier: Callable[[str], str | dict[str, Any]],
	minimum_confidence: float = 0.80,
) -> MoodResponse:
	"""Use AI for ambiguous mood signals, falling back to local detection."""
	if not isinstance(text, str):
		raise TypeError("text must be a string")
	if not 0 <= minimum_confidence <= 1:
		raise ValueError("minimum_confidence must be between 0 and 1")

	local_mood = detect_mood(text)
	if local_mood != MoodState.NEUTRAL:
		return response_for_mood(local_mood)

	try:
		raw_result = classifier(_AI_MOOD_PROMPT.format(message=text.strip()))
		parsed = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
		mood = MoodState(parsed["mood"])
		confidence = float(parsed["confidence"])
		if not 0 <= confidence <= 1:
			raise ValueError("AI confidence must be between 0 and 1")
	except Exception:
		return response_for_mood(MoodState.NEUTRAL)

	if confidence < minimum_confidence:
		return response_for_mood(MoodState.NEUTRAL)
	return response_for_mood(mood)


def choose_response_strategy_with_openai(
	text: str,
	minimum_confidence: float = 0.80,
) -> MoodResponse:
	"""Run mood selection with the optional OpenAI classifier adapter."""
	from ai_client import openai_classifier

	return choose_response_strategy_with_ai(text, openai_classifier, minimum_confidence)


if __name__ == "__main__":
	examples = (
		"This is too hard.",
		"This is boring.",
		"How did you get that?",
		"I got it!",
		"What is the square root of 25?",
	)
	for example in examples:
		strategy = choose_response_strategy(example)
		print(f"{strategy.state.value}: {example}")
		print(f"  {strategy.encouragement}")
		print(f"  Action: {strategy.action.value}")
