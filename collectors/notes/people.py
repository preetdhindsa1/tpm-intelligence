"""People's names from public team lists, used only to mask them (ADR-0030 addendum 4).

Meeting notes mention people who are on no attendee list in the notes (a release manager
named in passing). The team config's ``people_sources`` name public GitHub files that list
people as ``Name ([@handle](...))``, such as the Kubernetes release-team and
release-managers pages, or as YAML ``- github: handle`` / ``name: Full Name`` pairs, such as
kubernetes/community ``sigs.yaml`` (SIG chairs and leads, named in retros, #183). They are read through the GitHub contents API (read-only, the shared
HTTP client) when masking runs, and the names are never stored.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable

from collectors.http import HttpClient

logger = logging.getLogger("collectors.notes.people")
API = "https://api.github.com"
# "Marko Mudrinić ([@xmudrii](https://github.com/xmudrii))", also inside table cells.
_PERSON = re.compile(r"([A-Z][^\s()|\[\]*`]*(?: [A-Z][^\s()|\[\]*`]*){0,3})\s*\(\s*\[?@")
_HANDLE = re.compile(r"\[?@([A-Za-z0-9][\w-]*)\]?\(https://github\.com/")


def names_in_markdown(text: str) -> set[str]:
    """Full names and GitHub handles listed in a markdown file."""
    names = {m.group(1).strip() for m in _PERSON.finditer(text)}
    return names | {m.group(1) for m in _HANDLE.finditer(text)}


# "- github: soltysh\n  name: Full Name" (kubernetes/community sigs.yaml)
_YAML_PERSON = re.compile(r"-\s*github:\s*([\w-]+)\s*\n\s*name:\s*([^\n#]+)")


def names_in_yaml(text: str) -> set[str]:
    """Full names and handles from ``github:`` / ``name:`` pairs."""
    found: set[str] = set()
    for m in _YAML_PERSON.finditer(text):
        found |= {m.group(1), m.group(2).strip().strip("\"'")}
    return found


def fetch_people(sources: Iterable[str], http: HttpClient | None = None) -> set[str]:
    """Names from every ``owner/repo/path`` source; a source that fails is logged and skipped."""
    from pipeline.env import configured

    token = configured("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github.raw"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    client = http or HttpClient(API, headers=headers)
    found: set[str] = set()
    try:
        for source in sources:
            owner, repo, path = source.split("/", 2)
            try:
                res = client.get(f"/repos/{owner}/{repo}/contents/{path}")
            except Exception as exc:  # one missing list must not stop masking with the rest
                logger.warning("people source %s not read: %s", source, exc)
                continue
            yaml = path.endswith((".yaml", ".yml"))
            found |= names_in_yaml(res.text) if yaml else names_in_markdown(res.text)
    finally:
        if http is None:
            client.close()
    return found
