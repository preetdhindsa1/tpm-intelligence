"""Run the deterministic linker over a projected world. Pure, no I/O."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from engine.projection import Feature, World
from linker.candidates import CandidateIndex, FeatureDoc
from linker.methods import LinkStatus
from linker.packs import get_pack
from linker.rules import (
    LinkCandidate,
    LinkIndex,
    PullRequestInfo,
    WorkItemInfo,
    best_links,
)


@dataclass(frozen=True)
class ReleaseLinks:
    """Best link per (PR, feature), plus convenient views."""

    best: Mapping[tuple[str, str], LinkCandidate]

    def verified_prs(self, feature_key: str) -> list[str]:
        """PR keys with a verified link to the feature, sorted."""
        return sorted(
            pr
            for (pr, item), c in self.best.items()
            if item == feature_key and c.status is LinkStatus.VERIFIED
        )

    def suggested_prs(self, feature_key: str) -> list[str]:
        """PR keys whose best link to the feature is only suggested."""
        return sorted(
            pr
            for (pr, item), c in self.best.items()
            if item == feature_key and c.status is LinkStatus.SUGGESTED
        )

    def by_feature(self) -> Mapping[str, list[str]]:
        """Feature key -> verified PR keys."""
        out: dict[str, list[str]] = defaultdict(list)
        for (pr, item), c in sorted(self.best.items()):
            if c.status is LinkStatus.VERIFIED:
                out[item].append(pr)
        return out

    def linked_pr_keys(self) -> frozenset[str]:
        """PRs with at least one verified link (everything else is unlinked load)."""
        return frozenset(pr for (pr, _), c in self.best.items() if c.status is LinkStatus.VERIFIED)


def _info(f: Feature) -> WorkItemInfo:
    return WorkItemInfo(
        key=f.key,
        number=f.number,
        description=f.description,
        feature_flags=f.feature_flags,
        labels=tuple(sorted(f.labels)),
    )


def _pack_name(release_key: str, link_pack: str | None) -> str:
    if link_pack is not None:
        return link_pack
    from connectors.load import link_pack_for_project

    return link_pack_for_project(release_key.split(":", 1)[0])


def link_release(world: World, release_key: str, *, link_pack: str | None = None) -> ReleaseLinks:
    """Link every PR to features that are or were in ``release_key`` (removed ones too).

    ``link_pack`` selects the team linker (``kep``, ``jira_key``, …). When omitted, the
    pack is resolved from ``connectors/teams/`` by release project.
    """
    pack = get_pack(_pack_name(release_key, link_pack))
    index = LinkIndex.build(_info(f) for f in world.features_ever_in(release_key))
    best: dict[tuple[str, str], LinkCandidate] = {}
    for pr in world.pull_requests.values():
        info = PullRequestInfo(
            key=pr.key,
            repo=pr.repo,
            number=pr.number,
            title=pr.title,
            body=pr.body,
            labels=pr.labels,
        )
        best.update(best_links(list(pack.link(info, index))))
    in_release = {f.key for f in world.features_ever_in(release_key)}
    merge_extra_links(
        best,
        [
            c
            for c in world.extra_links
            if c.work_item_key in in_release and c.pull_request_key in world.pull_requests
        ],
    )
    return ReleaseLinks(best=best)


def merge_extra_links(
    best: dict[tuple[str, str], LinkCandidate], extra: Iterable[LinkCandidate]
) -> None:
    """Merge stored links into the rule links, in place.

    * A rule-verified link is never changed.
    * ``rejected`` (a person said no) removes a suggested link for that pair.
    * ``verified`` (a person confirmed) replaces a suggested link or adds one.
    * ``suggested`` is added only where no link exists for the pair.
    """
    for c in extra:
        pair = (c.pull_request_key, c.work_item_key)
        current = best.get(pair)
        if current is not None and current.status is LinkStatus.VERIFIED:
            continue
        if c.status is LinkStatus.REJECTED:
            best.pop(pair, None)
        elif c.status is LinkStatus.VERIFIED or current is None:
            best[pair] = c


def unlinked_pull_requests(world: World, release_key: str, links: ReleaseLinks) -> list[str]:
    """PRs opened during the release cycle with no link of any kind to its features.

    These are what the AI link suggester looks at. PRs that already have a rule-made
    ``suggested`` link are left out: they are waiting for a person already.
    """
    start = world.releases[release_key].cycle_start_at
    has_link = {pr for (pr, _), c in links.best.items() if c.status is not LinkStatus.REJECTED}
    return sorted(
        pr.key
        for pr in world.pull_requests.values()
        if pr.key not in has_link and (start is None or pr.created_at >= start)
    )


def candidate_index(world: World, release_key: str) -> CandidateIndex:
    """Shortlist index over every feature that is or was in the release (ADR-0011)."""
    return CandidateIndex.build(
        (
            FeatureDoc.build(f.key, f.title, f.description, f.feature_flags, f.labels, f.stage),
            f.description,
        )
        for f in world.features_ever_in(release_key)
    )
