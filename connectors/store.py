"""Team configs per tenant (ADR-0035, #233). The public demo reads YAML; others read here.

Every body is validated by ``TeamConfig`` on write and again on read, so the database never
holds a config the YAML loader would refuse. Writes bump ``version``; the audit log (#234)
keeps the previous body.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from connectors.schema import TeamConfig


@dataclass(frozen=True)
class StoredTeam:
    config: TeamConfig
    version: int
    updated_at: datetime


class TeamConfigStore(Protocol):
    def list(self) -> list[StoredTeam]: ...
    def put(self, body: dict[str, Any]) -> StoredTeam: ...
    def delete(self, team_id: str) -> bool: ...


def _validated(body: dict[str, Any], team_id: str | None = None) -> TeamConfig:
    config = TeamConfig.model_validate(body)
    if team_id is not None and config.id != team_id:
        raise ValueError(f"config id {config.id!r} does not match {team_id!r}")
    return config


@dataclass
class MemoryTeamConfigStore:
    """For tests: one tenant's configs in memory."""

    rows: dict[str, StoredTeam] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def list(self) -> list[StoredTeam]:
        with self._lock:
            return [self.rows[k] for k in sorted(self.rows)]

    def put(self, body: dict[str, Any]) -> StoredTeam:
        config = _validated(body)
        with self._lock:
            old = self.rows.get(config.id)
            row = StoredTeam(config, (old.version + 1) if old else 1, datetime.now(UTC))
            self.rows[config.id] = row
            return row

    def delete(self, team_id: str) -> bool:
        with self._lock:
            return self.rows.pop(team_id, None) is not None


class PostgresTeamConfigStore:
    """``team_configs`` for the session's tenant (row-level security picks the rows)."""

    def __init__(self, sessions: Any) -> None:
        self._sessions = sessions

    def list(self) -> list[StoredTeam]:
        from sqlalchemy import select

        from pipeline.store.models import TeamConfigRecord as R

        with self._sessions() as s:
            rows = s.scalars(select(R).order_by(R.team_id)).all()
            return [StoredTeam(_validated(r.config, r.team_id), r.version, r.updated_at)
                    for r in rows]  # fmt: skip

    def put(self, body: dict[str, Any]) -> StoredTeam:
        from sqlalchemy import func, select

        from pipeline.store.models import TeamConfigRecord as R

        config = _validated(body)
        stored = config.model_dump(mode="json")
        with self._sessions() as s, s.begin():
            row = s.scalars(select(R).where(R.team_id == config.id).with_for_update()).first()
            if row is None:
                row = R(team_id=config.id, config=stored, version=1)
                s.add(row)
            else:
                row.config, row.version, row.updated_at = stored, row.version + 1, func.now()
            s.flush()
            s.refresh(row)
            return StoredTeam(config, row.version, row.updated_at)

    def delete(self, team_id: str) -> bool:
        from sqlalchemy import delete

        from pipeline.store.models import TeamConfigRecord as R

        with self._sessions() as s, s.begin():
            return bool(s.execute(delete(R).where(R.team_id == team_id)).rowcount)
