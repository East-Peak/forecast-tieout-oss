"""Goal 2B: plan.yaml (the only source of further hires and of program
pipeline) and the arithmetic of a program's ramp."""

import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from engine.tests.tieout_core.builders import write_profile
from engine.tests.tieout_core.test_tc_backtest import AS_OF as HISTORY_AS_OF
from engine.tests.tieout_core.test_tc_backtest import regular_history
from engine.tieout_core.actions import Ground, Scenario, plan_section
from engine.tieout_core.adoption import UNAVAILABLE, Adoption
from engine.tieout_core.capacity_config import RosterLoad
from engine.tieout_core.capacity_report import Capacity
from engine.tieout_core.fiscal import month_windows
from engine.tieout_core.fit import fit
from engine.tieout_core.history import as_known_at
from engine.tieout_core.load import load_profile
from engine.tieout_core.plan import (
    Plan,
    PlanProgram,
    load_plan,
    next_month_start,
    program_cost,
    program_inflows,
)
from engine.tieout_core.roster import Member

AS_OF = date(2026, 6, 30)
WINDOWS = month_windows(AS_OF, date(2027, 6, 30))  # 2026-07 .. 2027-06
FY_END = date(2027, 1, 31)


def write(tmp_path, doc):
    path = tmp_path / "plan.yaml"
    path.write_text(yaml.safe_dump(doc))
    return path


def test_the_next_month_starts_on_the_first_day_after_the_as_of_month():
    assert next_month_start(date(2026, 8, 31)) == date(2026, 9, 1)
    assert next_month_start(date(2026, 8, 1)) == date(2026, 9, 1)
    assert next_month_start(date(2026, 12, 15)) == date(2027, 1, 1)


def test_a_plan_is_hires_then_programs_in_file_order(tmp_path):
    path = write(
        tmp_path,
        {
            "programs": [{"name": "P1", "pipeline": 1000, "start": "2026-08"}],
            "hires": [
                {"segment": "mm", "start": "2026-09", "count": 2},
                {"segment": "ent", "start": "2026-08", "count": 1},
            ],
        },
    )
    plan = load_plan(path, AS_OF, ())
    assert [(h.segment, h.start, h.count) for h in plan.hires] == [
        ("mm", date(2026, 9, 1), 2),
        ("ent", date(2026, 8, 1), 1),
    ]
    assert [i.label for i in plan.items()] == [
        "2 Mm hires from 2026-09",
        "1 Ent hire from 2026-08",
        "P1",
    ]
    members = plan.hire_members()
    assert len(members) == 3 and {m.role for m in members} == {"ae"}
    assert [m.start for m in members] == [date(2026, 9, 1)] * 2 + [date(2026, 8, 1)]


def test_a_plan_may_not_repeat_a_signed_hire(tmp_path):
    signed = [Member("S1", "ae", "mm", date(2026, 9, 14), None, None)]
    path = write(
        tmp_path, {"hires": [{"segment": "mm", "start": "2026-09", "count": 1}]}
    )
    with pytest.raises(ValueError, match="repeats a signed hire"):
        load_plan(path, AS_OF, signed)
    other = write(
        tmp_path, {"hires": [{"segment": "ent", "start": "2026-09", "count": 1}]}
    )
    assert load_plan(
        other, AS_OF, signed
    ).hires  # a different segment is a different hire


def test_a_plan_item_must_start_after_the_as_of_date(tmp_path):
    path = write(
        tmp_path, {"hires": [{"segment": "mm", "start": "2026-06", "count": 1}]}
    )
    with pytest.raises(ValueError, match="after the as-of"):
        load_plan(path, AS_OF, ())


def test_a_malformed_plan_is_refused_with_the_reason(tmp_path):
    with pytest.raises(ValueError, match="count"):
        load_plan(
            write(
                tmp_path, {"hires": [{"segment": "mm", "start": "2026-09", "count": 0}]}
            ),
            AS_OF,
            (),
        )
    with pytest.raises(ValueError, match="pipeline"):
        load_plan(
            write(
                tmp_path,
                {"programs": [{"name": "x", "pipeline": -5, "start": "2026-09"}]},
            ),
            AS_OF,
            (),
        )


def program(
    pipeline, start="2026-09-01", ramp=None, months=None, cost=None, payments=None
):
    return PlanProgram(
        "P", Decimal(pipeline), date.fromisoformat(start), ramp, months, cost, payments
    )


def test_program_ramp_arithmetic_by_hand_over_four_months():
    # $900,000 over four months (July to October) with a three-month ramp: month j
    # runs at min(1, j/3) of full rate, so the weights are 1/3, 2/3, 1, 1, which
    # add to 3, and the months get 1/9, 2/9, 3/9, 3/9 of the dollars:
    # $100,000, $200,000, $300,000, $300,000.
    flows = program_inflows(
        program(900_000, "2026-07-01", ramp=3, months=4), WINDOWS, AS_OF, FY_END, 3
    )
    assert [round(f.dollars) for f in flows] == [100_000, 200_000, 300_000, 300_000]
    assert sum((f.dollars for f in flows), Decimal(0)) == pytest.approx(
        Decimal(900_000)
    )
    # each month's dollars are created evenly over that month's days
    assert [(f.start, f.end) for f in flows] == [(0, 31), (31, 62), (62, 92), (92, 123)]


def test_a_program_runs_to_the_fiscal_year_end_unless_it_says_otherwise():
    # Starting 2026-09 with a two-month ramp, through January 2027: five months with
    # weights 1/2, 1, 1, 1, 1 (4.5): the first month gets 1/9 of the dollars.
    flows = program_inflows(
        program(900_000, "2026-09-01", ramp=2), WINDOWS, AS_OF, FY_END, 3
    )
    assert len(flows) == 5
    assert flows[0].dollars == pytest.approx(Decimal(100_000))
    assert flows[1].dollars == pytest.approx(Decimal(200_000))


def test_the_configured_ramp_is_used_when_the_plan_gives_none():
    # Ramp 3 over three months: weights 1/3, 2/3, 1 add to 2, so 1/6, 1/3, 1/2 of $300,000.
    flows = program_inflows(
        program(300_000, "2026-09-01", months=3), WINDOWS, AS_OF, FY_END, 3
    )
    assert [round(f.dollars) for f in flows] == [50_000, 100_000, 150_000]


def test_a_programs_cost_is_its_own_or_pipeline_times_the_rate_or_not_entered():
    assert program_cost(program(1000, cost=Decimal(70)), Decimal("0.05")) == Decimal(70)
    assert program_cost(program(1000), Decimal("0.05")) == Decimal(50)
    assert program_cost(program(1000), None) is None


# ---------------------------------------------------------------- ordered contributions


def test_ordered_plan_contributions_by_hand():
    # A world where every created deal books exactly 45 days later at its full size
    # (win rate 1), so a program's dollars book on the day they are created plus 45.
    # Fiscal year ends 2027-01-31; the as-of is 2026-06-30.
    #   A: $360,000 over July, August, September (ramp 1: equal thirds). Everything
    #      is created by 09-30 and booked by 11-14, inside the year: it adds $360,000
    #      to the rest of the year and to the twelve months.
    #   B: $240,000 over December and January: $120,000 each. December's books from
    #      01-15 to 02-14 and counts for the year only up to 01-31, i.e. the deals
    #      created 12-01..12-17 = 17 of 31 days: 120,000 x 17/31 = 65,806.45 (to the
    #      cent). January's books after 02-15: nothing in the year. In twelve months B
    #      adds all $240,000.
    with tempfile.TemporaryDirectory() as tmp:
        profile = load_profile(write_profile(Path(tmp)))
        data = regular_history()
        model = fit(as_known_at(data, HISTORY_AS_OF), HISTORY_AS_OF, profile)
    plan = Plan(
        (),
        (
            PlanProgram("A", Decimal(360_000), date(2026, 7, 1), 1, 3, None),
            PlanProgram("B", Decimal(240_000), date(2026, 12, 1), 1, 2, None),
        ),
    )
    cap = Capacity(
        None,
        RosterLoad((), (), {}, 0, "none"),
        Adoption(UNAVAILABLE, "none"),
        None,
        None,
        365,
        None,
    )
    labels = [w.label for w in WINDOWS]
    rest = [w.label for w in WINDOWS if w.end <= FY_END]
    g = Ground(cap, model, data, AS_OF, WINDOWS, rest, labels, rest, Decimal(0), Decimal(10**9), date(2026, 2, 1),
               FY_END, None, Decimal(0), Decimal(10**9), 365)  # fmt: skip
    section, checks = plan_section(g, Scenario(g), plan, Path("plan.yaml"))
    a, b = section["items"]
    # (every month is shown to the cent, so a total can be a few cents from the exact figure)
    near = Decimal("0.06")
    assert abs(Decimal(a["contribution"]["rest of fiscal year"]) - 360_000) <= near
    assert abs(Decimal(a["contribution"]["next twelve months"]) - 360_000) <= near
    assert (
        abs(Decimal(b["contribution"]["rest of fiscal year"]) - Decimal("65806.45"))
        <= near
    )
    assert abs(Decimal(b["contribution"]["next twelve months"]) - 240_000) <= near
    assert abs(Decimal(section["difference"]["next twelve months"]) - 600_000) <= near
    assert all(c.passed for c in checks)


# ---------------------------------------------------------------- review round: full schedule first


def test_a_program_longer_than_the_window_is_normalized_over_its_whole_length():
    # $2.4M over 24 months with a one-month ramp is $100,000 a month: the first
    # twelve months carry $1.2M, not all $2.4M.
    flows = program_inflows(
        program(2_400_000, "2026-07-01", ramp=1, months=24), WINDOWS, AS_OF, FY_END, 3
    )
    assert len(flows) == 12
    assert sum((f.dollars for f in flows), Decimal(0)) == pytest.approx(
        Decimal(1_200_000)
    )


def test_a_partial_final_month_takes_its_share_of_the_days_inside_the_window():
    # As of 2026-06-15 the window ends 2027-06-15. A 12-month program of $1.2M
    # (ramp 1, $100,000 a month) from July has June 2027 as its last month, of which
    # 15 of 30 days fall inside: 11 x 100,000 + 50,000.
    as_of = date(2026, 6, 15)
    windows = month_windows(as_of, date(2027, 6, 15))
    flows = program_inflows(
        program(1_200_000, "2026-07-01", ramp=1, months=12), windows, as_of, FY_END, 3
    )
    assert sum((f.dollars for f in flows), Decimal(0)) == pytest.approx(
        Decimal(1_150_000)
    )
    assert flows[-1].dollars == pytest.approx(Decimal(50_000))


def test_only_the_cost_that_falls_in_the_window_is_counted_cost_follows_the_pipeline():
    # $2.4M over 24 months at 5 cents a dollar costs $120,000, paid in step with the
    # pipeline it creates: half of it falls in the first twelve months.
    from engine.tieout_core.plan import program_cost_in_window

    p = program(2_400_000, "2026-07-01", ramp=1, months=24)
    flows = program_inflows(p, WINDOWS, AS_OF, FY_END, 3)
    assert program_cost_in_window(
        p, Decimal("0.05"), flows, WINDOWS[-1].end
    ) == pytest.approx(Decimal(60_000))
    assert program_cost_in_window(p, None, flows, WINDOWS[-1].end) is None


def test_a_program_that_starts_late_pays_only_for_what_it_creates_in_the_window():
    from engine.tieout_core.plan import program_cost_in_window

    # Starts 2027-04 for 6 months at ramp 1: April, May, June 2027 are in the window
    # (half the program), so half of a $60,000 cost.
    p = program(600_000, "2027-04-01", ramp=1, months=6, cost=Decimal(60_000))
    flows = program_inflows(p, WINDOWS, AS_OF, FY_END, 3)
    assert program_cost_in_window(p, None, flows, WINDOWS[-1].end) == pytest.approx(
        Decimal(30_000)
    )


def test_a_payment_schedule_in_the_plan_overrides_the_default():
    from engine.tieout_core.plan import program_cost_in_window

    p = program(600_000, "2026-10-01", ramp=1, months=24,
                  payments=((date(2026, 10, 1), Decimal(40_000)), (date(2028, 1, 1), Decimal(10_000))))  # fmt: skip
    flows = program_inflows(p, WINDOWS, AS_OF, FY_END, 3)
    assert program_cost_in_window(p, Decimal("0.5"), flows, WINDOWS[-1].end) == Decimal(
        40_000
    )


def test_a_plan_loads_payments_and_refuses_a_payment_before_the_as_of(tmp_path):
    ok = write(tmp_path, {"programs": [{"name": "x", "pipeline": 100, "start": "2026-09",
                                          "payments": [{"month": "2026-09", "amount": 5}]}]})  # fmt: skip
    assert load_plan(ok, AS_OF, ()).programs[0].payments == (
        (date(2026, 9, 1), Decimal(5)),
    )
    bad = write(tmp_path, {"programs": [{"name": "x", "pipeline": 100, "start": "2026-09",
                                           "payments": [{"month": "2026-05", "amount": 5}]}]})  # fmt: skip
    with pytest.raises(ValueError, match="payments"):
        load_plan(bad, AS_OF, ())
