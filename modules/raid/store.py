"""RAID items: identity, IDs, lifecycle, merge suggestions and history (ADR-0030 add. 2).

Pure rules plus an in-memory store; the Postgres store implements the same protocol. No AI
here: the extractor only *adds suggestions*, and only a person moves an item out of
``suggested``.
"""

from __future__ import annotations

import hashlib
import re
import threading
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Literal, Protocol

ItemType = Literal["risk", "action", "issue", "decision", "question"]
Review = Literal["suggested", "confirmed", "edited", "rejected"]
Status = Literal["open", "in_progress", "closed", "superseded"]
LETTER: dict[str, str] = {
    "risk": "R",
    "action": "A",
    "issue": "I",
    "decision": "D",
    "question": "Q",
}
MERGE_OVERLAP = 0.6  # Jaccard on lowercased word sets (ADR-0030 addendum 2)
_KEY = re.compile(r"#(\d{3,6})\b")
_WORD = re.compile(r"[a-z0-9]+")


def normalize_quote(quote: str) -> str:
    """Whitespace collapsed: the only difference the quote check allows."""
    return " ".join(quote.split())


def suggestion_key(document_id: str, meeting_date: str, type_: str, quote: str) -> str:
    """Stable identity of a suggestion, so a re-run of the extractor adds nothing new."""
    raw = "\x1f".join((document_id, meeting_date, type_, normalize_quote(quote)))
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def next_raid_id(used: set[str], workstream: str, type_: str) -> str:
    """The next free ``{WORKSTREAM}-{TYPE}-{SEQ}``; numbers ever used are never reused."""
    prefix = f"{workstream}-{LETTER[type_]}-"
    seqs = [int(u[len(prefix) :]) for u in used if u.startswith(prefix)]
    return f"{prefix}{max(seqs, default=0) + 1:03d}"


def merge_reason(a: RaidItem, b: RaidItem) -> str | None:
    """Why ``a`` may repeat ``b``, or None. Only ever a suggestion for a person."""
    if a.type != b.type or a.release_key != b.release_key:
        return None
    shared = sorted(set(_KEY.findall(a.quote)) & set(_KEY.findall(b.quote)))
    if shared:
        return f"Same {a.type} and both mention #{shared[0]}."
    wa, wb = set(_WORD.findall(a.quote.lower())), set(_WORD.findall(b.quote.lower()))
    overlap = len(wa & wb) / len(wa | wb) if wa | wb else 0.0
    if overlap >= MERGE_OVERLAP:
        return f"Same {a.type}; the quotes share {overlap:.0%} of their words."
    return None


@dataclass(frozen=True)
class HistoryRow:
    at: datetime
    actor: Literal["extractor", "approver"]
    action: str
    changes: dict[str, Any]
    reason: str | None
    by: str | None = None  # the approver's login, stored for audit, never returned


@dataclass(frozen=True)
class RaidItem:
    item_id: int
    key: str  # suggestion_key
    release_key: str
    workstream: str
    type: ItemType
    title: str
    quote: str
    document_id: str
    meeting_date: str
    owner: str | None = None
    status: Status = "open"
    review: Review = "suggested"
    raid_id: str | None = None
    links: tuple[str, ...] = ()
    merge_into: int | None = None
    merge_reason: str | None = None
    history: tuple[HistoryRow, ...] = field(default=())


class RaidStore(Protocol):
    def suggest(self, item: RaidItem, at: datetime) -> RaidItem | None: ...
    def decide(
        self,
        item_id: int,
        action: Review,
        by: str,
        at: datetime,
        changes: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> RaidItem: ...
    def items(self, release_key: str) -> list[RaidItem]: ...


class MemoryRaidStore:
    """In-process store with the same rules as the Postgres one (tests, local runs)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[int, RaidItem] = {}
        self._used: set[str] = set()

    def suggest(self, item: RaidItem, at: datetime) -> RaidItem | None:
        """Add a suggestion; None if this key exists already (also when it was rejected)."""
        with self._lock:
            if any(i.key == item.key for i in self._items.values()):
                return None
            new = replace(item, item_id=len(self._items) + 1, review="suggested", raid_id=None)
            for other in self._items.values():
                why = merge_reason(new, other)
                if why and other.review != "rejected":
                    new = replace(new, merge_into=other.item_id, merge_reason=why)
                    break
            row = HistoryRow(at, "extractor", "suggested", {"type": new.type}, None)
            new = replace(new, history=(row,))
            self._items[new.item_id] = new
            return new

    def decide(
        self,
        item_id: int,
        action: Review,
        by: str,
        at: datetime,
        changes: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> RaidItem:
        """A person confirms, edits (and so confirms) or rejects. Rejection needs a reason."""
        if action == "suggested":
            raise ValueError("only the extractor suggests")
        if action == "rejected" and not (reason and reason.strip()):
            raise ValueError("a rejection needs a reason")
        changes = {k: v for k, v in (changes or {}).items() if v is not None}
        if "quote" in changes:
            raise ValueError("the quote is the source's words and cannot be edited")
        with self._lock:
            item = self._items[item_id]
            if item.review == "rejected":
                raise ValueError("a rejected item cannot be decided again")
            item = replace(item, **changes, review=action)
            if action != "rejected" and item.raid_id is None:
                rid = next_raid_id(self._used, item.workstream, item.type)
                self._used.add(rid)
                item = replace(item, raid_id=rid)
                changes = {**changes, "raid_id": rid}
            row = HistoryRow(at, "approver", action, changes, reason, by)
            item = replace(item, history=(*item.history, row))
            self._items[item_id] = item
            return item

    def items(self, release_key: str) -> list[RaidItem]:
        with self._lock:
            return [i for i in self._items.values() if i.release_key == release_key]
