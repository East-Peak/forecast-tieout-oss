"""Cases whose expected values are worked out here, from first principles, with plain fractions:
never through ``Probe`` or ``Scenario``. A win lands ``t + d`` days after the cutoff for a deal
created on day ``t`` with a win time of ``d``; a creation day contributes
``deals x win rate x won ARR / total timing weight`` to every window its wins land in."""

from datetime import date
from decimal import Decimal
from fractions import Fraction as F

from engine.tieout_core import worksheet_drivers as wd
from engine.tieout_core import worksheet_rules as rules
from engine.tieout_core.actions import Ground
from engine.tieout_core.adoption import ADOPTED, UNAVAILABLE, Adoption
from engine.tieout_core.capacity import CapacityFit
from engine.tieout_core.capacity_config import RosterLoad
from engine.tieout_core.capacity_report import Capacity
from engine.tieout_core.fiscal import month_windows
from engine.tieout_core.fit import FitParams, Model, NewPipeline, Timing
from engine.tieout_core.forecast import Creation, Inflow
from engine.tieout_core.ramp import Attrition, RampFit
from engine.tieout_core.rates import RateBook
from engine.tieout_core.records import Dataset
from engine.tieout_core.roster import Member, RampCurve

D = Decimal
AS_OF = date(2026, 8, 31)
FY_END = date(2026, 12, 31)
WINDOWS = month_windows(AS_OF, date(2027, 8, 31))
H = (WINDOWS[-1].end - AS_OF).days
PER_MONTH = F(3043750, 100000)  # an AE-month is 30.4375 days
REP = Member("A", "ae", "mm", date(2020, 1, 1), None, None)
HIRE = Member("H", "ae", "mm", date(2026, 10, 1), None, None)


def build(
    timing,
    weights=None,
    won=1000,
    wr="0.5",
    created_per_day="0.2",
    created_arr=2000,
    rate=None,
):
    new = NewPipeline(
        win_rate=D(wr), timing=Timing(timing, "t", weights), mean_won_arr=D(won),
        mean_created_arr=D(created_arr), created_per_day=D(created_per_day),
        won_arr_samples=(D(won),), cohort_size=10,
    )  # fmt: skip
    model = Model(
        cutoff=AS_OF, params=FitParams(), rates=RateBook(), cells={}, stage_rates={}, timings={},
        new_pipeline=new, unknown_stage_observations=0,
    )  # fmt: skip
    if rate is None:
        cap = Capacity(None, RosterLoad((), (), {}, 0, "none"), Adoption(UNAVAILABLE, "none"), None, None, H, None)  # fmt: skip
    else:
        fit = CapacityFit(
            AS_OF, RampFit(RampCurve((), "entered"), 0, 0), Attrition(D(0), "entered", 0, D(0)),
            D(rate), 0, D(0),
        )  # fmt: skip
        cap = Capacity(
            None, RosterLoad((REP,), (), {}, 1, ""), Adoption(ADOPTED, "x"), fit, Creation((), ""), H, None
        )  # fmt: skip
    rest = [w.label for w in WINDOWS if w.end <= FY_END]
    labels = [w.label for w in WINDOWS]
    return Ground(
        cap, model, Dataset((), (), None), AS_OF, WINDOWS, rest, labels, rest,
        D(0), D(10**9), date(2026, 2, 1), FY_END, None, D(0), D(10**9), H,
    )  # fmt: skip


def by_hand(samples, weights, per_day, won, wr, flows=(), created_arr=2000):
    """Expected new-pipeline bookings in each window, as exact fractions. ``per_day(t)`` is the
    deals created on day ``t``; ``flows`` are (start, end, dollars)."""
    weights = weights or (1,) * len(samples)
    total = sum(F(w) for w in weights)
    k = F(wr) * F(won) / total

    def through(x):
        return sum((F(w) for d, w in zip(samples, weights) if d <= x), F(0))

    out = {}
    for w in WINDOWS:
        a, b = (w.start - AS_OF).days, (w.end - AS_OF).days
        flat = sum(
            (
                F(per_day(t)) * k * (through(b - t) - through(a - t))
                for t in range(1, H + 1)
            ),
            F(0),
        )
        for s, e, dollars in flows:
            deals = F(dollars) / (e - s) / F(created_arr)
            flat += sum(
                (
                    deals * k * (through(b - t) - through(a - t))
                    for t in range(s + 1, e + 1)
                ),
                F(0),
            )
        out[w.label] = flat
    return out


def run(g, hires=(), inflows=()):
    probe = wd.Probe(g, hires, inflows)
    f = probe.forecast(g)
    parts = ("future pipeline", "added pipeline")
    return {
        w.label: sum(
            (f.components[p][w.label] for p in parts if p in f.components), D(0)
        )
        for w in WINDOWS
    }


def close(got, want):
    for label in want:
        assert abs(F(got[label]) - want[label]) <= F(1, 10**15) * max(
            F(1), abs(want[label])
        ), label


def test_weighted_timing_counts_each_day_by_its_weight():
    # win times 10 and 20 days, weighted 3 and 1: three quarters of wins land after ten days
    g = build((10, 20), (D(3), D(1)))
    close(run(g), by_hand((10, 20), (3, 1), lambda t: F(1, 5), 1000, F(1, 2)))


def test_the_mean_of_a_weighted_timing_is_the_weighted_mean():
    assert wd.timing_mean(Timing((10, 20), "t", (D(3), D(1)))) == D("12.5")


def test_a_cycle_scale_keeps_the_weights_and_rounds_each_day_up():
    g = build((10, 21), (D(3), D(1)))
    scaled = wd.with_cycle_scale(g, F(1, 2))
    # 10 -> 5 and 21 -> 11 (ten and a half rounds up), still weighted three to one
    close(run(scaled), by_hand((5, 11), (3, 1), lambda t: F(1, 5), 1000, F(1, 2)))


def test_adopted_capacity_with_a_hire_and_a_program_and_productivity_changed():
    # rate 2 deals per ramped AE-month; the rep is fully ramped, the hire (curve with no
    # entries) counts as ramped from the first day; no attrition. Productivity moves to 3.
    g = build((30, 60), rate="2")
    hires, flows = (HIRE,), (Inflow(30, 120, D(600_000)),)
    hire_day = (
        HIRE.start - AS_OF
    ).days  # the first offset on which the hire is employed

    def per_day(rate):
        return lambda t: F(rate) * (1 + (1 if t >= hire_day else 0)) / PER_MONTH

    changed = wd.with_setting(g, rules.PRODUCTIVITY, D(3))
    want = by_hand((30, 60), None, per_day(3), 1000, F(1, 2), [(30, 120, 600_000)])
    close(run(changed, hires, flows), want)
    # and the program part alone does not move with productivity
    base = by_hand((30, 60), None, lambda t: 0, 1000, F(1, 2), [(30, 120, 600_000)])
    close(run(build((30, 60), rate="0"), hires, flows), base)


def test_a_size_change_scales_program_bookings_but_not_the_deals_a_program_buys():
    # $400,000 over days 10 to 110 at $2,000 a created deal is 2 deals a day, whatever a win is
    # worth; doubling won ARR doubles what those deals book.
    g = build((30,), created_per_day="0", won=1000)
    flows = (Inflow(10, 110, D(400_000)),)
    before = by_hand((30,), None, lambda t: 0, 1000, F(1, 2), [(10, 110, 400_000)])
    after = by_hand((30,), None, lambda t: 0, 2000, F(1, 2), [(10, 110, 400_000)])
    close(run(g, inflows=flows), before)
    close(run(wd.with_setting(g, rules.WON_ARR, D(2000)), inflows=flows), after)
    assert all(after[k] == 2 * before[k] for k in before)


def test_a_win_rate_above_one_is_a_win_rate_of_one():
    g = build((30,))
    close(
        run(wd.with_setting(g, rules.WIN_RATE, D(3))),
        by_hand((30,), None, lambda t: F(1, 5), 1000, F(1)),
    )


def test_a_cycle_of_zero_days_everywhere_is_a_zero_day_win():
    # a sample of zero days lands the win on the creation day itself
    g = build((0,))
    close(run(g), by_hand((0,), None, lambda t: F(1, 5), 1000, F(1, 2)))
