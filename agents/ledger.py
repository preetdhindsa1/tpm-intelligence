"""Where AI spend and cached results live: Postgres in services, in-memory in tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Protocol

from agents.pricing import TokenUsage


@dataclass(frozen=True)
class UsageRecord:
    """One call attempt, as written to ``ai_usage``."""

    task: str
    prompt_version: str
    model_requested: str
    essential: bool
    outcome: str  # ok | refused | max_tokens | error | budget_denied | cache_hit
    fingerprint: str
    usages: tuple[TokenUsage, ...] = ()
    model_served: str | None = None
    request_id: str | None = None
    detail: str | None = None
    at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def cost_usd(self) -> float:
        """Sum over every model billed in this call."""
        return sum(u.cost_usd for u in self.usages)


@dataclass(frozen=True)
class CachedResult:
    """A stored structured output."""

    fingerprint: str
    output: dict[str, Any]
    check_counts: dict[str, Any] | None


class Ledger(Protocol):
    """Budget and cache storage used by the gateway."""

    def spent_today(self, now: datetime) -> float:
        """USD spent since 00:00 UTC."""
        ...

    def last_nonessential_at(self, now: datetime) -> datetime | None:
        """Time of today's latest non-essential paid call."""
        ...

    def record(self, rec: UsageRecord) -> None:
        """Append one usage record."""
        ...

    def get_result(self, fingerprint: str) -> CachedResult | None:
        """Cached output for a fingerprint."""
        ...

    def put_result(
        self,
        fingerprint: str,
        *,
        task: str,
        prompt_version: str,
        model: str,
        output: dict[str, Any],
    ) -> None:
        """Store an output (first write wins)."""
        ...

    def set_check_counts(self, fingerprint: str, counts: dict[str, Any]) -> None:
        """Attach fact-check counts to a cached output."""
        ...


def day_start(now: datetime) -> datetime:
    """00:00 UTC of ``now``'s day."""
    return datetime.combine(now.astimezone(UTC).date(), time(), tzinfo=UTC)


_PAID = ("ok", "refused", "max_tokens", "error")


class MemoryLedger:
    """In-process ledger for tests and offline runs."""

    def __init__(self) -> None:
        self.records: list[UsageRecord] = []
        self.results: dict[str, CachedResult] = {}

    def spent_today(self, now: datetime) -> float:
        start = day_start(now)
        return sum(r.cost_usd for r in self.records if start <= r.at < start + timedelta(days=1))

    def last_nonessential_at(self, now: datetime) -> datetime | None:
        start = day_start(now)
        times = [
            r.at for r in self.records if not r.essential and r.outcome in _PAID and r.at >= start
        ]
        return max(times, default=None)

    def record(self, rec: UsageRecord) -> None:
        self.records.append(rec)

    def get_result(self, fingerprint: str) -> CachedResult | None:
        return self.results.get(fingerprint)

    def put_result(
        self,
        fingerprint: str,
        *,
        task: str,
        prompt_version: str,
        model: str,
        output: dict[str, Any],
    ) -> None:
        self.results.setdefault(fingerprint, CachedResult(fingerprint, output, None))

    def set_check_counts(self, fingerprint: str, counts: dict[str, Any]) -> None:
        if fingerprint in self.results:
            old = self.results[fingerprint]
            self.results[fingerprint] = CachedResult(fingerprint, old.output, counts)


class PostgresLedger:
    """``ai_usage`` / ``ai_results`` tables (migration 0002)."""

    def __init__(self, session_factory: Any) -> None:
        self._sessions = session_factory

    def spent_today(self, now: datetime) -> float:
        from sqlalchemy import func, select

        from pipeline.store.models import AIUsage

        start = day_start(now)
        with self._sessions() as s:
            total = s.scalar(
                select(func.coalesce(func.sum(AIUsage.cost_usd), 0)).where(
                    AIUsage.at >= start, AIUsage.at < start + timedelta(days=1)
                )
            )
        return float(total or 0)

    def last_nonessential_at(self, now: datetime) -> datetime | None:
        from sqlalchemy import func, select

        from pipeline.store.models import AIUsage

        with self._sessions() as s:
            result: datetime | None = s.scalar(
                select(func.max(AIUsage.at)).where(
                    AIUsage.at >= day_start(now),
                    AIUsage.essential.is_(False),
                    AIUsage.outcome.in_(_PAID),
                )
            )
        return result

    def record(self, rec: UsageRecord) -> None:
        from pipeline.store.models import AIUsage

        tokens = {
            "input_tokens": sum(u.input_tokens for u in rec.usages),
            "output_tokens": sum(u.output_tokens for u in rec.usages),
            "cache_read_tokens": sum(u.cache_read_tokens for u in rec.usages),
            "cache_write_tokens": sum(u.cache_write_tokens for u in rec.usages),
        }
        with self._sessions() as s, s.begin():
            s.add(
                AIUsage(
                    at=rec.at,
                    task=rec.task,
                    prompt_version=rec.prompt_version,
                    model_requested=rec.model_requested,
                    model_served=rec.model_served,
                    essential=rec.essential,
                    outcome=rec.outcome,
                    cost_usd=Decimal(str(round(rec.cost_usd, 6))),
                    fingerprint=rec.fingerprint,
                    request_id=rec.request_id,
                    detail=rec.detail,
                    **tokens,
                )
            )

    def get_result(self, fingerprint: str) -> CachedResult | None:
        from sqlalchemy import select

        from pipeline.store.models import AIResult

        with self._sessions() as s:  # the session's tenant scopes the cache (ADR-0034)
            row = s.scalars(select(AIResult).where(AIResult.fingerprint == fingerprint)).first()
            return None if row is None else CachedResult(fingerprint, row.output, row.check_counts)

    def put_result(
        self,
        fingerprint: str,
        *,
        task: str,
        prompt_version: str,
        model: str,
        output: dict[str, Any],
    ) -> None:
        from sqlalchemy.dialects.postgresql import insert

        from pipeline.store.models import AIResult

        stmt = (
            insert(AIResult)
            .values(
                fingerprint=fingerprint,
                task=task,
                prompt_version=prompt_version,
                model=model,
                output=output,
            )
            .on_conflict_do_nothing(index_elements=["tenant_id", "fingerprint"])
        )
        with self._sessions() as s, s.begin():
            s.execute(stmt)

    def set_check_counts(self, fingerprint: str, counts: dict[str, Any]) -> None:
        from sqlalchemy import update

        from pipeline.store.models import AIResult

        with self._sessions() as s, s.begin():
            s.execute(
                update(AIResult)
                .where(AIResult.fingerprint == fingerprint)
                .values(check_counts=counts)
            )
