"""RAID extractor eval and CI gate (#178; threshold in ADR-0030 addendum 2).

Every ``evals/cases/raid/*.json`` case is a masked excerpt of public meeting notes with a
person's labels: ``expected`` items (type + quote) and ``optional`` ones that are fine
either way (neither a false positive nor a miss). Seed cases are marked ``"seed": true``.

* **Live run** (paid): ``python -m evals.raid_extractor`` runs the extractor on every
  case and writes ``docs/results/agent-evals-<stamp>-raid_extractor.json`` with the items
  it kept per case and each case's SHA.
* **CI gate** (no paid calls, ``run_evals``; next PR): re-scores the stored items against
  the cases in the repo. A case added or changed since the last live run fails the gate
  until ``make evals-live SUITE=raid_extractor`` is run again, so new cases always count.

Gate (all must hold): quote match 100% of kept items; no errors or unrun cases; for every
type with at least ``MIN_SUPPORT`` expected items, precision >= 0.80 and recall >= 0.60.
Types with fewer labels are reported but not gated. A kept item matches a label of the
same type when one quote contains the other, or they share ``MIN_OVERLAP`` of their words.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from agents.gateway import AIError, Gateway
from agents.prompts import load_prompt
from agents.raid_extractor import TASK, Meeting, extract
from modules.raid.store import normalize_quote

CASES = Path(__file__).parent / "cases" / "raid"

TYPES = ("risk", "action", "issue", "decision", "question")
MIN_PRECISION, MIN_RECALL, MIN_SUPPORT, MIN_OVERLAP = 0.80, 0.60, 5, 0.5
_WORD = re.compile(r"[a-z0-9]+")


def load_cases(directory: Path = CASES) -> list[dict[str, Any]]:
    """Every case file, in name order, with its content SHA."""
    out = []
    for path in sorted(directory.glob("*.json")):
        text = path.read_text()
        out.append({**json.loads(text), "sha": hashlib.sha256(text.encode()).hexdigest()})
    return out


def same(a: str, b: str) -> bool:
    """Do two quotes point at the same line of the notes?"""
    a, b = normalize_quote(a).lower(), normalize_quote(b).lower()
    if a in b or b in a:
        return True
    wa, wb = set(_WORD.findall(a)), set(_WORD.findall(b))
    return bool(wa | wb) and len(wa & wb) / len(wa | wb) >= MIN_OVERLAP


def score_case(case: Mapping[str, Any], kept: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """True/false positives and misses per type for one case (one-to-one matching)."""
    source = normalize_quote(case["notes"])
    open_labels = [dict(x) for x in case["expected"]]
    tp: dict[str, int] = dict.fromkeys(TYPES, 0)
    fp: dict[str, int] = dict.fromkeys(TYPES, 0)
    quotes_ok = 0
    for item in kept:
        quotes_ok += normalize_quote(item["quote"]) in source
        hit = next(
            (
                x
                for x in open_labels
                if x["type"] == item["type"] and same(x["quote"], item["quote"])
            ),
            None,
        )
        if hit is not None:
            open_labels.remove(hit)
            tp[item["type"]] += 1
        elif not any(
            o["type"] == item["type"] and same(o["quote"], item["quote"]) for o in case["optional"]
        ):
            fp[item["type"]] += 1
    fn = {t: sum(x["type"] == t for x in open_labels) for t in TYPES}
    return {"tp": tp, "fp": fp, "fn": fn, "kept": len(kept), "quotes_ok": quotes_ok}


def summarize(rows: Sequence[Mapping[str, Any]], missing: Sequence[str] = ()) -> dict[str, Any]:
    """Per-type precision and recall, quote match, and the gate verdict."""
    ok = [r for r in rows if "error" not in r]
    per_type = {}
    for t in TYPES:
        tp, fp, fn = (sum(r["score"][k][t] for r in ok) for k in ("tp", "fp", "fn"))
        support = tp + fn
        per_type[t] = {
            "support": support,
            "kept": tp + fp,
            "precision": round(tp / (tp + fp), 3) if tp + fp else None,
            "recall": round(tp / support, 3) if support else None,
            "gated": support >= MIN_SUPPORT,
        }
    kept = sum(r["score"]["kept"] for r in ok)
    quotes = sum(r["score"]["quotes_ok"] for r in ok)
    gated = {t: m for t, m in per_type.items() if m["gated"]}
    failing = [
        t
        for t, m in gated.items()
        if (m["precision"] or 0.0) < MIN_PRECISION or (m["recall"] or 0.0) < MIN_RECALL
    ]
    summary = {
        "cases": len(rows) + len(missing),
        "seed_cases": sum(bool(r.get("seed")) for r in rows),
        "errors": len(rows) - len(ok),
        "not_run": list(missing),
        "quote_match": round(quotes / kept, 3) if kept else None,
        "dropped": {k: sum(r.get("dropped", {}).get(k, 0) for r in ok) for k in _drops(ok)},
        "per_type": per_type,
        "failing_types": failing,
        "cost_usd": round(sum(r.get("cost_usd", 0.0) for r in ok), 6),
    }
    summary["passed"] = bool(
        ok
        and not missing
        and not summary["errors"]
        and summary["quote_match"] in (None, 1.0)
        and gated
        and not failing
    )
    return summary


def _drops(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    return sorted({k for r in rows for k in r.get("dropped", {})})


def run(gateway: Gateway, cases_dir: Path = CASES) -> dict[str, Any]:
    """Live: extract every case, store what was kept, and score it."""
    prompt = load_prompt(TASK.name)
    rows: list[dict[str, Any]] = []
    for case in load_cases(cases_dir):
        base = {"id": case["id"], "sha": case["sha"], "seed": case.get("seed", False)}
        date = case["source"]["meeting_date"]
        meeting = Meeting(case["id"], case["release_key"], case["workstream"], date, case["notes"])
        try:
            result = extract(gateway, prompt, meeting, (), case["teams"])
        except AIError as exc:
            rows.append({**base, "error": str(exc)})
            continue
        kept = [{"type": i.type, "quote": i.quote, "owner": i.owner} for i in result.items]
        rows.append(
            {
                **base,
                "kept": kept,
                "returned": result.returned,
                "dropped": result.dropped,
                "cost_usd": round(result.cost_usd, 6),
                "score": score_case(case, kept),
            }
        )
    return report(prompt.label, prompt.sha, gateway.settings.model_for(TASK.role), rows)


def report(
    label: str, sha: str, model: str, rows: list[dict[str, Any]], missing: Sequence[str] = ()
) -> dict[str, Any]:
    """The results-file shape shared by the live run and the CI gate."""
    summary = summarize(rows, missing)
    return {
        "suite": "agent:raid_extractor",
        "task": TASK.name,
        "prompt": label,
        "prompt_sha": sha,
        "model": model,
        "thresholds": {
            "quote_match": 1.0,
            "min_precision": MIN_PRECISION,
            "min_recall": MIN_RECALL,
            "min_support": MIN_SUPPORT,
        },
        "passed": summary["passed"],
        "summary": summary,
        "cases": rows,
    }
