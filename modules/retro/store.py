"""Stored retro runs (migration 0012). Rows are only ever appended; readers take the latest."""

from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from modules.retro.facts import DayFacts, FeatureRow, RetroRun, Slip
from pipeline.store.models import RetroRunRecord as R


def _json(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_json(v) for v in value]
    return value


def to_body(run: RetroRun) -> dict[str, Any]:
    """JSON-ready run."""
    return dict(_json(asdict(run)))


def _dt(v: str | None) -> datetime | None:
    return datetime.fromisoformat(v) if v else None


def from_body(b: dict[str, Any]) -> RetroRun:
    """The run back from its JSON body."""
    slips = tuple(
        Slip(
            **{
                **s,
                "slipped_at": _dt(s["slipped_at"]),
                "first_warning_at": _dt(s["first_warning_at"]),
            }
        )
        for s in b["slips"]
    )
    days = tuple(DayFacts(**{**d, "at": _dt(d["at"])}) for d in b["days"])
    rows = tuple(FeatureRow(**{**r, "flags_seen": tuple(r["flags_seen"])}) for r in b["features"])
    computed, cutoff = datetime.fromisoformat(b["computed_at"]), datetime.fromisoformat(b["cutoff"])
    return RetroRun(b["release_key"], computed, cutoff, b["model_version"], b["planned"], slips,
                    b["warned_landed"], days, rows)  # fmt: skip


class RetroStore(Protocol):
    def add(self, run: RetroRun) -> None: ...
    def latest(self, release_key: str) -> RetroRun | None: ...
    def latest_all(self) -> list[RetroRun]: ...


@dataclass
class MemoryRetroStore:
    runs: list[RetroRun] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def add(self, run: RetroRun) -> None:
        with self._lock:
            self.runs.append(from_body(to_body(run)))  # same round trip as Postgres

    def latest(self, release_key: str) -> RetroRun | None:
        with self._lock:
            return next((r for r in reversed(self.runs) if r.release_key == release_key), None)

    def latest_all(self) -> list[RetroRun]:
        with self._lock:
            return list({r.release_key: r for r in self.runs}.values())


class PostgresRetroStore:
    """``retro_runs``; a trigger refuses UPDATE and DELETE."""

    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def add(self, run: RetroRun) -> None:
        with self._sessions() as s, s.begin():
            s.add(R(release_key=run.release_key, computed_at=run.computed_at,
                    model_version=run.model_version, body=to_body(run)))  # fmt: skip

    def latest(self, release_key: str) -> RetroRun | None:
        with self._sessions() as s:
            rec = s.scalars(select(R).where(R.release_key == release_key)
                            .order_by(R.id.desc()).limit(1)).first()  # fmt: skip
            return from_body(rec.body) if rec else None

    def latest_all(self) -> list[RetroRun]:
        with self._sessions() as s:
            recs = s.scalars(select(R).order_by(R.id)).all()
            return [from_body(b) for b in {r.release_key: r.body for r in recs}.values()]
