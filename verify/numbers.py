"""Find the numbers a sentence states, ignoring identifiers and dates. Pure, no I/O.

A claim can carry the right ``value`` but say something else in its text ("odds are 80%"
with value 0.38). The checker compares every number left after masking against the facts
the claim cites.
"""

from __future__ import annotations

import re

_MONTHS = (
    "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|"
    "june|july|august|september|october|november|december"
)

# Order matters: longer, more specific patterns first.
_MASKS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\b\d{4}-\d{2}-\d{2}(?:[t ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:z|[+-]\d{2}:?\d{2})?)?",
        rf"\b(?:{_MONTHS})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+\d{{4}})?",
        rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{_MONTHS})\b(?:,?\s+\d{{4}})?",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:utc|am|pm)?",
        r"[\w./-]*#\d+",  # #6395, kubernetes/kubernetes#143709
        r"\bv\d+(?:\.\d+)+\b",  # v1.38
        r"\b[A-Z][A-Z0-9]+-\d+\b",  # KEP-6395, KAFKA-19831
        r"\bsig[/-][\w-]+",
        r"\b(?:19|20)\d{2}\b",  # a bare year
    )
)
_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:,\d{3})*(?:\.\d+)?")


def stated_numbers(text: str) -> list[float]:
    """Numbers in ``text`` once dates, times, versions and issue/PR keys are masked."""
    masked = text
    for pattern in _MASKS:
        masked = pattern.sub(" ", masked)
    return [float(m.group().replace(",", "")) for m in _NUMBER.finditer(masked)]
