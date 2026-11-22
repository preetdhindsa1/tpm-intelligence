"""Typed facts the agents may cite, and the only things a claim can be checked against.

Every fact comes from deterministic engine output (CLAUDE.md section 2.1). Keys are stable
strings so an AI claim can reference them::

    release::code_freeze_at
    feature:kubernetes/enhancements#6395::odds.probability
    pr:kubernetes/kubernetes#143709::merged_at
    sig:sig/node::unlinked_open_prs

``::`` separates the subject from the field, because subject keys contain ``/``, ``#``,
``:`` and ``.``. Pure, no I/O.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

FactValue = int | float | bool | str | datetime | None


class FactKind(StrEnum):
    """How a fact's value is compared with a claimed value."""

    COUNT = "count"  # exact integer
    PROBABILITY = "probability"  # 0..1, compared within one percentage point
    DATE = "date"  # UTC datetime; a date-only claim matches the calendar day
    DURATION_DAYS = "duration_days"  # compared within half a day
    BOOLEAN = "boolean"
    LABEL = "label"  # exact string (case-insensitive): states, stages, PR keys, titles


@dataclass(frozen=True)
class Fact:
    """One computed fact. The value's type must match its kind (checked on creation)."""

    key: str
    kind: FactKind
    value: FactValue

    def __post_init__(self) -> None:
        v = self.value
        ok = (
            v is None
            or {
                FactKind.COUNT: isinstance(v, int) and not isinstance(v, bool),
                FactKind.PROBABILITY: isinstance(v, int | float) and not isinstance(v, bool),
                FactKind.DURATION_DAYS: isinstance(v, int | float) and not isinstance(v, bool),
                FactKind.DATE: isinstance(v, datetime),
                FactKind.BOOLEAN: isinstance(v, bool),
                FactKind.LABEL: isinstance(v, str),
            }[self.kind]
        )
        if not ok:
            raise TypeError(f"{self.key}: {self.kind.value} fact cannot hold {v!r}")


def fact_key(scope: str, field: str, subject: str | None = None) -> str:
    """Build a key: ``fact_key("feature", "odds.probability", "k/e#1")``."""
    return f"{scope}:{subject}::{field}" if subject is not None else f"{scope}::{field}"


class FactSheet(Mapping[str, Fact]):
    """Immutable set of facts by key (later duplicates are rejected)."""

    def __init__(self, facts: Iterable[Fact]) -> None:
        by_key: dict[str, Fact] = {}
        for f in facts:
            if f.key in by_key:
                raise ValueError(f"duplicate fact key {f.key!r}")
            by_key[f.key] = f
        self._facts = by_key

    def __getitem__(self, key: str) -> Fact:
        return self._facts[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._facts)

    def __len__(self) -> int:
        return len(self._facts)

    def subset(self, prefix: str) -> FactSheet:
        """Facts whose key starts with ``prefix`` (e.g. one feature, for one agent call)."""
        return FactSheet(f for k, f in self._facts.items() if k.startswith(prefix))

    def to_records(self) -> list[dict[str, object]]:
        """JSON-safe rows (dates as ISO 8601), sorted by key. Inverse of ``from_records``."""
        return [
            {
                "key": f.key,
                "kind": f.kind.value,
                "value": f.value.isoformat() if isinstance(f.value, datetime) else f.value,
            }
            for f in sorted(self._facts.values(), key=lambda f: f.key)
        ]

    @classmethod
    def from_records(cls, rows: Iterable[Mapping[str, object]]) -> FactSheet:
        """Rebuild from ``to_records`` output."""
        facts: list[Fact] = []
        for row in rows:
            kind = FactKind(str(row["kind"]))
            value = row["value"]
            if kind is FactKind.DATE and isinstance(value, str):
                value = datetime.fromisoformat(value)
            facts.append(Fact(str(row["key"]), kind, value))  # type: ignore[arg-type]
        return cls(facts)

    def as_prompt_rows(self) -> list[dict[str, str]]:
        """Plain rows for an agent prompt: key, kind, value (dates in ISO 8601 UTC)."""
        return [
            {"key": f.key, "kind": f.kind.value, "value": _render(f.value)}
            for f in sorted(self._facts.values(), key=lambda f: f.key)
        ]


def _render(value: FactValue) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return "null" if value is None else str(value)
