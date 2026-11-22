"""Numbers stated in claim text, with identifiers and dates masked."""

from __future__ import annotations

import pytest

from verify.numbers import stated_numbers


@pytest.mark.parametrize(
    ("text", "numbers"),
    [
        ("Odds are 38% (likely 30-46%).", [38.0, 30.0, 46.0]),
        ("#6395 was removed at Code Freeze on Nov 17, 2026 12:05 UTC.", []),
        ("kubernetes/kubernetes#143709 merged 2026-11-20T23:28:24Z, after freeze.", []),
        ("KEP-6395 and KAFKA-19831 are in v1.38.", []),
        ("3 of 5 linked PRs merged; 1 still open in sig/node.", [3.0, 5.0, 1.0]),
        ("Opened 15.4 days before 17 November.", [15.4]),
        ("1,234 PRs in the window", [1234.0]),
    ],
)
def test_stated_numbers(text: str, numbers: list[float]) -> None:
    assert stated_numbers(text) == numbers


def test_stated_dates() -> None:
    from verify.numbers import stated_dates

    assert stated_dates("opened on 23 July, merged Nov 17 and 2026-11-20T23:28Z") == [
        (11, 20),
        (7, 23),
        (11, 17),
    ]
    assert stated_dates("v1.38 has 3 PRs") == []
