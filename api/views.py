"""Convert engine results into API response models."""

from __future__ import annotations

from typing import Any

from api.schemas import (
    CouplingOut,
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
    OddsOut,
    PullRequestOut,
    ReleaseOut,
    SigPairOut,
    StatedDependencyOut,
    SummaryOut,
    TimelineEntryOut,
    WaitingPROut,
)
from api.service import ReleaseSummary, ReleaseView
from connectors.load import display_name_for_project
from engine.assess import FeatureAssessment
from engine.forecast import Forecast
from engine.projection import ReleaseInfo


def _project(release: ReleaseInfo) -> str:
    return release.key.split(":", 1)[0] if ":" in release.key else release.key


def _release_fields(release: ReleaseInfo) -> dict[str, Any]:
    project = _project(release)
    return {
        "key": release.key,
        "name": release.name,
        "project": project,
        "display_name": display_name_for_project(project),
        "cycle_start_at": release.cycle_start_at,
        "enhancements_freeze_at": release.enhancements_freeze_at,
        "code_freeze_at": release.code_freeze_at,
        "release_at": release.release_at,
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
    return int(key.rsplit("#", 1)[1])


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
        "outcome_definition": "still in the release 3 days after Code Freeze",
        "note": "Decision support: if these measured inputs hold, the odds are likely in "
        "the range shown. Not a guarantee.",
    }
    return FeatureDetailOut(
        **row.model_dump(),
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
    from engine.forecast import LANDED_WINDOW, landed

    release = view.assessment.release
    codes = {f.code for f in a.flags}
    freeze = release.code_freeze_at
    if freeze is None or view.assessment.as_of < freeze + LANDED_WINDOW:
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
        unlinked_open_prs=sum(n for _, n in a.unlinked_open_prs_by_sig),
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
            label=f"#{_number(f.key)}",
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
