"""Runs what-if scenarios for the API, with cached state and baselines (ADR-0012).

* The calibration is read from the store (fitted offline by ``make sim-calibrate``).
* The starting state is rebuilt when the release view changes (new events).
* The baseline is cached per calibration and state, so a scenario request runs only the
  scenario (CLAUDE.md §14: p95 under 2 seconds).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from opentelemetry import trace

from api.service import ReleaseView
from api.sim_store import SimStore, StoredCalibration
from simulator.scenario import (
    REPLICATIONS,
    Comparison,
    Outcome,
    Scenario,
    State,
    compare,
    current_state,
    run,
)

tracer = trace.get_tracer(__name__)
CALIBRATION_TTL = 60.0  # seconds; a new `make sim-calibrate` shows up within a minute


class NoCalibrationError(LookupError):
    """No calibration stored for the release."""


@dataclass(frozen=True)
class Simulation:
    """One answered request."""

    calibration: StoredCalibration
    state: State
    comparison: Comparison
    seconds: float


class SimulatorService:
    """Thread-safe caches around ``simulator.scenario``."""

    def __init__(self, store: SimStore, replications: int = REPLICATIONS) -> None:
        self.store = store
        self.replications = replications
        self._cal: dict[str, tuple[float, StoredCalibration]] = {}
        self._states: dict[tuple[str, int, int], State] = {}
        self._baselines: dict[tuple[str, int, int], Outcome] = {}
        self._lock = threading.Lock()

    def calibration(self, release_key: str) -> StoredCalibration:
        """Newest stored calibration for the release."""
        with self._lock:
            hit = self._cal.get(release_key)
        if hit is not None and time.monotonic() - hit[0] <= CALIBRATION_TTL:
            return hit[1]
        row = self.store.latest_calibration(release_key)
        if row is None:  # not cached: a calibration stored later is picked up at once
            raise NoCalibrationError(release_key)
        with self._lock:
            self._cal[release_key] = (time.monotonic(), row)
        return row

    def state(self, view: ReleaseView) -> tuple[StoredCalibration, State]:
        """Calibration and the release's current starting state."""
        key = view.assessment.release.key
        cal = self.calibration(key)
        cache = (key, cal.id, view.version)
        with self._lock:
            state = self._states.get(cache)
        if state is None:
            with tracer.start_as_current_span("sim.current_state"):
                state = current_state(view.world, key, list(cal.calibration.inputs.pools))
            with self._lock:
                self._states = {cache: state} | {
                    k: v for k, v in self._states.items() if k[0] != key
                }
        return cal, state

    def simulate(self, view: ReleaseView, scenario: Scenario) -> Simulation:
        """Baseline (cached) next to ``scenario``."""
        started = time.perf_counter()
        cal, state = self.state(view)
        cache = (state.release_key, cal.id, view.version)
        with self._lock:
            base = self._baselines.get(cache)
        if base is None:
            with tracer.start_as_current_span("sim.baseline"):
                base = run(cal.calibration, state, Scenario(), self.replications)
            with self._lock:
                self._baselines = {cache: base} | {
                    k: v for k, v in self._baselines.items() if k[0] != state.release_key
                }
        with tracer.start_as_current_span(
            "sim.scenario", attributes={"tpm.release": state.release_key}
        ):
            result = compare(cal.calibration, state, scenario, self.replications, baseline=base)
        return Simulation(cal, state, result, round(time.perf_counter() - started, 3))
