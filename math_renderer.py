"""Turn common mathematical notation in an LLM response into speech text."""

from __future__ import annotations

import re
from types import SimpleNamespace


_GREEK_NAMES = {
	"alpha": "alpha",
	"beta": "beta",
	"gamma": "gamma",
	"delta": "delta",
	"epsilon": "epsilon",
	"lambda": "lambda",
	"mu": "mu",
	"pi": "pi",
	"rho": "rho",
	"sigma": "sigma",
	"tau": "tau",
	"phi": "phi",
	"omega": "omega",
}


def _strip_math_delimiters(text: str) -> str:
	text = re.sub(r"\\\[(.*?)\\\]", r"\1", text, flags=re.DOTALL)
	text = re.sub(r"\\\((.*?)\\\)", r"\1", text, flags=re.DOTALL)
	text = re.sub(r"\$\$(.*?)\$\$", r"\1", text, flags=re.DOTALL)
	return re.sub(r"\$(.*?)\$", r"\1", text, flags=re.DOTALL)


def _replace_latex_commands(text: str) -> str:
	text = re.sub(r"\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}", r"the fraction \1 over \2", text)
	text = re.sub(r"\\sqrt\s*\[([^]]+)\]\s*\{([^{}]+)\}", r"the \1 root of \2", text)
	text = re.sub(r"\\sqrt\s*\{([^{}]+)\}", r"the square root of \1", text)
	text = re.sub(r"\\cbrt\s*\{([^{}]+)\}", r"the cube root of \1", text)
	text = re.sub(r"\\int\s*_\{?([^_{}^ ]+)\}?\s*\^\{?([^{} ]+)\}?", r"the integral from \1 to \2 of", text)
	text = re.sub(r"\\lim\s*_\{?([^{}]+)\}?", r"the limit as \1", text)
	text = re.sub(r"\\([A-Za-z]+)", lambda match: _GREEK_NAMES.get(match.group(1), match.group(1)), text)
	return text


def _replace_structured_notation(text: str) -> str:
	text = re.sub(
		r"d\^\s*2\s*([A-Za-z])\s*/\s*d([A-Za-z])\^\s*2",
		r"the second derivative of \1 with respect to \2",
		text,
		flags=re.IGNORECASE,
	)
	text = re.sub(
		r"d([A-Za-z])\s*/\s*d([A-Za-z])",
		r"the derivative of \1 with respect to \2",
		text,
		flags=re.IGNORECASE,
	)
	text = re.sub(r"\b(?:int|∫)_?([^\s^]+)\^([^\s]+)", r"the integral from \1 to \2 of", text)
	text = re.sub(r"\blim\s*\(?([A-Za-z])\s*(?:->|→)\s*([^),]+)\)?", r"the limit as \1 approaches \2", text)
	text = re.sub(r"\bsqrt\s*\(([^()]+)\)", r"the square root of \1", text, flags=re.IGNORECASE)
	text = re.sub(r"\bcbrt\s*\(([^()]+)\)", r"the cube root of \1", text, flags=re.IGNORECASE)
	text = re.sub(r"\^\s*2\b", " squared", text)
	text = re.sub(r"\^\s*3\b", " cubed", text)
	text = re.sub(r"\^\s*([A-Za-z0-9]+)", r" to the power of \1", text)
	text = re.sub(r"(?<![A-Za-z])([0-9]+(?:\.[0-9]+)?)e([+-]?[0-9]+)\b", r"\1 times 10 to the \2", text, flags=re.IGNORECASE)
	text = text.replace("->", " approaches ").replace("→", " approaches ")
	return text


def _replace_matrices(text: str) -> str:
	def speak_matrix(match: re.Match[str]) -> str:
		rows = [row.strip() for row in match.group(1).split("],")]
		rows = [row.strip(" []") for row in rows]
		row_words = [" and ".join(value.strip() for value in row.split(",")) for row in rows]
		dimensions = f"{len(rows)} by {len(row_words[0].split(' and '))}" if row_words else "matrix"
		return f"a {dimensions} matrix, " + ", ".join(f"row {index + 1}: {values}" for index, values in enumerate(row_words))

	return re.sub(r"\[\[(.*?)\]\]", speak_matrix, text)


def _clean_for_speech(text: str) -> str:
	text = re.sub(r"[*_`#]", "", text)
	text = re.sub(r"\s+", " ", text)
	text = re.sub(r"\s+([,.;:?!])", r"\1", text)
	return text.strip()


def render_math(text: str) -> str:
	"""Render math notation inside Codex prose as natural English for TTS."""
	if not isinstance(text, str):
		raise TypeError("text must be a string")

	rendered = _strip_math_delimiters(text)
	rendered = _replace_latex_commands(rendered)
	rendered = _replace_matrices(rendered)
	rendered = _replace_structured_notation(rendered)
	return _clean_for_speech(rendered)


math_to_speech = render_math


if __name__ == "__main__":
	examples = [
		r"The derivative of $x^2$ is $2x$.",
		r"Evaluate $\sqrt{x}$ and $\frac{a}{b}$.",
		"The matrix [[1,2],[3,4]] has determinant -2.",
		"Avogadro's number is 6.02e23.",
	]
	for example in examples:
		print(render_math(example))

	print("\nCodex response example:")
	codex_response = SimpleNamespace(
		output_text="To solve x^2 = 25, take the square root of both sides: x = sqrt(25) = 5."
	)
	speakable_text = render_math(codex_response.output_text)
	print("Codex:", codex_response.output_text)
	print("Speakable:", speakable_text)
