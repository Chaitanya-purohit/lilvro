"""
speech_normalizer.py — Chai's module

Converts spoken math phrases (from Deepgram transcript) into structured math
using Unicode math symbols, so Claude can reason over them correctly.

Input:  "what is the square root of x plus x squared"
Output: "what is √x + x^2"
"""

import re


# Spoken phrase -> Unicode symbol (order matters: longer phrases first)
SYMBOL_MAP = [
    # Comparisons (longer phrases before shorter)
    (r"less than or equal to",      "≤"),
    (r"greater than or equal to",   "≥"),
    (r"not equal to",               "≠"),
    (r"approximately equals",       "≈"),
    (r"less than",                  "<"),
    (r"greater than",               ">"),

    # Arithmetic
    (r"divided by",                 "÷"),
    (r"times",                      "×"),
    (r"plus",                       "+"),
    (r"minus",                      "−"),

    # Sets
    (r"is not in",                  "∉"),
    (r"is not an element of",       "∉"),
    (r"belongs to",                 "∈"),
    (r"is in",                      "∈"),
    (r"is an element of",           "∈"),
    (r"empty set",                  "∅"),

    # Calculus
    (r"(?:the )?summation",         "∑"),
    (r"(?:the )?sum",               "∑"),
    (r"(?:the )?product",           "∏"),

    # Greek letters (spoken forms including pronunciation hints)
    (r"\bpi\b|pie\b",               "π"),
    (r"\balpha\b|al-?fuh\b",        "α"),
    (r"\bbeta\b|bay-?tuh\b",        "β"),
    (r"\bgamma\b|gam-?uh\b",        "γ"),
    (r"\bdelta\b|del-?tuh\b",       "δ"),
    (r"\btheta\b|thay-?tuh\b",      "θ"),
    (r"\blambda\b|lam-?duh\b",      "λ"),
    (r"\bmu\b|mew\b",               "μ"),
    (r"\bsigma\b|sig-?muh\b",       "σ"),
    (r"\bphi\b|fie\b|fee\b",        "φ"),
    (r"\bomega\b|oh-?may-?guh\b",   "ω"),
]

# Ordinal words for higher-order derivatives
ORDINALS = {
    "second": "2", "third": "3", "fourth": "4",
    "fifth": "5", "sixth": "6", "seventh": "7",
}

# Word numbers to digits
WORD_NUMBERS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12",
}


def _apply(text, pattern, replacement, flags=re.IGNORECASE):
    return re.sub(pattern, replacement, text, flags=flags)


def normalize(text: str) -> str:
    t = text.lower().strip()

    # --- Pre-substitute tokens needed by structured patterns ---
    t = _apply(t, r"\bequals\b", "=")
    t = _apply(t, r"\binfinity\b", "∞")

    # --- Roots (before symbol substitution to avoid clobbering) ---
    t = _apply(t, r"(?:the )?cube root of ([a-z0-9 ]+?)(?= |$|[+\-×÷=<>≤≥≠,\.])", r"∛\1")
    t = _apply(t, r"(?:the )?square root of ([a-z0-9 ]+?)(?= |$|[+\-×÷=<>≤≥≠,\.])", r"√\1")

    # --- Powers / exponents ---
    t = _apply(t, r"([a-z0-9]+) squared",               r"\1²")
    t = _apply(t, r"([a-z0-9]+) cubed",                 r"\1³")
    t = _apply(t, r"([a-z0-9]+) to the power of ([a-z0-9]+)", r"\1^\2")
    t = _apply(t, r"([a-z0-9]+) to the ([a-z0-9]+)",   r"\1^\2")

    # --- Derivatives (before "partial" and "integral" get swapped) ---
    for word, digit in ORDINALS.items():
        t = _apply(t, rf"the {word} derivative of ([a-z]+) with respect to ([a-z]+)",
                   rf"d^{digit}\1/d\2^{digit}")
    t = _apply(t, r"the derivative of ([a-z]+) with respect to ([a-z]+)", r"d\1/d\2")
    t = _apply(t, r"d([a-z]) by d([a-z])", r"d\1/d\2")
    t = _apply(t, r"partial ([a-z]+) (?:with respect to|over) partial ([a-z]+)", r"∂\1/∂\2")

    # --- Integrals (structured, before bare ∫ substitution) ---
    t = _apply(
        t,
        r"(?:the )?integral from ([a-z0-9]+) to ([a-z0-9]+) of ([a-z0-9 \(\)]+?) d([a-z])",
        r"∫_\1^\2 \3 d\4",
    )
    t = _apply(t, r"(?:the )?integral of ([a-z0-9 \(\)]+?) d([a-z])", r"∫ \1 d\2")

    # --- Limits ---
    t = _apply(
        t,
        r"the limit as ([a-z]+) approaches ([a-z0-9∞]+)",
        r"lim_{\1→\2}",
    )

    # --- Fractions ---
    t = _apply(t, r"([a-z0-9]+) over ([a-z0-9]+)", r"\1/\2")

    # --- Summation with bounds ---
    t = _apply(
        t,
        r"(?:the )?sum from ([a-z0-9 =]+?) to ([a-z0-9∞]+) of",
        lambda m: f"∑_{{{m.group(1).replace(' ', '')}}}^{{{m.group(2)}}}",
    )

    # --- Word numbers ---
    for word, digit in WORD_NUMBERS.items():
        t = _apply(t, rf"\b{word}\b", digit)

    # --- Symbol substitutions ---
    for pattern, symbol in SYMBOL_MAP:
        t = _apply(t, pattern, symbol)

    # Clean up extra whitespace
    t = re.sub(r" +", " ", t).strip()
    return t


if __name__ == "__main__":
    tests = [
        ("what is the square root of x",            "what is √x"),
        ("what is x squared plus x cubed",          "what is x² + x³"),
        ("the derivative of y with respect to x",   "dy/dx"),
        ("the second derivative of y with respect to x", "d^2y/dx^2"),
        ("the integral from a to b of f of x dx",  "∫_a^b f of x dx"),
        ("the limit as x approaches zero of f",     "lim_{x→0} of f"),
        ("x to the power of n plus two",            "x^n + 2"),
        ("cube root of x plus x squared",           "∛x + x²"),
        ("x is not equal to y",                     "x is ≠ y"),
        ("x less than or equal to y",               "x ≤ y"),
        ("x is in the empty set",                   "x ∈ the ∅"),
        ("the sum from i equals 1 to infinity of",  "∑_{i=1}^{∞}"),
        ("theta plus pi equals phi",                "θ + π = φ"),
        ("x times y divided by z",                  "x × y ÷ z"),
    ]

    print("Running speech_normalizer tests...\n")
    passed = 0
    for spoken, expected in tests:
        result = normalize(spoken)
        status = "PASS" if result == expected else "FAIL"
        if status == "PASS":
            passed += 1
        print(f"  [{status}] '{spoken}'")
        if status == "FAIL":
            print(f"         expected: {expected}")
            print(f"         got:      {result}")

    print(f"\n{passed}/{len(tests)} passed")
