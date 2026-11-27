"""Goal 2B: plan.yaml (the only source of further hires and of programme
pipeline) and the arithmetic of a programme's ramp."""

from datetime import date
from decimal import Decimal

import pytest
import yaml

from engine.tieout_core.fiscal import month_windows
from engine.tieout_core.plan import (
    PlanProgramme,
    load_plan,
    next_month_start,
    programme_cost,
    programme_inflows,
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


def test_a_plan_is_hires_then_programmes_in_file_order(tmp_path):
    path = write(
        tmp_path,
        {
            "programmes": [{"name": "P1", "pipeline": 1000, "start": "2026-08"}],
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
        "2 mm hires from 2026-09",
        "1 ent hire from 2026-08",
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
                {"programmes": [{"name": "x", "pipeline": -5, "start": "2026-09"}]},
            ),
            AS_OF,
            (),
        )


def programme(pipeline, start="2026-09-01", ramp=None, months=None, cost=None):
    return PlanProgramme(
        "P", Decimal(pipeline), date.fromisoformat(start), ramp, months, cost
    )


def test_programme_ramp_arithmetic_by_hand_over_four_months():
    # $900,000 over four months (July to October) with a three-month ramp: month j
    # runs at min(1, j/3) of full rate, so the weights are 1/3, 2/3, 1, 1, which
    # add to 3, and the months get 1/9, 2/9, 3/9, 3/9 of the dollars:
    # $100,000, $200,000, $300,000, $300,000.
    flows = programme_inflows(
        programme(900_000, "2026-07-01", ramp=3, months=4), WINDOWS, AS_OF, FY_END, 3
    )
    assert [round(f.dollars) for f in flows] == [100_000, 200_000, 300_000, 300_000]
    assert sum((f.dollars for f in flows), Decimal(0)) == pytest.approx(
        Decimal(900_000)
    )
    # each month's dollars are created evenly over that month's days
    assert [(f.start, f.end) for f in flows] == [(0, 31), (31, 62), (62, 92), (92, 123)]


def test_a_programme_runs_to_the_fiscal_year_end_unless_it_says_otherwise():
    # Starting 2026-09 with a two-month ramp, through January 2027: five months with
    # weights 1/2, 1, 1, 1, 1 (4.5): the first month gets 1/9 of the dollars.
    flows = programme_inflows(
        programme(900_000, "2026-09-01", ramp=2), WINDOWS, AS_OF, FY_END, 3
    )
    assert len(flows) == 5
    assert flows[0].dollars == pytest.approx(Decimal(100_000))
    assert flows[1].dollars == pytest.approx(Decimal(200_000))


def test_the_configured_ramp_is_used_when_the_plan_gives_none():
    # Ramp 3 over three months: weights 1/3, 2/3, 1 add to 2, so 1/6, 1/3, 1/2 of $300,000.
    flows = programme_inflows(
        programme(300_000, "2026-09-01", months=3), WINDOWS, AS_OF, FY_END, 3
    )
    assert [round(f.dollars) for f in flows] == [50_000, 100_000, 150_000]


def test_a_programmes_cost_is_its_own_or_pipeline_times_the_rate_or_not_entered():
    assert programme_cost(
        programme(1000, cost=Decimal(70)), Decimal("0.05")
    ) == Decimal(70)
    assert programme_cost(programme(1000), Decimal("0.05")) == Decimal(50)
    assert programme_cost(programme(1000), None) is None
