"""Fact checker on facts built from the real #6395 / #2570 history (CLAUDE.md section 11)."""

from __future__ import annotations

from datetime import datetime
from functools import cache

import pytest

from engine.assess import assess_release
from engine.projection import project
from tests.engine.conftest import K2570, K6395, MAIN_PR, V138, fixture_events, utc
from verify.build import OddsFacts, build_fact_sheet
from verify.checker import Reason, Verdict, check_claim, check_claims
from verify.claims import Claim
from verify.facts import Fact, FactKind, FactSheet, fact_key

F = f"feature:{K6395}::"
PR = f"pr:{MAIN_PR}::"


@cache
def sheet(as_of: datetime) -> FactSheet:
    report = assess_release(project(fixture_events(), as_of), V138)
    odds = {K6395: OddsFacts(0.384, 0.3, 0.46, 0.72, validated=False)}
    return build_fact_sheet(report, odds)


NOV18 = utc(2026, 11, 18)
NOV21 = utc(2026, 11, 21, 12)


def verdict(claim: Claim, as_of: datetime = NOV21) -> tuple[Verdict, Reason | None]:
    c = check_claim(claim, sheet(as_of))
    return c.verdict, c.reason


# ---------------------------------------------------------------- the fact sheet


def test_fact_sheet_has_the_verified_6395_facts() -> None:
    s = sheet(NOV21)
    assert s["release::code_freeze_at"].value == utc(2026, 11, 17, 12)
    assert s[F + "main_pr"].value == MAIN_PR
    assert s[PR + "merged_at"].value == utc(2026, 11, 20, 23, 28, 24)
    assert s[PR + "freeze_status"].value == "merged_after_freeze_with_exception"
    assert s[F + "last_removed_from_release_at"].value.replace(second=0) == utc(2026, 11, 17, 12, 5)
    assert s[F + "in_release"].value is True
    assert s[F + "odds.validated"].value is False


def test_suggested_link_is_not_a_linked_pr() -> None:
    """#143644 mentions #6395 in passing: it stays suggested and is never a PR fact."""
    s = sheet(NOV21)
    assert "pr:kubernetes/kubernetes#143644::state" not in s
    assert s[F + "prs.suggested"].value >= 1


def test_on_nov_18_the_feature_is_out_and_the_main_pr_unmerged() -> None:
    s = sheet(NOV18)
    assert s[F + "in_release"].value is False
    assert s[F + "flag.main_pr_not_merged"].value is True
    assert PR + "merged_at" not in s
    assert s[f"feature:{K2570}::flag.removed_at_freeze"].value is True


# ---------------------------------------------------------------- verdicts


@pytest.mark.parametrize(
    ("claim", "expected"),
    [
        (
            Claim(
                text="#6395 was removed from v1.38 at Code Freeze, Nov 17 12:05 UTC.",
                type=FactKind.DATE,
                refs=(F + "last_removed_from_release_at",),
                value="2026-11-17T12:05:57Z",
            ),
            (Verdict.VERIFIED, None),
        ),
        (
            Claim(
                text="The main PR merged after Code Freeze, with an exception.",
                type=FactKind.LABEL,
                refs=(PR + "freeze_status",),
                value="merged_after_freeze_with_exception",
            ),
            (Verdict.VERIFIED, None),
        ),
        (
            Claim(
                text="Odds of landing are 38% (likely 30-46%), not validated.",
                type=FactKind.PROBABILITY,
                refs=(F + "odds.probability", F + "odds.low", F + "odds.high"),
                value=0.38,
            ),
            (Verdict.VERIFIED, None),
        ),
        (
            Claim(
                text="The main PR merged on Nov 19.",
                type=FactKind.DATE,
                refs=(PR + "merged_at",),
                value="2026-11-19",
            ),
            (Verdict.REMOVED, Reason.WRONG_VALUE),
        ),
        (
            Claim(
                text="Odds of landing are 80%.",
                type=FactKind.PROBABILITY,
                refs=(F + "odds.probability",),
                value=0.384,
            ),
            (Verdict.REMOVED, Reason.TEXT_MISMATCH),
        ),
        (
            Claim(
                text="The SIG Node reviewers are overloaded.",
                type=FactKind.BOOLEAN,
                refs=(),
                value=True,
            ),
            (Verdict.REMOVED, Reason.NO_SUPPORTING_DATA),
        ),
        (
            Claim(
                text="Reviewer load on the main PR is high.",
                type=FactKind.COUNT,
                refs=(PR + "reviewer_load",),
                value=12,
            ),
            (Verdict.REMOVED, Reason.NO_SUPPORTING_DATA),
        ),
        (
            Claim(
                text="Odds are reliable.",
                type=FactKind.BOOLEAN,
                refs=(F + "odds.probability",),
                value=True,
            ),
            (Verdict.REMOVED, Reason.TYPE_MISMATCH),
        ),
        (
            Claim(
                text="The forecast for #6395 is validated.",
                type=FactKind.BOOLEAN,
                refs=(F + "odds.validated",),
                value=True,
            ),
            (Verdict.REMOVED, Reason.WRONG_VALUE),
        ),
    ],
)
def test_verdicts(claim: Claim, expected: tuple[Verdict, Reason | None]) -> None:
    assert verdict(claim) == expected


def test_same_claim_differs_by_prediction_point() -> None:
    """'#6395 is in the release' is false on Nov 18 and true on Nov 21."""
    claim = Claim(
        text="#6395 is in v1.38.", type=FactKind.BOOLEAN, refs=(F + "in_release",), value=True
    )
    assert verdict(claim, NOV18) == (Verdict.REMOVED, Reason.WRONG_VALUE)
    assert verdict(claim, NOV21) == (Verdict.VERIFIED, None)


def test_report_counts_and_rate() -> None:
    claims = [
        Claim(text="5 verified PRs.", type=FactKind.COUNT, refs=(F + "prs.total",), value=99),
        Claim(text="In release.", type=FactKind.BOOLEAN, refs=(F + "in_release",), value=True),
        Claim(text="Unsupported.", type=FactKind.COUNT, refs=(), value=1),
    ]
    report = check_claims(claims, sheet(NOV21))
    assert report.counts["verified"] == 1
    assert report.counts["removed.wrong_value"] == 1
    assert report.counts["removed.no_supporting_data"] == 1
    assert report.counts["removed.text_mismatch"] == 0
    assert report.removal_rate == pytest.approx(2 / 3)
    assert [c.text for c in report.verified] == ["In release."]


# ---------------------------------------------------------------- tolerances


def _one(kind: FactKind, value: object) -> FactSheet:
    return FactSheet([Fact(fact_key("release", "x"), kind, value)])  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("kind", "fact", "claimed", "ok"),
    [
        (FactKind.COUNT, 3, 3, True),
        (FactKind.COUNT, 3, 3.5, False),
        (FactKind.COUNT, 3, True, False),
        (FactKind.PROBABILITY, 0.384, 0.38, True),
        (FactKind.PROBABILITY, 0.384, 0.40, False),
        (FactKind.PROBABILITY, 0.384, 38, False),  # percent, not a probability
        (FactKind.DURATION_DAYS, 15.4, 15, True),
        (FactKind.DURATION_DAYS, 15.4, 16, False),
        (FactKind.DATE, utc(2026, 11, 17, 12), "2026-11-17", True),
        (FactKind.DATE, utc(2026, 11, 17, 23, 30), "2026-11-18", False),
        (FactKind.DATE, utc(2026, 11, 17, 12), "2026-11-17T12:00:40Z", True),
        (FactKind.DATE, utc(2026, 11, 17, 12), "2026-11-17T12:02:00Z", False),
        (FactKind.DATE, utc(2026, 11, 17, 12), "2026-11-17T12:00:00", False),  # naive
        (FactKind.LABEL, "alpha", "Alpha", True),
        (FactKind.BOOLEAN, False, "false", False),
    ],
)
def test_tolerances(kind: FactKind, fact: object, claimed: object, ok: bool) -> None:
    claim = Claim(text="x", type=kind, refs=(fact_key("release", "x"),), value=claimed)  # type: ignore[arg-type]
    assert (check_claim(claim, _one(kind, fact)).verdict is Verdict.VERIFIED) is ok


def test_duplicate_fact_keys_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        FactSheet([Fact("release::x", FactKind.COUNT, 1), Fact("release::x", FactKind.COUNT, 2)])
