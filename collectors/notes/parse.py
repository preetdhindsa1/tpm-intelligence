"""Split a meeting-notes document into one segment per meeting. Pure, no I/O.

Kubernetes release-team notes put every meeting under a heading such as
``Week 12 - Wednesday 18 November 2026 Weekly Meeting (recording)``. Real headings vary:
the weekday is sometimes the literal word ``Weekday``, the day can carry a suffix
(``2nd September``), and a heading can sit in a bullet (``   * Week 8 - ...``). The
template heading (``Week N - Weekday Day Month 2026``) has no numbers and is skipped.
Text before the first meeting (links, roster, template) is not a meeting and is dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

_MONTHS = {
    m: i
    for i, m in enumerate(
        ["january", "february", "march", "april", "may", "june", "july", "august",
         "september", "october", "november", "december"],
        start=1,
    )
}  # fmt: skip

HEADING = re.compile(
    r"^[\s*•-]*Week\s+(?P<week>\d+)\s*[\u2013-]\s*"
    r"(?:[A-Za-z]+day,?\s+)?"
    r"(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+(?P<month>[A-Za-z]+)\s+(?P<year>\d{4})\s+"
    r"(?P<name>[A-Za-z/]+\s+Meeting)",
)


@dataclass(frozen=True)
class Meeting:
    """One meeting's notes, verbatim."""

    heading: str
    meeting_date: date | None
    week: int
    text: str


def _date(day: str, month: str, year: str) -> date | None:
    m = _MONTHS.get(month.lower()) or next(
        (i for name, i in _MONTHS.items() if len(month) >= 3 and name.startswith(month.lower())),
        None,
    )
    if m is None:
        return None
    try:
        return date(int(year), m, int(day))
    except ValueError:
        return None


def split_meetings(text: str) -> list[Meeting]:
    """Meetings in document order. Each ``text`` runs from its heading to the next one."""
    lines = text.replace("\r\n", "\n").lstrip("﻿").split("\n")
    starts: list[tuple[int, re.Match[str]]] = []
    for i, line in enumerate(lines):
        match = HEADING.match(line)
        if match:
            starts.append((i, match))
    meetings = []
    for n, (i, match) in enumerate(starts):
        end = starts[n + 1][0] if n + 1 < len(starts) else len(lines)
        body = "\n".join(lines[i:end]).strip()
        heading = re.sub(r"^[\s*•-]+", "", lines[i]).strip()
        heading = re.sub(r"\s*\(recording\)\s*$", "", heading)
        meetings.append(
            Meeting(
                heading=heading,
                meeting_date=_date(match["day"], match["month"], match["year"]),
                week=int(match["week"]),
                text=body,
            )
        )
    return meetings


RETRO_DATE = re.compile(
    r"Part\s*1\s*:\s*(?:[A-Za-z]+day,?\s+)?(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(?P<month>[A-Za-z]+)\s+(?P<year>\d{4})"
)
RETRO_START = re.compile(r"^\s*\([^)]*\)\s*What went well", re.IGNORECASE)


def split_retro(text: str) -> list[Meeting]:
    """A retrospective document as one meeting (Kubernetes release retros).

    Dated by the first ``Part 1: 29th Jul 2026`` line. The text starts at the "What went
    well" section, so the header (call details, facilitators, attendees) is dropped.
    """
    lines = text.replace("\r\n", "\n").lstrip("\ufeff").split("\n")
    match = next((m for line in lines if (m := RETRO_DATE.search(line))), None)
    start = next((i for i, line in enumerate(lines) if RETRO_START.match(line)), None)
    if start is None:
        return []
    when = _date(match["day"], match["month"], match["year"]) if match else None
    title = lines[0].strip() or "Release retrospective"
    return [
        Meeting(heading=title, meeting_date=when, week=0, text="\n".join(lines[start:]).strip())
    ]
