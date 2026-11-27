"""Incremental-sync cursors with poll health (feeds the "2 failed polls in a row" alert)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from pipeline.store.models import SyncCursor
from pipeline.store.session import session_scope


@dataclass(frozen=True)
class StreamHealth:
    """One stream's sync health, without its error text (it may hold URLs; ADR-0036)."""

    stream: str
    last_success_at: datetime | None
    consecutive_failures: int


class CursorStore(Protocol):
    """Where collectors keep their position per stream."""

    def get(self, stream: str) -> str | None:
        """Current cursor, or None if never synced."""
        ...

    def record_success(self, stream: str, cursor: str | None, at: datetime) -> None:
        """Advance the cursor and reset the failure count."""
        ...

    def record_failure(self, stream: str, error: str, at: datetime) -> int:
        """Keep the cursor, count the failure; return consecutive failures."""
        ...


@dataclass
class InMemoryCursorStore:
    """For tests and dry runs."""

    cursors: dict[str, str | None] = field(default_factory=dict)
    failures: dict[str, int] = field(default_factory=dict)
    successes: dict[str, datetime] = field(default_factory=dict)

    def get(self, stream: str) -> str | None:
        """Current cursor."""
        return self.cursors.get(stream)

    def record_success(self, stream: str, cursor: str | None, at: datetime) -> None:
        """Advance and reset failures."""
        self.cursors[stream] = cursor
        self.failures[stream] = 0
        self.successes[stream] = at

    def record_failure(self, stream: str, error: str, at: datetime) -> int:
        """Count a failure."""
        self.failures[stream] = self.failures.get(stream, 0) + 1
        return self.failures[stream]

    def health(self) -> list[StreamHealth]:
        """Every stream seen."""
        streams = sorted({*self.failures, *self.successes})
        return [StreamHealth(s, self.successes.get(s), self.failures.get(s, 0)) for s in streams]


class PostgresCursorStore:
    """``sync_cursors`` table; each call is its own short transaction."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def get(self, stream: str) -> str | None:
        """Current cursor."""
        with session_scope(self._factory) as session:
            return session.scalar(select(SyncCursor.cursor).where(SyncCursor.stream == stream))

    def record_success(self, stream: str, cursor: str | None, at: datetime) -> None:
        """Advance the cursor and reset failures."""
        values = {
            "stream": stream,
            "cursor": cursor,
            "last_attempt_at": at,
            "last_success_at": at,
            "consecutive_failures": 0,
            "last_error": None,
        }
        stmt = insert(SyncCursor).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[SyncCursor.tenant_id, SyncCursor.stream],
            set_={k: stmt.excluded[k] for k in values if k != "stream"},
        )
        with session_scope(self._factory) as session:
            session.execute(stmt)

    def record_failure(self, stream: str, error: str, at: datetime) -> int:
        """Keep the cursor; increment and return the failure count."""
        base = insert(SyncCursor).values(
            stream=stream, last_attempt_at=at, consecutive_failures=1, last_error=error[:2000]
        )
        stmt = base.on_conflict_do_update(
            index_elements=[SyncCursor.tenant_id, SyncCursor.stream],
            set_={
                "last_attempt_at": at,
                "last_error": error[:2000],
                "consecutive_failures": SyncCursor.consecutive_failures + 1,
            },
        ).returning(SyncCursor.consecutive_failures)
        with session_scope(self._factory) as session:
            return int(session.execute(stmt).scalar_one())

    def health(self) -> list[StreamHealth]:
        """Every stream of the current tenant (row-level security), for freshness."""
        cols = (SyncCursor.stream, SyncCursor.last_success_at, SyncCursor.consecutive_failures)
        with session_scope(self._factory) as session:
            return [StreamHealth(*row) for row in session.execute(select(*cols)).all()]
