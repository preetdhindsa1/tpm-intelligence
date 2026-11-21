"""Find KEP references in PR text. Pure functions, no I/O.

A reference is **strong** when the author declares it in a structured way:

1. in the PR title (``KEP-6395``, ``[KEP 6395]``);
2. on a ``KEP:`` line (``KEP: https://github.com/kubernetes/enhancements/issues/6395``);
3. in an "implements" phrase (``Implements Alpha support for **KEP-6395: ...``);
4. under the kubernetes/kubernetes PR template heading
   "Which issue(s) this PR is related to" (#143442, #143445 and #143474 do this).

Anything else (e.g. #143644: "as discussed in .../issues/6395") is a **passing** mention.
HTML comments are removed first: the PR template contains example text inside them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

_COMMENTS = re.compile(r"<!--.*?-->", re.S)
# A KEP number: "KEP-6395", "KEP 6395", "KEP6395", an enhancements issue URL or short ref,
# or a keps/ path. The look-arounds stop "KEP-63951" or "#63950" matching 6395.
_REF = re.compile(
    r"(?:\bKEP[-\s]?(?P<kep>\d{1,5})(?!\d)"
    r"|github\.com/kubernetes/enhancements/issues/(?P<url>\d{1,5})(?!\d)"
    r"|kubernetes/enhancements#(?P<short>\d{1,5})(?!\d)"
    r"|keps/[\w-]+/(?P<path>\d{1,5})-)",
    re.I,
)
_KEP_LINE = re.compile(r"^\s*(?:[-*]\s*)?\**KEP\**\s*:", re.I)
_IMPLEMENTS = re.compile(
    r"\bimplement\w*\b[^\n.]{0,80}?(?:\bKEP[-\s]?|enhancements/issues/)(\d{1,5})(?!\d)", re.I
)
_RELATED_HEADING = re.compile(r"^\s*#+\s*which issue\(s\)", re.I)
_ANY_HEADING = re.compile(r"^\s*#+\s")


class Where(StrEnum):
    """Where in the PR a reference was found."""

    TITLE = "title"
    KEP_LINE = "kep_line"
    IMPLEMENTS = "implements"
    RELATED_ISSUES = "related_issues_section"
    BODY = "body"


STRONG = frozenset({Where.TITLE, Where.KEP_LINE, Where.IMPLEMENTS, Where.RELATED_ISSUES})


@dataclass(frozen=True)
class KepRef:
    """One KEP reference, with the strongest place it was found and the text around it."""

    number: int
    where: Where
    snippet: str

    @property
    def strong(self) -> bool:
        """Declared in a structured way (see module docstring)."""
        return self.where in STRONG


def numbers_in(text: str) -> list[int]:
    """All KEP numbers referenced in ``text``, in order, without duplicates."""
    seen: dict[int, None] = {}
    for m in _REF.finditer(text):
        seen.setdefault(int(next(g for g in m.groups() if g is not None)), None)
    return list(seen)


def find_kep_refs(title: str, body: str) -> list[KepRef]:
    """KEP references in a PR, one per number, keeping the strongest location."""
    best: dict[int, KepRef] = {}

    def offer(number: int, where: Where, snippet: str) -> None:
        current = best.get(number)
        if current is None or (where in STRONG and not current.strong):
            best[number] = KepRef(number, where, snippet.strip()[:200])

    for n in numbers_in(title):
        offer(n, Where.TITLE, title)

    text = _COMMENTS.sub("", body or "")
    in_related = False
    for line in text.splitlines():
        if _ANY_HEADING.match(line):
            in_related = bool(_RELATED_HEADING.match(line))
            continue
        for m in _IMPLEMENTS.finditer(line):
            offer(int(m.group(1)), Where.IMPLEMENTS, line)
        where = (
            Where.KEP_LINE
            if _KEP_LINE.match(line)
            else Where.RELATED_ISSUES
            if in_related
            else Where.BODY
        )
        for n in numbers_in(line):
            offer(n, where, line)
    return sorted(best.values(), key=lambda r: r.number)


_PR_URL = re.compile(r"github\.com/(?P<repo>[\w.-]+/[\w.-]+)/pull/(?P<number>\d+)(?!\d)")


def tracked_pull_requests(description: str) -> list[tuple[str, int]]:
    """PR URLs listed in a work item's description (the KEP issue tracking list)."""
    seen: dict[tuple[str, int], None] = {}
    for m in _PR_URL.finditer(_COMMENTS.sub("", description or "")):
        seen.setdefault((m.group("repo"), int(m.group("number"))), None)
    return list(seen)


def mentions_identifier(text: str, identifier: str) -> bool:
    """Whole-word, case-sensitive match (feature gate names are CamelCase identifiers)."""
    return re.search(rf"(?<![\w]){re.escape(identifier)}(?![\w])", text) is not None
