"""Goal 2D: every threshold, tolerance and builder call that governs the stretched
ranges, declared here before any score is computed on the demo companies.

The candidate (design doc, Goal 2D): the simulated range is stretched away from its
median by a lower and an upper factor per tested horizon (1, 3 and 6 months), each the
smallest factor, never below 1, that would have put at least ``SIDE_COVERAGE`` of the
eligible past folds inside on that side. A fold is eligible for a forecast dated D only
if its whole horizon had ended by D. The report's own ranges use every fold eligible at
the as-of date; a back-test fold is scored with the factors learned from the folds
eligible at its own date, and is not scored with fewer than ``MIN_ELIGIBLE_FOLDS`` of
them. Coverage of the stretched and the simulated 80% range is counted on the same
scored folds.

The adoption rule, per company: adopted if there are at least ``MIN_SCORED_FOLDS``
scored folds at 1 and at 3 months, pooled 80% coverage over 1 and 3 months is closer to
80% than the simulated range's on the same folds, and no horizon (1, 3 or 6 months)
moves more than ``MAX_WORSENING`` further from 80%. Otherwise the simulated ranges stay,
the report says "not adopted" with the numbers or "not enough history" with the counts.
No second attempt: nothing here changes once a company's score has been seen. A bug in
the implementation of the declared candidate is corrected and re-scored, and said so;
that is not a second candidate.

Builder calls (the spec's silences), each with its reason; where the spec could be read
two ways the reading that is harder to pass is taken:

1. "Closer to 80%" is strictly closer: a tie is not adopted.
2. "More than 10 points further" is read literally: exactly ten points is allowed,
   ten and a fraction is not. Coverage is compared as exact fractions, never floats.
3. Pooled coverage pools folds (inside over scored, summed over 1 and 3 months), not
   the two horizons' percentages.
4. A horizon with no scored fold at all (6 months can have none, because a six-month
   fold needs five earlier folds whose six months had ended) cannot move, so the
   10-point test skips it and the report says it was not scored. A horizon with scored
   folds is tested however few: at one scored fold the test is a coin flip, and the
   rule says so rather than exempting it.
5. The six-month factors stretch every range that spans more than six months, and the
   label says so. A range belongs to the smallest tested horizon that is at least the
   number of months from the as-of date to the end of the range's last month: a
   one-month window nine months out is not a one-month forecast.
6. "Smallest factor that puts at least 90% inside": with n eligible folds, the
   ceil(0.9 * n)-th smallest of the factors each fold would have needed, in integers.
7. A fold the factor cannot reach (its median sits exactly on the edge of the range,
   so no finite stretch helps) needs an infinite factor; the side is left unstretched
   and the fold counts as a miss.
8. Stretching never takes a bookings total below zero: a stretched lower edge is
   floored at 0.

Recovery fixtures (``test_tc_stretch_fixtures``), tolerances declared before the
fixtures were run:

- no shift: every factor, over three seeds, three horizons and two sides, is at most
  ``NO_SHIFT_MAX_FACTOR`` and the median of them at most ``NO_SHIFT_MEDIAN_FACTOR``.
  Basis: a well-calibrated side has a 10% miss rate, so the 90% rank is exceeded by a
  few small misses (a miss at the 92nd percentile of a normal needs about 1.08 of the
  distance to the 90th), plus the fit's own error on 40 deals a month.
- a common shift (advance probabilities x ``SHIFT_FACTOR`` from the middle of the
  history): pooled over the seeds, the simulated range holds at most
  ``SHIFT_MAX_SIMULATED`` of the scored 1 and 3 month actuals and the stretched range
  holds at least ``SHIFT_MIN_GAIN`` more.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

HORIZONS = (1, 3, 6)
SCORED_HORIZONS = (1, 3)  # the horizons whose pooled coverage must move closer

TARGET = Fraction(4, 5)  # the nominal two-sided coverage
SIDE_COVERAGE = Fraction(9, 10)  # per side, so about 80% two-sided
MIN_ELIGIBLE_FOLDS = 5
MIN_SCORED_FOLDS = 6
MAX_WORSENING = Fraction(1, 10)

ADOPTED, NOT_ADOPTED, NOT_ENOUGH_HISTORY = (
    "adopted",
    "not adopted",
    "not enough history",
)

# Recovery fixtures.
FIXTURE_SEEDS = 3
NO_SHIFT_MAX_FACTOR = 1.35
NO_SHIFT_MEDIAN_FACTOR = 1.10
SHIFT_FACTOR = 0.5
SHIFT_MAX_SIMULATED = 0.60
SHIFT_MIN_GAIN = 0.15


def side_rank(eligible: int) -> int:
    """How many of ``eligible`` folds must be inside on a side: ceil(0.9 * n), exactly."""
    return -(-eligible * SIDE_COVERAGE.numerator // SIDE_COVERAGE.denominator)


@dataclass(frozen=True)
class Counts:
    """One horizon's scored folds, and how many of them each range held."""

    horizon: int
    scored: int
    inside_simulated: int
    inside_stretched: int


@dataclass(frozen=True)
class Decision:
    outcome: str
    reason: str
    pooled: tuple[Fraction, Fraction] | None  # (simulated, stretched), 1 and 3 months
    worst: tuple[int, Fraction] | None  # (horizon, points further from 80%)


def _pct(x: Fraction) -> str:
    return f"{float(x):.0%}"


def _distance(coverage: Fraction) -> Fraction:
    return abs(coverage - TARGET)


def decide(counts: list[Counts]) -> Decision:
    """The declared rule, applied to one company's scored folds."""
    by_h = {c.horizon: c for c in counts}
    for h in SCORED_HORIZONS:
        n = by_h[h].scored if h in by_h else 0
        if n < MIN_SCORED_FOLDS:
            return Decision(
                NOT_ENOUGH_HISTORY,
                f"{n} scored folds at {h} month(s); at least {MIN_SCORED_FOLDS} are needed",
                None,
                None,
            )
    scored = sum(by_h[h].scored for h in SCORED_HORIZONS)
    simulated = Fraction(sum(by_h[h].inside_simulated for h in SCORED_HORIZONS), scored)
    stretched = Fraction(sum(by_h[h].inside_stretched for h in SCORED_HORIZONS), scored)
    pooled = (simulated, stretched)
    text = (
        f"pooled over 1 and 3 months, {scored} scored folds: simulated "
        f"{sum(by_h[h].inside_simulated for h in SCORED_HORIZONS)} held ({_pct(simulated)}), "
        f"stretched {sum(by_h[h].inside_stretched for h in SCORED_HORIZONS)} held ({_pct(stretched)})"
    )
    worst: tuple[int, Fraction] | None = None
    for c in counts:
        if not c.scored:
            continue
        further = _distance(Fraction(c.inside_stretched, c.scored)) - _distance(
            Fraction(c.inside_simulated, c.scored)
        )
        if worst is None or further > worst[1]:
            worst = (c.horizon, further)
    if not _distance(stretched) < _distance(simulated):
        return Decision(
            NOT_ADOPTED,
            f"{text}; the stretched coverage is not closer to 80%",
            pooled,
            worst,
        )
    if worst is not None and worst[1] > MAX_WORSENING:
        return Decision(
            NOT_ADOPTED,
            f"{text}; at {worst[0]} month(s) the stretched coverage is {float(worst[1]) * 100:.0f} "
            f"points further from 80%, more than the {float(MAX_WORSENING) * 100:.0f} allowed",
            pooled,
            worst,
        )
    return Decision(
        ADOPTED,
        f"{text}; the stretched coverage is closer to 80% and no horizon is more than "
        f"{float(MAX_WORSENING) * 100:.0f} points further",
        pooled,
        worst,
    )
