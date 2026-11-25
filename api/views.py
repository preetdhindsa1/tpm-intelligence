"""Convert engine results into API response models."""

from __future__ import annotations

from typing import Any

from api.schemas import (
    CouplingOut,
    CurveFeatureOut,
    DependenciesOut,
    DepFeatureOut,
    DepPROut,
    FeatureDetailOut,
    FeatureOutcomeOut,
    FeatureRowOut,
    FlagOut,
    GraphEdgeOut,
    GraphNodeOut,
    GraphOut,
    LabBucketOut,
    LabCapOut,
    LabCollisionOut,
    LabDayOut,
    LabFirstPassOut,
    LabOut,
    LabSizeOut,
    LabWeekOut,
    MergeDateOut,
    MergeDatesOut,
    OddsOut,
    PodOut,
    PullRequestOut,
    ReleaseOut,
    SigPairOut,
    StatedDependencyOut,
    SummaryOut,
    TimelineEntryOut,
    WaitingPROut,
)
from api.service import ReleaseSummary, ReleaseView
from connectors.load import display_name_for_project, team_for_project
from connectors.schema import TeamConfig
from engine.assess import FeatureAssessment
from engine.forecast import Forecast, outcome_definition
from engine.lab import LabReport, LaneSpec
from engine.merge_date import MergeDateForecast
from engine.portfolio import LabFacts, ProgramFacts
from engine.projection import ReleaseInfo, key_number


def _project(release: ReleaseInfo) -> str:
    return release.key.split(":", 1)[0] if ":" in release.key else release.key


def _release_fields(release: ReleaseInfo) -> dict[str, Any]:
    project = _project(release)
    team = team_for_project(project)
    return {
        "key": release.key,
        "name": release.name,
        "project": project,
        "display_name": display_name_for_project(project),
        "cycle_start_at": release.cycle_start_at,
        "enhancements_freeze_at": release.enhancements_freeze_at,
        "code_freeze_at": release.code_freeze_at,
        "release_at": release.release_at,
        "has_lab": bool(team and team.author_lanes),
    }


def release_out(view: ReleaseView) -> ReleaseOut:
    """Release header."""
    r = view.assessment.release
    return ReleaseOut(
        **_release_fields(r),
        features_in_release=sum(1 for f in view.assessment.features if f.in_release),
        features_ever_in_release=len(view.assessment.features),
        as_of=view.assessment.as_of,
    )


def release_summary_out(summary: ReleaseSummary) -> ReleaseOut:
    """Release header from the cheap listing (same shape as :func:`release_out`)."""
    r = summary.release
    return ReleaseOut(
        **_release_fields(r),
        features_in_release=summary.features_in_release,
        features_ever_in_release=summary.features_ever_in_release,
        as_of=summary.as_of,
    )


def odds_out(fc: Forecast | None, view: ReleaseView | None = None) -> OddsOut:
    """Odds, or why there are none."""
    if fc is None:
        return OddsOut(status="not_in_release")
    return OddsOut(
        validated=view.validation.validated if view else False,
        base_rate=view.recalibration.base_rate if view else None,
        raw_probability=fc.raw_probability,
        status=fc.status,
        probability=fc.probability,
        low=fc.low,
        high=fc.high,
        open_prs=list(fc.open_prs),
        pr_on_time=dict(fc.pr_on_time),
        new_pr_needed=fc.new_pr_needed,
    )


def _number(key: str) -> int:
    return key_number(key)


def _label(key: str) -> str:
    """Short name: ``#6395`` for a GitHub issue, the key itself for Jira (``KAFKA-20682``)."""
    return f"#{key_number(key)}" if "#" in key else key


def _url(key: str) -> str:
    repo, number = key.rsplit("#", 1)
    return f"https://github.com/{repo}/pull/{number}"


def feature_row(view: ReleaseView, a: FeatureAssessment) -> FeatureRowOut:
    """One table row."""
    feature = view.world.features[a.key]
    return FeatureRowOut(
        key=a.key,
        number=_number(a.key),
        title=a.title,
        url=feature.url,
        in_release=a.in_release,
        tracked=a.tracked,
        stage=a.stage,
        teams=list(a.teams),
        odds=odds_out(view.forecasts.get(a.key), view),
        flags=[
            FlagOut(code=f.code, severity=f.severity.value, message=f.message, facts=dict(f.facts))
            for f in a.flags
        ],
        prs_total=len(a.pull_requests),
        prs_merged=sum(1 for p in a.pull_requests if p.state == "merged"),
        prs_open=sum(1 for p in a.pull_requests if p.state == "open"),
        suggested_prs=len(a.suggested_pull_requests),
    )


def feature_detail(view: ReleaseView, a: FeatureAssessment) -> FeatureDetailOut:
    """Feature page."""
    row = feature_row(view, a)
    assumptions: dict[str, Any] = {
        "calibration": view.calibration.describe(),
        "recalibration": {
            "training_releases": list(view.recalibration.training_releases),
            "training_cases": view.recalibration.n,
            "base_rate": view.recalibration.base_rate,
        },
        "validation": view.validation.as_dict(),
        "outcome_definition": outcome_definition(view.assessment.release),
        "note": "Decision support: if these measured inputs hold, the odds are likely in "
        "the range shown. Not a guarantee.",
    }
    md = view.merge_dates.get(a.key)
    return FeatureDetailOut(
        **row.model_dump(),
        merge_date=merge_date_out(md) if md else None,
        merge_date_validation=view.date_validation.as_dict(),
        pull_requests=[
            PullRequestOut(
                key=p.key,
                url=_url(p.key),
                title=p.title,
                state=p.state,
                created_at=p.created_at,
                merged_at=p.merged_at,
                review_rounds=p.review_rounds,
                review_records=p.review_records,
                failing_checks=p.failing_checks,
                freeze_status=p.freeze.status.value,
                counts_for_release=p.freeze.counts,
                is_main=p.is_main,
            )
            for p in a.pull_requests
        ],
        suggested_pull_requests=list(a.suggested_pull_requests),
        critical_path=list(a.critical_path),
        timeline=[TimelineEntryOut(at=e.at, kind=e.kind, ref=e.ref) for e in a.timeline],
        assumptions=assumptions,
    )


# ---- dashboard (ADR-0013) -------------------------------------------------------------------

_SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}

OUTCOMES = (
    "landed",
    "landed_prs_after_freeze",
    "landed_main_pr_open",
    "readded_after_freeze",
    "removed_after_freeze",
    "removed_at_freeze",
    "removed_before_freeze",
    "too_early",
)


def _max_severity(a: FeatureAssessment) -> str | None:
    levels = [f.severity.value for f in a.flags]
    return max(levels, key=lambda s: _SEVERITY_ORDER[s]) if levels else None


def feature_outcome(view: ReleaseView, a: FeatureAssessment) -> str:
    """Fact-based outcome at Code Freeze, split by what the rule flags show.

    Based on ADR-0005's outcome (still in the release 3 days after Code Freeze), except
    that a feature removed at freeze and back in the release is always "re-added".
    """
    from engine.forecast import landed, outcome_cutoff

    release = view.assessment.release
    codes = {f.code for f in a.flags}
    cutoff = outcome_cutoff(release)
    if cutoff is None or view.assessment.as_of < cutoff:
        return "too_early"
    if a.in_release and "removed_at_freeze" in codes:
        # Removed at freeze and back by exception, even when re-added inside the 3-day
        # window the forecast's outcome uses: the dashboard tile counts every removal, so
        # the chart must too (decision 2026-11-22, ADR-0013).
        return "readded_after_freeze"
    if landed(view.world.features[a.key], release):
        if not a.in_release:
            return "removed_after_freeze"
        if "main_pr_not_merged" in codes:
            return "landed_main_pr_open"
        if "merged_after_freeze" in codes:
            return "landed_prs_after_freeze"
        return "landed"
    if a.in_release:
        return "readded_after_freeze"
    return "removed_at_freeze" if "removed_at_freeze" in codes else "removed_before_freeze"


def summary_out(view: ReleaseView) -> SummaryOut:
    """Dashboard tiles: counts of computed facts only."""
    from collections import Counter

    a = view.assessment
    outcomes = {f.key: feature_outcome(view, f) for f in a.features}
    counts = Counter(outcomes.values())
    early = all(o == "too_early" for o in outcomes.values())
    return SummaryOut(
        release=a.release.key,
        as_of=a.as_of,
        phase="before_freeze" if early else "after_freeze",
        features_in_release=sum(f.in_release for f in a.features),
        features_ever=len(a.features),
        landed=None
        if early
        else sum(counts[o] for o in ("landed", "landed_prs_after_freeze", "landed_main_pr_open")),
        removed_at_freeze=sum(
            any(x.code == "removed_at_freeze" for x in f.flags) for f in a.features
        ),
        critical_features=sum(f.in_release and _max_severity(f) == "critical" for f in a.features),
        open_linked_prs=sum(
            p.state == "open" for f in a.features if f.in_release for p in f.pull_requests
        ),
        unlinked_open_prs=a.unlinked_open_prs,
        outcomes={o: counts[o] for o in OUTCOMES if counts[o]},
        features=[
            FeatureOutcomeOut(
                key=f.key,
                number=_number(f.key),
                title=f.title,
                outcome=outcomes[f.key],
                sigs=list(f.teams),
            )
            for f in a.features
        ],
    )


def graph_out(view: ReleaseView) -> GraphOut:
    """Release -> features -> linked PRs, plus stated PR dependencies (engine/graph.py)."""
    from engine.graph import pr_dependencies

    a = view.assessment
    world = view.world
    nodes: dict[str, GraphNodeOut] = {
        a.release.key: GraphNodeOut(
            id=a.release.key, kind="release", label=a.release.name, title=a.release.name
        )
    }
    edges: list[GraphEdgeOut] = []
    for f in a.features:
        feature = world.features[f.key]
        nodes[f.key] = GraphNodeOut(
            id=f.key,
            kind="feature",
            label=_label(f.key),
            title=f.title,
            url=feature.url,
            sigs=list(f.teams),
            in_release=f.in_release,
            severity=_max_severity(f),
            flags=sorted({x.code for x in f.flags}),
        )
        edges.append(GraphEdgeOut(source=a.release.key, target=f.key, kind="contains"))
        critical = set(f.critical_path)
        for p in f.pull_requests:
            if p.key not in nodes:
                pr = world.pull_requests[p.key]
                nodes[p.key] = GraphNodeOut(
                    id=p.key,
                    kind="pull_request",
                    label=f"PR #{_number(p.key)}",
                    title=p.title,
                    url=_url(p.key),
                    sigs=sorted(lb for lb in pr.labels if lb.startswith("sig/")),
                    state=p.state,
                    is_main=p.is_main,
                    on_critical_path=p.key in critical,
                    feature=f.key,
                )
            edges.append(GraphEdgeOut(source=f.key, target=p.key, kind="implemented_by"))
    for key, node in list(nodes.items()):
        if node.kind != "pull_request":
            continue
        for dep in pr_dependencies(world.pull_requests[key]):
            if dep in nodes:
                edges.append(GraphEdgeOut(source=dep, target=key, kind="blocks"))
    return GraphOut(release=a.release.key, as_of=a.as_of, nodes=list(nodes.values()), edges=edges)


def dependencies_out(view: ReleaseView, include_removed: bool = False) -> DependenciesOut:
    """Feature-to-feature dependencies: shared PRs, stated "depends on", waiting PRs."""
    from engine.graph import feature_dependencies, pr_dependencies

    a = view.assessment
    world = view.world
    feats = [f for f in a.features if include_removed or f.in_release]
    feature_prs = {f.key: [p.key for p in f.pull_requests] for f in feats}
    owned = {k for keys in feature_prs.values() for k in keys}
    pr_deps = {k: pr_dependencies(world.pull_requests[k]) for k in owned}
    known = owned | {d for deps in pr_deps.values() for d in deps if d in world.pull_requests}
    pr_state = {k: world.pull_requests[k].state for k in known}
    deps = feature_dependencies(feature_prs, {f.key: f.teams for f in feats}, pr_state, pr_deps)
    cluster_of = {k: i for i, members in enumerate(deps.clusters) for k in members}

    def title(key: str) -> str:
        pr = world.pull_requests.get(key)
        return pr.title if pr else ""

    return DependenciesOut(
        release=a.release.key,
        as_of=a.as_of,
        include_removed=include_removed,
        features=[
            DepFeatureOut(
                key=f.key,
                number=_number(f.key),
                title=f.title,
                url=world.features[f.key].url,
                sigs=list(f.teams),
                in_release=f.in_release,
                severity=_max_severity(f),
                flags=sorted({x.code for x in f.flags}),
                outcome=feature_outcome(view, f),
                cluster=cluster_of.get(f.key),
                prs=[
                    DepPROut(
                        key=p.key,
                        number=_number(p.key),
                        title=p.title,
                        url=_url(p.key),
                        state=p.state,
                        is_main=p.is_main,
                        freeze_status=p.freeze.status.value,
                    )
                    for p in f.pull_requests
                ],
            )
            for f in feats
        ],
        pr_edges=[
            GraphEdgeOut(source=d, target=k, kind="blocks")
            for k in sorted(owned)
            for d in pr_deps[k]
            if d in known
        ],
        couplings=[
            CouplingOut(
                a=c.a,
                b=c.b,
                shared_prs=list(c.shared_prs),
                stated=[
                    StatedDependencyOut(
                        upstream=d.upstream,
                        downstream=d.downstream,
                        blocker=d.blocker,
                        dependent=d.dependent,
                    )
                    for d in c.stated
                ],
            )
            for c in deps.couplings
        ],
        clusters=[list(c) for c in deps.clusters],
        waiting=[
            WaitingPROut(
                pr=w.pr,
                pr_title=title(w.pr),
                waits_on=w.waits_on,
                waits_on_title=title(w.waits_on),
                waits_on_state=w.waits_on_state,
                features=list(w.features),
            )
            for w in deps.waiting
        ],
        sig_pairs=[SigPairOut(a=x, b=y, features=n) for x, y, n in deps.sig_pairs],
    )


MERGE_DATE_NOTE = (
    "Days are relative to Code Freeze. 'Required code' is the main PR and the PRs it says "
    "it depends on. If the measured inputs hold, the count is likely inside the band. "
    "Decision support, not a guarantee."
)


def merge_date_out(m: MergeDateForecast) -> MergeDateOut:
    """One feature's merge-date forecast."""
    return MergeDateOut(
        feature_key=m.feature_key,
        status=m.status,
        done_day=m.done_day,
        p10=m.p10,
        p50=m.p50,
        p90=m.p90,
        by_freeze=m.by_freeze,
        by_release=m.by_release,
        cdf=list(m.cdf),
    )


def merge_dates_out(view: ReleaseView) -> MergeDatesOut:
    """Release days-of-delay chart and the features on it."""
    a = view.assessment
    c = view.curve
    titles = {f.key: f.title for f in a.features}
    items = [
        CurveFeatureOut(
            key=k,
            number=_number(k),
            title=titles.get(k, ""),
            status=m.status,
            done_day=m.done_day,
            p10=m.p10,
            p50=m.p50,
            p90=m.p90,
            by_release=m.by_release,
        )
        for k, m in sorted(view.merge_dates.items())
    ]
    return MergeDatesOut(
        release=a.release.key,
        as_of=a.as_of,
        code_freeze_at=a.release.code_freeze_at,
        release_at=a.release.release_at,
        as_of_day=c.as_of_day if c else None,
        release_day=c.release_day if c else None,
        features=c.features if c else 0,
        done_now=c.done_now if c else 0,
        forecast=list(c.forecast) if c else [],
        actual=list(c.actual) if c else [],
        items=items,
        validation=view.date_validation.as_dict(),
        note=MERGE_DATE_NOTE,
    )


def lab_out(report: LabReport, *, project: str, lanes_configured: bool) -> LabOut:
    """Lab counts. Scenario numbers stay null while the sample is small."""
    cap = report.cap
    return LabOut(
        release=report.release_key,
        project=project,
        lanes_configured=lanes_configured,
        as_of=report.as_of,
        n_pull_requests=report.n_pull_requests,
        n_merged=report.n_merged,
        n_open=report.n_open,
        small_sample=report.small_sample,
        buckets=[
            LabBucketOut(lane=b.lane, opened=b.opened, merged=b.merged, still_open=b.still_open)
            for b in report.buckets
        ],
        approval_rate=report.approval_rate,
        approved_merged=report.approved_merged,
        median_hours_to_merge=report.median_hours_to_merge,
        arrivals=[LabWeekOut(week=a.week, lane=a.lane, count=a.count) for a in report.arrivals],
        queue=[LabDayOut(day=d.day, count=d.count) for d in report.queue],
        time_to_first_review_hours=list(report.time_to_first_review_hours),
        still_waiting=report.still_waiting,
        review_round_counts=list(report.review_round_counts),
        review_rounds_median=report.review_rounds_median,
        rework=report.rework,
        ci_failures=report.ci_failures,
        collisions=[
            LabCollisionOut(
                kind=c.kind,
                pull_requests=list(c.pull_requests),
                paths=list(c.paths),
                truncated=c.truncated,
            )
            for c in report.collisions
        ],
        cap=LabCapOut(
            observed_max_open=cap.observed_max_open,
            held=cap.held if cap.comparable else None,
            scenario_max_open=cap.scenario_max_open,
            comparable=cap.comparable,
            assumption=cap.assumption,
        ),
        first_pass=LabFirstPassOut(
            observed_median_hours=report.first_pass.observed_median_hours,
            n=report.first_pass.n,
            waiting=report.first_pass.waiting,
            comparable=report.first_pass.comparable,
            assumption=report.first_pass.assumption,
        ),
        size=LabSizeOut(
            over_cap=report.size.over_cap,
            extra_pull_requests=report.size.extra_pull_requests,
            comparable=report.size.comparable,
            assumption=report.size.assumption,
        ),
        pod=PodOut.model_validate(report.pod) if report.pod else None,
    )


def lane_specs(team_lanes: dict[str, Any]) -> tuple[LaneSpec, ...]:
    """Team-file lanes in file order."""
    return tuple(
        LaneSpec(name, rule.labels, rule.branch_prefixes, rule.trailers)
        for name, rule in team_lanes.items()
    )


def program_facts(
    view: ReleaseView,
    team: TeamConfig,
    *,
    draft_id: int | None,
    suggested_links: int,
    lab: LabFacts | None,
) -> ProgramFacts:
    """Stored facts for one Portfolio row (ADR-0025). Counts only, no names."""
    a = view.assessment
    r = a.release
    in_release = [f for f in a.features if f.in_release]
    return ProgramFacts(
        key=r.key,
        project=team.project,
        display_name=team.display_name,
        release=r.name,
        planning_tool=team.planning.source,
        code_tools=("github",),  # every connector's code activity is GitHub today
        as_of=a.as_of,
        dates={
            "cycle_start_at": r.cycle_start_at,
            "enhancements_freeze_at": r.enhancements_freeze_at,
            "code_freeze_at": r.code_freeze_at,
            "release_at": r.release_at,
        },
        features_in_release=len(in_release),
        features_ever=len(a.features),
        critical_codes=tuple(
            codes
            for f in in_release
            if (codes := tuple(x.code for x in f.flags if x.severity == "critical"))
        ),
        linked_features=sum(1 for f in in_release if f.pull_requests),
        readded_after_freeze=sum(
            feature_outcome(view, f) == "readded_after_freeze" for f in a.features
        ),
        unlinked_open_prs=a.unlinked_open_prs,
        draft_update_id=draft_id,
        suggested_links=suggested_links,
        lab=lab,
    )
