"""RAID extractor eval: scoring, the per-type threshold and the offline CI gate."""

from __future__ import annotations

from evals.raid_extractor import load_cases, same, score_case, summarize
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
