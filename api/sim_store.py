"""Stored simulator calibrations and saved scenarios (ADR-0012, migration 0006)."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from simulator.scenario import Calibration, calibration_from_json, calibration_to_json


class ScenarioExistsError(Exception):
    """A scenario with this name is already saved for the release."""


@dataclass(frozen=True)
class StoredCalibration:
    """A calibration and its row id."""

    id: int
    calibration: Calibration
    created_at: datetime


@dataclass(frozen=True)
class SavedScenario:
    """A named scenario, its settings and its result when it was saved."""

    id: int
    release_key: str
    calibration_id: int
    name: str
    settings: dict[str, Any]
    result: dict[str, Any]
    created_by: str
    created_at: datetime


class SimStore(Protocol):
    """Where calibrations and scenarios are kept."""

    def save_calibration(self, cal: Calibration) -> StoredCalibration: ...
    def latest_calibration(self, release_key: str) -> StoredCalibration | None: ...
    def save_scenario(
        self,
        release_key: str,
        calibration_id: int,
        name: str,
        settings: dict[str, Any],
        result: dict[str, Any],
        created_by: str,
    ) -> SavedScenario: ...
    def list_scenarios(self, release_key: str) -> list[SavedScenario]: ...
    def get_scenario(self, release_key: str, scenario_id: int) -> SavedScenario | None: ...


@dataclass
class MemorySimStore:
    """For tests and demos."""

    calibrations: list[StoredCalibration] = field(default_factory=list)
    scenarios: list[SavedScenario] = field(default_factory=list)
    _ids: itertools.count[int] = field(default_factory=lambda: itertools.count(1))

    def save_calibration(self, cal: Calibration) -> StoredCalibration:
        row = StoredCalibration(next(self._ids), cal, datetime.now(UTC))
        self.calibrations.append(row)
        return row

    def latest_calibration(self, release_key: str) -> StoredCalibration | None:
        rows = [c for c in self.calibrations if c.calibration.release_key == release_key]
        return rows[-1] if rows else None

    def save_scenario(
        self,
        release_key: str,
        calibration_id: int,
        name: str,
        settings: dict[str, Any],
        result: dict[str, Any],
        created_by: str,
    ) -> SavedScenario:
        if any(s.release_key == release_key and s.name == name for s in self.scenarios):
            raise ScenarioExistsError(name)
        row = SavedScenario(
            next(self._ids),
            release_key,
            calibration_id,
            name,
            settings,
            result,
            created_by,
            datetime.now(UTC),
        )
        self.scenarios.append(row)
        return row

    def list_scenarios(self, release_key: str) -> list[SavedScenario]:
        return [s for s in reversed(self.scenarios) if s.release_key == release_key]

    def get_scenario(self, release_key: str, scenario_id: int) -> SavedScenario | None:
        return next(
            (s for s in self.scenarios if s.id == scenario_id and s.release_key == release_key),
            None,
        )


class PostgresSimStore:
    """``sim_calibrations`` and ``sim_scenarios`` tables."""

    def __init__(self, session_factory: Any) -> None:
        self._sessions = session_factory

    def save_calibration(self, cal: Calibration) -> StoredCalibration:
        from pipeline.store.models import SimCalibrationRecord as R

        with self._sessions() as s, s.begin():
            rec = R(
                release_key=cal.release_key,
                source_releases=list(cal.inputs.source_releases),
                measured_at=cal.inputs.measured_at,
                validated=cal.validated,
                body=calibration_to_json(cal),
            )
            s.add(rec)
            s.flush()
            return StoredCalibration(rec.id, cal, rec.created_at or datetime.now(UTC))

    def latest_calibration(self, release_key: str) -> StoredCalibration | None:
        from sqlalchemy import select

        from pipeline.store.models import SimCalibrationRecord as R

        with self._sessions() as s:
            rec = s.scalars(
                select(R).where(R.release_key == release_key).order_by(R.id.desc()).limit(1)
            ).first()
            if rec is None:
                return None
            return StoredCalibration(rec.id, calibration_from_json(rec.body), rec.created_at)

    @staticmethod
    def _from(rec: Any) -> SavedScenario:
        return SavedScenario(
            rec.id,
            rec.release_key,
            rec.calibration_id,
            rec.name,
            rec.settings,
            rec.result,
            rec.created_by,
            rec.created_at,
        )

    def save_scenario(
        self,
        release_key: str,
        calibration_id: int,
        name: str,
        settings: dict[str, Any],
        result: dict[str, Any],
        created_by: str,
    ) -> SavedScenario:
        from sqlalchemy.exc import IntegrityError

        from pipeline.store.models import SimScenarioRecord as R

        try:
            with self._sessions() as s, s.begin():
                rec = R(
                    release_key=release_key,
                    calibration_id=calibration_id,
                    name=name,
                    settings=settings,
                    result=result,
                    created_by=created_by,
                )
                s.add(rec)
                s.flush()
                s.refresh(rec)
                return self._from(rec)
        except IntegrityError as exc:
            raise ScenarioExistsError(name) from exc

    def list_scenarios(self, release_key: str) -> list[SavedScenario]:
        from sqlalchemy import select

        from pipeline.store.models import SimScenarioRecord as R

        with self._sessions() as s:
            q = select(R).where(R.release_key == release_key).order_by(R.id.desc())
            return [self._from(r) for r in s.scalars(q)]

    def get_scenario(self, release_key: str, scenario_id: int) -> SavedScenario | None:
        from pipeline.store.models import SimScenarioRecord as R

        with self._sessions() as s:
            rec = s.get(R, scenario_id)
            return self._from(rec) if rec is not None and rec.release_key == release_key else None
