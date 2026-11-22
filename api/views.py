"""Convert engine results into API response models."""

from __future__ import annotations

from typing import Any

from api.schemas import (
    FeatureDetailOut,
    FeatureRowOut,
    FlagOut,
    OddsOut,
    PullRequestOut,
    ReleaseOut,
    TimelineEntryOut,
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
