"""Measured inputs and real metrics on the #6395 fixtures (ADR-0012)."""

from __future__ import annotations

from engine.projection import project
from simulator.calibrate import OTHER, assign, path_of, primary_sig, window, window_prs
from simulator.replay import Check, real_metrics
from tests.engine.conftest import MAIN_PR, V138, fixture_events, utc


def test_primary_sig_is_first_sorted_sig_label() -> None:
    assert primary_sig(["kind/feature", "sig/storage", "sig/node"]) == "sig/node"
    assert primary_sig(["kind/bug"]) == "none"


def test_small_sigs_share_the_other_pool() -> None:
    world = project(fixture_events(), utc(2026, 11, 22))
    pr = world.pull_requests[MAIN_PR]
    # #143709 carries sig/api-machinery, which sorts first: a known limit (ADR-0012).
    assert assign(pr, ["sig/api-machinery", OTHER]) == "sig/api-machinery"
    assert assign(pr, ["sig/network", OTHER]) == OTHER


def test_path_of_the_6395_main_pr() -> None:
    world = project(fixture_events(), utc(2026, 11, 22))
    pr = world.pull_requests[MAIN_PR]
    path = path_of(pr, utc(2026, 11, 22))
    assert path.merges  # merged Nov 20, after Code Freeze
    assert len(path.waits_days) == path.rounds
    assert path.final_days >= 0
    before = path_of(pr, utc(2026, 11, 19))
    assert not before.merges  # not merged yet at that horizon


def test_window_and_real_metrics_respect_the_horizon() -> None:
    world = project(fixture_events(), utc(2026, 11, 22))
    w = window(world, V138)
    assert w.freeze == utc(2026, 11, 17, 12)
    prs = window_prs(world, w)
    assert all(w.start <= p.created_at < w.freeze for p in prs)
    m = real_metrics(world, w)
    assert m.merged <= len(prs)


def test_check_tolerance() -> None:
    assert Check("x", 1.0, 1.19, None, None).passed
    assert not Check("x", 1.0, 0.62, None, None).passed
    assert Check("x", 1.0, 0.62, None, None).error == -0.38
    assert not Check("x", None, 1.0, None, None).passed


def test_staffing_counts_only_weeks_that_have_happened() -> None:
    """Kafka 4.5.0 (2026-11-25): 4 of 14 weeks observed; future weeks are not zero reviewers."""
    from datetime import timedelta

    from engine.projection import PullRequest, Review
    from simulator.calibrate import Window, reviewer_weeks

    start = utc(2026, 10, 26)
    reviews = tuple(
        Review(f"r{wk}{who}", who, "approved", start + timedelta(weeks=wk, days=1), None)
        for wk in range(4)
        for who in ("rev-a", "rev-b", "rev-c")
    )
    pr = PullRequest(
        key="apache/kafka#1", repo="apache/kafka", number=1, title="t", body="", author="dev",
        labels=(), created_at=start, state="open", merged_at=None, closed_at=None,
        reviews=reviews, checks=(),
    )  # fmt: skip
    freeze, now = start + timedelta(weeks=14), start + timedelta(weeks=4)
    in_progress = Window("KAFKA:4.5.0", start, freeze, now)
    weeks = reviewer_weeks([pr], in_progress, {pr.key: OTHER})[OTHER]
    assert len(weeks) == 4
    assert weeks == [3.0, 3.0, 3.0, 3.0]
    finished = Window("KAFKA:4.4.0", start, start + timedelta(weeks=4), start + timedelta(weeks=9))
    assert len(reviewer_weeks([pr], finished, {pr.key: OTHER})[OTHER]) == 4  # unchanged
