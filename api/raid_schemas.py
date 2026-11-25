"""RAID tracker API models (Wave 4, ADR-0030; contract: docs/api/raid-contract.md).

AI never confirms an item: an item stays ``suggested`` until a person confirms, edits or
rejects it, and it gets its RAID ID (``{WORKSTREAM}-{TYPE}-{SEQ}``) on first confirm.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ItemType = Literal["risk", "action", "issue", "decision", "question"]
Status = Literal["open", "in_progress", "closed", "superseded"]
Review = Literal["suggested", "confirmed", "edited", "rejected"]
TYPE_LETTER: dict[str, str] = {
    "risk": "R",
    "action": "A",
    "issue": "I",
    "decision": "D",
    "question": "Q",
}


class _Out(BaseModel):
    model_config = ConfigDict(frozen=True)


class RaidSourceOut(_Out):
    """Where the item was said or written. ``quote`` is verbatim from it."""

    kind: Literal["meeting", "ticket", "pr", "retro"]
    title: str
    url: str | None
    date: datetime
    synthetic: bool


class RaidLinkOut(_Out):
    """A link to work. ``explicit_key`` links (a KEP or issue number) are verified."""

    kind: Literal["feature", "issue", "pr"]
    ref: str
    method: Literal["explicit_key", "ai_suggested"]
    status: Literal["verified", "suggested"]


class MergeSuggestionOut(_Out):
    """The extractor thinks this repeats another item. Never applied without a person."""

    into_item_id: int
    reason: str


class RaidItemOut(_Out):
    """One risk, action, issue, decision or question."""

    item_id: int  # internal, stable; used in URLs
    raid_id: str | None  # "K8S-R-001", given on first confirm, never changed or reused
    workstream: str
    type: ItemType
    title: str
    quote: str
    source: RaidSourceOut
    owner: str | None  # a role or team in the public demo, never a person's name
    status: Status
    review: Review
    links: list[RaidLinkOut]
    merge_suggestion: MergeSuggestionOut | None
    created_at: datetime
    updated_at: datetime


class RaidListOut(_Out):
    """Items for one program's release."""

    project: str
    release: str
    as_of: datetime
    synthetic: bool
    items: list[RaidItemOut]


class RaidHistoryEntryOut(_Out):
    """One append-only history row. ``actor`` is a role: extractor, approver."""

    at: datetime
    actor: Literal["extractor", "approver"]
    action: Literal["suggested", "confirmed", "edited", "rejected", "status_changed"]
    changes: dict[str, Any]
    reason: str | None


class RaidHistoryOut(_Out):
    item_id: int
    raid_id: str | None
    synthetic: bool
    history: list[RaidHistoryEntryOut]


class RaidCountOut(_Out):
    type: ItemType
    suggested: int
    open: int
    in_progress: int
    closed: int
    superseded: int
    rejected: int


class RaidSummaryOut(_Out):
    project: str
    release: str
    as_of: datetime
    synthetic: bool
    by_type: list[RaidCountOut]
    risks_without_owner: int  # open confirmed risks with no owner (a readiness criterion)
    waiting_for_review: int


class RaidEditIn(BaseModel):
    """A person's corrections; the quote cannot be edited (it is the source's words)."""

    title: str | None = Field(default=None, min_length=1, max_length=300)
    type: ItemType | None = None
    owner: str | None = Field(default=None, max_length=120)
    status: Status | None = None
    note: str | None = Field(default=None, max_length=1000)


class RaidConfirmIn(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class RaidRejectIn(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)
