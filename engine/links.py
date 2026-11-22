"""Run the deterministic linker over a projected world. Pure, no I/O."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass

from engine.projection import Feature, World
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
    return ReleaseLinks(best=best)
