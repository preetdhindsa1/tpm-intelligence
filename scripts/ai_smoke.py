"""End-to-end check of the AI plumbing with one real, cheap call (Phase 2 M2).

    make ai-smoke

Sends the real-shaped #6395 / v1.38 fact sheet (evals/cases/fact_sets.json) to the
``simple`` model, asks for claims, fact-checks them, and prints the verdicts, cost and
today's budget use. A second run with the same facts is served from the cache for $0.
"""

from __future__ import annotations

import json
import sys

from sqlalchemy.orm import sessionmaker

from agents.gateway import AIError, Gateway, TaskSpec, verify_output
from agents.ledger import PostgresLedger
from agents.prompts import load_prompt
from agents.schemas import ClaimsOut
from agents.settings import AISettings, ModelRole
from evals.fact_checker import load_fact_sets
from observability.telemetry import init_telemetry
from pipeline.store.session import make_engine

TASK = TaskSpec("smoke", ModelRole.SIMPLE, effort="low", max_tokens=4000, essential=False)


def main() -> int:
    """Run once; exit 1 if the call fails."""
    telemetry = init_telemetry("tpm-ai-smoke")
    try:
        settings = AISettings()
        ledger = PostgresLedger(sessionmaker(make_engine()))
        facts = load_fact_sets()["k8s"]
        gateway = Gateway(settings, ledger)
        try:
            response = gateway.run(TASK, load_prompt("smoke"), facts.as_prompt_rows(), ClaimsOut)
        except AIError as exc:
            print(f"AI call failed: {exc}", file=sys.stderr)
            return 1
        report = verify_output(response, facts, ledger)
        print(
            json.dumps(
                {
                    "model": response.model,
                    "cached": response.cached,
                    "cost_usd": round(response.cost_usd, 6),
                    "budget_used_fraction": round(gateway.budget_fraction(), 4),
                    "counts": report.counts,
                    "claims": [
                        {
                            "verdict": c.verdict.value,
                            "reason": c.reason.value if c.reason else None,
                            "text": c.claim.text,
                            "detail": c.detail,
                        }
                        for c in report.checked
                    ],
                },
                indent=1,
            )
        )
        return 0
    finally:
        telemetry.shutdown()


if __name__ == "__main__":
    sys.exit(main())
