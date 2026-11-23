"""Computes release views from stored events and caches them. All numbers come from engine/.

Events are loaded incrementally (by database id). A release view is recomputed when new
events arrive or after ``ttl`` (odds depend on the time left before Code Freeze).

Stale-while-revalidate: once a release has been computed, a request never waits for a
recompute caused by new events or the TTL. It gets the previous view (whose "data as of"
time says how old it is) while one background thread computes the new one. A person's own
action (``invalidate``, e.g. confirming a link) still waits, so they see its effect. A
warmer thread keeps viewed releases fresh even when nobody is looking.
"""

from __future__ import annotations

import functools
import gc
import logging
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Protocol

from opentelemetry import trace
from sqlalchemy.orm import Session, sessionmaker

from api.validation import Validation, load_date_validation, load_validation
from connectors.load import scope_events
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
from engine.links import link_release
from engine.merge_date import MergeDateForecast, ReleaseCurve, forecast_release_dates, release_curve
from engine.odds import training_pairs
from engine.projection import ReleaseInfo, World, project
from engine.recalibrate import Recalibration, fit
from linker.rules import LinkCandidate
from pipeline.events import NormalizedEvent, ReleaseObserved

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
    merge_dates: dict[str, MergeDateForecast] = field(default_factory=dict)
    curve: ReleaseCurve | None = None
    date_validation: Validation = field(
        default_factory=lambda: Validation(False, "merge dates not computed")
    )

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
        date_validation: Callable[[], Validation] = load_date_validation,
        extra_links: Callable[[str], Sequence[LinkCandidate]] | None = None,
        on_computed: Callable[[ReleaseView], None] | None = None,
    ) -> None:
        self._source = source
        self._project = project_name
        self._forecast = forecast
        self._ttl = ttl.total_seconds()
        self._now = now
        self._events: list[NormalizedEvent] = []
        # Release keys seen in the events, for resolving bare names ("4.4.0").
        self._release_keys: set[str] = set()
        self._last_id = 0
        self._version = 0
        self._views: dict[str, ReleaseView] = {}
        self._recal: dict[tuple[str, int], tuple[float, Recalibration]] = {}
        self._recal_ttl = recalibration_ttl.total_seconds()
        self._validation = validation
        self._date_validation = date_validation
        # Called after each new view (e.g. to store the day's forecast snapshot).
        self._on_computed = on_computed
        # AI link suggestions and people's decisions on them, per release (ADR-0011).
        self._extra_links = extra_links
        self._lock = threading.Lock()
        # One lock per release key: concurrent requests wait for a running computation
        # instead of starting their own (single flight).
        self._key_locks: dict[str, threading.Lock] = {}
        self._key_locks_guard = threading.Lock()
        self._summaries: tuple[int, float, list[ReleaseSummary]] | None = None
        self._summaries_lock = threading.Lock()
        # Views older than this version must be recomputed before they are served
        # (raised by ``invalidate``: the user's own action must show).
        self._required_version = 0
        self._refreshing: set[str] = set()
        self._refreshing_guard = threading.Lock()
        self._warmer: threading.Thread | None = None
        self._stop = threading.Event()

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
                self._release_keys.update(
                    e.subject.external_key for e in new if isinstance(e.payload, ReleaseObserved)
                )
                self._last_id = last
                self._version += 1
            return len(new)

    def invalidate(self) -> None:
        """Recompute views before their next use (e.g. after a person confirms a link)."""
        with self._lock:
            self._version += 1
            self._required_version = self._version

    def release_keys(self) -> list[str]:
        """Known release keys, oldest first."""
        return [r.release.key for r in self.releases()]

    def releases(self) -> list[ReleaseSummary]:
        """Every known release with dates and feature counts, oldest first.

        Uses one projection of the stored events (no assessment, no forecast), cached
        until new events arrive or ``ttl`` passes.
        """
        self.refresh()
        hit = self._summaries
        if hit and (hit[0] != self._version or time.monotonic() - hit[1] >= self._ttl):
            self._in_background("__releases__", self._compute_summaries)
            return hit[2]
        if hit:
            return hit[2]
        return self._compute_summaries()

    def _compute_summaries(self) -> list[ReleaseSummary]:
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

    def current_release_name(self, project: str | None = None) -> str | None:
        """The project's earliest release not yet released, else its newest (None if none).

        ``project`` defaults to the service's default project.
        """
        wanted = project or self._project
        rows = [r for r in self.releases() if _project_of(r.release.key) == wanted]
        if not rows:
            return None
        now = self._now()
        open_ = [r for r in rows if r.release.release_at is None or r.release.release_at > now]
        return (open_[0] if open_ else rows[-1]).release.name

    def current_release_keys(self) -> list[str]:
        """The current release of every project (for warming on boot)."""
        projects = sorted({_project_of(r.release.key) for r in self.releases()})
        out = []
        for project_ in projects:
            name = self.current_release_name(project_)
            if name:
                out.append(f"{project_}:{name}")
        return out

    def resolve(self, release: str) -> str:
        """Release key for ``kubernetes:v1.38``, or a bare name that is unique (``4.4.0``).

        A bare name that several projects use resolves to the default project's release.
        """
        if ":" in release:
            return release
        self.refresh()
        with self._lock:
            matches = sorted(k for k in self._release_keys if k.split(":", 1)[1] == release)
        default = f"{self._project}:{release}"
        if len(matches) == 1:
            return matches[0]
        return default

    def view(self, release_name: str, *, wait: bool = False) -> ReleaseView:
        """Current view of a release.

        Fresh views are returned as they are. A stale view is returned at once while a
        background thread recomputes it, unless ``wait`` is set, the view predates an
        ``invalidate``, or there is no view yet: then the caller waits (one computation
        per release at a time).
        """
        key = self.resolve(release_name)
        self.refresh()
        cached = self._views.get(key)
        if cached and self._is_fresh(cached):
            return cached
        if cached and not wait and cached.version >= self._required_version:
            self._in_background(key, lambda: self._compute_locked(key))
            return cached
        return self._compute_locked(key)

    def warm(self, release_names: Sequence[str] = ()) -> None:
        """Start background recomputes for stale views and for ``release_names``."""
        self.refresh()
        keys = set(self._views) | {self.resolve(n) for n in release_names}
        for key in keys:
            cached = self._views.get(key)
            if cached is None or not self._is_fresh(cached):
                self._in_background(key, functools.partial(self._compute_locked, key))

    def start_warmer(self, interval: timedelta = timedelta(seconds=30)) -> None:
        """Keep viewed releases fresh in a daemon thread, checking every ``interval``."""
        if self._warmer is not None:
            return

        def loop() -> None:
            while not self._stop.wait(interval.total_seconds()):
                try:
                    self.warm()
                except Exception:
                    logger.exception("release view warmer failed")

        self._warmer = threading.Thread(target=loop, name="release-warmer", daemon=True)
        self._warmer.start()

    def stop_warmer(self) -> None:
        """Stop the warmer thread (tests, shutdown)."""
        self._stop.set()

    def refreshing(self) -> set[str]:
        """Keys being recomputed in the background right now."""
        with self._refreshing_guard:
            return set(self._refreshing)

    def _in_background(self, key: str, compute: Callable[[], object]) -> None:
        """Run ``compute`` in a daemon thread unless one is already running for ``key``."""
        with self._refreshing_guard:
            if key in self._refreshing:
                return
            self._refreshing.add(key)

        def run() -> None:
            try:
                compute()
            except KeyError:
                pass  # release no longer known
            except Exception:
                logger.exception("background recompute of %s failed", key)
            finally:
                with self._refreshing_guard:
                    self._refreshing.discard(key)

        threading.Thread(target=run, name=f"recompute-{key}", daemon=True).start()

    def _compute_locked(self, key: str) -> ReleaseView:
        with self._key_lock(key):
            cached = self._views.get(key)
            if cached and self._is_fresh(cached):
                return cached  # another thread may have just computed it
            with tracer.start_as_current_span(
                "api.compute_release_view", attributes={"tpm.release": key}
            ):
                view = self._compute(key)
            self._views[key] = view
            # The projected world is large (about 300k events) and lives until the next
            # refresh. Moving it out of the garbage collector's reach stops full
            # collections, triggered by simulator requests, from re-scanning it each time
            # (measured: 3-4 s pauses on every ~9th request). Frozen objects are still freed
            # by reference counting; only reference cycles among them are kept.
            gc.collect()
            gc.freeze()
            if self._on_computed is not None:
                self._on_computed(view)
            return view

    def _is_fresh(self, cached: ReleaseView) -> bool:
        return cached.version == self._version and time.monotonic() - cached.computed_at < self._ttl

    def _key_lock(self, key: str) -> threading.Lock:
        with self._key_locks_guard:
            return self._key_locks.setdefault(key, threading.Lock())

    def _snapshot_events(self) -> Sequence[NormalizedEvent]:
        with self._lock:
            return list(self._events)

    def _compute(self, key: str) -> ReleaseView:
        now = self._now()
        # One world per project (ADR-0018): Kafka PRs are not Kubernetes load.
        events = scope_events(self._snapshot_events(), _project_of(key))
        world = project(events, now)
        if key not in world.releases:
            raise KeyError(key)
        if self._extra_links is not None:
            world = replace(world, extra_links=tuple(self._extra_links(key)))
        started = time.perf_counter()
        # Link once and share it (P3-M4): each stage used to link the release itself.
        links = link_release(world, key)
        assessment = assess_release(world, key, links=links)
        calibration = calibrate(world, finished_releases(world, now, exclude=key))
        raw = forecast_release(world, key, calibration, self._forecast, links=links)
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
        dates = forecast_release_dates(world, key, calibration, self._forecast, links=links)
        curve = release_curve(world.releases[key], world.as_of, dates)
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
            merge_dates={d.feature_key: d for d in dates},
            curve=curve,
            date_validation=self._date_validation(),
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


def _project_of(release_key: str) -> str:
    return release_key.split(":", 1)[0]
