"""Which features are at risk, and which facts an agent sees for one (M3). Pure, no I/O.

Agents only receive engine facts (CLAUDE.md section 8). Selection is deterministic so the
same data always produces the same agent input (and the same cache key).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from agents.asks import ask_facts
from engine.assess import FeatureAssessment
from engine.rules import Severity
from verify.facts import Fact, FactSheet

# Release-level facts every feature note may cite.
_RELEASE_FIELDS = (
    "release::name",
    "release::as_of",
    "release::enhancements_freeze_at",
    "release::code_freeze_at",
    "release::release_at",
)


def is_at_risk(feature: FeatureAssessment, facts: FactSheet) -> bool:
    """In the release and either flagged (warning/critical) or below the base rate."""
    if not feature.in_release:
        return False
    if any(f.severity in (Severity.WARNING, Severity.CRITICAL) for f in feature.flags):
        return True
    p = facts.get(f"feature:{feature.key}::odds.probability")
    base = facts.get(f"feature:{feature.key}::odds.base_rate")
    return (
        p is not None
        and base is not None
        and isinstance(p.value, float)
        and isinstance(base.value, float)
        and p.value < base.value
    )


def feature_facts(feature: FeatureAssessment, facts: FactSheet) -> FactSheet:
    """The feature's own facts, its verified PRs, release dates and its SIGs' unlinked load."""
    keep: list[str] = [k for k in _RELEASE_FIELDS if k in facts]
    prefixes = [f"feature:{feature.key}::"] + [f"pr:{p.key}::" for p in feature.pull_requests]
    keep += [k for k in facts if k.startswith(tuple(prefixes))]
    keep += [k for k in _sig_keys(feature.teams) if k in facts]
    return FactSheet(facts[k] for k in sorted(set(keep)))


def _sig_keys(teams: Iterable[str]) -> list[str]:
    return [f"sig:{t}::unlinked_open_prs" for t in teams]


def critical_flag_keys(feature: FeatureAssessment) -> list[str]:
    """Fact keys of the feature's critical flags: an explanation must cite each one."""
    return sorted(
        {
            f"feature:{feature.key}::flag.{f.code}"
            for f in feature.flags
            if f.severity is Severity.CRITICAL
        }
    )


def risk_rank(feature: FeatureAssessment, facts: FactSheet) -> tuple[int, int, float, str]:
    """Most critical flags first, then most warnings, then lowest odds, then key."""
    crit = sum(f.severity is Severity.CRITICAL for f in feature.flags)
    warn = sum(f.severity is Severity.WARNING for f in feature.flags)
    p = facts.get(f"feature:{feature.key}::odds.probability")
    odds = p.value if p is not None and isinstance(p.value, float) else 1.0
    return (-crit, -warn, odds, feature.key)


_UPDATE_FEATURE_FIELDS = (
    "title",
    "in_release",
    "stage",
    "main_pr",
    "prs.total",
    "prs.merged",
    "prs.open",
    "last_removed_from_release_at",
    "last_added_to_release_at",
)


def update_facts(
    features: Sequence[FeatureAssessment], facts: FactSheet, *, top_n: int = 8, removed_n: int = 10
) -> tuple[FactSheet, list[str], list[str]]:
    """Facts for the executive update: release counts, top at-risk features, removals, asks.

    Returns (sheet, at-risk feature keys in rank order, removed-at-freeze feature keys).
    """
    at_risk = sorted(
        (f for f in features if is_at_risk(f, facts)), key=lambda f: risk_rank(f, facts)
    )
    top = at_risk[:top_n]
    removed = sorted(
        (
            f
            for f in features
            if not f.in_release and any(fl.code == "removed_at_freeze" for fl in f.flags)
        ),
        key=lambda f: f.key,
    )[:removed_n]

    keep = {k for k in facts if k.startswith("release::")}
    for f in top:
        prefix = f"feature:{f.key}::"
        keep |= {prefix + name for name in _UPDATE_FEATURE_FIELDS if prefix + name in facts}
        keep |= {k for k in facts if k.startswith((prefix + "flag.", prefix + "odds."))}
        main = facts.get(prefix + "main_pr")
        if main is not None:
            keep |= {k for k in facts if k.startswith(f"pr:{main.value}::")}
    for f in removed:
        prefix = f"feature:{f.key}::"
        keep |= {
            prefix + n
            for n in ("title", "in_release", "last_removed_from_release_at")
            if prefix + n in facts
        }
        keep |= {k for k in facts if k.startswith(prefix + "flag.removed_at_freeze")}

    rows: list[Fact] = [facts[k] for k in sorted(keep)]
    for f in top:
        rows.extend(ask_facts(f))
    return FactSheet(rows), [f.key for f in top], [f.key for f in removed]
