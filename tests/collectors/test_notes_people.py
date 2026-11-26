"""Names from public team lists, used only to mask meeting notes (made-up names)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from agents.raid_job import run_release
from collectors.notes.people import fetch_people, names_in_markdown
from connectors import load_team
from modules.raid.mask import MASK, mask_names
from modules.raid.store import MemoryRaidStore
from tests.agents.test_raid_job import PAYLOAD, PROMPT, gw

TEAM_MD = """| Team/Role | Lead Name (GitHub / Slack ID) | Shadow Name(s) |
|---|---|---|
| Release Team Lead | Alex Doe ([@adoe](https://github.com/adoe) / Slack: `@alex`) | \
Kim Lee ([@kimlee](https://github.com/kimlee)) |
"""
MANAGERS_MD = """### Release Managers
- Dana Mudrić ([@dmudric](https://github.com/dmudric))
- Robin Roe ([@rroe](https://github.com/rroe))
"""


def test_names_and_handles_come_from_both_list_formats() -> None:
    names = names_in_markdown(TEAM_MD + MANAGERS_MD)
    assert {"Alex Doe", "Kim Lee", "Dana Mudrić", "Robin Roe"} <= names
    assert {"adoe", "kimlee", "dmudric", "rroe"} <= names
    assert not {"Release Team Lead", "Team", "Slack"} & names


def test_a_name_mentioned_in_passing_is_masked() -> None:
    text = "We'll work with Dana to finalize the team; ping dmudric on Slack."
    masked = mask_names(text, names_in_markdown(MANAGERS_MD))
    assert masked == f"We'll work with {MASK} to finalize the team; ping {MASK} on Slack."


@dataclass
class _Res:
    text: str


class _Http:
    def __init__(self, files: dict[str, str]) -> None:
        self.files, self.calls = files, []  # type: ignore[var-annotated]

    def get(self, path: str, **_: Any) -> _Res:
        self.calls.append(path)
        if path not in self.files:
            raise RuntimeError("404")
        return _Res(self.files[path])


def test_fetch_reads_each_source_and_skips_one_that_fails() -> None:
    http = _Http({"/repos/o/r/contents/a/team.md": TEAM_MD})
    names = fetch_people(["o/r/a/team.md", "o/r/missing.md"], http)  # type: ignore[arg-type]
    assert "Alex Doe" in names
    assert http.calls == ["/repos/o/r/contents/a/team.md", "/repos/o/r/contents/missing.md"]


def test_kubernetes_lists_its_release_team_and_release_managers() -> None:
    sources = load_team("kubernetes").people_sources
    assert any(s.endswith("release-1.38/release-team.md") for s in sources)
    assert any(s.endswith("release-managers.md") for s in sources)


def test_the_job_masks_known_names_in_the_text_sent_to_ai() -> None:
    text = PAYLOAD["text"] + "   * We'll work with Dana to finalize the team by next week.\n"
    client_gw = gw([])
    run_release(
        client_gw, PROMPT, [{**PAYLOAD, "text": text}], "kubernetes:v1.38", "K8S",
        MemoryRaidStore(), datetime(2026, 11, 25, tzinfo=UTC), {"Dana Mudrić"},
    )  # fmt: skip
    sent = str(client_gw.client.calls[0])  # type: ignore[attr-defined]
    assert "Dana" not in sent
    assert f"work with {MASK}" in sent


def test_yaml_people_files_give_names_and_handles() -> None:
    from collectors.notes.people import names_in_yaml

    text = """sigs:
  - dir: sig-apps
    leadership:
      chairs:
        - github: pexample
          name: Pat Example
          company: Example
        - github: rsample
          name: "Robin Sample"
"""
    assert names_in_yaml(text) == {"pexample", "Pat Example", "rsample", "Robin Sample"}
