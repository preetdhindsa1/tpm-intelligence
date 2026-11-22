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
