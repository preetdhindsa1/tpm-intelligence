"""Executive updates: stored drafts and their approval state (M3b)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from verify.claims import Claim
from verify.facts import FactSheet


class UpdateStatus(StrEnum):
    """Lifecycle. The platform never sends anything: approval only marks it ready to copy."""

    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ClaimWarning:
    """An edited claim that no longer passes the fact checker."""

    section: str
    text: str
    reason: str
    detail: str | None


@dataclass(frozen=True)
class ExecUpdate:
    """One executive update with everything needed to audit it."""

    release_key: str
    as_of: datetime
    header: dict[str, Any]  # computed by code, never by AI
    sections: dict[str, list[Claim]]  # verified (or TPM-edited) claims per section
    facts: FactSheet
    counts: dict[str, int]  # fact-check counts of the shown attempt
    removed: list[dict[str, Any]]  # removed claims with reasons (audit trail)
    attempts: int
    model: str
    prompt_version: str
    cost_usd: float
    trimmed_for_length: int = 0
    status: UpdateStatus = UpdateStatus.DRAFT
    edited: bool = False
    warnings: list[ClaimWarning] = field(default_factory=list)
    decided_by: str | None = None
    decided_at: datetime | None = None
    decision_note: str | None = None
    approved_with_warnings: bool = False
    approved_while_stale: bool = False
    id: int | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def word_count(self) -> int:
        """Words in the shown claims (the header is not counted)."""
        return sum(len(c.text.split()) for claims in self.sections.values() for c in claims)


class UpdateStore(Protocol):
    """Persistence for executive updates."""

    def add(self, update: ExecUpdate) -> ExecUpdate:
        """Insert and return with its id."""
        ...

    def get(self, update_id: int) -> ExecUpdate | None:
        """One update."""
        ...

    def list(self, release_key: str) -> list[ExecUpdate]:
        """Newest first."""
        ...

    def save(self, update: ExecUpdate) -> None:
        """Replace an existing update."""
        ...


class MemoryUpdateStore:
    """For tests."""

    def __init__(self) -> None:
        self.items: dict[int, ExecUpdate] = {}

    def add(self, update: ExecUpdate) -> ExecUpdate:
        stored = replace(update, id=len(self.items) + 1)
        self.items[stored.id] = stored  # type: ignore[index]
        return stored

    def get(self, update_id: int) -> ExecUpdate | None:
        return self.items.get(update_id)

    def list(self, release_key: str) -> list[ExecUpdate]:
        return sorted(
            (u for u in self.items.values() if u.release_key == release_key),
            key=lambda u: u.id or 0,
            reverse=True,
        )

    def save(self, update: ExecUpdate) -> None:
        assert update.id is not None  # noqa: S101 - programming error, not input
        self.items[update.id] = update


def _claims_json(sections: dict[str, list[Claim]]) -> dict[str, list[dict[str, Any]]]:
    return {name: [c.model_dump(mode="json") for c in claims] for name, claims in sections.items()}


def _claims_from(data: dict[str, list[dict[str, Any]]]) -> dict[str, list[Claim]]:
    return {name: [Claim.model_validate(c) for c in claims] for name, claims in data.items()}


class PostgresUpdateStore:
    """``exec_updates`` table (migration 0004)."""

    def __init__(self, session_factory: Any) -> None:
        self._sessions = session_factory

    @staticmethod
    def _to_update(row: Any) -> ExecUpdate:
        return ExecUpdate(
            id=row.id,
            release_key=row.release_key,
            as_of=row.as_of,
            header=row.header,
            sections=_claims_from(row.sections),
            facts=FactSheet.from_records(row.facts),
            counts=row.counts,
            removed=row.removed,
            attempts=row.attempts,
            model=row.model,
            prompt_version=row.prompt_version,
            cost_usd=float(row.cost_usd),
            trimmed_for_length=row.trimmed_for_length,
            status=UpdateStatus(row.status),
            edited=row.edited,
            warnings=[ClaimWarning(**w) for w in row.warnings],
            decided_by=row.decided_by,
            decided_at=row.decided_at,
            decision_note=row.decision_note,
            approved_with_warnings=row.approved_with_warnings,
            approved_while_stale=row.approved_while_stale,
            created_at=row.created_at,
        )

    @staticmethod
    def _fields(u: ExecUpdate) -> dict[str, Any]:
        from decimal import Decimal

        return {
            "release_key": u.release_key,
            "as_of": u.as_of,
            "header": u.header,
            "sections": _claims_json(u.sections),
            "facts": u.facts.to_records(),
            "counts": u.counts,
            "removed": u.removed,
            "attempts": u.attempts,
            "model": u.model,
            "prompt_version": u.prompt_version,
            "cost_usd": Decimal(str(round(u.cost_usd, 6))),
            "trimmed_for_length": u.trimmed_for_length,
            "status": u.status.value,
            "edited": u.edited,
            "warnings": [w.__dict__ for w in u.warnings],
            "decided_by": u.decided_by,
            "decided_at": u.decided_at,
            "decision_note": u.decision_note,
            "approved_with_warnings": u.approved_with_warnings,
            "approved_while_stale": u.approved_while_stale,
            "created_at": u.created_at,
        }

    def add(self, update: ExecUpdate) -> ExecUpdate:
        from pipeline.store.models import ExecUpdateRecord

        with self._sessions() as s, s.begin():
            row = ExecUpdateRecord(**self._fields(update))
            s.add(row)
            s.flush()
            return replace(update, id=row.id)

    def get(self, update_id: int) -> ExecUpdate | None:
        from pipeline.store.models import ExecUpdateRecord

        with self._sessions() as s:
            row = s.get(ExecUpdateRecord, update_id)
            return None if row is None else self._to_update(row)

    def list(self, release_key: str) -> list[ExecUpdate]:
        from sqlalchemy import select

        from pipeline.store.models import ExecUpdateRecord

        with self._sessions() as s:
            rows = s.scalars(
                select(ExecUpdateRecord)
                .where(ExecUpdateRecord.release_key == release_key)
                .order_by(ExecUpdateRecord.id.desc())
                .limit(20)
            ).all()
            return [self._to_update(r) for r in rows]

    def save(self, update: ExecUpdate) -> None:
        from sqlalchemy import update as sql_update

        from pipeline.store.models import ExecUpdateRecord

        with self._sessions() as s, s.begin():
            s.execute(
                sql_update(ExecUpdateRecord)
                .where(ExecUpdateRecord.id == update.id)
                .values(**self._fields(update))
            )
