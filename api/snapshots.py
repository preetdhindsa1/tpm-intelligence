"""Forecast snapshots: a daily, append-only record of every forecast (ADR-0015).

Each day, the current release's odds and merge-date forecasts are stored with the model
version, settings, calibration inputs and validation labels. Rows are never updated or
deleted (a Postgres trigger refuses it), so when the release finishes it can be scored on
exactly what was predicted at the time. Those predictions were made before the outcome
existed, so they are a fair, unseen test.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Protocol

import numpy as np

from engine.forecast import DEFAULT_FORECAST, ForecastConfig, model_version
from engine.merge_date import TAIL

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeatureSnapshot:
    """One feature's recorded forecast."""

    feature_key: str
    in_release: bool
    odds_status: str
    probability: float | None
    low: float | None
    high: float | None
    raw_probability: float | None
    merge_status: str
    done_day: float | None
    p10: float | None
    p50: float | None
    p90: float | None
    by_freeze: float | None
    by_release: float | None
    cdf: list[list[float]] = field(default_factory=list)


@dataclass(frozen=True)
class SnapshotRun:
    """One release's forecast on one day."""

    release_key: str
    snapshot_date: date
    as_of: datetime
    model_version: str
    code_freeze_at: datetime | None
    release_at: datetime | None
    body: dict[str, Any]
    features: tuple[FeatureSnapshot, ...]
    id: int | None = None


def build_snapshot(view: Any, config: ForecastConfig = DEFAULT_FORECAST) -> SnapshotRun:
    """Turn a computed release view (api.service.ReleaseView) into a snapshot run."""
    a = view.assessment
    r = a.release
    feats: list[FeatureSnapshot] = []
    for f in a.features:
        fc = view.forecasts.get(f.key)
        md = view.merge_dates.get(f.key)
        feats.append(
            FeatureSnapshot(
                feature_key=f.key,
                in_release=f.in_release,
                odds_status=fc.status if fc else "not_in_release",
                probability=fc.probability if fc else None,
                low=fc.low if fc else None,
                high=fc.high if fc else None,
                raw_probability=fc.raw_probability if fc else None,
                merge_status=md.status if md else "none",
                done_day=md.done_day if md else None,
                p10=md.p10 if md else None,
                p50=md.p50 if md else None,
                p90=md.p90 if md else None,
                by_freeze=md.by_freeze if md else None,
                by_release=md.by_release if md else None,
                cdf=[list(c) for c in md.cdf] if md else [],
            )
        )
    curve = view.curve
    return SnapshotRun(
        release_key=r.key,
        snapshot_date=a.as_of.date(),
        as_of=a.as_of,
        model_version=model_version(config),
        code_freeze_at=r.code_freeze_at,
        release_at=r.release_at,
        body={
            "config": asdict(config),
            "calibration": view.calibration.describe(),
            "recalibration": {
                "training_releases": list(view.recalibration.training_releases),
                "base_rate": view.recalibration.base_rate,
            },
            "odds_validation": view.validation.as_dict(),
            "merge_date_validation": view.date_validation.as_dict(),
            "curve": {
                "forecast": [list(x) for x in curve.forecast],
                "actual": [list(x) for x in curve.actual],
                "features": curve.features,
                "done_now": curve.done_now,
            }
            if curve
            else None,
        },
        features=tuple(feats),
    )


def worth_recording(run: SnapshotRun) -> bool:
    """Only releases still in play: before release day + the merge-date tail."""
    end = run.release_at or run.code_freeze_at
    return end is None or run.as_of <= end + TAIL


class SnapshotStore(Protocol):
    """Where snapshots live."""

    def has(self, release_key: str, day: date, version: str) -> bool:
        """Whether that day's snapshot exists."""
        ...

    def save(self, run: SnapshotRun) -> int | None:
        """Store a run; None if that day's run already exists (never overwritten)."""
        ...

    def runs(self, release_key: str, version: str | None = None) -> list[SnapshotRun]:
        """Runs for a release, oldest first, with their features."""
        ...


@dataclass
class MemorySnapshotStore:
    """For tests."""

    stored: list[SnapshotRun] = field(default_factory=list)

    def has(self, release_key: str, day: date, version: str) -> bool:
        """Whether that day's snapshot exists."""
        return any(
            r.release_key == release_key and r.snapshot_date == day and r.model_version == version
            for r in self.stored
        )

    def save(self, run: SnapshotRun) -> int | None:
        """Append unless that day's run exists."""
        if self.has(run.release_key, run.snapshot_date, run.model_version):
            return None
        rid = len(self.stored) + 1
        self.stored.append(SnapshotRun(**{**run.__dict__, "id": rid}))
        return rid

    def runs(self, release_key: str, version: str | None = None) -> list[SnapshotRun]:
        """Runs for a release, oldest first."""
        return sorted(
            (
                r
                for r in self.stored
                if r.release_key == release_key and (version is None or r.model_version == version)
            ),
            key=lambda r: r.as_of,
        )


class PostgresSnapshotStore:
    """``forecast_snapshot_runs`` and ``forecast_snapshots`` (insert only)."""

    def __init__(self, factory: Any) -> None:
        self._factory = factory

    def has(self, release_key: str, day: date, version: str) -> bool:
        """Whether that day's snapshot exists."""
        from sqlalchemy import select

        from pipeline.store.models import ForecastSnapshotRunRecord as Run

        with self._factory() as s:
            q = select(Run.id).where(
                Run.release_key == release_key,
                Run.snapshot_date == day,
                Run.model_version == version,
            )
            return s.scalar(q) is not None

    def save(self, run: SnapshotRun) -> int | None:
        """Insert the run and its features in one transaction."""
        from sqlalchemy.exc import IntegrityError

        from pipeline.store.models import ForecastSnapshotRecord, ForecastSnapshotRunRecord

        with self._factory() as s:
            rec = ForecastSnapshotRunRecord(
                release_key=run.release_key,
                snapshot_date=run.snapshot_date,
                as_of=run.as_of,
                model_version=run.model_version,
                code_freeze_at=run.code_freeze_at,
                release_at=run.release_at,
                body=run.body,
            )
            s.add(rec)
            try:
                s.flush()
            except IntegrityError:
                s.rollback()
                return None  # someone else stored today's run
            s.add_all(ForecastSnapshotRecord(run_id=rec.id, **asdict(f)) for f in run.features)
            s.commit()
            return int(rec.id)

    def runs(self, release_key: str, version: str | None = None) -> list[SnapshotRun]:
        """Runs for a release, oldest first, with their features."""
        from sqlalchemy import select

        from pipeline.store.models import ForecastSnapshotRecord as Row
        from pipeline.store.models import ForecastSnapshotRunRecord as Run

        with self._factory() as s:
            q = select(Run).where(Run.release_key == release_key).order_by(Run.as_of)
            if version is not None:
                q = q.where(Run.model_version == version)
            out: list[SnapshotRun] = []
            for r in s.scalars(q).all():
                rows = s.scalars(select(Row).where(Row.run_id == r.id)).all()
                out.append(
                    SnapshotRun(
                        release_key=r.release_key,
                        snapshot_date=r.snapshot_date,
                        as_of=r.as_of,
                        model_version=r.model_version,
                        code_freeze_at=r.code_freeze_at,
                        release_at=r.release_at,
                        body=r.body,
                        features=tuple(
                            FeatureSnapshot(
                                **{k: getattr(x, k) for k in FeatureSnapshot.__dataclass_fields__}
                            )
                            for x in rows
                        ),
                        id=r.id,
                    )
                )
            return out


def recorder(
    store: SnapshotStore, config: ForecastConfig = DEFAULT_FORECAST
) -> Callable[[Any], None]:
    """A callback for ReleaseService: store the day's snapshot of a computed view once."""

    def record(view: Any) -> None:
        try:
            a = view.assessment
            version = model_version(config)
            if store.has(a.release.key, a.as_of.date(), version):
                return
            run = build_snapshot(view, config)
            if worth_recording(run) and store.save(run) is not None:
                logger.info(
                    "forecast snapshot stored",
                    extra={"release": run.release_key, "model_version": version},
                )
        except Exception:
            logger.exception("forecast snapshot failed")

    return record


# ------------------------------------------------------------------ scoring (ADR-0015)


@dataclass(frozen=True)
class LeadScore:
    """Scores of the snapshot taken closest to one lead time."""

    lead_days: int
    snapshot_date: str | None
    n: int
    brier: float | None = None
    brier_baseline: float | None = None
    skill: float | None = None
    coverage: float | None = None
    crps: float | None = None
    crps_baseline: float | None = None
    crps_skill: float | None = None


def pick(runs: Sequence[SnapshotRun], freeze: datetime, lead_days: int) -> SnapshotRun | None:
    """The run taken closest to ``freeze - lead_days``, if within 2 days of it."""
    target = freeze - timedelta(days=lead_days)
    best = min(runs, key=lambda r: abs(r.as_of - target), default=None)
    if best is None or abs(best.as_of - target) > timedelta(days=2):
        return None
    return best


def score_odds(run: SnapshotRun, landed: Mapping[str, bool], lead: int) -> LeadScore:
    """Brier of the recorded odds against outcomes, and against the recorded base rate."""
    base = run.body.get("recalibration", {}).get("base_rate")
    pairs = [
        (f.probability, landed[f.feature_key])
        for f in run.features
        if f.odds_status == "forecast" and f.probability is not None and f.feature_key in landed
    ]
    if not pairs or base is None:
        return LeadScore(lead, str(run.snapshot_date), len(pairs))
    b = sum((p - float(y)) ** 2 for p, y in pairs) / len(pairs)
    b0 = sum((base - float(y)) ** 2 for _, y in pairs) / len(pairs)
    return LeadScore(
        lead,
        str(run.snapshot_date),
        len(pairs),
        brier=round(b, 4),
        brier_baseline=round(b0, 4),
        skill=round(1 - b / b0, 3) if b0 else None,
    )


def score_merge_dates(
    run: SnapshotRun, actual: Mapping[str, float], baseline: Sequence[float], lead: int
) -> LeadScore:
    """Coverage of the recorded 10th-90th range and CRPS against a baseline ECDF."""
    rows = [
        f
        for f in run.features
        if f.merge_status == "forecast" and f.cdf and f.feature_key in actual
    ]
    if not rows:
        return LeadScore(lead, str(run.snapshot_date), 0)
    base = np.asarray(baseline, dtype=np.float64)
    covered: list[bool] = []
    crps: list[float] = []
    crps0: list[float] = []
    for f in rows:
        y = actual[f.feature_key]
        lo = f.p10 if f.p10 is not None else float("inf")
        hi = f.p90 if f.p90 is not None else float("inf")
        covered.append(lo <= y <= hi)
        days = [c[0] for c in f.cdf]
        crps.append(sum((c[1] - float(y <= c[0])) ** 2 for c in f.cdf))
        f0 = [float((base <= d).mean()) if base.size else 0.0 for d in days]
        crps0.append(sum((p - float(y <= d)) ** 2 for p, d in zip(f0, days, strict=True)))
    c = float(np.mean(crps))
    c0 = float(np.mean(crps0))
    return LeadScore(
        lead,
        str(run.snapshot_date),
        len(rows),
        coverage=round(float(np.mean(covered)), 3),
        crps=round(c, 3),
        crps_baseline=round(c0, 3),
        crps_skill=round(1 - c / c0, 3) if c0 else None,
    )
