"""Moving wins in time: what a change in cycle length does to a creation cohort.

A deal created on day ``t`` after the as-of date is won, if it is, after one of the pooled timing's
lags ``L`` (each with its weight). A cycle action multiplies the lags of the cohorts it reaches by a
scale ``f`` (one plus the ramped relative change of the target over the pooled baseline) and rounds
up to whole days, so a lag of ``L`` days becomes ``ceil(L * f)``; weights, and so counts and dollars,
do not change. Only where they land does.

A win keeps the price of the atom it was priced in before it moved: (its segment, the month it was to
land in, the quarter its deal was created in), the atoms ``driver_actions.price_index`` freezes, and a
further one, the tail, for every landing after the last month the report holds, so a win that a shorter
cycle pulls in from beyond the horizon has a price and one a longer cycle pushes out is not dropped from
the cohort's dollars, only from the months shown.

Everything is per sample: a cohort's lags are cut into pieces at the month edges of their original and
of their moved landings, and each piece (original month, moved month, weight, moved lag times weight)
is one block of the same wins. Both the forward function and the lanes read the pieces, so they agree.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Sequence
from decimal import Decimal
from fractions import Fraction
from itertools import pairwise

from .fit import Timing

ONE = Fraction(1)


class Piece:
    """Wins of one cohort that land in one original month and one moved month."""

    __slots__ = ("moment", "moved", "original", "weight")

    def __init__(
        self, original: int, moved: int, weight: Decimal, moment: Decimal
    ) -> None:
        self.original = (
            original  # the month the wins were to land in (the tail is ``len(edges)``)
        )
        self.moved = moved  # the month they land in (the tail: beyond the months shown)
        self.weight = weight  # their share of the timing's weight
        self.moment = moment  # their moved lags times their weights, summed

    def __repr__(self) -> str:
        return f"Piece({self.original}, {self.moved}, {self.weight}, {self.moment})"


class Transport:
    """The pooled timing, the months the report holds and the pieces a cohort splits into.

    ``edges`` are the days after the as-of date on which each month ends (months are contiguous and
    the first begins after day 0). Pieces are cached by (creation day, scale)."""

    def __init__(self, timing: Timing, edges: Sequence[int]) -> None:
        self.timing = timing
        self.edges = tuple(edges)
        self.samples = timing.samples
        weights = timing.weights
        self.weights = (
            tuple(weights) if weights is not None else (Decimal(1),) * len(self.samples)
        )
        total = Decimal(0)
        cum = [Decimal(0)]
        for w in self.weights:
            total += w
            cum.append(total)
        self.total = total
        self.cum = cum
        self._scaled: dict[Fraction, tuple[tuple[int, ...], list[Decimal]]] = {}
        self._pieces: dict[tuple[int, Fraction], tuple[Piece, ...]] = {}

    @property
    def tail(self) -> int:
        """The index of the landing beyond the last month shown."""
        return len(self.edges)

    def with_timing(self, timing: Timing) -> Transport:
        """The same months over another timing (the worksheet's flex of the cycle)."""
        return Transport(timing, self.edges)

    def scaled(self, f: Fraction) -> tuple[tuple[int, ...], list[Decimal]]:
        """The lags multiplied by ``f`` and rounded up, and the running sum of moved lag times weight."""
        found = self._scaled.get(f)
        if found is None:
            lags = (
                self.samples
                if f == ONE
                else tuple(-(-(d * f.numerator) // f.denominator) for d in self.samples)
            )
            moment = [Decimal(0)]
            for d, w in zip(lags, self.weights):
                moment.append(moment[-1] + Decimal(d) * w)
            found = (lags, moment)
            self._scaled[f] = found
        return found

    def pieces(self, day: int, f: Fraction) -> tuple[Piece, ...]:
        """The blocks of the wins of a deal created ``day`` days after the as-of date, at scale ``f``."""
        key = (day, f)
        found = self._pieces.get(key)
        if found is not None:
            return found
        lags, moment = self.scaled(f)
        original = [bisect_right(self.samples, e - day) for e in self.edges]
        moved = [bisect_right(lags, e - day) for e in self.edges]
        k = len(self.samples)
        cuts = sorted({0, k, *original, *moved})
        out = []
        for x, y in pairwise(cuts):
            weight = self.cum[y] - self.cum[x]
            if y <= x:
                continue
            j = bisect_left(
                original, y
            )  # the first month that holds the piece's last sample
            i = bisect_left(moved, y)
            out.append(Piece(j, i, weight, moment[y] - moment[x]))
        found = tuple(out)
        self._pieces[key] = found
        return found
