"""Run the GitHub poller once.

    python -m collectors.github_poller --team kubernetes --release v1.38
    python -m collectors.github_poller --team kubernetes --release v1.38 --backfill
    python -m collectors.github_poller --team kafka --release 4.4.0 --backfill
    python -m collectors.github_poller --poll kubernetes=v1.38 --poll "tpm-intelligence=Phase 3"
    python -m collectors.github_poller --all-tenants

``--all-tenants`` (ADR-0035) polls every team of every private tenant, each under its own
tenant and token, for the release its calendar says is current. One scheduled job covers
every organization; the public demo keeps its own explicit ``--poll`` schedule.

For a team that plans in Jira (Kafka, ADR-0018) only the code repo's PRs are synced,
over the window the Jira version dates give (previous x.y.0 release to this release, or
now while the release date is unset).

Repos and calendar come from ``connectors/teams/<team>.yaml`` so another team can
plug in without editing this module. ``--poll TEAM=RELEASE`` (repeatable) polls several
teams in one run, one after another; a failing team does not stop the others. Exit code:
0 if all succeeded, 1 if any stream failed, 2 on a configuration error (the worst wins).
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from typing import Any

SERVICE_NAME = "tpm-github-poller"


def parse_polls(
    polls: list[str] | None, team: str | None, release: str | None
) -> list[tuple[str, str]]:
    """(team, release) pairs from ``--poll TEAM=RELEASE`` or the single ``--team/--release``.

    Raises ``ValueError`` for a malformed pair, a mix of both styles, or no release.
    """
    if polls:
        if team is not None or release is not None:
            raise ValueError("use either --poll or --team/--release, not both")
        pairs = []
        for item in polls:
            name, sep, rel = item.partition("=")
            if not sep or not name.strip() or not rel.strip():
                raise ValueError(f"--poll expects TEAM=RELEASE, got {item!r}")
            pairs.append((name.strip(), rel.strip()))
        return pairs
    if release is None:
        raise ValueError("--release (or --poll TEAM=RELEASE) is required")
    return [(team or "kubernetes", release)]


def parse_since(value: str) -> datetime:
    """``2026-11-20`` as midnight UTC."""
    try:
        day = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as err:
        raise argparse.ArgumentTypeError(f"--since expects YYYY-MM-DD, got {value!r}") from err
    return day.replace(tzinfo=UTC)


def main(argv: list[str] | None = None) -> int:
    """Parse args, wire dependencies, poll each requested team once."""
    parser = argparse.ArgumentParser(prog="github_poller")
    parser.add_argument("--team", help="connectors/teams/<id>.yaml (default: kubernetes)")
    parser.add_argument("--release", help="e.g. v1.38")
    parser.add_argument(
        "--poll",
        action="append",
        metavar="TEAM=RELEASE",
        help="poll this team's release; repeat for several teams",
    )
    parser.add_argument("--backfill", action="store_true", help="ignore stored cursors")
    parser.add_argument(
        "--since",
        type=parse_since,
        help="with --backfill: re-read PRs from this UTC date (YYYY-MM-DD) to now, for history "
        "before the release's cycle start (this repo's PRs predate Phase 3, 2026-11-25)",
    )
    parser.add_argument(
        "--all-tenants",
        action="store_true",
        help="poll every private tenant's teams (their current releases)",
    )
    args = parser.parse_args(argv)
    if args.all_tenants:
        if args.poll or args.team or args.release:
            parser.error("--all-tenants takes no --poll, --team or --release")
        return _poll_all_tenants(backfill=args.backfill)
    try:
        polls = parse_polls(args.poll, args.team, args.release)
    except ValueError as err:
        parser.error(str(err))
    if args.since is not None and not args.backfill:
        parser.error("--since needs --backfill")

    from observability.telemetry import init_telemetry

    telemetry = init_telemetry(SERVICE_NAME)
    logger = logging.getLogger("collectors.github_poller")
    try:
        from connectors.load import load_teams
        from connectors.secrets import team_secret

        worst = 0
        for team_id, release in polls:
            # The tenant's own token (ADR-0035); for the public demo, GITHUB_TOKEN as before.
            token = team_secret(load_teams().get(team_id), "github", "GITHUB_TOKEN")
            if not token:
                logger.error("no GitHub token for team %s (GITHUB_TOKEN or its secret ref)",
                             team_id)  # fmt: skip
                worst = max(worst, 2)
                continue
            try:
                code = _poll_team(
                    team_id, release, token=token, backfill=args.backfill, since=args.since
                )
            except Exception:
                logger.exception("poll of team %s release %s crashed", team_id, release)
                code = 1
            worst = max(worst, code)
        return worst
    finally:
        telemetry.shutdown()


def current_release(calendar: Any, now: datetime) -> str | None:
    """The release whose cycle has started and that shipped at most a week ago, latest
    first; None if no release is running (pure, for the all-tenant poll)."""
    from datetime import timedelta

    live = [r for r in calendar.releases
            if r.cycle_start <= now <= r.release + timedelta(days=7)]  # fmt: skip
    return max(live, key=lambda r: r.cycle_start).name if live else None


def private_tenants() -> list[str]:
    """Tenant ids other than the demo and the system tenant."""
    from sqlalchemy import select
    from sqlalchemy.orm import sessionmaker

    from pipeline.store.models import Tenant
    from pipeline.store.session import make_engine

    with sessionmaker(make_engine())() as s:
        ids = s.scalars(select(Tenant.id).where(Tenant.id.not_in(("demo", "system"))))
        return sorted(ids)


def _poll_all_tenants(*, backfill: bool, now: datetime | None = None) -> int:
    """Every private tenant's teams, each for its tenant; one failure never stops the rest."""
    from connectors.load import load_teams, team_calendar
    from connectors.secrets import team_secret
    from observability.telemetry import init_telemetry
    from pipeline.store.tenancy import use_tenant

    telemetry = init_telemetry(SERVICE_NAME)
    logger = logging.getLogger("collectors.github_poller")
    at = now or datetime.now(UTC)
    worst = 0
    try:
        for tenant in private_tenants():
            with use_tenant(tenant):
                for team in load_teams().values():
                    try:
                        calendar = team_calendar(team)
                        release = current_release(calendar, at) if calendar else None
                        token = team_secret(team, "github", "GITHUB_TOKEN")
                        if release is None or not token:
                            why = "no current release" if release is None else "no token"
                            logger.info("skip %s/%s: %s", tenant, team.id, why)
                            continue
                        code = _poll_team(team.id, release, token=token, backfill=backfill)
                    except Exception:
                        logger.exception("poll of %s/%s crashed", tenant, team.id)
                        code = 1
                    worst = max(worst, code)
        return worst
    finally:
        telemetry.shutdown()


def _poll_team(
    team_id: str, release: str, *, token: str, backfill: bool, since: datetime | None = None
) -> int:
    """Poll one team's release once. 0 ok, 1 a stream failed, 2 configuration error."""
    from sqlalchemy.orm import sessionmaker

    from collectors.github_poller.client import GitHubClient
    from collectors.github_poller.sync import GitHubPoller
    from pipeline.factory import create_transport
    from pipeline.queue import EventPublisher
    from pipeline.store.cursors import PostgresCursorStore
    from pipeline.store.session import make_engine

    logger = logging.getLogger("collectors.github_poller")
    from connectors.load import load_teams

    team = load_teams().get(team_id)  # the current tenant's team (YAML for the demo)
    if team is None:
        logger.error("no team %s for this tenant", team_id)
        return 2
    if team.planning_repo is None:
        window = _jira_window(team, release)
        if window is None:
            logger.error("release %s has no cycle start in Jira", release)
            return 2
        if since is not None:
            window = (since, None)
        poller = GitHubPoller(
            gh=GitHubClient.from_token(token),
            publisher=EventPublisher(create_transport()),
            cursors=PostgresCursorStore(sessionmaker(make_engine())),
            calendar=None,
            release_name=release,
            enhancements_repo=None,
            code_repo=team.primary_code_repo,
            window=window,
            lane_fields=bool(team.author_lanes),
        )
        logger.info("code-only poll of %s for %s: %s", team.primary_code_repo, release, window)
        stats = poller.run(backfill=backfill)
        return 1 if stats.failed_streams else 0

    from connectors.load import team_calendar

    calendar = team_calendar(team)  # inline releases for a tenant, else the YAML file
    if calendar is None:
        logger.error("team %s has no release calendar", team.id)
        return 2
    logger.info(
        "polling team %s planning=%s code=%s link_pack=%s release=%s",
        team.id,
        team.planning_repo,
        team.primary_code_repo,
        team.link_pack,
        release,
    )
    poller = GitHubPoller(
        gh=GitHubClient.from_token(token),
        publisher=EventPublisher(create_transport()),
        cursors=PostgresCursorStore(sessionmaker(make_engine())),
        calendar=calendar,
        release_name=release,
        enhancements_repo=team.planning_repo,
        code_repo=team.primary_code_repo,
        read_kep_specs=team.link_pack == "kep",  # only Kubernetes plans with kep.yaml
        lane_fields=bool(team.author_lanes),
        window=(since, None) if since is not None else None,
    )
    stats = poller.run(backfill=backfill)
    return 1 if stats.failed_streams else 0


def _jira_window(team: Any, release: str) -> tuple[datetime, datetime | None] | None:
    """(cycle start, release day) for a Jira-planned release, from its Jira versions."""
    from collectors.jira import normalize
    from collectors.jira.client import JiraClient
    from connectors.load import release_plan
    from connectors.schema import JiraPlanning

    planning = team.planning
    if not isinstance(planning, JiraPlanning):
        return None
    jira = JiraClient.from_base_url(planning.base_url)
    try:
        versions = jira.versions(planning.project_key)
    finally:
        jira.close()
    events = normalize.release_events(
        versions,
        [release],
        project=team.project,
        project_key=planning.project_key,
        base_url=planning.base_url,
        observed_at=datetime.now(UTC),
        plan=release_plan(team),
    )
    if not events:
        return None
    payload = events[0].payload
    start = getattr(payload, "cycle_start_at", None)
    return (start, getattr(payload, "release_at", None)) if start else None


if __name__ == "__main__":
    from pipeline.store.tenancy import cli_tenant, use_tenant

    with use_tenant(cli_tenant()):  # TPM_TENANT, else the public demo (ADR-0034)
        sys.exit(main())
