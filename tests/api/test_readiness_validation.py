"""Readiness "validated" comes from the newest backtest file (#184, ADR-0032)."""

from __future__ import annotations

import json
from pathlib import Path

from api.validation import latest_readiness_backtest, load_readiness_validation


def write(d: Path, stamp: str, passed: bool) -> None:
    v = {"passed": passed, "rule": "the ADR-0032 rule", "reason": "recall 0.5 < 0.6"}
    (d / f"readiness-backtest-{stamp}.json").write_text(json.dumps({"verdict": v}))


def test_no_file_failed_and_passed(tmp_path: Path) -> None:
    assert load_readiness_validation(tmp_path).validated is False
    assert latest_readiness_backtest(tmp_path) is None
    write(tmp_path, "20261126T000000Z", False)
    v = load_readiness_validation(tmp_path)
    assert (v.validated, v.source_file) == (False, "readiness-backtest-20261126T000000Z.json")
    assert "recall 0.5 < 0.6" in v.reason
    write(tmp_path, "20261201T000000Z", True)  # the newest file decides
    assert load_readiness_validation(tmp_path).validated is True


def test_the_committed_result_is_published_and_failed_honestly() -> None:
    body = latest_readiness_backtest()
    assert body is not None
    assert body["verdict"]["passed"] is False
    assert {r["release_key"] for r in body["releases"]} == {
        "kubernetes:v1.36", "kubernetes:v1.37", "kubernetes:v1.38", "KAFKA:4.4.0"}  # fmt: skip
    assert load_readiness_validation().validated is False
