"""Projection: state as of a time, and the no-future-data guarantee."""

from __future__ import annotations

from datetime import datetime

import pytest

from engine.projection import project
from pipeline.events import PullRequestObserved, WorkItemObserved, WorkItemSpecObserved
from tests.engine.conftest import K2570, K6395, MAIN_PR, V138, fixture_events, utc

SNAPSHOT_TYPES = (WorkItemObserved, WorkItemSpecObserved, PullRequestObserved)


def test_6395_removed_on_nov_18() -> None:
    world = project(fixture_events(), utc(2026, 11, 18))
    f = world.features[K6395]
    assert V138 not in f.release_keys
    assert not f.tracked
    assert "tracked/no" in f.labels
    assert K6395 not in [x.key for x in world.features_in(V138)]
    assert K6395 in [x.key for x in world.features_ever_in(V138)]
    pr = world.pull_requests[MAIN_PR]
    assert (pr.state, pr.merged_at) == ("open", None)  # merges on Nov 20


def test_6395_back_in_release_after_readd() -> None:
    world = project(fixture_events(), utc(2026, 11, 21, 1))
    f = world.features[K6395]
    assert V138 in f.release_keys
    assert f.tracked
    assert world.pull_requests[MAIN_PR].merged_at == utc(2026, 11, 20, 23, 28, 24)


def test_2570_removed_then_readded() -> None:
    assert V138 not in project(fixture_events(), utc(2026, 11, 18)).features[K2570].release_keys
    assert V138 in project(fixture_events(), utc(2026, 11, 21, 3)).features[K2570].release_keys


def test_prs_do_not_exist_before_they_were_opened() -> None:
    world = project(fixture_events(), utc(2026, 11, 1))
    assert MAIN_PR not in world.pull_requests  # opened Nov 2
    assert "kubernetes/kubernetes#143522" in world.pull_requests  # opened Oct 28


def test_reviews_after_as_of_are_invisible() -> None:
    as_of = utc(2026, 11, 10)
    pr = project(fixture_events(), as_of).pull_requests[MAIN_PR]
    full = project(fixture_events(), utc(2027, 1, 1)).pull_requests[MAIN_PR]
    assert all(r.submitted_at < as_of for r in pr.reviews)
    assert len(pr.reviews) < len(full.reviews)


@pytest.mark.parametrize(
    "as_of",
    [utc(2026, 9, 25), utc(2026, 11, 10), utc(2026, 11, 17, 12, 6), utc(2026, 11, 21, 1)],
)
def test_no_future_data(as_of: datetime) -> None:
    """Dropping every time-varying event at or after as_of must change nothing."""
    events = fixture_events()
    past_only = [
        e for e in events if e.occurred_at < as_of or isinstance(e.payload, SNAPSHOT_TYPES)
    ]
    assert project(events, as_of) == project(past_only, as_of)
