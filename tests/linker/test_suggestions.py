"""Deterministic checks on AI link answers (ADR-0011)."""

from __future__ import annotations

from linker.candidates import Candidate, FeatureDoc
from linker.suggestions import DropReason, Outcome, check_suggestion

DOC = FeatureDoc(
    key="kubernetes/enhancements#6395",
    title="Dynamic node-local ephemeral volumes",
    summary="Support dynamically adding node-local ephemeral volumes to existing pods.",
    feature_gates=("DynamicNodeLocalEphemeralVolumes",),
    sigs=("sig/node",),
)
CANDS = [Candidate(DOC, 2, 3.1, ("ephemeral",), ())]
PR = "kubelet: hot-plug ephemeral volumes\nAdds   volume hot-plug to running pods."


def check(key: str | None, pr_quote: str, feature_quote: str):  # type: ignore[no-untyped-def]
    return check_suggestion(key, pr_quote, feature_quote, PR, CANDS)


def test_kept_when_both_quotes_are_found() -> None:
    got = check(DOC.key, "adds volume HOT-PLUG to running pods", "node-local ephemeral volumes")
    assert got.outcome is Outcome.SUGGESTED
    assert got.rank == 2


def test_gate_name_counts_as_feature_text() -> None:
    got = check(DOC.key, "hot-plug ephemeral volumes", "DynamicNodeLocalEphemeralVolumes")
    assert got.outcome is Outcome.SUGGESTED


def test_null_is_none() -> None:
    assert check(None, "", "").outcome is Outcome.NONE


def test_feature_not_on_shortlist_is_dropped() -> None:
    got = check("kubernetes/enhancements#9999", "hot-plug ephemeral volumes", "volumes")
    assert (got.outcome, got.reason) == (Outcome.DROPPED, DropReason.NOT_ON_SHORTLIST)


def test_paraphrased_pr_quote_is_dropped() -> None:
    got = check(DOC.key, "hot-plug of ephemeral volumes", "ephemeral volumes")
    assert got.reason is DropReason.PR_QUOTE_NOT_FOUND


def test_empty_or_stopword_quote_is_dropped() -> None:
    assert check(DOC.key, "", "ephemeral volumes").reason is DropReason.PR_QUOTE_NOT_FOUND
    assert check(DOC.key, "to", "ephemeral volumes").reason is DropReason.PR_QUOTE_EMPTY


def test_invented_feature_quote_is_dropped() -> None:
    got = check(DOC.key, "hot-plug ephemeral volumes", "volume hot-plug API")
    assert got.reason is DropReason.FEATURE_QUOTE_NOT_FOUND
