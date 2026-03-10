"""Convert user-facing calculator phrases into parser-friendly text."""

from __future__ import annotations

import re


_NUMBER_COMMA_PATTERN = re.compile(r"(?<=\d),(?=\d)")
_SPACING_PATTERN = re.compile(r"\s+")
_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bto the power of\b", re.IGNORECASE), " ^ "),
    (re.compile(r"\braised to\b", re.IGNORECASE), " ^ "),
    (re.compile(r"\bmultiplied by\b", re.IGNORECASE), " * "),
    (re.compile(r"\btimes\b", re.IGNORECASE), " * "),
    (re.compile(r"\bdivided by\b", re.IGNORECASE), " / "),
    (re.compile(r"\bover\b", re.IGNORECASE), " / "),
    (re.compile(r"\bplus\b", re.IGNORECASE), " + "),
    (re.compile(r"\bminus\b", re.IGNORECASE), " - "),
    (re.compile(r"\bmodulo\b", re.IGNORECASE), " % "),
    (re.compile(r"\bmod\b", re.IGNORECASE), " % "),
)


def normalize_expression(text: str) -> str:
    """Normalize a small subset of natural-language calculator syntax."""
    normalized = text.strip()
    normalized = normalized.replace("×", "*")
    normalized = normalized.replace("÷", "/")
    normalized = normalized.replace("–", "-")
    normalized = normalized.replace("—", "-")

    for pattern, replacement in _REPLACEMENTS:
        normalized = pattern.sub(replacement, normalized)

    normalized = _NUMBER_COMMA_PATTERN.sub("", normalized)
    normalized = _SPACING_PATTERN.sub(" ", normalized)
    return normalized.strip()
