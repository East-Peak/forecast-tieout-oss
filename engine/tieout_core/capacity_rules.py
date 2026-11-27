"""Goal 2B: every threshold, tolerance and builder call that governs a score,
declared here before any score is computed.

The adoption test (design doc, Goal 2B) asks whether headcount explains
created pipeline, conditional on realized staffing. It is scored on created
pipeline dollars, at 3 and 6 months, on the same folds as the back-test. The
per-rep rate is fitted only from data before each cutoff, then applied to the
ramped AE-months that actually occurred. Capacity is adopted only if all of:

- ramped AE-months varied by at least ``MIN_STAFFING_VARIATION`` across the
  scored period (variation = (largest - smallest) / mean of the monthly
  ramped AE-month totals, over the calendar months from the earliest scored
  cutoff to the last observed date; the roster is today's, the ramp the one
  fitted or entered at the as-of date);
- the capacity predictor's mean absolute error is at least ``MIN_IMPROVEMENT``
  lower than the flat trailing rate's, i.e. (flat - capacity) / flat >= 0.10,
  at both horizons;
- there are at least ``MIN_FOLDS`` folds at each horizon.

No second attempt after a score: nothing here is changed once a company's
result has been seen.

Builder calls (the spec's "left to the builder"), each with its reason:

1. An AE-month is a fixed ``DAYS_PER_AE_MONTH`` days (365.25 / 12), not a
   calendar month, so a roster that reproduces history's ramped AE-months
   reproduces history's daily creation exactly (the baseline-equivalence
   fixture) and the synthetic generator's own convention is matched. Cash cost
   is a different thing and uses calendar months (see ``plan.py``).
2. Tenure months are anniversary months: tenure month k of a rep who started
   on s is [s + (k-1) months, s + k months). Ramp weights are given for tenure
   months 1..n and are 1 after n. The reference for "ramped" is a rep with
   ``TENURED_AFTER_MONTHS`` or more months' tenure. A fit needs
   ``RAMP_MIN_REPS`` reps observed from hire through their sixth month
   (``RAMP_ELIGIBLE_MONTHS``, the spec's gate) and then estimates every tenure
   month before the reference (``RAMP_FITTED_MONTHS`` = 11), so a ramp longer
   than six months is not forced to one at month seven.
3. At a past cutoff a departure dated on or before the cutoff is known (it
   happened); one dated after is hidden and the person is treated as still
   employed. A start after the cutoff is hidden. At the as-of date itself a
   start after it is a signed hire and an end date after it a signed departure.
4. Created-pipeline dollars use ``history.creation_amounts`` (first recorded
   amount), the single rule from Goal 1; deals with no recorded amount add
   nothing to either side of a comparison.
5. The per-rep rate is dollars (or deals, for the forward function) created in
   the trailing ``TRAILING_DAYS`` days per ramped AE-month in the same days.
6. Expected attrition is a constant daily hazard: the monthly rate r (per
   AE-month) gives a daily survival of (1 - r) ** (1 / DAYS_PER_AE_MONTH).
   Departures in the ranges are geometric draws from the same hazard, so the
   draws are centered on the expectation.
7. Defaults, used only where neither history nor capacity.yaml supplies a
   value, are labeled "default": a linear six-month ramp and an attrition of
   1.5% per AE-month (about 17% a year, a round figure in line with public
   sales-headcount commentary; no company's figure).

Recovery tolerances (the fitted ramp and attrition must recover a known truth
on generated fixtures; 200 seeds, the true value inside the 95% range in at
least ``RECOVERY_MIN_COVERAGE`` of them, and a point-error bound so a wide
range cannot pass alone). The fixtures are in ``test_tc_ramp.py``:

- ramp: 40 hired reps, 8 reps already tenured, 8 deals per full-ramp rep-month,
  linear ramp over six months, a fit of tenure months 1 to 11. Expected
  relative standard error of one month's weight is about 0.07 at full ramp and
  smaller before it, so the median absolute error of the mean across the
  eleven months is about 0.035; the tolerance 0.06 is 1.7 times that.
- attrition: 40 reps over 30 months, 2% a month: about 24 departures over about
  1,200 AE-months, standard error 0.004; the median absolute error of an
  unbiased estimate is about 0.0028; the tolerance 0.004 is one standard
  error.
"""

from __future__ import annotations

from decimal import Decimal

DAYS_PER_AE_MONTH = Decimal("30.4375")
TRAILING_DAYS = 365

# The adoption test.
SCORED_HORIZONS = (3, 6)
MIN_FOLDS = 6
MIN_STAFFING_VARIATION = Decimal("0.20")
MIN_IMPROVEMENT = Decimal("0.10")

# Fitting ramp and attrition.
TENURED_AFTER_MONTHS = 12
RAMP_ELIGIBLE_MONTHS = 6
RAMP_FITTED_MONTHS = TENURED_AFTER_MONTHS - 1
RAMP_MIN_REPS = 8
RAMP_MIN_TENURED = 3
MIN_DEPARTURES = 5

# Defaults, labeled as such wherever used.
DEFAULT_RAMP = tuple(Decimal(2 * k - 1) / 12 for k in range(1, 7))
DEFAULT_MONTHLY_ATTRITION = Decimal("0.015")

# Recovery on generated fixtures.
RECOVERY_SEEDS = 200
RECOVERY_MIN_COVERAGE = 0.90
RAMP_POINT_TOLERANCE = 0.06
ATTRITION_POINT_TOLERANCE = 0.004
