"""Release calendar: v1.38 dates pinned to CLAUDE.md section 11."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from collectors.github_poller.calendar import load_calendar


def test_v1_38_dates_match_claude_md() -> None:
    v138 = load_calendar().get("v1.38")
    assert v138.enhancements_freeze == datetime(2026, 9, 30, 12, tzinfo=UTC)
    assert v138.code_freeze == datetime(2026, 11, 17, 12, tzinfo=UTC)
    assert v138.release.date() == datetime(2026, 12, 16, tzinfo=UTC).date()
    assert v138.cycle_start == datetime(2026, 8, 31, tzinfo=UTC)
    assert "release-1.38" in v138.source_url


def test_calibration_releases_present_and_ordered() -> None:
    cal = load_calendar()
    names = [r.name for r in cal.releases]
    assert names == ["v1.33", "v1.34", "v1.35", "v1.36", "v1.37", "v1.38"]
    for earlier, later in zip(cal.releases, cal.releases[1:], strict=False):
        assert earlier.release <= later.cycle_start


def test_unknown_release_is_an_error() -> None:
    with pytest.raises(KeyError, match=r"v9\.99"):
        load_calendar().get("v9.99")


def test_out_of_order_dates_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "cal.yaml"
    bad.write_text(
        "project: k\nreleases:\n  - name: v1\n    cycle_start: 2026-02-01T00:00:00Z\n"
        "    enhancements_freeze: 2026-01-01T00:00:00Z\n    code_freeze: 2026-03-01T00:00:00Z\n"
        "    release: 2026-04-01T00:00:00Z\n    source_url: x\n"
    )
    with pytest.raises(ValueError, match="out of order"):
        load_calendar(bad)
