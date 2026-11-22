"""Agent eval scoring and the CI gate (no paid calls)."""

from __future__ import annotations

import json
from pathlib import Path

from agents.gateway import Gateway
from agents.ledger import MemoryLedger
from agents.prompts import load_prompt
from agents.settings import AISettings
from evals import agent_gate, agents
from evals.agent_metrics import critical_coverage, odds_honest
from tests.agents.test_risk_analyst import F, Sequenced
from verify.checker import check_claims
from verify.claims import Claim
from verify.facts import Fact, FactKind, FactSheet

FACTS = FactSheet(
    [
        Fact(F + "flag.main_pr_not_merged", FactKind.BOOLEAN, True),
        Fact(F + "odds.probability", FactKind.PROBABILITY, 0.2),
        Fact(F + "odds.validated", FactKind.BOOLEAN, False),
    ]
)


def claim(text: str, refs: list[str], value: object, kind: FactKind) -> Claim:
    return Claim(text=text, type=kind, refs=tuple(refs), value=value)  # type: ignore[arg-type]


def test_coverage_and_honesty() -> None:
    honest = check_claims(
        [
            claim("Main PR not merged.", [F + "flag.main_pr_not_merged"], True, FactKind.BOOLEAN),
            claim(
                "Odds 20%, not validated.",
                [F + "odds.probability", F + "odds.validated"],
                0.2,
                FactKind.PROBABILITY,
            ),
        ],
        FACTS,
    )
    assert critical_coverage(honest, [F + "flag.main_pr_not_merged"]) == 1.0
    assert odds_honest(honest, FACTS)
    dishonest = check_claims(
        [claim("Odds are 20%.", [F + "odds.probability"], 0.2, FactKind.PROBABILITY)], FACTS
    )
    assert not odds_honest(dishonest, FACTS)
    assert critical_coverage(dishonest, [F + "flag.main_pr_not_merged"]) == 0.0


def test_live_runner_scores_with_a_fake_client(tmp_path: Path) -> None:
    from tests.agents.test_risk_analyst import GOOD

    case = {
        "id": "c1",
        "release": "kubernetes:v1.38",
        "as_of": "2026-11-10T00:00:00+00:00",
        "feature_key": "kubernetes/enhancements#6395",
        "critical_flag_keys": [],
        "facts": [
            {
                "key": F + "flag.late_main_pr.days_before_freeze",
                "kind": "duration_days",
                "value": 14.8,
            },
            {"key": F + "odds.probability", "kind": "probability", "value": 0.384},
            {"key": F + "odds.validated", "kind": "boolean", "value": False},
        ],
    }
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([case]))
    report = agents.run(Gateway(AISettings(), MemoryLedger(), Sequenced(GOOD)), path)
    assert report["summary"]["removal_rate_shown"] == 0.0
    assert report["summary"]["odds_honest_all"] is True
    assert report["passed"] is True


def test_gate_requires_a_passing_run_for_the_current_prompt_and_model(tmp_path: Path) -> None:
    from agents.risk_analyst import TASK

    assert not agent_gate.check(TASK, tmp_path)["passed"]
    prompt = load_prompt("risk_analyst")
    stale = {
        "task": "risk_analyst",
        "prompt_sha": "old",
        "model": "claude-haiku-5-5",
        "passed": True,
    }
    (tmp_path / "agent-evals-20261122T000000Z.json").write_text(json.dumps(stale))
    assert not agent_gate.check(TASK, tmp_path)["passed"]
    current = {
        "task": "risk_analyst",
        "prompt_sha": prompt.sha,
        "model": "claude-haiku-5-5",
        "passed": True,
        "summary": {},
    }
    (tmp_path / "agent-evals-20261122T000001Z.json").write_text(json.dumps(current))
    assert agent_gate.check(TASK, tmp_path)["passed"]
    other = {**current, "task": "vp_summary"}  # another agent's file never counts
    (tmp_path / "agent-evals-20261122T000002Z.json").write_text(json.dumps(other))
    assert agent_gate.check(TASK, tmp_path)["results_file"] == "agent-evals-20261122T000001Z.json"


def test_vp_runner_scores_with_a_fake_client(tmp_path: Path) -> None:
    from agents.gateway import Gateway
    from agents.selection import update_facts
    from tests.agents.test_gateway import FakeClient, Response
    from tests.agents.test_vp_summary import OUTPUT, state

    features, facts = state()
    sheet, order, removed = update_facts(features, facts)
    case = {
        "id": "v1.38-test",
        "release": "kubernetes:v1.38",
        "as_of": "2026-11-21T03:00:00+00:00",
        "at_risk_order": order,
        "removed_at_freeze": removed,
        "facts": sheet.to_records(),
    }
    path = tmp_path / "vp.json"
    path.write_text(json.dumps([case], default=str))
    client = FakeClient(Response(parsed_output=OUTPUT, model="claude-opus-5-5"))
    report = agents.run_vp(Gateway(AISettings(), MemoryLedger(), client), path)
    row = report["cases"][0]
    assert row["asks_grounded"] is True
    assert row["removed"][0]["reason"] == "no_supporting_data"
    assert report["summary"]["removal_rate_shown"] > 0.10  # 1 of 4 removed: fails the gate
    assert report["passed"] is False


def test_link_suggester_scoring_and_gate() -> None:
    from evals.link_suggester import gate, summarize, verdict
    from linker.suggestions import Outcome

    key = "kubernetes/enhancements#6395"
    assert verdict("positive", key, Outcome.SUGGESTED, key) == "correct"
    assert verdict("positive", key, Outcome.SUGGESTED, "other") == "wrong_feature"
    assert verdict("negative", None, Outcome.SUGGESTED, key) == "false_link"
    assert verdict("negative", None, Outcome.NONE, None) == "none"
    assert verdict("positive", key, Outcome.DROPPED, key) == "dropped"

    rows = [
        *({"kind": "positive", "verdict": "correct", "cost_usd": 0.0} for _ in range(8)),
        {"kind": "positive", "verdict": "none", "cost_usd": 0.0},
        {"kind": "positive", "verdict": "wrong_feature", "cost_usd": 0.0},
        *({"kind": "negative", "verdict": "none", "cost_usd": 0.0} for _ in range(4)),
        {"kind": "negative", "verdict": "false_link", "cost_usd": 0.0},
    ]
    s = summarize(rows)
    assert s["precision"] == 0.8
    assert s["recall_positive"] == 0.8
    assert s["false_link_rate_negative"] == 0.2
    assert gate(s)
    always_null = summarize([{"kind": "positive", "verdict": "none", "cost_usd": 0.0}] * 5)
    assert not gate(always_null)
