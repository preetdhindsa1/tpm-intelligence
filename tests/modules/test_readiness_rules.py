"""Readiness criteria on the real #6395 / #2570 history (CLAUDE.md section 11 fixtures)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any

from connectors.load import load_team
from engine.assess import ReleaseAssessment, assess_release
from engine.projection import project
from modules.raid.store import RaidItem
from modules.readiness.rules import ALL, MAX_EVIDENCE, ci_green, evaluate, risks_owned, verdict
from tests.engine.conftest import K6395, MAIN_PR, V138, fixture_events, utc


def report(as_of: datetime) -> ReleaseAssessment:
    return assess_release(project(fixture_events(), as_of), V138)


def by_id(as_of: datetime, **kw: Any) -> dict[str, Any]:
    r = evaluate(report(as_of), **kw)
    return {c.id: c for c in r.criteria} | {"verdict": r.verdict, "as_of": r.as_of}


def risk(n: int, review: str = "confirmed", owner: str | None = "Release Signal",
         status: str = "open") -> RaidItem:  # fmt: skip
    return RaidItem(n, f"k{n}", V138, "K8S", "risk", f"Risk {n}", "quote", "doc", "2026-11-18",
                    owner=owner, status=status, review=review,  # type: ignore[arg-type]
                    raid_id=f"K8S-R-{n:03d}" if review != "suggested" else None)  # fmt: skip


def test_before_the_freeze_the_unmerged_main_pr_fails_code_merged() -> None:
    c = by_id(utc(2026, 11, 10))
    code = c["code_merged"]
    assert code.status == "fail"
    assert any(e.ref == f"feature:{K6395}" and MAIN_PR in e.text
               for e in code.evidence)  # fmt: skip
    assert c["no_critical_flags"].status == "pass"
    assert c["verdict"] == "not_ready"
    assert c["as_of"] == utc(2026, 11, 10)


def test_a_feature_removed_at_the_freeze_does_not_count() -> None:
    c = by_id(utc(2026, 11, 18))
    refs = [e.ref for cid in ("code_merged", "no_critical_flags") for e in c[cid].evidence]
    assert K6395 not in " ".join(refs)


def test_readded_with_an_exception_resolves_both_critical_flags() -> None:
    r = report(utc(2026, 11, 21, 3))
    f = next(f for f in r.features if f.key == K6395)
    assert {"removed_at_freeze", "main_pr_not_merged"} <= {fl.code for fl in f.flags}
    c = by_id(utc(2026, 11, 21, 3))
    code = c["code_merged"]
    # #6395's main PR counts (exception); #2570 has no linked PR in the fixture, so unknown.
    assert (code.status, code.evidence) == ("unknown", ())
    assert "1 has no verified PR, so it is not counted" in code.detail
    assert c["no_critical_flags"].status == "pass"
    assert c["verdict"] == "unknown"  # no confirmed risks, no docs repo


def test_ci_counts_open_prs_with_failing_checks_and_says_what_it_counts() -> None:
    r = report(utc(2026, 11, 10))
    features = [f for f in r.features if f.in_release]
    f = next(f for f in features if f.key == K6395)
    pr = replace(f.pull_requests[0], state="open", failing_checks=2)
    c = ci_green([replace(f, pull_requests=(pr,))])
    assert (c.status, c.count, c.evidence[0].ref) == ("fail", 1, f"pr:{pr.key}")
    assert "required checks" in c.detail
    assert ci_green([replace(f, pull_requests=())]).status == "unknown"


def test_risks_owned_counts_confirmed_items_only() -> None:
    assert risks_owned([]).status == "unknown"
    waiting = risks_owned([risk(1, review="suggested", owner=None)])
    assert waiting.status == "unknown"
    assert "1 suggested risks wait for review" in waiting.detail
    unowned = risks_owned([risk(2, owner=None), risk(3), risk(4, owner=None, status="closed")])
    assert (unowned.status, unowned.count) == ("fail", 1)
    assert unowned.evidence[0].ref == "raid:K8S-R-002"
    assert risks_owned([risk(5), risk(6, review="edited")]).status == "pass"


def test_docs_merged_needs_a_docs_repo_and_linked_docs_prs() -> None:
    as_of = utc(2026, 11, 21, 3)
    assert by_id(as_of)["docs_merged"].status == "unknown"
    other = by_id(as_of, docs_repos=["kubernetes/website"])["docs_merged"]
    assert "No docs PRs" in other.detail
    # Treat the code repo as the docs repo to exercise the rule on real PR states.
    kk = by_id(as_of, docs_repos=["kubernetes/kubernetes"])["docs_merged"]
    assert kk.status == "fail"  # #143442 closed unmerged
    assert any("#143442" in e.ref for e in kk.evidence)


def test_only_configured_criteria_run_and_risks_are_per_release() -> None:
    other = replace(risk(2, owner=None), release_key="kubernetes:v1.37")
    r = evaluate(report(utc(2026, 11, 21, 3)), [risk(1), other], ["code_merged", "risks_owned"])
    assert [c.id for c in r.criteria] == ["code_merged", "risks_owned"]
    assert r.verdict == "unknown"  # #2570 has no linked PR
    assert r.criteria[1].status == "pass"  # v1.37's unowned risk is not this release's
    assert all(len(c.evidence) <= MAX_EVIDENCE for c in r.criteria)


def test_verdict_and_team_config() -> None:
    assert verdict([]) == "unknown"
    team = load_team("kubernetes")
    assert team.readiness.criteria == ALL
    assert team.readiness.docs_repos == ()
