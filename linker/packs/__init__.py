"""Link packs: team-specific linking rules behind one interface."""

from __future__ import annotations

from typing import Literal

from linker.packs.base import LinkPack
from linker.packs.github_issue import GitHubIssuePack
from linker.packs.jira_key import JiraKeyPack
from linker.packs.kep import KepPack

PackName = Literal["kep", "jira_key", "github_issue"]

_PACKS: dict[str, LinkPack] = {
    "kep": KepPack(),
    "jira_key": JiraKeyPack(),
    "github_issue": GitHubIssuePack(),
}


def get_pack(name: PackName | str) -> LinkPack:
    """Return the link pack registered under ``name``."""
    try:
        return _PACKS[name]
    except KeyError as exc:
        known = ", ".join(sorted(_PACKS))
        raise KeyError(f"unknown link pack {name!r} (known: {known})") from exc


__all__ = ["LinkPack", "get_pack"]
