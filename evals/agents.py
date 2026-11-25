"""Live agent evals (paid): run the risk analyst on the golden cases and score it.

    make evals-live        # ~$0.03 with Haiku; records spend in the normal AI ledger

Gate (all must hold, ADR-0010):
* removal rate of the shown attempt <= 10% overall (claims removed / claims checked);
* every critical flag covered by a verified claim (100%);
* odds honesty: claims citing odds also cite "not validated" when it is false (100%);
* 2-5 claims shown per case.

The results file records the prompt SHA and model, so CI can require a passing run for the
exact prompt and model in the repo (evals/agent_gate.py) without making paid calls.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agents.gateway import AIError, Gateway
from agents.loop import run_loop
from agents.prompts import load_prompt
from agents.risk_analyst import TASK
from agents.settings import AISettings
from evals.agent_metrics import score_case
from verify.facts import FactSheet

CASES = Path(__file__).parent / "cases" / "agent_risk_notes.json"
VP_CASES = Path(__file__).parent / "cases" / "agent_vp_updates.json"
MAX_WORDS = 220
OUT = Path(__file__).resolve().parent.parent / "docs" / "results"
MAX_REMOVAL_RATE = 0.10


def run(gateway: Gateway, cases_path: Path = CASES) -> dict[str, Any]:
    """Run every case; return the scored report."""
    prompt = load_prompt("risk_analyst")
    cases = json.loads(cases_path.read_text())
    rows: list[dict[str, Any]] = []
    for case in cases:
        facts = FactSheet.from_records(case["facts"])
        try:
            result = run_loop(gateway, TASK, prompt, facts)
        except AIError as exc:
            rows.append({"id": case["id"], "error": str(exc)})
            continue
        rows.append(
            {
                "id": case["id"],
                "attempts": len(result.attempts),
                "cost_usd": round(result.cost_usd, 6),
                "model": result.best.model,
                **score_case(
                    result.attempts[0].report,
                    result.best.report,
                    facts,
                    case["critical_flag_keys"],
                ),
                "claims": [c.text for c in result.claims],
                "removed": [
                    {
                        "text": c.claim.text,
                        "reason": c.reason.value if c.reason else None,
                        "detail": c.detail,
                    }
                    for c in result.best.report.checked
                    if c.reason is not None
                ],
            }
        )
    ok = [r for r in rows if "error" not in r]
    removed = sum(r["claims_total"] - r["claims_shown"] for r in ok)
    checked = sum(r["claims_total"] for r in ok)
    coverage = [r["critical_coverage"] for r in ok if r["critical_coverage"] is not None]
    summary = {
        "cases": len(rows),
        "errors": len(rows) - len(ok),
        "removal_rate_shown": round(removed / checked, 4) if checked else None,
        "removal_rate_first_attempt_mean": round(
            sum(r["removal_rate_first_attempt"] or 0 for r in ok) / len(ok), 4
        )
        if ok
        else None,
        "critical_coverage_min": min(coverage) if coverage else None,
        "odds_honest_all": all(r["odds_honest"] for r in ok),
        "claims_shown_range": [
            min(r["claims_shown"] for r in ok),
            max(r["claims_shown"] for r in ok),
        ]
        if ok
        else None,
        "retried_cases": sum(r["attempts"] > 1 for r in ok),
        "cost_usd": round(sum(r["cost_usd"] for r in ok), 6),
    }
    passed = (
        not summary["errors"]
        and summary["removal_rate_shown"] is not None
        and summary["removal_rate_shown"] <= MAX_REMOVAL_RATE
        and (summary["critical_coverage_min"] in (None, 1.0))
        and summary["odds_honest_all"]
        and summary["claims_shown_range"] is not None
        and summary["claims_shown_range"][0] >= 2
        and summary["claims_shown_range"][1] <= 5
    )
    return {
        "suite": "agent:risk_analyst",
        "task": TASK.name,
        "prompt": prompt.label,
        "prompt_sha": prompt.sha,
        "model": gateway.settings.model_for(TASK.role),
        "thresholds": {"max_removal_rate": MAX_REMOVAL_RATE, "critical_coverage": 1.0},
        "passed": passed,
        "summary": summary,
        "cases": rows,
    }


def run_vp(gateway: Gateway, cases_path: Path = VP_CASES) -> dict[str, Any]:
    """VP summarizer on the golden release fact sheets.

    Gate: removal rate <= 10%; <= 220 words shown; the top 3 at-risk features each cited;
    every ask grounded in a rule-made ask fact; odds honesty; a non-empty summary.
    """
    from agents.schemas import ExecUpdateOut
    from agents.vp_summary import TASK as VP_TASK
    from agents.vp_summary import trim, verified_sections
    from evals.agent_metrics import asks_grounded, features_covered, odds_honest

    prompt = load_prompt("vp_summary")
    rows: list[dict[str, Any]] = []
    for case in json.loads(cases_path.read_text()):
        facts = FactSheet.from_records(case["facts"])
        try:
            result = run_loop(
                gateway,
                VP_TASK,
                prompt,
                facts,
                extra_inputs={
                    "at_risk_order": case["at_risk_order"],
                    "removed_at_freeze": case["removed_at_freeze"],
                },
                output_model=ExecUpdateOut,
            )
        except AIError as exc:
            rows.append({"id": case["id"], "error": str(exc)})
            continue
        output = result.best.output
        assert isinstance(output, ExecUpdateOut)  # noqa: S101
        raw = verified_sections(output, result.best.report)
        sections, dropped = trim(raw, MAX_WORDS)
        shown = [c for claims in sections.values() for c in claims]
        best = result.best.report
        rows.append(
            {
                "id": case["id"],
                "attempts": len(result.attempts),
                "cost_usd": round(result.cost_usd, 6),
                "model": result.best.model,
                "claims_total": len(best.checked),
                "claims_verified": len(best.verified),
                "removal_rate_first_attempt": result.attempts[0].report.removal_rate,
                "removal_rate_shown_attempt": best.removal_rate,
                "words_verified": sum(
                    len(c.text.split()) for claims in raw.values() for c in claims
                ),
                "words_shown": sum(len(c.text.split()) for c in shown),
                "trimmed_for_length": dropped,
                "top3_covered": features_covered(shown, case["at_risk_order"][:3]),
                "asks_grounded": asks_grounded(sections["asks"]),
                "odds_honest": odds_honest(best, facts),
                "summary_present": bool(sections["summary"]),
                "sections": {k: [c.text for c in v] for k, v in sections.items()},
                "removed": [
                    {
                        "text": c.claim.text,
                        "reason": c.reason.value if c.reason else None,
                        "detail": c.detail,
                    }
                    for c in best.checked
                    if c.reason is not None
                ],
            }
        )
    ok = [r for r in rows if "error" not in r]
    removed = sum(r["claims_total"] - r["claims_verified"] for r in ok)
    checked = sum(r["claims_total"] for r in ok)
    top3 = [r["top3_covered"] for r in ok if r["top3_covered"] is not None]
    summary = {
        "cases": len(rows),
        "errors": len(rows) - len(ok),
        "removal_rate_shown": round(removed / checked, 4) if checked else None,
        "words_shown_max": max((r["words_shown"] for r in ok), default=None),
        "trimmed_cases": sum(r["trimmed_for_length"] > 0 for r in ok),
        "top3_coverage_min": min(top3) if top3 else None,
        "asks_grounded_all": all(r["asks_grounded"] for r in ok),
        "odds_honest_all": all(r["odds_honest"] for r in ok),
        "summary_present_all": all(r["summary_present"] for r in ok),
        "retried_cases": sum(r["attempts"] > 1 for r in ok),
        "cost_usd": round(sum(r["cost_usd"] for r in ok), 6),
    }
    passed = bool(
        ok
        and not summary["errors"]
        and summary["removal_rate_shown"] is not None
        and summary["removal_rate_shown"] <= MAX_REMOVAL_RATE
        and summary["words_shown_max"] is not None
        and summary["words_shown_max"] <= MAX_WORDS
        and summary["top3_coverage_min"] in (None, 1.0)
        and summary["asks_grounded_all"]
        and summary["odds_honest_all"]
        and summary["summary_present_all"]
    )
    return {
        "suite": "agent:vp_summary",
        "task": VP_TASK.name,
        "prompt": prompt.label,
        "prompt_sha": prompt.sha,
        "model": gateway.settings.model_for(VP_TASK.role),
        "thresholds": {
            "max_removal_rate": MAX_REMOVAL_RATE,
            "max_words": MAX_WORDS,
            "top3_coverage": 1.0,
        },
        "passed": passed,
        "summary": summary,
        "cases": rows,
    }


def main(argv: list[str] | None = None) -> int:
    """Run live with the Postgres ledger (spend counts against the daily cap)."""
    import argparse

    from sqlalchemy.orm import sessionmaker

    from agents.ledger import PostgresLedger
    from observability.telemetry import init_telemetry
    from pipeline.store.session import make_engine

    parser = argparse.ArgumentParser(prog="evals.agents")
    parser.add_argument(
        "--suite",
        choices=["all", "risk_analyst", "vp_summary", "link_suggester", "raid_extractor"],
        default="all",
    )
    args = parser.parse_args(argv)

    telemetry = init_telemetry("tpm-agent-evals")
    try:
        gateway = Gateway(AISettings(), PostgresLedger(sessionmaker(make_engine())))
        from evals.link_suggester import run as run_links
        from evals.raid_extractor import run as run_raid

        runners = {
            "risk_analyst": run,
            "vp_summary": run_vp,
            "link_suggester": run_links,
            "raid_extractor": run_raid,
        }
        chosen = list(runners) if args.suite == "all" else [args.suite]
        all_passed = True
        for name in chosen:
            report = runners[name](gateway)
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            report["measured_at"] = stamp
            OUT.mkdir(parents=True, exist_ok=True)
            path = OUT / f"agent-evals-{stamp}-{name}.json"
            path.write_text(json.dumps(report, indent=1) + "\n")
            keys = ("suite", "prompt", "model", "passed", "summary")
            print(json.dumps({k: report[k] for k in keys}, indent=1))
            all_passed = all_passed and bool(report["passed"])
        return 0 if all_passed else 1
    finally:
        telemetry.shutdown()


if __name__ == "__main__":
    sys.exit(main())
