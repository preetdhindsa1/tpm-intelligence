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


def main() -> int:
    """Run live with the Postgres ledger (spend counts against the daily cap)."""
    from sqlalchemy.orm import sessionmaker

    from agents.ledger import PostgresLedger
    from observability.telemetry import init_telemetry
    from pipeline.store.session import make_engine

    telemetry = init_telemetry("tpm-agent-evals")
    try:
        gateway = Gateway(AISettings(), PostgresLedger(sessionmaker(make_engine())))
        report = run(gateway)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        report["measured_at"] = stamp
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f"agent-evals-{stamp}.json").write_text(json.dumps(report, indent=1) + "\n")
        print(
            json.dumps(
                {k: report[k] for k in ("suite", "prompt", "model", "passed", "summary")}, indent=1
            )
        )
        return 0 if report["passed"] else 1
    finally:
        telemetry.shutdown()


if __name__ == "__main__":
    sys.exit(main())
