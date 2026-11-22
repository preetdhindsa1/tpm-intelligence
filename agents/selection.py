"""Which features are at risk, and which facts an agent sees for one (M3). Pure, no I/O.

Agents only receive engine facts (CLAUDE.md section 8). Selection is deterministic so the
same data always produces the same agent input (and the same cache key).
"""

from __future__ import annotations

from collections.abc import Iterable

from engine.assess import FeatureAssessment
from engine.rules import Severity
from verify.facts import FactSheet

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
