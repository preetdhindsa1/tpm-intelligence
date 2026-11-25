"""Prepare a meeting's notes for RAID extraction (pure, no I/O).

The roster (attendee and host lines) names people and holds no RAID items, so it is
removed before masking. Team names come from the notes' own update headings
("* Release Signal (APAC: ... )"), so no per-team list has to be kept in sync by hand.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

_ROSTER = re.compile(r"\((?:he|she|they|sh)(?:/|\b)[^)\n]*\)?\s*$", re.I)
_HOST = re.compile(r"^\s*(?:Host|Attendees)\b|^\s*(?:APAC|Americas/EMEA|EMEA)\s*:\s*$", re.I)
_TEAM = re.compile(r"^\s*[*-]?\s*([A-Z][A-Za-z/-]+(?: [A-Za-z/-]+){0,3}?)\s*\((?=[^)\n]*[@:/])")
_NOT_TEAMS = frozenset({"Docs Freeze", "Code Freeze", "Host", "Attendees"})


def drop_roster(text: str) -> str:
    """The notes without attendee lines ("Name (she/her, role)") and roster headings."""
    return "\n".join(
        line for line in text.splitlines() if not (_ROSTER.search(line) or _HOST.match(line))
    )


def teams_in(texts: Iterable[str]) -> list[str]:
    """Team names from update headings (roster lines excluded), in first-seen order."""
    seen: dict[str, None] = {}
    for text in texts:
        for line in drop_roster(text).splitlines():
            m = _TEAM.match(line)
            if m and m.group(1) not in _NOT_TEAMS:
                seen.setdefault(m.group(1).strip(), None)
    return list(seen)
