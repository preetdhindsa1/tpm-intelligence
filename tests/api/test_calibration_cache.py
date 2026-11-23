"""P3-M4 calibration cache, option A (ADR-0019).

Calibration is reused until a new event touches what it read (a finished release's
feature, a PR linked to one, or the release itself), the finished releases change, the
time limit passes, or a person acts (``invalidate``). Otherwise its numbers would go
stale without anyone noticing.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from api.service import InMemoryEventSource, ReleaseService
from api.validation import Validation
from engine.forecast import ForecastConfig, calibrate, finished_releases
from engine.projection import project
from tests.engine.conftest import utc
from tests.engine.test_forecast import OBS, two_releases

FAST = ForecastConfig(replications=5, sims=100)
NOW = utc(2026, 10, 1)


def setup(now: datetime = NOW) -> tuple[ReleaseService, InMemoryEventSource, object]:
    stream, _, _ = two_releases()
    source = InMemoryEventSource(list(stream.events))
    clock = {"now": now}
    svc = ReleaseService(
        source,
        forecast=FAST,
        now=lambda: clock["now"],
        validation=lambda: Validation(False, "test"),
        ttl=timedelta(seconds=0),  # every view recomputes; only the calibration may be reused
    )
    return svc, source, clock


def more(build: object) -> list:
    """Events from a fresh stream that ``build(stream)`` adds to."""
    from tests.engine.synthetic import Stream

    s = Stream(OBS)
    build(s)  # type: ignore[operator]
    return s.events


def test_reused_when_new_events_touch_only_the_current_release() -> None:
    svc, source, _ = setup()
    svc.view("v1.38", wait=True)
    assert svc.calibrations_computed == 1
    source.events += more(lambda s: s.feature(200, "kubernetes:v1.38", [(utc(2026, 9, 2), True)]))
    view = svc.view("v1.38", wait=True)
    assert "kubernetes/enhancements#200" in view.world.features  # the view did recompute
    assert svc.calibrations_computed == 1  # the calibration did not


def test_rebuilt_when_a_finished_releases_pr_changes() -> None:
    svc, source, _ = setup()
    svc.view("v1.38", wait=True)
    # PR 5006 belonged to a feature that slipped in v1.37; it merges late.
    source.events += more(lambda s: s.pr(5006, 106, utc(2026, 6, 7), merged=utc(2026, 9, 20)))
    view = svc.view("v1.38", wait=True)
    assert svc.calibrations_computed == 2
    # And the rebuilt calibration equals a from-scratch one.
    world = project(source.events, NOW)
    fresh = calibrate(world, finished_releases(world, NOW, exclude="kubernetes:v1.38"))
    assert view.calibration.durations_days == fresh.durations_days


def test_rebuilt_after_the_time_limit_and_after_a_person_acts() -> None:
    svc, _, clock = setup()
    svc.view("v1.38", wait=True)
    clock["now"] = NOW + timedelta(minutes=1)
    svc.view("v1.38", wait=True)
    assert svc.calibrations_computed == 1
    svc.invalidate()
    svc.view("v1.38", wait=True)
    assert svc.calibrations_computed == 2


def test_time_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    import api.service as service_module

    svc, _, _ = setup()
    t = {"mono": 1000.0}
    monkeypatch.setattr(service_module.time, "monotonic", lambda: t["mono"])
    svc.view("v1.38", wait=True)
    t["mono"] += 6 * 3600 + 1
    svc.view("v1.38", wait=True)
    assert svc.calibrations_computed == 2


def test_cached_calibration_gives_the_same_view_as_a_fresh_one() -> None:
    svc, source, _ = setup()
    svc.view("v1.38", wait=True)
    source.events += more(lambda s: s.feature(201, "kubernetes:v1.38", [(utc(2026, 9, 3), True)]))
    cached = svc.view("v1.38", wait=True)
    fresh_svc, fresh_source, _ = setup()
    fresh_source.events[:] = list(source.events)
    fresh = fresh_svc.view("v1.38", wait=True)
    assert cached.calibration == fresh.calibration
    assert {k: f.probability for k, f in cached.forecasts.items()} == {
        k: f.probability for k, f in fresh.forecasts.items()
    }


def _on_pr(number: int, payload: object, ident: str) -> object:
    from pipeline.events import Source, SubjectKind, SubjectRef, new_event

    return new_event(
        source=Source.GITHUB,
        subject=SubjectRef(
            kind=SubjectKind.PULL_REQUEST,
            source=Source.GITHUB,
            external_key=f"kubernetes/kubernetes#{number}",
        ),
        occurred_at=utc(2026, 9, 25),
        observed_at=OBS,
        payload=payload,  # type: ignore[arg-type]
        identity=(ident,),
    )


def test_reviews_comments_and_unchanged_snapshots_do_not_rebuild() -> None:
    """Most live events are reviews and comments on PRs; calibration never reads them."""
    from pipeline.events import CommentPosted, ReviewState, ReviewSubmitted

    svc, source, _ = setup()
    svc.view("v1.38", wait=True)
    at = utc(2026, 9, 25)
    source.events += [
        _on_pr(
            5000,
            ReviewSubmitted(
                review_id="r1", reviewer="x", state=ReviewState.APPROVED, submitted_at=at
            ),
            "r",
        ),
        _on_pr(5001, CommentPosted(comment_id="c1", author="y", posted_at=at), "c"),
    ]
    # PR 5002 re-observed with the same dates and text (GitHub bumps updated_at on any activity).
    source.events += more(lambda s: s.pr(5002, 102, utc(2026, 6, 3), merged=utc(2026, 6, 13)))
    svc.view("v1.38", wait=True)
    assert svc.calibrations_computed == 1
