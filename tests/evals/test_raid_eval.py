"""RAID extractor eval: scoring, the per-type threshold and the offline CI gate."""

from __future__ import annotations

import json
from pathlib import Path

from agents.prompts import load_prompt
from agents.raid_extractor import TASK
from agents.settings import AISettings
from evals.raid_extractor import gate, load_cases, same, score_case, summarize
from modules.raid.store import normalize_quote

NOTES = "* We will chase the docs authors this week.\n* The beta cut slipped by a day.\n"
CASE = {
    "id": "c1",
    "notes": NOTES,
    "expected": [{"type": "action", "quote": "We will chase the docs authors this week."}],
    "optional": [{"type": "issue", "quote": "The beta cut slipped by a day."}],
}


def test_seed_cases_are_marked_and_every_label_is_in_its_notes() -> None:
    cases = load_cases()
    seeds = [c for c in cases if c.get("seed")]
    assert len(seeds) >= 5
    for c in cases:
        source = normalize_quote(c["notes"])
        for x in c["expected"] + c["optional"]:
            assert normalize_quote(x["quote"]) in source, (c["id"], x["quote"])
        assert "he/him" not in c["notes"]  # attendee lists are never part of a case


def test_quotes_match_by_containment_or_word_overlap() -> None:
    assert same("We will chase the docs authors", "We will chase the docs authors this week.")
    assert not same("We will chase the docs authors", "The beta cut slipped by a day.")


def test_score_counts_hits_misses_and_ignores_optional_items() -> None:
    kept = [
        {"type": "action", "quote": "We will chase the docs authors this week."},
        {"type": "issue", "quote": "The beta cut slipped by a day."},  # optional: not counted
        {"type": "risk", "quote": "The beta cut slipped by a day."},  # wrong type: false positive
    ]
    s = score_case(CASE, kept)
    assert (s["tp"]["action"], s["fp"]["issue"], s["fp"]["risk"]) == (1, 0, 1)
    assert s["fn"]["action"] == 0
    assert s["quotes_ok"] == 3
    assert score_case(CASE, [])["fn"]["action"] == 1


def row(tp: int, fp: int, fn: int, t: str = "action") -> dict:
    zero = dict.fromkeys(("risk", "action", "issue", "decision", "question"), 0)
    score = {
        "tp": {**zero, t: tp},
        "fp": {**zero, t: fp},
        "fn": {**zero, t: fn},
        "kept": tp + fp,
        "quotes_ok": tp + fp,
    }
    return {"id": "x", "score": score}


def test_threshold_applies_only_to_types_with_five_labels() -> None:
    assert summarize([row(4, 1, 1)])["passed"]  # precision 0.8, recall 0.8
    assert not summarize([row(4, 2, 1)])["passed"]  # precision 0.67
    assert not summarize([row(2, 0, 3)])["passed"]  # recall 0.4
    small = summarize([row(1, 3, 0)])
    assert small["per_type"]["action"]["gated"] is False
    assert not small["passed"]  # nothing has enough labels to be gated: not a pass


def test_recall_exactly_at_threshold_passes() -> None:
    s = summarize([row(6, 0, 4)])
    assert s["per_type"]["action"]["recall"] == 0.6
    assert s["passed"]


def test_gate_fails_until_every_case_has_a_live_run(tmp_path: Path) -> None:
    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / "c1.json").write_text(json.dumps(CASE))
    results = tmp_path / "results"
    results.mkdir()
    first = gate(results, cases)
    assert not first["passed"]
    assert first["summary"]["not_run"] == ["c1"]

    sha = load_cases(cases)[0]["sha"]
    kept = ["action | - | We will chase the docs authors this week."]
    prompt = load_prompt(TASK.name)
    model = AISettings.model_fields[f"model_{TASK.role.value}"].default
    stored = {
        "prompt_sha": prompt.sha,
        "model": model,
        "cases": [{"id": "c1", "sha": sha, "kept": kept}],
    }
    (results / "agent-evals-20261125T000000Z-raid_extractor.json").write_text(json.dumps(stored))
    second = gate(results, cases)
    assert second["summary"]["not_run"] == []
    assert second["summary"]["quote_match"] == 1.0
    assert not second["passed"]  # one label is too few to gate: honest, not a pass
    assert second["enforced"] is False  # 1 independent case of the 30 needed to block CI
    assert second["independent_cases"] == 1


def test_a_failing_suite_blocks_ci_only_when_enforced(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from evals import run_evals

    suites = [{"suite": "a", "passed": True}, {"suite": "raid", "passed": False, "enforced": False}]
    monkeypatch.setattr(run_evals, "run_all", lambda: suites)
    assert run_evals.main(["--no-save"]) == 0
    suites[1]["enforced"] = True
    assert run_evals.main(["--no-save"]) == 1
