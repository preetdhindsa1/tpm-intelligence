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


_MONTH_NUM = {
    m: i
    for i, names in enumerate(
        (
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ),
        start=1,
    )
    for m in names
}
_DAY_MONTH = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTHS})\b", re.IGNORECASE)
_MONTH_DAY = re.compile(rf"\b({_MONTHS})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", re.IGNORECASE)
_ISO_DATE = re.compile(r"\b\d{4}-(\d{2})-(\d{2})")


def stated_dates(text: str) -> list[tuple[int, int]]:
    """(month, day) for each calendar date written in ``text``."""
    found: list[tuple[int, int]] = []
    for m in _ISO_DATE.finditer(text):
        found.append((int(m.group(1)), int(m.group(2))))
    rest = _ISO_DATE.sub(" ", text)
    for m in _DAY_MONTH.finditer(rest):
        found.append((_MONTH_NUM[m.group(2).lower()], int(m.group(1))))
    rest = _DAY_MONTH.sub(" ", rest)
    for m in _MONTH_DAY.finditer(rest):
        found.append((_MONTH_NUM[m.group(1).lower()], int(m.group(2))))
    return found
