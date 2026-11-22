"""Stored link suggestions and the review queue (ADR-0011).

``suggested`` rows wait for a person. ``confirm`` and ``reject`` record who decided and
when; only ``suggested`` rows can be decided, and decisions are final (a person can undo a
confirmation only by asking a developer, which keeps the record honest).

``engine_links`` turns the rows into links for ``engine.links.link_release``:
confirmed -> verified (``ai_suggested``, ``verified_by`` = the person), rejected ->
rejected, suggested -> suggested.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol

from linker.methods import LinkMethod, LinkStatus
from linker.rules import LinkCandidate
from linker.suggestions import AI_SUGGESTED_CONFIDENCE, PERSON_CONFIRMED_CONFIDENCE


class SuggestionStatus(StrEnum):
    """Lifecycle of a stored answer."""

    SUGGESTED = "suggested"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    NONE = "none"
    DROPPED = "dropped"


DECIDABLE = frozenset({SuggestionStatus.SUGGESTED})


class SuggestionError(Exception):
    """A review action that the workflow does not allow."""


@dataclass(frozen=True)
class LinkSuggestion:
    """One stored answer."""

    release_key: str
    pull_request_key: str
    feature_key: str | None
    status: SuggestionStatus
    evidence: dict[str, Any]
    input_sha: str
    prompt_version: str
    model: str
    cost_usd: float
    id: int | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None
    decision_note: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def engine_links(rows: Iterable[LinkSuggestion]) -> list[LinkCandidate]:
    """Links for the engine. A decision on a (PR, feature) pair beats any pending row."""
    decided: dict[tuple[str, str], LinkSuggestion] = {}
    pending: dict[tuple[str, str], LinkSuggestion] = {}
    for r in sorted(rows, key=lambda r: (r.created_at, r.id or 0)):
        if r.feature_key is None:
            continue
        pair = (r.pull_request_key, r.feature_key)
        if r.status in (SuggestionStatus.CONFIRMED, SuggestionStatus.REJECTED):
            decided[pair] = r
        elif r.status is SuggestionStatus.SUGGESTED:
            pending[pair] = r
    out: list[LinkCandidate] = []
    for pair, r in sorted({**pending, **decided}.items()):
        if r.status is SuggestionStatus.CONFIRMED:
            status, confidence = LinkStatus.VERIFIED, PERSON_CONFIRMED_CONFIDENCE
        elif r.status is SuggestionStatus.REJECTED:
            status, confidence = LinkStatus.REJECTED, Decimal("0")
        else:
            status, confidence = LinkStatus.SUGGESTED, AI_SUGGESTED_CONFIDENCE
        evidence = {
            "pr_quote": r.evidence.get("pr_quote"),
            "feature_quote": r.evidence.get("feature_quote"),
            "suggestion_id": r.id,
            **({"verified_by": r.decided_by} if r.decided_by else {}),
        }
        out.append(
            LinkCandidate(pair[0], pair[1], LinkMethod.AI_SUGGESTED, status, confidence, evidence)
        )
    return out


def decided(
    row: LinkSuggestion, confirm: bool, by: str, note: str | None, now: datetime
) -> LinkSuggestion:
    """The row after a decision, or ``SuggestionError``."""
    if row.status not in DECIDABLE:
        raise SuggestionError(
            f"suggestion {row.id} is {row.status.value}; only suggested can be decided"
        )
    status = SuggestionStatus.CONFIRMED if confirm else SuggestionStatus.REJECTED
    return replace(row, status=status, decided_by=by, decided_at=now, decision_note=note)


class LinkSuggestionStore(Protocol):
    """Persistence for link suggestions."""

    def seen(self, release_key: str) -> set[tuple[str, str, str]]:
        """(PR key, input SHA, prompt version) already processed."""
        ...

    def save(self, row: LinkSuggestion) -> LinkSuggestion:
        """Insert; returns the row with its id."""
        ...

    def list(
        self, release_key: str, status: SuggestionStatus | None = None
    ) -> list[LinkSuggestion]:
        """Rows for a release, newest first."""
        ...

    def get(self, release_key: str, suggestion_id: int) -> LinkSuggestion | None:
        """One row."""
        ...

    def decide(
        self,
        release_key: str,
        suggestion_id: int,
        *,
        confirm: bool,
        by: str,
        note: str | None = None,
    ) -> LinkSuggestion:
        """Confirm or reject a suggested row."""
        ...


class MemoryLinkSuggestionStore:
    """For tests."""

    def __init__(self) -> None:
        self.rows: list[LinkSuggestion] = []
        self._lock = threading.Lock()

    def seen(self, release_key: str) -> set[tuple[str, str, str]]:
        return {
            (r.pull_request_key, r.input_sha, r.prompt_version)
            for r in self.rows
            if r.release_key == release_key
        }

    def save(self, row: LinkSuggestion) -> LinkSuggestion:
        with self._lock:
            saved = replace(row, id=len(self.rows) + 1)
            self.rows.append(saved)
            return saved

    def list(
        self, release_key: str, status: SuggestionStatus | None = None
    ) -> list[LinkSuggestion]:
        found = [
            r
            for r in self.rows
            if r.release_key == release_key and (status is None or r.status is status)
        ]
        return sorted(found, key=lambda r: -(r.id or 0))

    def get(self, release_key: str, suggestion_id: int) -> LinkSuggestion | None:
        return next(
            (r for r in self.rows if r.id == suggestion_id and r.release_key == release_key), None
        )

    def decide(
        self,
        release_key: str,
        suggestion_id: int,
        *,
        confirm: bool,
        by: str,
        note: str | None = None,
    ) -> LinkSuggestion:
        with self._lock:
            row = self.get(release_key, suggestion_id)
            if row is None:
                raise KeyError(suggestion_id)
            new = decided(row, confirm, by, note, datetime.now(UTC))
            self.rows[self.rows.index(row)] = new
            return new


class PostgresLinkSuggestionStore:
    """``link_suggestions`` table (migration 0005)."""

    def __init__(self, session_factory: Any) -> None:
        self._sessions = session_factory

    @staticmethod
    def _from(rec: Any) -> LinkSuggestion:
        return LinkSuggestion(
            id=rec.id,
            release_key=rec.release_key,
            pull_request_key=rec.pull_request_key,
            feature_key=rec.feature_key,
            status=SuggestionStatus(rec.status),
            evidence=rec.evidence,
            input_sha=rec.input_sha,
            prompt_version=rec.prompt_version,
            model=rec.model,
            cost_usd=float(rec.cost_usd),
            decided_by=rec.decided_by,
            decided_at=rec.decided_at,
            decision_note=rec.decision_note,
            created_at=rec.created_at,
        )

    def seen(self, release_key: str) -> set[tuple[str, str, str]]:
        from sqlalchemy import select

        from pipeline.store.models import LinkSuggestionRecord as R

        with self._sessions() as s:
            rows = s.execute(
                select(R.pull_request_key, R.input_sha, R.prompt_version).where(
                    R.release_key == release_key
                )
            ).all()
        return {(a, b, c) for a, b, c in rows}

    def save(self, row: LinkSuggestion) -> LinkSuggestion:
        from pipeline.store.models import LinkSuggestionRecord as R

        with self._sessions() as s, s.begin():
            rec = R(
                release_key=row.release_key,
                pull_request_key=row.pull_request_key,
                feature_key=row.feature_key,
                status=row.status.value,
                evidence=row.evidence,
                input_sha=row.input_sha,
                prompt_version=row.prompt_version,
                model=row.model,
                cost_usd=Decimal(str(round(row.cost_usd, 6))),
                created_at=row.created_at,
            )
            s.add(rec)
            s.flush()
            return replace(row, id=rec.id)

    def list(
        self, release_key: str, status: SuggestionStatus | None = None
    ) -> list[LinkSuggestion]:
        from sqlalchemy import select

        from pipeline.store.models import LinkSuggestionRecord as R

        q = select(R).where(R.release_key == release_key)
        if status is not None:
            q = q.where(R.status == status.value)
        with self._sessions() as s:
            return [self._from(r) for r in s.scalars(q.order_by(R.id.desc()))]

    def get(self, release_key: str, suggestion_id: int) -> LinkSuggestion | None:
        from pipeline.store.models import LinkSuggestionRecord as R

        with self._sessions() as s:
            rec = s.get(R, suggestion_id)
            return self._from(rec) if rec is not None and rec.release_key == release_key else None

    def decide(
        self,
        release_key: str,
        suggestion_id: int,
        *,
        confirm: bool,
        by: str,
        note: str | None = None,
    ) -> LinkSuggestion:
        from pipeline.store.models import LinkSuggestionRecord as R

        with self._sessions() as s, s.begin():
            rec = s.get(R, suggestion_id, with_for_update=True)
            if rec is None or rec.release_key != release_key:
                raise KeyError(suggestion_id)
            new = decided(self._from(rec), confirm, by, note, datetime.now(UTC))
            rec.status = new.status.value
            rec.decided_by = new.decided_by
            rec.decided_at = new.decided_at
            rec.decision_note = new.decision_note
            return new
