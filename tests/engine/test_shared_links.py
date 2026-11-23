"""P3-M4: linking once and sharing it gives exactly the same results as each stage
linking the release itself (the #6395 fixtures, fixed seeds)."""

from __future__ import annotations

import dataclasses
from typing import Any

import numpy as np

from engine.assess import assess_release
from engine.forecast import ForecastConfig, calibrate, forecast_release
from engine.links import link_release
from engine.merge_date import forecast_release_dates
from engine.projection import project
from tests.engine.conftest import fixture_events, utc

KEY = "kubernetes:v1.38"
FAST = ForecastConfig(replications=5, sims=200)


def plain(x: Any) -> Any:
    """Comparable form: dataclasses and arrays become dicts and lists."""
    if dataclasses.is_dataclass(x) and not isinstance(x, type):
        return {f.name: plain(getattr(x, f.name)) for f in dataclasses.fields(x)}
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, dict):
        return {k: plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [plain(v) for v in x]
    return x


def test_shared_links_change_nothing() -> None:
    for as_of in (utc(2026, 11, 10), utc(2026, 11, 21, 3)):  # before and after freeze
        world = project(fixture_events(), as_of)
        links = link_release(world, KEY)
        cal = calibrate(world, [])
        assert plain(assess_release(world, KEY, links=links)) == plain(assess_release(world, KEY))
        assert plain(forecast_release(world, KEY, cal, FAST, links=links)) == plain(
            forecast_release(world, KEY, cal, FAST)
        )
        assert plain(forecast_release_dates(world, KEY, cal, FAST, links=links)) == plain(
            forecast_release_dates(world, KEY, cal, FAST)
        )
