"""Local safety and topic guardrails for the Lilvro voice agent."""

from __future__ import annotations

import re
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


class GuardrailCategory(str, Enum):
	ALLOWED = "allowed"
	OFF_TOPIC = "off_topic"
	PERSONAL_DATA = "personal_data"
	MENTAL_HEALTH = "mental_health"
	INTERNET_REQUEST = "internet_request"
	UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class GuardrailResult:
	allowed: bool
	category: GuardrailCategory
	response: str


_PERSONAL_DATA_PATTERNS = (
	r"\bwhat(?:'s| is) your name\b",
	r"\bwhat(?:'s| is) my name\b",
	r"\bwhere do you live\b",
	r"\bwhat(?:'s| is) my (?:address|location|school)\b",
	r"\btell me your (?:name|address|location)\b",
	r"\bwhat(?:'s| is) your (?:address|location)\b",
	r"\b(?:give|tell|send) me your phone number\b",
	r"\b(?:give|tell|send) me (?:my|your) email\b",
)

_MENTAL_HEALTH_PATTERNS = (
	r"\b(?:kill|hurt|harm) myself\b",
	r"\bi want to die\b",
	r"\bsuicid(?:e|al)\b",
	r"\bself[- ]?harm\b",
	r"\bno reason to live\b",
	r"\bi(?:'m| am) being abused\b",
	r"\bsomeone is hurting me\b",
)

_OFF_TOPIC_PATTERNS = (
	r"\b(?:play|playing) (?:a )?(?:video )?game\b",
	r"\b(?:minecraft|fortnite|roblox|tiktok|instagram|snapchat)\b",
	r"\b(?:dating|boyfriend|girlfriend|crush|relationship)\b",
	r"\b(?:make|write) (?:a )?(?:love|dating) message\b",
)

_INTERNET_PATTERNS = (
	r"\b(?:search|browse|look) (?:the )?internet\b",
	r"\bgoogle\b",
	r"\bopen (?:a )?website\b",
	r"\bwhat(?:'s| is) happening online\b",
)

_STEM_PATTERNS = (
	(r"\b(?:math|mathematics|algebra|geometry|calculus|equation|number|fraction|"
	 r"decimal|percent|triangle|angle|area|volume|probability|graph|function|"
	 r"derivative|integral|physics|chemistry|biology|science|engineering|code|"
	 r"coding|programming|algorithm|experiment|atom|force|energy|plant|animal)\b"),
	r"(?:\d|\+|−|-|\*|/|=|\^|sqrt|\bhow many\b|\bwhy does\b)",
)

_REDIRECT_RESPONSE = "I can help with math, science, engineering, or coding. Let's choose a STEM question to work on."
_AI_GUARDRAIL_PROMPT = """Classify this child's message for a STEM learning voice assistant.
Return only valid JSON with exactly these keys:
{{"category":"allowed|off_topic|personal_data|mental_health|internet_request|uncertain","confidence":0.0}}

Allowed means the message is about math, science, engineering, or coding.
Use mental_health for distress, self-harm, abuse, or danger.
Use personal_data if it asks for identifying information about the child or assistant.
Use internet_request for browsing, websites, searches, or online content.
Use off_topic for gaming, social media, relationships, or unrelated requests.
Use uncertain when the intent is ambiguous. Never include a response to the child.

Message: {message}"""


def _matches(text: str, patterns: tuple[str, ...]) -> bool:
	return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _result(category: GuardrailCategory, response: str) -> GuardrailResult:
	return GuardrailResult(
		allowed=category == GuardrailCategory.ALLOWED,
		category=category,
		response=response,
	)


def _deterministic_check(message: str) -> GuardrailResult | None:
	text = message.strip()
	if not text:
		return _result(
			GuardrailCategory.OFF_TOPIC,
			"Let's work on a math or science question together. What would you like to explore?",
		)

	if _matches(text, _MENTAL_HEALTH_PATTERNS):
		return _result(
			GuardrailCategory.MENTAL_HEALTH,
			"I'm sorry you're going through this. Please tell a trusted adult right now, like a parent, teacher, or school counselor. If you may be in immediate danger, contact local emergency services now.",
		)

	if _matches(text, _PERSONAL_DATA_PATTERNS):
		return _result(
			GuardrailCategory.PERSONAL_DATA,
			"I can't ask for or share personal information. Let's keep our conversation focused on a math or science question.",
		)

	if _matches(text, _INTERNET_PATTERNS):
		return _result(
			GuardrailCategory.INTERNET_REQUEST,
			"I can't browse the internet or open websites. I can still help explain a math or science idea using what I know.",
		)

	if _matches(text, _OFF_TOPIC_PATTERNS):
		return _result(GuardrailCategory.OFF_TOPIC, _REDIRECT_RESPONSE)

	if _matches(text, _STEM_PATTERNS):
		return _result(GuardrailCategory.ALLOWED, "")

	return None


def check_message(message: str) -> GuardrailResult:
	"""Classify a student message before sending it to the language model."""
	if not isinstance(message, str):
		raise TypeError("message must be a string")

	deterministic_result = _deterministic_check(message)
	return deterministic_result or _result(GuardrailCategory.OFF_TOPIC, _REDIRECT_RESPONSE)


def _parse_ai_result(raw_result: str | dict[str, Any]) -> tuple[GuardrailCategory, float]:
	if isinstance(raw_result, str):
		parsed = json.loads(raw_result)
	else:
		parsed = raw_result

	category = GuardrailCategory(parsed["category"])
	confidence = float(parsed["confidence"])
	if not 0 <= confidence <= 1:
		raise ValueError("AI confidence must be between 0 and 1")
	return category, confidence


def check_message_with_ai(
	message: str,
	classifier: Callable[[str], str | dict[str, Any]],
	minimum_confidence: float = 0.90,
) -> GuardrailResult:
	"""Use AI only for messages the deterministic rules cannot classify.

	The classifier must return JSON (or a parsed dict) containing ``category``
	and ``confidence``. Invalid, low-confidence, or failed classifications are
	blocked as uncertain, and the AI never writes the user-facing safety reply.
	"""
	if not isinstance(message, str):
		raise TypeError("message must be a string")
	if not 0 <= minimum_confidence <= 1:
		raise ValueError("minimum_confidence must be between 0 and 1")

	deterministic_result = _deterministic_check(message)
	if deterministic_result is not None:
		return deterministic_result

	try:
		category, confidence = _parse_ai_result(
			classifier(_AI_GUARDRAIL_PROMPT.format(message=message.strip()))
		)
	except Exception:
		return _result(GuardrailCategory.UNCERTAIN, _REDIRECT_RESPONSE)

	if confidence < minimum_confidence or category != GuardrailCategory.ALLOWED:
		return _result(
			category if confidence >= minimum_confidence else GuardrailCategory.UNCERTAIN,
			_REDIRECT_RESPONSE,
		)

	return _result(GuardrailCategory.ALLOWED, "")


def check_message_with_openai(
	message: str,
	minimum_confidence: float = 0.90,
) -> GuardrailResult:
	"""Run the guardrail with the optional OpenAI classifier adapter."""
	from ai_client import openai_classifier

	return check_message_with_ai(message, openai_classifier, minimum_confidence)


def is_safe_for_model(message: str) -> bool:
	"""Return whether a message may be forwarded to the language model."""
	return check_message(message).allowed


if __name__ == "__main__":
	examples = [
		"What is the square root of 25?",
		"Can you play Minecraft with me?",
		"What is your address?",
		"I want to hurt myself.",
		"Can you search the internet for this?",
	]
	for example in examples:
		result = check_message(example)
		print(f"{result.category.value}: {example}")
		if result.response:
			print(f"  {result.response}")
