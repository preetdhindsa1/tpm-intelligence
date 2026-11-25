"""Mask people's names in meeting notes before they are shown or sent to AI (ADR-0030 add. 2).

Public notes name contributors in attendee lists, in team headings ("Docs (Name / @handle)")
and in the text. The platform shows roles and counts, never names (CLAUDE.md section 10),
so the extractor only ever sees the masked text, and quotes are checked against it.
Masking errs towards hiding: a capitalised word that is also a name is masked too.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

MASK = "[participant]"
# "* Jane Doe (she/her, Release Docs Lead)" in an attendee or host list.
_ATTENDEE = re.compile(
    r"^[\s*:\w/-]*?([A-Z][\w.'-]+(?: [A-Z][\w.'-]+){0,3})\s*\((?:he|she|they)\b", re.M | re.I
)
# "Docs (APAC: Jane Doe / @jdoe | EMEA: Sam Roe)": everything inside the brackets.
_HEADING = re.compile(r"\(([^()\n]*@[^()\n]*)\)")
_HEADING_NAME = re.compile(r"(?:^|[:|,/])\s*([A-Z][\w.'-]+(?: [A-Z][\w.'-]+){0,3})\s*(?=$|[|,/])")
_HANDLE = re.compile(r"@[A-Za-z0-9][\w-]*(?: [A-Za-z][\w-]*)?(?=\s*[|,)/]|$)|@[A-Za-z0-9][\w-]*")
# "* [Kat + Dipesh] ..." at the start of a line; "[Flaking Test]" and "[sig-node]" are not people.
_SPEAKER = re.compile(r"^(\s*[*-]?\s*)\[([^\]\n]{1,40})\]", re.M)
_NOT_SPEAKER = re.compile(r"^(?:sig\b|feature|flaking|failing|participant$)", re.I)
_SPLIT = re.compile(r"\s*(?:\+|/|,|\band\b|\(|\))\s*")
_NOT_NAMES = frozenset(
    {"APAC", "EMEA", "Americas", "Release", "Lead", "Shadow", "N/A", "NAME", "LMKTFY"}
)


def names_in(text: str) -> set[str]:
    """Full names and their first names, from attendee lists and team headings."""
    found: set[str] = {m.group(1) for m in _ATTENDEE.finditer(text)}
    for m in _HEADING.finditer(text):
        inner = _HANDLE.sub("/", m.group(1))
        found.update(n.group(1) for n in _HEADING_NAME.finditer(inner))
    for m in _SPEAKER.finditer(text):
        if not _NOT_SPEAKER.match(m.group(2)):
            found.update(p for p in _SPLIT.split(m.group(2)) if p[:1].isupper())
    names = {n.strip() for n in found if n.strip() not in _NOT_NAMES}
    return names | {n.split()[0] for n in names if n.split()[0] not in _NOT_NAMES}


def mask_names(text: str, names: Iterable[str]) -> str:
    """``text`` with handles, ``[Speaker]`` tags and the given names replaced by the mask."""
    out = _HANDLE.sub(MASK, text)
    out = _SPEAKER.sub(
        lambda m: m.group(0) if _NOT_SPEAKER.match(m.group(2)) else m.group(1) + MASK, out
    )
    ordered = sorted({n for n in names if len(n) > 1}, key=len, reverse=True)
    if ordered:
        alt = "|".join(map(re.escape, ordered))
        out = re.sub(rf"(?<![\w@])(?:{alt})(?![\w])", MASK, out)
    return out
