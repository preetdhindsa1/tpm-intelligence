"""Stored risk notes: the verified claims shown on a feature page (M3a)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from verify.claims import Claim
from verify.facts import FactSheet


@dataclass(frozen=True)
class RiskNote:
    """Verified claims for one feature, with the facts they were checked against."""

    release_key: str
    feature_key: str
    prompt_version: str
    model: str
    facts: FactSheet
    claims: tuple[Claim, ...]
    counts: dict[str, int]  # best attempt's fact-check counts
    attempts: int
    cost_usd: float
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class NoteStore(Protocol):
    """Persistence for risk notes."""

    def latest(self, release_key: str, feature_key: str) -> RiskNote | None:
        """Most recent note for a feature in a release."""
        ...

    def save(self, note: RiskNote) -> None:
        """Append a note."""
        ...


class MemoryNoteStore:
    """For tests."""

    def __init__(self) -> None:
        self.notes: list[RiskNote] = []

    def latest(self, release_key: str, feature_key: str) -> RiskNote | None:
        found = [
            n for n in self.notes if (n.release_key, n.feature_key) == (release_key, feature_key)
        ]
        return found[-1] if found else None

    def save(self, note: RiskNote) -> None:
        self.notes.append(note)


class PostgresNoteStore:
    """``risk_notes`` table (migration 0003)."""

    def __init__(self, session_factory: Any) -> None:
        self._sessions = session_factory

    def latest(self, release_key: str, feature_key: str) -> RiskNote | None:
        from sqlalchemy import select

        from pipeline.store.models import RiskNoteRecord

        with self._sessions() as s:
            row = s.scalars(
                select(RiskNoteRecord)
                .where(
                    RiskNoteRecord.release_key == release_key,
                    RiskNoteRecord.feature_key == feature_key,
                )
                .order_by(RiskNoteRecord.id.desc())
                .limit(1)
            ).first()
            if row is None:
                return None
            return RiskNote(
                release_key=row.release_key,
                feature_key=row.feature_key,
                prompt_version=row.prompt_version,
                model=row.model,
                facts=FactSheet.from_records(row.facts),
                claims=tuple(Claim.model_validate(c) for c in row.claims),
                counts=row.counts,
                attempts=row.attempts,
                cost_usd=float(row.cost_usd),
                created_at=row.created_at,
            )

    def save(self, note: RiskNote) -> None:
        from decimal import Decimal

        from pipeline.store.models import RiskNoteRecord

        with self._sessions() as s, s.begin():
            s.add(
                RiskNoteRecord(
                    release_key=note.release_key,
                    feature_key=note.feature_key,
                    prompt_version=note.prompt_version,
                    model=note.model,
                    facts=note.facts.to_records(),
                    claims=[c.model_dump(mode="json") for c in note.claims],
                    counts=note.counts,
                    attempts=note.attempts,
                    cost_usd=Decimal(str(round(note.cost_usd, 6))),
                    created_at=note.created_at,
                )
            )
