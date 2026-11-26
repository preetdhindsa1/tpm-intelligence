"""Retro layout (#183): the real v1.37 retrospective's shape, names replaced."""

from __future__ import annotations

from datetime import date

from collectors.notes.parse import split_meetings, split_retro

RETRO = """﻿Kubernetes v1.37 Release Retrospective
This Meeting
* When:
   * Part 1: 29th Jul 2026
   * Part 2:  2nd Sep 2026
* Attendees
   * Part 1: Wednesday 29th July 2026
      * Pat Example (Release Docs Shadow)
(+) What went well in v1.37
* [participant] Kudos and Thanks
   * Enhancements tracking went smoothly.
(-) What could have gone better in v1.37
* [participant] Several KEPs needed exceptions after Code Freeze, KEP-4568 among them.
(🔺) What will we do differently in v1.38 (and beyond)
* Start exception reviews a week before Code Freeze.
"""


def test_a_retro_is_one_meeting_dated_by_part_one_without_the_roster() -> None:
    [m] = split_retro(RETRO)
    assert (m.heading, m.meeting_date) == (
        "Kubernetes v1.37 Release Retrospective",
        date(2026, 7, 29),
    )
    assert m.text.startswith("(+) What went well in v1.37")
    assert "Pat Example" not in m.text
    assert "KEP-4568" in m.text
    assert split_meetings(RETRO) == []  # the weekly layout finds nothing here


def test_a_document_without_the_retro_sections_gives_nothing() -> None:
    assert split_retro("Week 1 - 1 July 2026 Weekly Meeting\n* notes") == []
