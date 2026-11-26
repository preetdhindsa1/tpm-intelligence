"""Retro facts for one release (#182, ADR-0032 addendum 2). Pure, no I/O, no AI.

1. **Replay.** Project the world from events dated before each replay day (12:00 UTC, from
   Enhancements Freeze to the outcome cutoff) and run the rule flags. Warnings come only
   from what was known that day, never from today's data.
2. **Slips** are judged at the outcome cutoff (engine/forecast.py: 3 days after Code Freeze,
   or after the release for teams that drop late):
   - ``dropped``: out of the release at the cutoff and in no later release;
   - ``moved``: out of it, but in a later release of the same project;
   - ``late_exception``: landed, but its main PR merged after the freeze with exception
     evidence; or out at the cutoff and re-added later (#6395 in v1.38).
3. **First warning:** the first replay day before the slip on which the feature carried a
   warning flag (``WARNING_FLAGS``). ``lead_time_days`` = slip time - first warning.
   Features that landed but were warned before Code Freeze are counted too
   (``warned_landed``), so a warning that fires for everything cannot look good.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from statistics import mean, median

from engine.assess import ReleaseAssessment
from engine.forecast import outcome_cutoff, releases_at
from engine.freeze import CodeStatus
from engine.projection import Feature, ReleaseInfo, World
from engine.rules import Severity

# ``no_linked_prs`` is left out: early in a cycle most features have no PR yet, so it would
# "warn" about almost every feature on day one and carry no signal.
WARNING_FLAGS = frozenset({
    "late_main_pr", "review_waiting", "ci_failing", "main_pr_not_merged",
    "merged_after_freeze", "removed_at_freeze",
})  # fmt: skip
MIN_GROUP = 10  # patterns per pool only for groups this large (CLAUDE.md section 6)
MODEL_VERSION = "retro-1"


@dataclass(frozen=True)
class Slip:
    feature_key: str
    title: str
    pool: str | None
    slip: str  # dropped | moved | late_exception
    slipped_at: datetime
    first_warning_at: datetime | None
    first_warning_flag: str | None
    lead_time_days: float | None
    moved_to: str | None = None


@dataclass(frozen=True)
class DayFacts:
    """What the rules showed on one replay day, for "said vs showed"."""

    at: datetime
    in_release: int
    features_at_risk: int  # in the release with a warning flag
    critical_flags: int


@dataclass(frozen=True)
class FeatureRow:
    """One planned feature, for patterns per pool."""

    key: str
    pool: str | None
    slipped: bool
    flags_seen: tuple[str, ...]  # warning flags seen on any replay day before Code Freeze


@dataclass(frozen=True)
class RetroRun:
    release_key: str
    computed_at: datetime
    cutoff: datetime
    model_version: str
    planned: int
    slips: tuple[Slip, ...]
    warned_landed: int
    days: tuple[DayFacts, ...]
    features: tuple[FeatureRow, ...] = field(default=())

    def totals(self) -> dict[str, float | int | None]:
        leads = [s.lead_time_days for s in self.slips if s.lead_time_days is not None]
        return {
            "slips": len(self.slips),
            "warned": len(leads),
            "average_lead_time_days": round(mean(leads), 1) if leads else None,
            "median_lead_time_days": round(median(leads), 1) if leads else None,
            "planned": self.planned,
            "warned_landed": self.warned_landed,
        }


def pool_of(feature: Feature) -> str | None:
    """The owning team (one pool per feature), else the first team label."""
    if feature.owning_team:
        return f"sig/{feature.owning_team.removeprefix('sig-')}"
    return min(feature.teams, default=None)


def replay_days(release: ReleaseInfo, cutoff: datetime) -> list[datetime]:
    """Noon UTC each day from Enhancements Freeze (else 5 weeks before Code Freeze)."""
    freeze = release.code_freeze_at or cutoff
    start = release.enhancements_freeze_at or freeze - timedelta(days=35)
    day = datetime.combine(start.date(), time(12), tzinfo=start.tzinfo)
    out = []
    while day < cutoff:
        out.append(day)
        day += timedelta(days=1)
    return [*out, cutoff]


def _later(feature: Feature, release: ReleaseInfo, world: World) -> str | None:
    """A later release of the same project the feature is in now, if any."""
    project = release.key.split(":", 1)[0]
    freeze = release.code_freeze_at
    for key in sorted(releases_at(feature, world.as_of)):
        other = world.releases.get(key)
        if (other and key != release.key and key.startswith(f"{project}:") and freeze
                and other.code_freeze_at and other.code_freeze_at > freeze):  # fmt: skip
            return key
    return None


def _removed_at(feature: Feature, release_key: str, cutoff: datetime) -> datetime:
    out = [m.at for m in feature.membership
           if m.release_key == release_key and not m.added and m.at <= cutoff]  # fmt: skip
    return max(out) if out else cutoff


def _warn(a: ReleaseAssessment) -> dict[str, list[str]]:
    return {f.key: sorted({fl.code for fl in f.flags if fl.code in WARNING_FLAGS})
            for f in a.features}  # fmt: skip


def retro(
    release_key: str,
    replay: Callable[[datetime], ReleaseAssessment],
    now: World,
    computed_at: datetime,
) -> RetroRun:
    """The retro for one release. ``replay(day)`` projects events dated before ``day`` only;
    ``now`` is today's world, used only for membership history (moved, dropped)."""
    release = now.releases[release_key]
    cutoff = outcome_cutoff(release)
    if cutoff is None or cutoff > now.as_of:
        raise ValueError(f"{release_key} has no outcome yet (cutoff {cutoff})")
    start = release.enhancements_freeze_at or cutoff - timedelta(days=60)
    # Planned: in the release at Enhancements Freeze, or added to it before the cutoff.
    planned = {
        f.key: f for f in now.features_ever_in(release_key)
        if release_key in releases_at(f, start)
        or any(m.release_key == release_key and m.added and start <= m.at <= cutoff
               for m in f.membership)
    }  # fmt: skip
    freeze = release.code_freeze_at or cutoff
    first: dict[str, tuple[datetime, str]] = {}
    seen: dict[str, set[str]] = defaultdict(set)
    days: list[DayFacts] = []
    final: ReleaseAssessment | None = None
    for day in replay_days(release, cutoff):
        a = replay(day)
        final = a
        warn = _warn(a)
        live = [f for f in a.features if f.in_release]
        days.append(DayFacts(day, len(live), sum(bool(warn[f.key]) for f in live),
                             sum(fl.severity is Severity.CRITICAL for f in live
                                 for fl in f.flags)))  # fmt: skip
        for key, codes in warn.items():
            if codes and key in planned:
                first.setdefault(key, (day, codes[0]))
                if day < freeze:  # early warnings only; the freeze flags come after it
                    seen[key].update(codes)
    slips: list[Slip] = []
    for key, f in sorted(planned.items()):
        later = None
        if release_key not in releases_at(f, cutoff):
            at = _removed_at(f, release_key, cutoff)
            if release_key in releases_at(f, now.as_of):  # re-added after the cutoff
                kind = "late_exception"
            else:
                later = _later(f, release, now)
                kind = "moved" if later else "dropped"
        else:
            fa = next((x for x in final.features if x.key == key), None) if final else None
            main = next((p for p in fa.pull_requests if p.is_main), None) if fa else None
            if not (main and main.freeze.status is CodeStatus.MERGED_AFTER_FREEZE_WITH_EXCEPTION):
                continue
            kind, at = "late_exception", release.code_freeze_at or cutoff
        warned = first.get(key)
        if warned is not None and warned[0] < at:
            lead = round((at - warned[0]).total_seconds() / 86400, 1)
            slips.append(
                Slip(key, f.title, pool_of(f), kind, at, warned[0], warned[1], lead, later)
            )
        else:
            slips.append(Slip(key, f.title, pool_of(f), kind, at, None, None, None, later))
    slipped = {s.feature_key for s in slips}
    rows = tuple(FeatureRow(k, pool_of(f), k in slipped, tuple(sorted(seen[k])))
                 for k, f in sorted(planned.items()))  # fmt: skip
    warned_landed = sum(1 for r in rows if not r.slipped and r.flags_seen)
    return RetroRun(release_key, computed_at, cutoff, MODEL_VERSION, len(planned), tuple(slips),
                    warned_landed, tuple(days), rows)  # fmt: skip


@dataclass(frozen=True)
class Pattern:
    pool: str
    pattern: str
    text: str
    value: float
    n: int
    releases: tuple[str, ...]


PATTERNS = {
    "slipped": "share of planned features that slipped (dropped, moved or late exception)",
    "late_main_pr": "share of planned features whose main PR opened within 21 days of freeze",
}


def patterns(runs: Iterable[RetroRun]) -> tuple[list[Pattern], int]:
    """Per pool across releases; groups under ``MIN_GROUP`` are counted, not shown."""
    groups: dict[str, list[tuple[str, FeatureRow]]] = defaultdict(list)
    for run in runs:
        for row in run.features:
            if row.pool:
                groups[row.pool].append((run.release_key.split(":", 1)[1], row))
    shown: list[Pattern] = []
    suppressed = 0
    for pool, rows in sorted(groups.items()):
        if len(rows) < MIN_GROUP:
            suppressed += 1
            continue
        rels = tuple(sorted({r for r, _ in rows}))
        n = len(rows)
        tests: dict[str, Callable[[FeatureRow], bool]] = {
            "slipped": lambda r: r.slipped,
            "late_main_pr": lambda r: "late_main_pr" in r.flags_seen,
        }
        for name, test in tests.items():
            value = round(sum(test(r) for _, r in rows) / n, 3)
            shown.append(Pattern(pool, name, PATTERNS[name], value, n, rels))
    return shown, suppressed


def same_day(days: Sequence[DayFacts], when: datetime) -> DayFacts | None:
    """The replay day on or just before ``when`` (said vs showed)."""
    before = [d for d in days if d.at <= when]
    return before[-1] if before else None
