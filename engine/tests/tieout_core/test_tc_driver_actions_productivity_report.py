"""Creation-productivity actions in the report, on Sapling's demo data (the capacity term in use)
and Mighty Oak's (a flat creation rate): what they are worth, the worksheet's own flex of the
same change, how the two stack, and what the contract refuses."""

import copy
from decimal import Decimal

import pytest

from engine.scripts import generate_app_reports as gen
from engine.tieout_core import actions, contract
from engine.tieout_core import driver_actions as da
from engine.tieout_core import worksheet_drivers as wd
from engine.tieout_core.forecast import EXISTING
from engine.tieout_core.markdown import render
from engine.tieout_core.plan import parse_plan
from engine.tieout_core.report import finish, prepare
from engine.tieout_core.worksheet_rules import PRODUCTIVITY

D = Decimal
REST, NEXT = "rest of fiscal year", "next twelve months"
COMPANY = "sapling-industries"
HIRES = [{"segment": "mid_market", "start": "2026-10", "count": 2}]
PROGRAMS = [{"name": "P", "pipeline": 3_000_000, "start": "2026-10"}]


@pytest.fixture(scope="module")
def state():
    with gen.in_repo():
        yield prepare(gen.PROFILES / COMPANY, gen.DATA / COMPANY, gen.AS_OF, 400, 0)


@pytest.fixture(scope="module")
def flat():
    with gen.in_repo():
        yield prepare(
            gen.PROFILES / "mighty-oak-holdings",
            gen.DATA / "mighty-oak-holdings",
            gen.AS_OF,
            400,
            0,
        )


def plan_of(state, *acts, hires=(), programs=()):
    doc = {"actions": list(acts), "hires": list(hires), "programs": list(programs)}
    return parse_plan(doc, state.as_of, state.cap.members, "plan.yaml")


def act(
    id="x", slice="company", start="2026-09", ramp=0, target=None, driver="productivity"
):
    return {
        "id": id, "name": id, "driver": driver, "slice": slice, "start": start,
        "ramp_months": ramp, "target": str(target),
    }  # fmt: skip


def report(state, *acts, company=COMPANY, **kw):
    with gen.in_repo():
        return finish(state, plan_of(state, *acts, **kw), "plan.yaml", company, "x")


def rate(state):
    return wd.current_value(state.ground, PRODUCTIVITY)


def more(state, percent):
    """The pooled creation rate and ``percent`` more of it, as an entered target."""
    return (rate(state) * (100 + D(percent)) / 100).quantize(D("0.0000001"))


def months(state, w):
    return {REST: state.ground.rest_labels, NEXT: state.ground.twelve_labels}[w]


def probe_of(state, **kw):
    plan = plan_of(state, **kw)
    hires, inflows = actions.plan_inputs(state.ground, plan)
    return wd.Probe(state.ground, hires, inflows)


def new_bookings(probe, state, w, only=("future pipeline",)):
    return sum(
        (
            sum(v[m] for k, v in probe.base.components.items() if k in only)
            for m in months(state, w)
        ),
        D(0),
    )


# ----------------------------------------------------- the worksheet's own flex, to the cent


@pytest.mark.parametrize("kw", [{}, {"hires": HIRES}])
def test_ten_percent_more_creation_company_wide_from_the_first_day_is_the_worksheets_flex(
    state, kw
):
    """With no program pipeline the segments' organic creation is all the new pipeline, so the
    actions' prices add back to the pooled one and the figure is the worksheet's, to the cent."""
    target = rate(state) * D("1.1")
    r = report(state, act(target=target), **kw)
    probe = probe_of(state, **kw)
    flex = probe.change(
        probe.forecast(wd.with_setting(state.ground, PRODUCTIVITY, target))
    )
    for w in (REST, NEXT):
        assert D(r["driver_actions"]["joint_gain"][w]) == D(flex[w]), w


@pytest.mark.parametrize("kw", [{}, {"hires": HIRES}])
def test_that_gain_is_a_tenth_of_the_bookings_the_plans_own_people_create_after_the_as_of_date(
    state, kw
):
    """The by-hand route: a tenth of the future-pipeline component of the plan without actions
    (organic creation, hires included; the programs' pipeline is another component)."""
    r = report(state, act(target=rate(state) * D("1.1")), **kw)
    probe = probe_of(state, **kw)
    for w in (REST, NEXT):
        got = D(r["driver_actions"]["joint_gain"][w])
        assert abs(got - new_bookings(probe, state, w) / 10) <= D("0.02"), w


def test_a_hire_in_the_plan_creates_organic_deals_that_the_action_changes_too(state):
    plain = report(state, act(target=rate(state) * D("1.1")))
    hired = report(state, act(target=rate(state) * D("1.1")), hires=HIRES)
    for w in (REST, NEXT):
        assert D(hired["driver_actions"]["joint_gain"][w]) > D(
            plain["driver_actions"]["joint_gain"][w]
        )


def test_with_programs_the_company_figure_is_still_the_worksheets_flex_to_the_cent(
    state,
):
    """Programs' deals are shared by frozen creation shares and organic ones by the people, so
    the two streams do not have the same mix of segments, and the segments' frozen prices (which
    add back to the pooled one over all the wins) do not add back over the organic wins alone.
    The organic deals an action adds or takes away are priced at the index over the organic wins,
    so that the company's change is the pooled one: with this plan's programs and hires the two
    price indexes differ, and the figure is the worksheet's all the same."""
    kw = {"hires": HIRES, "programs": PROGRAMS}
    target = rate(state) * D("1.1")
    r = report(state, act(target=target), **kw)
    plan = plan_of(state, act(target=target), **kw)
    h, i = actions.plan_inputs(state.ground, plan)
    f = da.effect_for(state, plan, h, i).frame
    assert any(f.price[s] != f.organic_price[s] for s in f.segments)
    probe = probe_of(state, **kw)
    flex = probe.change(
        probe.forecast(wd.with_setting(state.ground, PRODUCTIVITY, target))
    )
    for w in (REST, NEXT):
        assert D(r["driver_actions"]["joint_gain"][w]) == D(flex[w]), w


def test_a_zero_target_removes_the_organic_creations_bookings_and_leaves_the_programs(
    state,
):
    kw = {"hires": HIRES}
    r = report(state, act(target="0"), **kw)
    probe = probe_of(state, **kw)
    for w in (REST, NEXT):
        removed = D(r["driver_actions"]["joint_gain"][w])
        assert abs(removed + new_bookings(probe, state, w)) <= D("0.02"), w
    # and with a program: what stays is the program's pipeline and the existing, up to the mix
    kw = {"hires": HIRES, "programs": PROGRAMS}
    r = report(state, act(target="0"), **kw)
    probe = probe_of(state, **kw)
    for w in (REST, NEXT):
        left = D(r["driver_actions"]["with_actions"]["bookings"][w])
        existing = sum(
            (probe.base.components[EXISTING][m] for m in months(state, w)), D(0)
        )
        added = new_bookings(probe, state, w, only=("added pipeline",))
        assert abs(left - existing - added) <= D("0.02"), w


def test_a_zero_target_leaves_no_organic_wins_and_creates_only_the_programs_deals(
    state,
):
    plan = plan_of(state, act(target="0"), hires=HIRES, programs=PROGRAMS)
    h, i = actions.plan_inputs(state.ground, plan)
    e = da.effect_for(state, plan, h, i)
    for s in e.frame.segments:
        left = e.lift.created(s)  # September 1 is the first day, so it is all of them
        assert all(
            abs(a - b) < D("1e-20") for a, b in zip(left, e.lift.program[s])
        )  # the programs' deals are all that is created
        assert e.lift.creation[s][0] == -1 and e.lift.creation[s][-1] == -1


# ----------------------------------------------------- nothing, or nothing changed


def test_a_target_equal_to_the_pooled_rate_changes_no_figure_anywhere(state):
    hold = {"hires": HIRES, "programs": PROGRAMS}
    base = report(state, **hold)
    same = report(state, act(target=rate(state)), **hold)
    for key in ("gap", "forecasts", "actions", "required_pipeline", "history"):
        assert same[key] == base[key], key
    a, b = copy.deepcopy(base["plan"]), copy.deepcopy(same["plan"])
    step = b["items"].pop()
    assert step["kind"] == "actions"
    assert step["contribution"] == {REST: "0.00", NEXT: "0.00"}
    for doc in (a, b):
        for k in ("order", "cost_note"):
            doc.pop(k)
        doc["ranges"].pop("what_is_drawn")
    assert a == b
    for a, b in zip(base["worksheet"]["drivers"], same["worksheet"]["drivers"]):
        if (
            a["driver"] == "productivity"
        ):  # only what is said of it with an action on it
            assert {**a, "limitation": None} == {**b, "limitation": None}
            assert b["limitation"].endswith("at that setting.")
            continue
        assert a == b, a["driver"]


def test_pipeline_created_before_the_start_is_unchanged_a_late_start_is_worth_nothing_in_the_year(
    state,
):
    r = report(state, act(start="2027-02", target=more(state, 30)))
    gain = r["driver_actions"]["joint_gain"]
    assert gain[REST] == "0.00" and D(gain[NEXT]) > 0


# ----------------------------------------------------- the worksheet's flex stacks with it


def test_the_worksheets_flex_of_the_rate_stacks_with_the_action_multiplying_it(state):
    """The action says the slice's people create half again as many deals as the rate does; the
    worksheet then moves the rate itself to V: organic creation is V over the baseline rate times
    half again, so what the plan books from it is that times the future pipeline's."""
    kw = {"hires": HIRES}
    plan = plan_of(state, act(target=more(state, 50)), **kw)
    h, i = actions.plan_inputs(state.ground, plan)
    effect = da.effect_for(state, plan, h, i)
    probe = wd.Probe(state.ground, h, i, effect.lift)
    plain = wd.Probe(state.ground, h, i)
    v = rate(state) * D("1.2")
    got = probe.forecast(wd.with_setting(state.ground, PRODUCTIVITY, v))
    for w in (REST, NEXT):
        grown = sum(
            (
                sum(got.components[k][m] for k in got.components if k != EXISTING)
                for m in months(state, w)
            ),
            D(0),
        )
        want = (
            sum(
                (plain.base.components["future pipeline"][m] for m in months(state, w)),
                D(0),
            )
            * (v / rate(state))
            * D("1.5")
        )
        assert abs(grown - want) / want < D("1e-6"), (
            w
        )  # the segments' creation sums to the roster's to 1e-6


def test_the_rate_never_goes_below_zero_however_it_is_set(state):
    g = state.ground
    assert wd.with_setting(g, PRODUCTIVITY, D("-3")).cap.fit.rate == 0
    assert wd.with_setting(g, "won_arr", D("-3")).model.new_pipeline.mean_won_arr == 0


def test_the_productivity_row_still_solves_with_a_productivity_action_on_the_plan(
    state,
):
    r = report(state, act(target=more(state, 20)))
    row = next(d for d in r["worksheet"]["drivers"] if d["driver"] == "productivity")
    n = row["needed_alone"]
    assert n is not None
    if n["outcome"] == wd.SOLVES:
        assert D(n["achieved_fiscal_year_bookings"]) >= D(n["target"])
    rate_row = next(d for d in r["worksheet"]["drivers"] if d["driver"] == "win_rate")
    assert (
        rate_row["needed_alone"] is not None
    )  # only a win-rate action stacks on the win rate


# ----------------------------------------------------- ranges, where the capacity term is in use or not


@pytest.mark.parametrize("percent", [30, -30, 900, -100])
def test_the_simulation_is_centered_where_the_capacity_term_is_adopted(state, percent):
    assert state.ground.cap.adopted
    r = report(state, act(target=more(state, percent)), hires=HIRES, programs=PROGRAMS)
    names = {
        c["name"]: c["passed"] for c in r["verdicts"]["software_correct"]["checks"]
    }
    assert names["plan simulation centered on its expectation"] is True
    assert r["verdicts"]["software_correct"]["verdict"] == "yes"


@pytest.mark.parametrize("percent", [30, -30, 900, -100])
def test_the_simulation_is_centered_where_creation_is_flat(flat, percent):
    assert not flat.ground.cap.adopted
    r = report(flat, act(target=more(flat, percent)), company="mighty-oak-holdings")
    names = {
        c["name"]: c["passed"] for c in r["verdicts"]["software_correct"]["checks"]
    }
    assert names["plan simulation centered on its expectation"] is True
    assert r["verdicts"]["software_correct"]["verdict"] == "yes"
    item = r["driver_actions"]["items"][0]
    row = next(d for d in r["worksheet"]["drivers"] if d["driver"] == "productivity")
    assert row["unit"] == "organic deals per day"
    assert item["evidence"]["baseline"] == row["current"]["value"]


def test_the_unit_is_the_one_the_report_gives_for_the_company(state):
    r = report(state, act(target=more(state, 10)))
    row = next(d for d in r["worksheet"]["drivers"] if d["driver"] == "productivity")
    assert row["unit"] == "created deals per ramped AE-month"


# ----------------------------------------------------- a segment, or three drivers


def test_a_segment_action_changes_that_segments_creation_only(state):
    plan = plan_of(state, act(slice="enterprise", target=more(state, 50)))
    e = da.effect_for(state, plan, (), ())
    assert any(e.lift.creation["enterprise"]) and not any(e.lift.creation["mid_market"])
    assert e.lift.created("mid_market") == tuple(e.lift.counts("mid_market"))
    assert e.lift.created("enterprise") != tuple(e.lift.counts("enterprise"))


def test_the_company_is_every_segment_and_the_same_report_figures_follow(state):
    target = more(state, 20)
    company = report(state, act("c", target=target))
    each = report(
        state,
        *(act(s, s, target=target) for s in ("commercial", "enterprise", "mid_market")),
    )
    assert (
        company["driver_actions"]["joint_gain"] == each["driver_actions"]["joint_gain"]
    )
    assert company["plan"]["with_plan"] == each["plan"]["with_plan"]
    assert company["plan"]["ranges"] == each["plan"]["ranges"]


def three_acts(state, **over):
    g = state.ground
    target = {
        "win_rate": g.model.new_pipeline.win_rate * D("1.1"),
        "won_arr": g.model.new_pipeline.mean_won_arr * D("1.1"),
        "productivity": rate(state) * D("1.1"),
    }
    return target, [act(d, driver=d, target=t, **over) for d, t in target.items()]


@pytest.mark.parametrize(
    "kw", [{"hires": HIRES}, {"hires": HIRES, "programs": PROGRAMS}]
)
def test_three_drivers_on_one_slice_gain_what_the_direct_forecast_says_and_reconcile(
    state, kw
):
    from engine.tieout_core.worksheet_rules import WIN_RATE, WON_ARR

    g = state.ground
    target, acts = three_acts(state)
    r = report(state, *acts, **kw)
    d = r["driver_actions"]
    # the direct route: the forecast with all three as one change in each driver of the pooled
    # model, for these company-wide actions from the first day
    probe = probe_of(state, **kw)
    g1 = wd.with_setting(g, WIN_RATE, target["win_rate"])
    g1 = wd.with_setting(g1, WON_ARR, target["won_arr"])
    g1 = wd.with_setting(g1, PRODUCTIVITY, target["productivity"])
    flex = probe.change(probe.forecast(g1))
    items = {i["id"]: i["removal_value"] for i in d["items"]}
    for w in (REST, NEXT):
        assert D(d["joint_gain"][w]) == D(flex[w]), w
        removals = sum(D(v[w]) for v in items.values())
        assert D(d["reconciliation"]["values"][w]) == D(d["joint_gain"][w]) - removals
    assert d["reconciliation"]["material"][REST] is True
    assert d["reconciliation"]["sentences"][REST] == da.REINFORCE
    assert contract.validate(r) == []
    assert r["verdicts"]["software_correct"]["verdict"] == "yes"


def test_reordering_three_actions_changes_no_figure(state):
    g = state.ground
    a = act(
        "a",
        driver="win_rate",
        slice="enterprise",
        target=g.model.new_pipeline.win_rate * D("1.2"),
    )
    b = act(
        "b",
        driver="won_arr",
        ramp=2,
        target=g.model.new_pipeline.mean_won_arr * D("1.1"),
    )
    c = act("c", slice="mid_market", start="2026-10", target=more(state, 40))
    one, two = report(state, a, b, c), report(state, c, a, b)
    for key in ("with_plan", "difference", "expected_fiscal_year", "ranges", "gap"):
        assert one["plan"][key] == two["plan"][key], key
    assert (
        one["driver_actions"]["with_actions"] == two["driver_actions"]["with_actions"]
    )
    assert (
        one["driver_actions"]["reconciliation"]
        == two["driver_actions"]["reconciliation"]
    )

    def removals(r):
        return {i["id"]: i["removal_value"] for i in r["driver_actions"]["items"]}

    assert removals(one) == removals(two)


# ----------------------------------------------------- evidence and the contract


def test_the_evidence_reads_the_target_against_the_pooled_rate_and_the_worksheets_settings(
    state,
):
    target = more(state, 25)
    r = report(state, act(slice="enterprise", target=target))
    item = r["driver_actions"]["items"][0]
    e = item["evidence"]
    row = next(d for d in r["worksheet"]["drivers"] if d["driver"] == "productivity")
    assert item["driver"] == "productivity" and e["baseline"] == row["current"]["value"]
    assert e["change_percent"] == "25.00" and e["resulting"] == item["target"]
    low, high = (
        row["historical"]["low"]["setting"],
        row["historical"]["high"]["setting"],
    )
    assert (e["historical_low"], e["historical_high"]) == (low, high)
    assert e["label"] in (da.INSIDE, da.OUTSIDE)
    assert "Enterprise" in item["affects"] and "programs" in item["affects"]


@pytest.fixture(scope="module")
def good(state):
    return report(
        state,
        act("e", "enterprise", target=more(state, 25)),
        act("m", "mid_market", start="2026-10", ramp=2, target=more(state, 15)),
    )


EDITS = {
    "the baseline": lambda r: r["driver_actions"]["items"][0]["evidence"].update({"baseline": "9.0000"}),
    "the change in percent": lambda r: r["driver_actions"]["items"][0]["evidence"].update({"change_percent": "99.00"}),
    "a negative target": lambda r: r["driver_actions"]["items"][0].update({"target": "-0.1000"}),
    "the sentence on what it affects": lambda r: r["driver_actions"]["items"][0].update({"affects": "It adds 99."}),
    "the label": lambda r: r["driver_actions"]["items"][0]["evidence"].update({"label": "beyond what this team has done"}),
}  # fmt: skip


@pytest.mark.parametrize("what", list(EDITS))
def test_a_report_with_a_wrong_figure_or_sentence_is_refused(good, what):
    r = copy.deepcopy(good)
    EDITS[what](r)
    assert contract.validate(r) != [], what


def test_the_good_report_is_valid_and_the_markdown_names_the_rate_not_dollars(good):
    assert contract.validate(good) == []
    assert good["verdicts"]["software_correct"]["verdict"] == "yes"
    text = render(good)
    assert "Pooled baseline $" not in text and ", 25.00%, resulting " in text


# ----------------------------------------------------- the draws are centered on the expectation


@pytest.mark.parametrize("percent", [50, -50, -100, 400])
@pytest.mark.parametrize("seed", [1, 2])
def test_four_thousand_paths_have_the_expected_mean_with_a_changed_creation_and_a_program(
    state, percent, seed
):
    """Each path's organic deals are drawn apart from the programs', with those an action takes
    away taken one by one: the mean of the paths is the forward function's expectation to within
    what four thousand of them can tell (three and a half standard errors)."""
    from engine.tieout_core.forecast import model_forecast, simulate

    g, kw = state.ground, {"hires": HIRES, "programs": PROGRAMS}
    plan = plan_of(state, act(target=more(state, percent)), **kw)
    h, i = actions.plan_inputs(g, plan)
    lift = da.effect_for(state, plan, h, i).lift
    creation = actions.Scenario(g).creation(h)
    expected = model_forecast(
        g.model, g.pop, g.as_of, g.windows, creation=creation, inflows=i, lift=lift
    ).total()
    sim = simulate(
        g.model, g.pop, g.as_of, g.windows, draws=4000, seed=seed,
        creation=creation, inflows=i, lift=lift,
    )  # fmt: skip
    samples = sim.samples_total
    mean = sum(samples) / len(samples)
    sd = (sum((x - mean) ** 2 for x in samples) / (len(samples) - 1)) ** 0.5
    assert abs(mean - float(expected)) <= 3.5 * sd / len(samples) ** 0.5, (
        mean, float(expected), sd,
    )  # fmt: skip
