"""Link method precedence matches CLAUDE.md section 6."""

from __future__ import annotations

from linker.methods import LinkMethod


def test_precedence_order() -> None:
    assert [m.value for m in sorted(LinkMethod, key=lambda m: m.rank)] == [
        "explicit_key",
        "tracking_issue_link",
        "remote_link",
        "feature_gate",
        "labels",
        "ai_suggested",
    ]


def test_ai_suggested_is_weakest() -> None:
    assert max(LinkMethod, key=lambda m: m.rank) is LinkMethod.AI_SUGGESTED
