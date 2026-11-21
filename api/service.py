"""Computes release views from stored events and caches them. All numbers come from engine/.

Events are loaded incrementally (by database id). A release view is recomputed when new
events arrive or after ``ttl`` (odds depend on the time left before Code Freeze).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Protocol

from opentelemetry import trace
from sqlalchemy.orm import Session, sessionmaker

from api.validation import Validation, load_validation
from engine.assess import FeatureAssessment, ReleaseAssessment, assess_release
from engine.forecast import (
    DEFAULT_FORECAST,
    Calibration,
    Forecast,
    ForecastConfig,
    Rate,
    bucket,
    calibrate,
    finished_releases,
    forecast_release,
)
from engine.odds import training_pairs
from engine.projection import ReleaseInfo, World, project
from engine.recalibrate import Recalibration, fit
from pipeline.events import NormalizedEvent

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class EventSource(Protocol):
    """Where stored events come from."""

    def load_after(self, last_id: int) -> tuple[list[NormalizedEvent], int]:
        """Events with id > ``last_id`` and the new highest id."""
        ...


@dataclass
class InMemoryEventSource:
    """For tests and demos."""

    events: list[NormalizedEvent] = field(default_factory=list)

    def load_after(self, last_id: int) -> tuple[list[NormalizedEvent], int]:
        """Return events after position ``last_id``."""
        return self.events[last_id:], len(self.events)


class PostgresEventSource:
    """Reads the ``events`` table."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def load_after(self, last_id: int) -> tuple[list[NormalizedEvent], int]:
        """Incremental read ordered by id."""
        from sqlalchemy import select

        from pipeline.store.events_repo import to_event
        from pipeline.store.models import EventRecord

        with self._factory() as session:
            rows = session.scalars(
                select(EventRecord).where(EventRecord.id > last_id).order_by(EventRecord.id)
            ).all()
            return [to_event(r) for r in rows], (rows[-1].id if rows else last_id)


@dataclass(frozen=True)
class ReleaseSummary:
    """A release's dates and feature counts, without assessment or forecast (cheap)."""

    release: ReleaseInfo
    features_in_release: int
    features_ever_in_release: int
    as_of: datetime


@dataclass(frozen=True)
class ReleaseView:
    """One computed release state."""

    world: World
    assessment: ReleaseAssessment
    calibration: Calibration
    recalibration: Recalibration
    forecasts: dict[str, Forecast]
    validation: Validation
    version: int
    computed_at: float

    def feature(self, key: str) -> FeatureAssessment | None:
        """Assessment for one feature key."""
        return next((f for f in self.assessment.features if f.key == key), None)


class ReleaseService:
    """Thread-safe cache of release views over an event source."""

    def __init__(
        self,
        source: EventSource,
        *,
        project_name: str = "kubernetes",
        forecast: ForecastConfig = DEFAULT_FORECAST,
        ttl: timedelta = timedelta(minutes=5),
        recalibration_ttl: timedelta = timedelta(hours=6),
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        validation: Callable[[], Validation] = load_validation,
    ) -> None:
        self._source = source
        self._project = project_name
        self._forecast = forecast
        self._ttl = ttl.total_seconds()
        self._now = now
        self._events: list[NormalizedEvent] = []
        self._last_id = 0
        self._version = 0
        self._views: dict[str, ReleaseView] = {}
        self._recal: dict[tuple[str, int], tuple[float, Recalibration]] = {}
        self._recal_ttl = recalibration_ttl.total_seconds()
        self._validation = validation
        self._lock = threading.Lock()
        # One lock per release key: concurrent requests wait for a running computation
        # instead of starting their own (single flight).
        self._key_locks: dict[str, threading.Lock] = {}
        self._key_locks_guard = threading.Lock()
        self._summaries: tuple[int, float, list[ReleaseSummary]] | None = None
        self._summaries_lock = threading.Lock()

    @property
    def version(self) -> int:
        """Increases whenever new events are loaded."""
        return self._version

    def refresh(self) -> int:
        """Load new events; return how many arrived."""
        with self._lock:
            new, last = self._source.load_after(self._last_id)
            if new:
                self._events.extend(new)
                self._last_id = last
                self._version += 1
            return len(new)

    def release_keys(self) -> list[str]:
        """Known release keys, oldest first."""
        return [r.release.key for r in self.releases()]

    def releases(self) -> list[ReleaseSummary]:
        """Every known release with dates and feature counts, oldest first.

        Uses one projection of the stored events (no assessment, no forecast), cached
        until new events arrive or ``ttl`` passes.
        """
        self.refresh()
        with self._summaries_lock:
            hit = self._summaries
            if hit and hit[0] == self._version and time.monotonic() - hit[1] < self._ttl:
                return hit[2]
            version = self._version
            with tracer.start_as_current_span("api.compute_release_list"):
                world = project(self._snapshot_events(), self._now())
                summaries = [
                    ReleaseSummary(
                        info,
                        len(world.features_in(key)),
                        len(world.features_ever_in(key)),
                        world.as_of,
                    )
                    for key, info in sorted(
                        world.releases.items(),
                        key=lambda kv: kv[1].cycle_start_at or world.as_of,
                    )
                ]
            self._summaries = (version, time.monotonic(), summaries)
            return summaries

    def view(self, release_name: str) -> ReleaseView:
        """Current view of a release (recomputed if stale, at most once at a time)."""
        key = f"{self._project}:{release_name}"
        self.refresh()
        cached = self._fresh(key)
        if cached:
            return cached
        with self._key_lock(key):
            cached = self._fresh(key)  # another request may have just computed it
            if cached:
                return cached
            with tracer.start_as_current_span(
                "api.compute_release_view", attributes={"tpm.release": key}
            ):
                view = self._compute(key)
            self._views[key] = view
            return view

    def _fresh(self, key: str) -> ReleaseView | None:
        cached = self._views.get(key)
        if (
            cached
            and cached.version == self._version
            and time.monotonic() - cached.computed_at < self._ttl
        ):
            return cached
        return None

    def _key_lock(self, key: str) -> threading.Lock:
        with self._key_locks_guard:
            return self._key_locks.setdefault(key, threading.Lock())

    def _snapshot_events(self) -> Sequence[NormalizedEvent]:
        with self._lock:
            return list(self._events)

    def _compute(self, key: str) -> ReleaseView:
        now = self._now()
        events = self._snapshot_events()
        world = project(events, now)
        if key not in world.releases:
            raise KeyError(key)
        started = time.perf_counter()
        assessment = assess_release(world, key)
        calibration = calibrate(world, finished_releases(world, now, exclude=key))
        raw = forecast_release(world, key, calibration, self._forecast)
        recal = self._recalibration(events, world, key, calibration)
        forecasts = {
            f.feature_key: (
                replace(
                    f,
                    probability=recal.apply(f.probability),
                    low=recal.apply(f.low),
                    high=recal.apply(f.high),
                    raw_probability=f.probability,
                )
                if f.probability is not None and f.low is not None and f.high is not None
                else f
            )
            for f in raw
        }
        logger.info(
            "release view computed",
            extra={
                "release": key,
                "events": len(events),
                "features": len(assessment.features),
                "seconds": round(time.perf_counter() - started, 2),
            },
        )
        return ReleaseView(
            world,
            assessment,
            calibration,
            recal,
            forecasts,
            self._validation(),
            self._version,
            time.monotonic(),
        )

    def _recalibration(
        self,
        events: Sequence[NormalizedEvent],
        world: World,
        key: str,
        calibration: Calibration,
    ) -> Recalibration:
        """Fit on earlier releases at the current lead time; cached per lead-day."""
        freeze = world.releases[key].code_freeze_at
        lead = (freeze - world.as_of).total_seconds() / 86400 if freeze else 0.0
        base = calibration.landing.get(bucket(max(lead, 0.0)), Rate(0, 0)).mean
        if freeze is None or lead <= 0:
            return Recalibration.identity_to_base(base)
        cache_key = (key, int(lead))
        hit = self._recal.get(cache_key)
        if hit and time.monotonic() - hit[0] < self._recal_ttl:
            return hit[1]
        with tracer.start_as_current_span(
            "api.fit_recalibration", attributes={"tpm.lead_days": int(lead)}
        ):
            pairs, used = training_pairs(events, key, world.as_of, lead, self._forecast)
            recal = fit(pairs, base_rate=base, training_releases=used)
        self._recal[cache_key] = (time.monotonic(), recal)
        return recal
