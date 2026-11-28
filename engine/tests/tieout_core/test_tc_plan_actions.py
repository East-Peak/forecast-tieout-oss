"""Actions on a slice: the plan item, how a plan file or the editor's plan names it, and what
it refuses."""

from datetime import date
from decimal import Decimal

import pytest

from engine.tieout_core.plan import (
    Plan,
    PlanAction,
    PlanHire,
    PlanProgram,
    parse_plan,
)
from engine.tieout_core.roster import Member

AS_OF = date(2026, 8, 31)
MEMBERS = (
    Member("A", "ae", "enterprise", date(2025, 1, 1), None, None),
    Member("B", "ae", "mid_market", date(2025, 1, 1), None, None),
)


def action(**over):
    base = {
        "id": "ent-win",
        "name": "Enterprise win rate",
        "driver": "win_rate",
        "slice": "enterprise",
        "start": "2026-10",
        "ramp_months": 2,
        "target": "0.25",
    }
    return {**base, **over}


def parse(*actions, **rest):
    return parse_plan({"actions": list(actions), **rest}, AS_OF, MEMBERS, "plan.yaml")


def refused(*actions):
    with pytest.raises(ValueError) as caught:
        parse(*actions)
    return str(caught.value)


def test_an_action_has_an_id_a_name_a_driver_a_slice_a_start_a_ramp_and_a_target():
    got = parse(action()).actions
    assert got == (
        PlanAction(
            "ent-win",
            "Enterprise win rate",
            "win_rate",
            "enterprise",
            date(2026, 10, 1),
            2,
            Decimal("0.25"),
        ),
    )


def test_the_company_is_a_slice_and_a_ramp_of_zero_is_immediate_and_the_default():
    plan = parse(action(slice="company", id="all"))
    assert plan.actions[0].segment is None and plan.actions[0].ramp_months == 2
    bare = parse({k: v for k, v in action().items() if k != "ramp_months"})
    assert bare.actions[0].ramp_months == 0
    assert parse(action(ramp_months=0)).actions[0].ramp_months == 0


def test_a_name_defaults_to_the_id():
    bare = {k: v for k, v in action().items() if k != "name"}
    assert parse(bare).actions[0].name == "ent-win"


def test_an_action_is_a_plan_item_after_hires_and_programs_and_keeps_its_place():
    plan = parse(
        action(),
        action(id="b", slice="mid_market"),
        hires=[{"segment": "enterprise", "start": "2026-09", "count": 1}],
        programs=[{"name": "P", "pipeline": 1000, "start": "2026-09"}],
    )
    kinds = [type(i) for i in plan.items()]
    assert kinds == [PlanHire, PlanProgram, PlanAction, PlanAction]
    assert [a.id for a in plan.actions] == ["ent-win", "b"]


def test_a_plan_with_no_actions_is_unchanged():
    plan = parse_plan({"hires": []}, AS_OF, MEMBERS, "plan.yaml")
    assert plan.actions == () and plan == Plan((), ())


@pytest.mark.parametrize("target", ["0", "0.0", 0, "1", 1, "0.2193", 0.5])
def test_the_probability_bounds_are_zero_and_one_inclusive(target):
    assert parse(action(target=target)).actions[0].target == Decimal(str(target))


@pytest.mark.parametrize("target", ["-0.01", "1.0001", 2, -1, "x", None, "nan"])
def test_a_target_outside_zero_and_one_or_no_number_is_refused(target):
    text = refused(action(target=target))
    assert text.startswith("plan.yaml: actions[1]: ") and "target" in text


def test_a_segment_nobody_is_in_is_refused_and_the_message_names_it():
    text = refused(action(slice="strategic"))
    assert (
        "actions[1]" in text and "'strategic' is not the company or a segment" in text
    )
    assert "(Enterprise, Mid Market)" in text and "slice" not in text


def test_an_unknown_driver_is_refused_and_lists_what_is_supported():
    text = refused(action(driver="cycle_days"))
    assert (
        "Only the win rate and won ARR per win can be changed by an action" in text
        and "win_rate" not in text
        and "cycle_days" not in text
    )
    assert "win rate" in refused({k: v for k, v in action().items() if k != "driver"})


def test_a_start_not_after_the_as_of_date_is_refused_as_every_other_item_is():
    text = refused(action(start="2026-08"))
    assert "actions[1]" in text and "not after the as-of date" in text
    assert "August 2026" in text and "August 31, 2026" in text and "2026-0" not in text
    assert parse(action(start="2026-09")).actions[0].start == date(2026, 9, 1)
    assert "start" in refused(action(start="soon"))


@pytest.mark.parametrize("ramp", [-1, 1.5, "2", True])
def test_a_ramp_is_a_whole_number_of_months_not_below_zero(ramp):
    text = refused(action(ramp_months=ramp))
    assert (
        "The ramp must be a whole number of months" in text
        and "ramp_months" not in text
    )


def test_an_action_needs_an_id_and_ids_are_unique():
    assert "id" in refused(action(id=""))
    assert "id" in refused({k: v for k, v in action().items() if k != "id"})
    text = refused(action(), action(slice="mid_market"))
    assert (
        "actions[2]" in text
        and "already has the id 'ent-win'" in text
        and "actions[1]" not in text.split(": ", 2)[2]
    )


def test_two_actions_on_the_same_driver_and_slice_are_refused_whatever_their_dates():
    text = refused(action(), action(id="b", start="2027-01", target="0.3"))
    assert text.endswith(
        "Overlaps 'Enterprise win rate': both change the win rate for Enterprise, so the change would be counted twice."
    )
    assert (
        "actions[1]" not in text.split(": ", 2)[2]
        and "win_rate" not in text
        and "enterprise" not in text.split(": ", 2)[2]
    )


@pytest.mark.parametrize("order", [(0, 1), (1, 0)])
def test_the_company_overlaps_every_segment_whichever_is_listed_first(order):
    pair = [action(slice="company", id="all"), action(id="b", slice="mid_market")]
    text = refused(*(pair[i] for i in order))
    body = text.split(": ", 2)[2]
    assert (
        body.startswith("Overlaps '")
        and "the whole company" in text
        and "actions[1]" not in body
    )


def test_different_segments_do_not_overlap():
    assert len(parse(action(), action(id="b", slice="mid_market")).actions) == 2


def test_shapes_that_are_not_actions_are_refused_with_a_message_not_a_crash():
    with pytest.raises(ValueError, match="actions"):
        parse_plan({"actions": [["not", "a mapping"]]}, AS_OF, MEMBERS, "plan.yaml")


def test_a_label_names_the_action_and_a_slice_label_the_slice():
    a = parse(action()).actions[0]
    assert a.label == "Enterprise win rate"
    assert a.slice_label == "Enterprise"
    assert parse(action(slice="company")).actions[0].slice_label == "Company"


# ------------------------------------------------------------ dispatch by kind


def _ground():
    from types import SimpleNamespace

    cap = SimpleNamespace(adopted=True, cfg=None)
    return SimpleNamespace(cap=cap, windows=[], as_of=AS_OF, fy_end=date(2027, 1, 31))


def test_an_action_is_not_a_program_so_it_adds_no_hires_and_no_pipeline():
    from engine.tieout_core.actions import plan_inputs

    plan = parse(
        action(), programs=[{"name": "P", "pipeline": 1000, "start": "2026-09"}]
    )
    hires, inflows = plan_inputs(_ground(), plan)
    assert (
        hires == () and len(inflows) == 0
    )  # no windows: the program's pipeline is clipped
    with_none = plan_inputs(_ground(), Plan((), (), parse(action()).actions))
    assert with_none == ((), ())


def test_an_item_of_a_kind_nobody_handles_is_an_error_not_a_program():
    from types import SimpleNamespace

    from engine.tieout_core.actions import plan_inputs

    stray = SimpleNamespace(items=lambda: [object()], members_for=lambda i: ())
    with pytest.raises(TypeError, match="plan item"):
        plan_inputs(_ground(), stray)


# ------------------------------------------------------------ the ramp's last day is a date


@pytest.mark.parametrize("ramp", [61, 100000, 10**9])
def test_a_ramp_longer_than_five_years_is_refused_where_it_is_read(ramp):
    text = refused(action(ramp_months=ramp))
    assert text.startswith("plan.yaml: actions[1]: The ramp") and "0 to 60" in text


def test_a_ramp_of_sixty_months_is_the_longest_and_needs_a_real_end_date():
    assert parse(action(ramp_months=60)).actions[0].ramp_months == 60
    text = refused(action(start="9999-12", ramp_months=1))
    assert (
        "actions[1]" in text
        and "runs past the last date" in text
        and "December 9999" in text
    )


def test_a_won_arr_action_takes_a_target_in_dollars_per_won_deal():
    got = parse(action(driver="won_arr", target="45000.50")).actions[0]
    assert got.driver == "won_arr" and got.target == Decimal("45000.50")
    assert parse(action(driver="won_arr", target="0")).actions[0].target == 0


def test_a_negative_or_unreadable_size_is_refused_in_words_about_dollars():
    text = refused(action(driver="won_arr", target="-5"))
    assert "The target won ARR per win must be zero or more dollars, not -$5" in text
    assert "actions[1]" in text and "driver" not in text.split("actions[1]")[1]
    text = refused(action(driver="won_arr", target="lots"))
    assert "The target won ARR per win must be a number of dollars" in text


def test_a_size_target_above_one_is_fine_where_a_win_rate_above_one_is_not():
    assert parse(action(driver="won_arr", target="1500000")).actions
    assert "between 0% and 100%" in refused(action(target="1.5"))


def test_actions_on_different_drivers_in_overlapping_slices_are_allowed():
    plan = parse(
        action(slice="company", id="rate"),
        action(slice="enterprise", id="size", driver="won_arr", target="500000"),
    )
    assert [a.id for a in plan.actions] == ["rate", "size"]


def test_the_same_driver_on_the_same_slice_or_the_company_against_a_segment_is_refused():
    both = refused(
        action(id="a", driver="won_arr", target="9"),
        action(id="b", driver="won_arr", target="8"),
    )
    assert "both change the size of a won deal for Enterprise" in both
    company = refused(
        action(id="a", slice="company", driver="won_arr", target="9"),
        action(id="b", driver="won_arr", target="8"),
    )
    assert (
        "one changes the size of a won deal for the whole company, which includes Enterprise"
        in company
    )
