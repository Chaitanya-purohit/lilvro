"""Optional OpenAI adapter for guardrail and mood classification.

This module does not read or store a key at import time. Set OPENAI_API_KEY
only when you are ready to make live requests.
"""

from __future__ import annotations

import os


def openai_classifier(prompt: str) -> str:
	"""Send a structured classification prompt to the configured OpenAI model."""
	api_key = os.getenv("OPENAI_API_KEY")
	if not api_key:
		raise RuntimeError("OPENAI_API_KEY is not set")

	try:
		from openai import OpenAI
	except ImportError as error:
		raise RuntimeError("Install the OpenAI package with: pip install openai") from error

	model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
	client = OpenAI(api_key=api_key)
	response = client.responses.create(model=model, input=prompt)
	return response.output_text


classify_with_openai = openai_classifier
