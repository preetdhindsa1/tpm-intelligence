"""The go/no-go decision log (ADR-0032). Rows are only ever appended, never changed.

A decision records what the rules said (``verdict``) and when those facts were computed
(``facts_as_of``), so a later reader sees what the person saw. ``by`` is kept for audit
and never returned by the API, which shows the role.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pipeline.store.models import ReadinessDecisionRecord as D

DecisionKind = Literal["go", "no_go", "defer"]


@dataclass(frozen=True)
class Decision:
    release_key: str
    decision: DecisionKind
    note: str
    decided_at: datetime
    facts_as_of: datetime
    verdict: str
    by: str

    def __post_init__(self) -> None:
        if self.decision not in ("go", "no_go", "defer"):
            raise ValueError(f"unknown decision {self.decision!r}")
        if len(self.note.strip()) < 3:
            raise ValueError("a decision needs a note")


class DecisionLog(Protocol):
    def append(self, decision: Decision) -> Decision: ...
    def list(self, release_key: str) -> list[Decision]: ...


@dataclass
class MemoryDecisionLog:
    """In-process log for tests and the database-free demo."""

    rows: list[Decision] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def append(self, decision: Decision) -> Decision:
        with self._lock:
            self.rows.append(decision)
        return decision

    def list(self, release_key: str) -> list[Decision]:
        with self._lock:
            return [d for d in self.rows if d.release_key == release_key]


class PostgresDecisionLog:
    """``readiness_decisions``; a trigger refuses UPDATE and DELETE (migration 0011)."""

    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def append(self, decision: Decision) -> Decision:
        with self._sessions() as s, s.begin():
            s.add(D(release_key=decision.release_key, decision=decision.decision,
                    note=decision.note.strip(), decided_at=decision.decided_at,
                    facts_as_of=decision.facts_as_of, verdict=decision.verdict,
                    by_login=decision.by))  # fmt: skip
        return decision

    def list(self, release_key: str) -> list[Decision]:
        with self._sessions() as s:
            rows = s.scalars(select(D).where(D.release_key == release_key).order_by(D.id))
            return [Decision(r.release_key, r.decision, r.note, r.decided_at,  # type: ignore[arg-type]
                             r.facts_as_of, r.verdict, r.by_login) for r in rows]  # fmt: skip
