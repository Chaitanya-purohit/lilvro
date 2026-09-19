"""
speech_normalizer.py — Chai's module

Converts spoken math phrases (from Deepgram transcript) into structured math
notation that Claude can reason over correctly.

Input:  "what is the square root of x plus x squared"
Output: "what is sqrt(x) + x^2"
"""

import re


# Ordinal words to digits for derivatives ("second derivative" -> 2)
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


def _apply(text: str, pattern: str, replacement, flags=re.IGNORECASE) -> str:
    return re.sub(pattern, replacement, text, flags=flags)


def normalize(text: str) -> str:
    t = text.lower().strip()

    # --- Roots ---
    t = _apply(t, r"(?:the )?cube root of ([a-z0-9 _]+?)(?= |$|[\+\-\*\/\,\.])", r"cbrt(\1)")
    t = _apply(t, r"(?:the )?square root of ([a-z0-9 _]+?)(?= |$|[\+\-\*\/\,\.])", r"sqrt(\1)")

    # --- Powers / exponents ---
    t = _apply(t, r"([a-z0-9]+) squared", r"\1^2")
    t = _apply(t, r"([a-z0-9]+) cubed", r"\1^3")
    t = _apply(t, r"([a-z0-9]+) to the power of ([a-z0-9]+)", r"\1^\2")
    t = _apply(t, r"([a-z0-9]+) to the ([a-z0-9]+)", r"\1^\2")

    # --- Derivatives ---
    for word, digit in ORDINALS.items():
        t = _apply(t, rf"the {word} derivative of ([a-z]+) with respect to ([a-z]+)",
                   rf"d^{digit}\1/d\2^{digit}")
    t = _apply(t, r"the derivative of ([a-z]+) with respect to ([a-z]+)", r"d\1/d\2")
    t = _apply(t, r"d([a-z]) by d([a-z])", r"d\1/d\2")

    # --- Integrals ---
    t = _apply(
        t,
        r"the integral from ([a-z0-9]+) to ([a-z0-9]+) of ([a-z0-9 \(\)]+?) d([a-z])",
        r"int_\1^\2 \3 d\4",
    )
    t = _apply(t, r"the integral of ([a-z0-9 \(\)]+?) d([a-z])", r"int \1 d\2")

    # --- Limits ---
    t = _apply(
        t,
        r"the limit as ([a-z]+) approaches ([a-z0-9]+)",
        r"lim_{\1->\2}",
    )

    # --- Fractions ---
    t = _apply(t, r"([a-z0-9]+) over ([a-z0-9]+)", r"\1/\2")

    # --- Arithmetic spoken words ---
    t = _apply(t, r"\bplus\b", "+")
    t = _apply(t, r"\bminus\b", "-")
    t = _apply(t, r"\btimes\b", "*")
    t = _apply(t, r"\bdivided by\b", "/")
    t = _apply(t, r"\bequals\b", "=")

    # --- Word numbers ---
    for word, digit in WORD_NUMBERS.items():
        t = _apply(t, rf"\b{word}\b", digit)

    # --- Greek letters ---
    t = _apply(t, r"\bpi\b", "pi")
    t = _apply(t, r"\btheta\b", "theta")
    t = _apply(t, r"\balpha\b", "alpha")
    t = _apply(t, r"\bbeta\b", "beta")
    t = _apply(t, r"\blambda\b", "lambda")

    # Clean up extra whitespace
    t = re.sub(r" +", " ", t).strip()
    return t


if __name__ == "__main__":
    tests = [
        ("what is the square root of x", "what is sqrt(x)"),
        ("what is x squared plus x cubed", "what is x^2 + x^3"),
        ("the derivative of y with respect to x", "dy/dx"),
        ("the second derivative of y with respect to x", "d^2y/dx^2"),
        ("the integral from a to b of f of x dx", "int_a^b f of x dx"),
        ("the limit as x approaches zero of f of x", "lim_{x->0} of f of x"),
        ("x to the power of n plus two", "x^n + 2"),
        ("cube root of x plus x squared", "cbrt(x) + x^2"),
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
