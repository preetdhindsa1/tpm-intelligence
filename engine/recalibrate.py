"""Recalibrate raw Monte Carlo odds on earlier releases (ADR-0005). Pure, no I/O.

The raw forecast ranks features somewhat (AUC 0.60-0.68) but its probabilities were
overconfident in the 2026-11-21 backtest. A monotone, binned mapping from raw score to the
landing rate actually observed on **earlier** releases fixes the scale without touching the
ranking:

1. Training pairs ``(raw probability, landed)`` come from releases that finished before the
   prediction point, each forecast at the same lead time using only its own past.
2. Per bin of raw probability: ``(landed + s * base) / (n + s)`` shrinks sparse bins toward
   the base rate (``s`` = ``strength`` pseudo-observations).
3. Pool-adjacent-violators makes the map non-decreasing, so a higher raw score never gets
   lower odds and the low/high range stays ordered.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass

DEFAULT_EDGES: tuple[float, ...] = (0.1, 0.3, 0.5, 0.7, 0.9)  # 6 bins on [0, 1]


@dataclass(frozen=True)
class Recalibration:
    """A fitted monotone map from raw probability to calibrated probability."""

    edges: tuple[float, ...]
    values: tuple[float, ...]  # one per bin, non-decreasing
    counts: tuple[int, ...]
    base_rate: float
    n: int
    training_releases: tuple[str, ...] = ()

    def apply(self, p: float) -> float:
        """Calibrated probability for a raw probability."""
        return self.values[bisect_right(self.edges, p)]

    @classmethod
    def identity_to_base(cls, base_rate: float) -> Recalibration:
        """No training data: every raw score maps to the base rate."""
        return cls(
            DEFAULT_EDGES,
            (base_rate,) * (len(DEFAULT_EDGES) + 1),
            (0,) * (len(DEFAULT_EDGES) + 1),
            base_rate,
            0,
        )


def _pava(values: list[float], weights: list[float]) -> list[float]:
    """Weighted pool-adjacent-violators: closest non-decreasing sequence."""
    blocks: list[tuple[float, float, int]] = []  # (mean, weight, size)
    for v, w in zip(values, weights, strict=True):
        blocks.append((v, w, 1))
        while len(blocks) > 1 and blocks[-2][0] > blocks[-1][0]:
            (v1, w1, n1), (v2, w2, n2) = blocks[-2], blocks[-1]
            blocks[-2:] = [((v1 * w1 + v2 * w2) / (w1 + w2), w1 + w2, n1 + n2)]
    out: list[float] = []
    for mean, _, size in blocks:
        out.extend([mean] * size)
    return out


def fit(
    pairs: Sequence[tuple[float, bool]],
    *,
    base_rate: float | None = None,
    edges: tuple[float, ...] = DEFAULT_EDGES,
    strength: float = 4.0,
    training_releases: Sequence[str] = (),
) -> Recalibration:
    """Fit the binned, shrunk, monotone map."""
    if base_rate is None:
        base_rate = sum(y for _, y in pairs) / len(pairs) if pairs else 0.5
    if not pairs:
        return Recalibration.identity_to_base(base_rate)
    bins = len(edges) + 1
    hits, totals = [0] * bins, [0] * bins
    for p, y in pairs:
        i = bisect_right(edges, p)
        totals[i] += 1
        hits[i] += int(y)
    raw = [(hits[i] + strength * base_rate) / (totals[i] + strength) for i in range(bins)]
    monotone = _pava(raw, [totals[i] + strength for i in range(bins)])
    return Recalibration(
        edges=edges,
        values=tuple(round(v, 4) for v in monotone),
        counts=tuple(totals),
        base_rate=round(base_rate, 4),
        n=len(pairs),
        training_releases=tuple(training_releases),
    )
