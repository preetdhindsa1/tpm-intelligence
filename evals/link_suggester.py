"""Live eval of the AI link suggester on hidden-key cases (paid; ADR-0011).

Cases (``scripts/build_link_cases.py``) are rule-linked PRs whose KEP references and gate
names were removed, so the right answer is known without hand labels:

* ``positive``: the linked feature is on the shortlist; the right answer is that feature.
* ``negative``: it was taken off the shortlist; the right answer is ``null``.

Gate (no AI grading AI; all deterministic):
* precision >= 0.80: of the suggestions that passed the checks, the share that were right;
* false links on negatives <= 20%;
* dropped answers (failed quote / shortlist checks) <= 15% of non-null answers;
* recall on positives >= 0.40, so that answering ``null`` to everything cannot pass;
* no errors.

Precision on real unlinked PRs needs a person's labels (``evals/cases/ai_links.csv``).
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from agents.gateway import AIError, Gateway
from agents.link_suggester import TASK, PullRequestText, suggest_link
from agents.prompts import load_prompt
from linker.candidates import Candidate, FeatureDoc
from linker.suggestions import Outcome

CASES = Path(__file__).parent / "cases" / "agent_link_suggester.json"
MIN_PRECISION = 0.80
MAX_FALSE_LINK_RATE = 0.20
MAX_DROP_RATE = 0.15
MIN_RECALL = 0.40


def candidates_from(rows: Sequence[Mapping[str, Any]]) -> list[Candidate]:
    """Rebuild shortlist entries stored in a case."""
    out = []
    for r in rows:
        f = r["feature"]
        doc = FeatureDoc(
            key=f["key"],
            title=f["title"],
            summary=f["summary"],
            feature_gates=tuple(f["feature_gates"]),
            sigs=tuple(f["sigs"]),
            stage=f.get("stage"),
        )
        out.append(
            Candidate(doc, r["rank"], r["score"], tuple(r["shared_words"]), tuple(r["shared_sigs"]))
        )
    return out


def verdict(kind: str, expected: str | None, outcome: Outcome, picked: str | None) -> str:
    """Classify one answer: correct | wrong_feature | false_link | none | dropped."""
    if outcome is Outcome.DROPPED:
        return "dropped"
    if outcome is Outcome.NONE:
        return "none"
    if kind == "negative":
        return "false_link"
    return "correct" if picked == expected else "wrong_feature"


def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate metrics over scored rows (rows with ``error`` count as errors)."""
    ok = [r for r in rows if "error" not in r]
    pos = Counter(r["verdict"] for r in ok if r["kind"] == "positive")
    neg = Counter(r["verdict"] for r in ok if r["kind"] == "negative")
    n_pos, n_neg = sum(pos.values()), sum(neg.values())
    shown = pos["correct"] + pos["wrong_feature"] + neg["false_link"]
    non_null = shown + pos["dropped"] + neg["dropped"]
    return {
        "cases": len(rows),
        "errors": len(rows) - len(ok),
        "positives": dict(pos),
        "negatives": dict(neg),
        "suggestions_shown": shown,
        "precision": round(pos["correct"] / shown, 3) if shown else None,
        "recall_positive": round(pos["correct"] / n_pos, 3) if n_pos else None,
        "false_link_rate_negative": round(neg["false_link"] / n_neg, 3) if n_neg else None,
        "drop_rate": round((pos["dropped"] + neg["dropped"]) / non_null, 3) if non_null else 0.0,
        "cost_usd": round(sum(r["cost_usd"] for r in ok), 6),
    }


def gate(summary: Mapping[str, Any]) -> bool:
    """Thresholds in the module docstring."""
    return bool(
        summary["cases"]
        and not summary["errors"]
        and summary["precision"] is not None
        and summary["precision"] >= MIN_PRECISION
        and (summary["false_link_rate_negative"] or 0.0) <= MAX_FALSE_LINK_RATE
        and summary["drop_rate"] <= MAX_DROP_RATE
        and (summary["recall_positive"] or 0.0) >= MIN_RECALL
    )


def run(gateway: Gateway, cases_path: Path = CASES) -> dict[str, Any]:
    """Run every case and score it."""
    prompt = load_prompt("link_suggester")
    rows: list[dict[str, Any]] = []
    for case in json.loads(cases_path.read_text())["cases"]:
        p = case["pull_request"]
        pr = PullRequestText(p["key"], p["title"], p["body"], tuple(p["labels"]))
        candidates = candidates_from(case["candidates"])
        base = {"id": case["id"], "kind": case["kind"], "expected": case["expected_feature"]}
        try:
            result = suggest_link(gateway, prompt, pr, candidates)
        except AIError as exc:
            rows.append({**base, "error": str(exc)})
            continue
        rows.append(
            {
                **base,
                "picked": result.answer.feature_key,
                "outcome": result.checked.outcome.value,
                "verdict": verdict(
                    case["kind"],
                    case["expected_feature"],
                    result.checked.outcome,
                    result.checked.feature_key,
                ),
                "expected_rank": next(
                    (c.rank for c in candidates if c.feature.key == case["expected_feature"]),
                    None,
                ),
                "evidence": result.evidence(),
                "model": result.model,
                "cost_usd": round(result.cost_usd, 6),
            }
        )
    summary = summarize(rows)
    return {
        "suite": "agent:link_suggester",
        "task": TASK.name,
        "prompt": prompt.label,
        "prompt_sha": prompt.sha,
        "model": gateway.settings.model_for(TASK.role),
        "thresholds": {
            "min_precision": MIN_PRECISION,
            "max_false_link_rate": MAX_FALSE_LINK_RATE,
            "max_drop_rate": MAX_DROP_RATE,
            "min_recall": MIN_RECALL,
        },
        "passed": gate(summary),
        "summary": summary,
        "cases": rows,
    }
