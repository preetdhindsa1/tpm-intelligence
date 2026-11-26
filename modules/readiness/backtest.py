"""Readiness backtest (#184): the pass rule fixed in ADR-0032 before any result. Pure.

Per release:

- **Freeze replay.** Project the events as of Code Freeze. A feature in the release then is
  *flagged* when ``code_merged`` fails for it (a main PR not merged by the freeze, with no
  exception evidence) or it has an open critical flag.
- **Outcome.** The feature *slipped* if it was out of the release at the outcome cutoff
  (removed after the freeze), or its main PR merged after the freeze. Judged with today's
  history, which is allowed for outcomes.
- **Release-day replay.** Features in the release on release day shipped. *False no-go*:
  one of them fails a feature-level criterion that day.

Pass (pooled over releases with at least ``MIN_FEATURES`` features at the freeze):
recall >= 0.60, precision >= base rate + 0.15, false no-go <= 0.05.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from engine.assess import FeatureAssessment, ReleaseAssessment
from engine.forecast import outcome_cutoff, releases_at
from engine.projection import World
from modules.readiness.rules import code_merged, no_critical_flags

MIN_FEATURES = 20
RECALL_MIN = 0.60
LIFT_MIN = 0.15
FALSE_NO_GO_MAX = 0.05
RULE = (
    f"recall >= {RECALL_MIN:.2f}, precision >= base rate + {LIFT_MIN:.2f}, "
    f"false no-go on release day <= {FALSE_NO_GO_MAX:.2f}; releases with "
    f">= {MIN_FEATURES} features (ADR-0032)"
)


def flagged(f: FeatureAssessment) -> bool:
    """``code_merged`` fails for the feature, or it has an open critical flag."""
    return code_merged([f]).status == "fail" or no_critical_flags([f]).status == "fail"


@dataclass(frozen=True)
class ReleaseResult:
    release_key: str
    features: int  # in the release at Code Freeze
    slipped: int
    flagged: int
    flagged_slipped: int
    shipped: int | None  # in the release on release day; None before the release
    false_no_go: int | None
    counts: bool  # enough features to count toward the pass

    @property
    def base_rate(self) -> float | None:
        return self.slipped / self.features if self.features else None

    def as_dict(self) -> dict[str, object]:
        return {**self.__dict__, "base_rate": _r(self.base_rate)}


def _r(x: float | None) -> float | None:
    return None if x is None else round(x, 3)


def _out_at_cutoff(world: World, release_key: str, key: str) -> bool:
    cutoff = outcome_cutoff(world.releases[release_key])
    return cutoff is not None and release_key not in releases_at(world.features[key], cutoff)


def replay_release(
    release_key: str,
    at: Callable[[datetime], ReleaseAssessment],
    now: World,
) -> ReleaseResult:
    """One release. ``at(when)`` assesses the release from events known at ``when``."""
    release = now.releases[release_key]
    freeze = release.code_freeze_at
    if freeze is None:
        raise ValueError(f"{release_key} has no freeze date")
    at_freeze = [f for f in at(freeze).features if f.in_release]
    late = _merged_after(at(now.as_of), freeze)
    out = {f.key: _out_at_cutoff(now, release_key, f.key) or f.key in late for f in at_freeze}
    marks = {f.key: flagged(f) for f in at_freeze}
    shipped = false_no_go = None
    if release.release_at is not None and release.release_at <= now.as_of:
        on_day = [f for f in at(release.release_at).features if f.in_release]
        shipped, false_no_go = len(on_day), sum(flagged(f) for f in on_day)
    return ReleaseResult(
        release_key, len(at_freeze), sum(out.values()), sum(marks.values()),
        sum(marks[k] and out[k] for k in marks), shipped, false_no_go,
        len(at_freeze) >= MIN_FEATURES,
    )  # fmt: skip


def _merged_after(a: ReleaseAssessment, freeze: datetime) -> set[str]:
    """Features whose main PR (as linked today) merged after the freeze."""
    return {
        f.key for f in a.features
        for p in f.pull_requests
        if p.is_main and p.merged_at is not None and p.merged_at > freeze
    }  # fmt: skip


@dataclass(frozen=True)
class Verdict:
    passed: bool
    recall: float | None
    precision: float | None
    base_rate: float | None
    false_no_go_rate: float | None
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {"passed": self.passed, "recall": _r(self.recall), "precision": _r(self.precision),
                "base_rate": _r(self.base_rate), "false_no_go_rate": _r(self.false_no_go_rate),
                "rule": RULE, "reason": self.reason}  # fmt: skip


def judge(results: Sequence[ReleaseResult]) -> Verdict:
    """The pass rule over the releases that count, pooled."""
    use = [r for r in results if r.counts]
    if not use:
        return Verdict(False, None, None, None, None, "no release has enough features")
    n, slipped = sum(r.features for r in use), sum(r.slipped for r in use)
    hit, marked = sum(r.flagged_slipped for r in use), sum(r.flagged for r in use)
    days = [r for r in use if r.shipped]
    recall = hit / slipped if slipped else None
    precision = hit / marked if marked else None
    base = slipped / n
    fng = (
        (sum(r.false_no_go or 0 for r in days) / sum(r.shipped or 0 for r in days))
        if days
        else None
    )
    fails = []
    if recall is None or recall < RECALL_MIN:
        fails.append(f"recall {_r(recall)} < {RECALL_MIN}")
    if precision is None or precision < base + LIFT_MIN:
        fails.append(f"precision {_r(precision)} < base rate {_r(base)} + {LIFT_MIN}")
    if fng is None or fng > FALSE_NO_GO_MAX:
        fails.append(f"false no-go {_r(fng)} > {FALSE_NO_GO_MAX}")
    return Verdict(not fails, recall, precision, base, fng, "; ".join(fails) or "all three hold")
