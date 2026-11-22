"""What a TPM could ask for, derived from flags by fixed rules (M3b). Pure, no I/O.

The VP summary's "Asks" section may only phrase these. The AI cannot invent actions such
as "reallocate 3 TPMs": an ask claim must cite one of the ``ask.*`` facts made here.
"""

from __future__ import annotations

from collections.abc import Iterator

from engine.assess import FeatureAssessment
from verify.facts import Fact, FactKind, fact_key


def _short(pr_key: object) -> str:
    return f"#{str(pr_key).rsplit('#', 1)[-1]}"


def asks_for(feature: FeatureAssessment) -> list[tuple[str, str]]:
    """(code, sentence) per applicable rule, in a stable order; one per code."""
    out: dict[str, str] = {}
    for flag in feature.flags:
        pr = flag.facts.get("pull_request")
        match flag.code:
            case "main_pr_not_merged" if feature.in_release:
                out.setdefault(
                    "confirm_exception_or_remove",
                    f"Confirm the exception for {_short(pr)}, "
                    "or remove the feature from the release.",
                )
            case "late_main_pr":
                out.setdefault(
                    "confirm_merge_plan", f"Confirm {_short(pr)} can merge before Code Freeze."
                )
            case "review_waiting":
                out.setdefault("find_reviewer", f"Find a reviewer for {_short(pr)}.")
            case "ci_failing":
                out.setdefault("fix_ci", f"Fix the failing checks on {_short(pr)}.")
            case "no_linked_prs":
                out.setdefault("link_pr", "Link the implementation PR to the planning issue.")
            case "merged_after_freeze" if (
                flag.facts.get("status") == "merged_after_freeze_no_exception"
            ):
                out.setdefault(
                    "confirm_exception", f"Confirm an approved exception exists for {_short(pr)}."
                )
            case _:
                pass
    # A late main PR stops mattering once the freeze-related ask exists.
    if "confirm_exception_or_remove" in out:
        out.pop("confirm_merge_plan", None)
    return sorted(out.items())


def ask_facts(feature: FeatureAssessment) -> Iterator[Fact]:
    """``feature:<key>::ask.<code>`` label facts."""
    for code, sentence in asks_for(feature):
        yield Fact(fact_key("feature", f"ask.{code}", feature.key), FactKind.LABEL, sentence)
