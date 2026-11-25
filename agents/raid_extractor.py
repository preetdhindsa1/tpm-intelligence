"""RAID extractor: risks, actions, issues, decisions and questions from one meeting (#177).

1. Code masks people's names (``modules.raid.mask``); the model sees only masked text.
2. Claude (simple model) lists items, each with a quote copied from that text.
3. Code checks every quote word for word (whitespace aside). An item whose quote is not
   found is dropped and counted, never stored. Explicit KEP and PR references in the quote
   become links by rule (``linker.refs``); everything else is left for a person.
4. Items are returned as ``suggested`` RAID items. Only a person confirms them.

Non-essential: when the daily budget pauses it, the run stops and resumes another day.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from opentelemetry import trace
from pydantic import BaseModel, ConfigDict, Field

from agents.gateway import Gateway, TaskSpec
from agents.prompts import Prompt
from agents.settings import ModelRole
from linker.refs import numbers_in, tracked_pull_requests
from modules.raid.mask import mask_names
from modules.raid.store import RaidItem, RaidStore, normalize_quote, suggestion_key

TASK = TaskSpec("raid_extractor", ModelRole.SIMPLE, effort="low", max_tokens=6000, essential=False)
MIN_QUOTE_WORDS = 4
_tracer = trace.get_tracer("agents.raid_extractor")
DropReason = Literal["quote_not_found", "quote_too_short", "duplicate"]


class ExtractedItemOut(BaseModel):
    """One item as the model gives it."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["risk", "action", "issue", "decision", "question"]
    title: str = Field(description="Plain summary in at most 15 words.", max_length=160)
    quote: str = Field(description="The sentence or bullet copied exactly from the notes.")
    owner: str | None = Field(description="One of the given teams, exactly as written, or null.")


class ExtractionOut(BaseModel):
    """The model's answer: every item in the meeting, or an empty list."""

    model_config = ConfigDict(extra="forbid")

    items: list[ExtractedItemOut]


@dataclass(frozen=True)
class Meeting:
    """One meeting's notes from a source document."""

    document_id: str
    release_key: str
    workstream: str  # RAID ID prefix, e.g. "K8S"
    meeting_date: str  # ISO date
    text: str  # as in the source; masked here before use


@dataclass(frozen=True)
class ExtractionResult:
    """What one meeting produced, what was dropped and what it cost."""

    items: tuple[RaidItem, ...]
    dropped: dict[str, int]
    model: str
    cost_usd: float
    cached: bool
    returned: int = 0
    unknown_owners: int = 0


def links_in(quote: str) -> tuple[str, ...]:
    """Work-item and PR keys the quote names explicitly; nothing is guessed."""
    keps = [f"kubernetes/enhancements#{n}" for n in numbers_in(quote)]
    prs = [f"{repo}#{n}" for repo, n in tracked_pull_requests(quote)]
    return tuple(dict.fromkeys(keps + prs))


def check_items(
    out: ExtractionOut, meeting: Meeting, masked: str, teams: Sequence[str]
) -> tuple[list[RaidItem], Counter[str], int]:
    """Keep items whose quote is in ``masked``; count the rest by reason."""
    source = normalize_quote(masked)
    dropped: Counter[str] = Counter()
    kept: dict[str, RaidItem] = {}
    unknown = 0
    for it in out.items:
        quote = normalize_quote(it.quote)
        reason: DropReason | None = None
        if len(quote.split()) < MIN_QUOTE_WORDS:
            reason = "quote_too_short"
        elif quote not in source:
            reason = "quote_not_found"
        key = suggestion_key(meeting.document_id, meeting.meeting_date, it.type, quote)
        if reason is None and key in kept:
            reason = "duplicate"
        if reason is not None:
            dropped[reason] += 1
            continue
        owner = it.owner if it.owner in teams else None
        unknown += it.owner is not None and owner is None
        kept[key] = RaidItem(
            item_id=0,
            key=key,
            release_key=meeting.release_key,
            workstream=meeting.workstream,
            type=it.type,
            title=it.title.strip(),
            quote=quote,
            document_id=meeting.document_id,
            meeting_date=meeting.meeting_date,
            owner=owner,
            links=links_in(quote),
        )
    return list(kept.values()), dropped, unknown


def extract(
    gateway: Gateway,
    prompt: Prompt,
    meeting: Meeting,
    names: Iterable[str],
    teams: Sequence[str],
) -> ExtractionResult:
    """One call plus the checks. Raises ``AIError`` (incl. budget) unchanged."""
    masked = mask_names(meeting.text, names)
    inputs = {"meeting_date": meeting.meeting_date, "teams": list(teams), "notes": masked}
    attrs = {"raid.document": meeting.document_id, "raid.meeting_date": meeting.meeting_date}
    with _tracer.start_as_current_span("raid.extract", attributes=attrs) as span:
        response = gateway.run(TASK, prompt, inputs, ExtractionOut)
        items, dropped, unknown = check_items(response.output, meeting, masked, teams)
        span.set_attribute("raid.returned", len(response.output.items))
        span.set_attribute("raid.kept", len(items))
        span.set_attribute("raid.dropped", sum(dropped.values()))
        span.set_attribute("ai.cost_usd", response.cost_usd)
    return ExtractionResult(
        items=tuple(items),
        dropped=dict(dropped),
        model=response.model,
        cost_usd=response.cost_usd,
        cached=response.cached,
        returned=len(response.output.items),
        unknown_owners=unknown,
    )


def store_all(store: RaidStore, results: Iterable[ExtractionResult], at: datetime) -> int:
    """Add each kept item as a suggestion; returns how many were new (re-runs add none)."""
    return sum(store.suggest(i, at) is not None for r in results for i in r.items)
