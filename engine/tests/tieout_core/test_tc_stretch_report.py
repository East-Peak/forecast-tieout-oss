"""Goal 2D in the report: the decision and its evidence, the stretched ranges, the labels,
the validator rules, and that nothing but ranges moves.

A generated, staffed company (not a demo company) is built into a report twice: as the
rule decides, and with the decision forced to "not adopted". The two must differ in ranges
and their labels only."""

import copy
import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from engine.scripts.generate_data_v2 import write_company_files
from engine.scripts.synth_history import generate
from engine.tests.tieout_core import staffed
from engine.tests.tieout_core.builders import write_profile
from engine.tieout_core import contract, stretch_report
from engine.tieout_core import report as report_module
from engine.tieout_core.markdown import render
from engine.tieout_core.stretch_rules import ADOPTED, NOT_ADOPTED

DRAWS = 300
PLAN = """\
programs:
  - name: Partner referrals
    pipeline: 300000
    start: 2026-09
    ramp_months: 2
"""


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    root = tmp_path_factory.mktemp("stretch")
    profile = write_profile(
        root / "profile", {f"Q{q}FY26": 2_000_000 for q in range(1, 5)}
    )
    (profile / "capacity.yaml").write_text(staffed.CAPACITY_YAML)
    data = root / "data"
    write_company_files(generate(staffed.company(1.5, 4)), data)
    plan = root / "plan.yaml"
    plan.write_text(PLAN)
    return profile, data, plan


def build(world, plan=True):
    profile, data, plan_path = world
    return report_module.build_report(
        profile, data, staffed.AS_OF, draws=DRAWS, plan_path=plan_path if plan else None
    )


def forced(world, outcome, plan=True):
    """The report with the decision forced. The suite's wrapper validates every report against
    the contract, and a forced decision breaks the contract's rule on purpose, so the check is
    lifted for this build only."""
    original, checked = stretch_report.evaluate, contract.validate

    def evaluate(bt, as_of):
        ev = original(bt, as_of)
        return replace(
            ev,
            decision=replace(
                ev.decision, outcome=outcome, reason="forced for the test"
            ),
        )

    stretch_report.evaluate, contract.validate = evaluate, lambda r: []
    try:
        return build(world, plan)
    finally:
        stretch_report.evaluate, contract.validate = original, checked


@pytest.fixture(scope="module")
def decided(world):
    return build(world)


@pytest.fixture(scope="module")
def unstretched(world):
    return forced(world, NOT_ADOPTED)


@pytest.fixture(scope="module")
def stretched(world):
    return forced(world, ADOPTED)


RANGE_KEYS = {
    "range80", "range95", "expected_range80", "expected_range95", "range80_label",
    "range95_label", "label_short", "label_full", "label95", "by_window_label", "fitted_ranges", "basis", "range_basis",
}  # fmt: skip


def strip(o, path=()):
    """A report with every range, every range label and the stretch's own evidence removed."""
    if isinstance(o, dict):
        return {
            k: strip(v, (*path, k))
            for k, v in o.items()
            if k not in RANGE_KEYS
            and (*path, k) != ("backtest", "candidates", "ranges")
        }
    if isinstance(o, list):
        return [strip(v, path) for v in o]
    return o


def test_the_report_carries_the_decision_with_its_evidence_per_horizon(decided):
    c = decided["backtest"]["candidates"]["ranges"]
    assert c["decision"] in (ADOPTED, NOT_ADOPTED, "not enough history")
    assert [h["horizon_months"] for h in c["horizons"]] == [1, 3, 6]
    assert contract.validate(decided) == []
    assert "scored folds" in c["reason"] or "pooled" in c["reason"]


def test_every_range_has_a_short_and_a_full_label_built_from_its_basis(stretched):
    f = stretched["forecasts"]["fitted_ranges"]
    assert f["by_window_label"].startswith("stretched by past misses")
    for h in f["horizons"].values():
        assert h["label_short"].startswith(
            ("Stretched on ", "Checked against past misses")
        )
        assert h["label_full"].startswith(
            "Stretched by the model's own past misses, using what "
        )
        assert h["label95"].startswith("Stretched the same way; not separately tested")
        assert h["basis"]["factor_horizon_months"] in (1, 3, 6)
        assert h["label_full"] in h["status"]
    year = stretched["gap"]["fiscal_year"]
    assert year["label_short"].startswith(
        ("Stretched on ", "Checked against past misses")
    )
    assert year["label95"].startswith("Stretched the same way")
    for q in stretched["gap"]["quarters"]:
        assert q["label_short"].startswith(("Stretched", "Checked against", "closed"))


def test_no_short_label_carries_a_date_or_a_count_and_the_full_label_never_prints_held_zero_of_one(
    stretched,
):
    texts = [stretched["gap"]["fiscal_year"]["label_short"]] + [
        q["label_short"] for q in stretched["gap"]["quarters"]
    ]
    horizons = stretched["forecasts"]["fitted_ranges"]["horizons"].values()
    texts += [h["label_short"] for h in horizons]
    assert not [t for t in texts if any(ch.isdigit() for ch in t)]
    for h in horizons:
        assert "held 0 of 1" not in h["label_full"] and "held 0 of 1" not in h["status"]
        assert (
            "2026-" not in h["label_full"] and "2027-" not in h["label_full"]
        )  # dates as the app writes them


def test_a_window_that_is_not_the_tested_cumulative_shape_says_it_is_not_exactly_the_tested_forecast(
    stretched,
):
    f = stretched["forecasts"]["fitted_ranges"]["horizons"]
    rest = f["rest of fiscal year"]
    assert rest["basis"]["extrapolated"] is True  # five months out, tested at six
    assert rest["basis"]["extrapolated_because"] == "not_the_tested_shape"
    assert "is not exactly the six-month forecast that was tested" in rest["label_full"]
    nxt = f["next twelve months"]
    assert nxt["basis"]["extrapolated_because"] == "longer_than_six_months"
    assert (
        "is longer than six months, so it uses the six-month factors"
        in nxt["label_full"]
    )
    quarters = [q for q in stretched["gap"]["quarters"] if q.get("range_basis")]
    assert quarters and all(q["range_basis"]["extrapolated"] for q in quarters)


def test_the_full_label_names_the_tested_horizon_and_the_evidence_at_it(stretched):
    ev = stretched["backtest"]["candidates"]["ranges"]["horizons"]
    six = next(h for h in ev if h["horizon_months"] == 6)
    nxt = stretched["forecasts"]["fitted_ranges"]["horizons"]["next twelve months"]
    assert "using what six-month forecasts needed" in nxt["label_full"]
    assert nxt["basis"]["held"] == six["inside_stretched"]
    assert nxt["basis"]["scored"] == six["scored_folds"]
    if six["scored_folds"] < 6:
        assert "Evidence at this length is thin" in nxt["label_full"]


def test_not_adopted_keeps_the_simulated_labels(unstretched):
    f = unstretched["forecasts"]["fitted_ranges"]
    assert not f["by_window_label"].startswith("stretched")
    for h in f["horizons"].values():
        assert not h["label_short"].startswith("Stretched")
        assert h["label95"] == "simulated, not separately tested"
        assert h["label_full"] == h["status"]
    assert not unstretched["gap"]["fiscal_year"]["label_short"].startswith("Stretched")


def test_stretching_moves_only_ranges(stretched, unstretched):
    assert strip(stretched) == strip(unstretched)


def test_the_stretched_range_contains_the_simulated_one_about_the_same_center(
    stretched, unstretched
):
    a = stretched["forecasts"]["fitted_ranges"]
    b = unstretched["forecasts"]["fitted_ranges"]
    for window in b["by_window"]:
        s, u = a["by_window"][window], b["by_window"][window]
        assert (s["mean"], s["median"]) == (u["mean"], u["median"])
        for key in ("range80", "range95"):
            assert float(s[key][0]) <= float(u[key][0])
            assert float(s[key][1]) >= float(u[key][1])
    assert a["by_window"] != b["by_window"]  # and something did stretch
    year_s, year_u = stretched["gap"]["fiscal_year"], unstretched["gap"]["fiscal_year"]
    assert float(year_s["expected_range80"][1]) >= float(year_u["expected_range80"][1])
    assert float(year_s["expected_range80"][0]) <= float(year_u["expected_range80"][0])


def test_the_with_plan_ranges_are_untouched(stretched, unstretched):
    assert "unavailable" not in stretched["plan"]
    assert stretched["plan"] == unstretched["plan"]


def test_a_closed_quarter_has_nothing_to_stretch(stretched, unstretched):
    for s, u in zip(
        stretched["gap"]["quarters"], unstretched["gap"]["quarters"], strict=True
    ):
        if s["status"] == "closed":
            assert s["expected_range80"] == u["expected_range80"]


def test_a_range_never_runs_below_zero(stretched):
    f = stretched["forecasts"]["fitted_ranges"]
    assert all(float(v["range95"][0]) >= 0 for v in f["by_window"].values())


def test_the_markdown_states_the_decision_and_the_labels(stretched):
    text = render(stretched)
    assert "Ranges stretched by the model's own past misses" in text
    assert "Stretched by the model's own past misses, using what" in text
    assert "is not exactly the" in text
    assert "plain empirical rule" in text
    assert "Lower factor" in text


def test_the_report_is_reproducible(world, decided):
    assert json.dumps(build(world), sort_keys=True) == json.dumps(
        decided, sort_keys=True
    )


# ---------------------------------------------------------------- the validator


def broken(report: dict, edit) -> list[str]:
    r = copy.deepcopy(report)
    edit(r)
    return contract.validate(r)


def row(r, h=3):
    return next(
        x
        for x in r["backtest"]["candidates"]["ranges"]["horizons"]
        if x["horizon_months"] == h
    )


def test_a_factor_below_one_is_refused(decided):
    problems = broken(decided, lambda r: row(r).update(lower_factor="0.9000"))
    assert any("below 1" in p for p in problems)


def test_a_decision_the_rule_does_not_give_is_refused(decided):
    other = (
        ADOPTED
        if decided["backtest"]["candidates"]["ranges"]["decision"] != ADOPTED
        else NOT_ADOPTED
    )
    problems = broken(
        decided, lambda r: r["backtest"]["candidates"]["ranges"].update(decision=other)
    )
    assert any("declared rule" in p for p in problems)


def test_evidence_that_disagrees_with_the_back_test_is_refused(decided):
    problems = broken(
        decided, lambda r: row(r).update(eligible_folds=row(r)["eligible_folds"] + 1)
    )
    assert any("back-test" in p for p in problems)
    problems = broken(
        decided, lambda r: row(r).update(inside_stretched=row(r)["scored_folds"] + 1)
    )
    assert any("more folds inside" in p for p in problems)
    problems = broken(decided, lambda r: row(r).update(coverage_stretched=0.0123))
    assert any("stretched coverage" in p for p in problems)


def test_a_stretched_label_on_a_range_that_was_not_stretched_is_refused(unstretched):
    # the forced report breaks the declared rule on purpose; what is checked here is the label rule
    problems = broken(
        unstretched,
        lambda r: r["gap"]["fiscal_year"].update(
            label_short="Stretched on the low side by past misses"
        ),
    )
    assert any("labeled stretched but nothing stands behind it" in p for p in problems)


def test_a_range_not_labeled_stretched_after_adoption_is_refused(stretched):
    problems = broken(
        stretched, lambda r: r["gap"]["fiscal_year"].update(label_short="simulated")
    )
    assert any("short label is not what its basis says" in p for p in problems)


def test_the_files_exist_in_a_short_history_report(tmp_path):
    from engine.tests.tieout_core.test_tc_report import PROFILE

    data = Path(tmp_path) / "d"
    from engine.tests.tieout_core.builders import deal, write_company

    write_company(
        data, [deal("A", "Closed Won", created="2026-05-01", close="2026-06-01")]
    )
    r = report_module.build_report(PROFILE, data, date(2026, 8, 31), draws=50)
    assert r["backtest"]["candidates"]["ranges"]["decision"] == "not enough history"
    assert contract.validate(r) == []


# ---------------------------------------------------------------- the structured evidence behind the labels


def horizon_range(r, name="rest of fiscal year"):
    return r["forecasts"]["fitted_ranges"]["horizons"][name]


def test_a_label_with_a_fabricated_count_is_refused(stretched):
    def edit(r):
        v = horizon_range(r)
        v["label_full"] = v["label_full"].replace(
            "could be scored", "could be scored, 9 held", 1
        )

    def short(r):
        horizon_range(r)["label_short"] += " and then some"

    assert any(
        "full label is not what its basis says" in p for p in broken(stretched, edit)
    )
    assert any(
        "short label is not what its basis says" in p for p in broken(stretched, short)
    )


def test_a_basis_whose_counts_are_not_the_evidences_is_refused(stretched):
    def edit(r):
        b = horizon_range(r)["basis"]
        b["held"] += 1

    assert any("basis counts" in p for p in broken(stretched, edit))


def test_a_ninety_five_label_that_claims_a_test_is_refused(stretched):
    def edit(r):
        horizon_range(r)["label95"] = "stretched and tested"

    assert any(
        "95% label is not what its basis says" in p for p in broken(stretched, edit)
    )


def test_a_basis_on_a_range_when_the_rule_does_not_adopt_is_refused(stretched):
    def tie(r):
        # make the stretched outcomes equal the simulated ones: the rule cannot call that closer
        for h in r["backtest"]["candidates"]["ranges"]["horizons"]:
            for d in h["scored_dates"]:
                d["inside_stretched"] = d["inside_simulated"]
            h["inside_stretched"] = h["inside_simulated"]

    assert any("stretch was not adopted" in p for p in broken(stretched, tie))


def test_the_window_must_use_the_horizon_it_belongs_to(stretched):
    def edit(r):
        horizon_range(r, "next twelve months")["basis"]["factor_horizon_months"] = 3

    assert any(
        "tested horizon its window belongs to" in p or "basis counts" in p
        for p in broken(stretched, edit)
    )


def test_an_extrapolated_range_must_give_its_reason(stretched):
    def edit(r):
        horizon_range(r)["basis"]["extrapolated_because"] = None

    problems = broken(stretched, edit)
    assert any("wrong account of its shape" in p for p in problems)
    assert any("extrapolated exactly when a reason is given" in p for p in problems)


def test_the_scored_dates_are_every_fold_with_enough_earlier_folds(stretched):
    def drop(r):
        row(r)["scored_dates"].pop()

    def flip(r):
        d = row(r)["scored_dates"][0]
        d["inside_simulated"] = not d["inside_simulated"]

    problems = broken(stretched, drop)
    assert any(
        "exactly the back-test folds" in p or "not as many" in p for p in problems
    )
    assert any("disagrees with the back-test" in p for p in broken(stretched, flip))


def test_a_scored_subset_with_more_hits_than_the_back_test_has_is_refused(stretched):
    def edit(r):
        h = row(r, 1)  # the one-month back-test has misses on this report
        assert h["inside_simulated"] < h["scored_folds"]
        for d in h["scored_dates"]:
            d["inside_simulated"] = True
        h["inside_simulated"] = h["scored_folds"]

    problems = broken(stretched, edit)
    assert any("disagrees with the back-test" in p for p in problems)
    assert any(
        "more hits or misses" in p or "simulated coverage is not the back-test's" in p
        for p in problems
    )


def test_a_null_factor_needs_its_reason_and_a_reason_needs_a_null_factor(stretched):
    def no_reason(r):
        row(r)["lower_factor"] = None

    def reason_without_null(r):
        row(r)["upper_reason"] = "because"

    assert any(
        "absent exactly when its reason is given" in p
        for p in broken(stretched, no_reason)
    )
    assert any(
        "absent exactly when its reason is given" in p
        for p in broken(stretched, reason_without_null)
    )


def test_what_the_rule_accepted_is_stated_and_checked(stretched):
    acc = stretched["backtest"]["candidates"]["ranges"]["acceptance"]
    assert acc["stretched_side"] in ("lower", "upper", "both", "neither")
    assert str(acc["six_month_scored_folds"]) in acc["sentence"]

    def edit(r):
        r["backtest"]["candidates"]["ranges"]["acceptance"]["sentence"] += (
            " It was a triumph."
        )

    assert any("what its fields say" in p for p in broken(stretched, edit))

    def side(r):
        a = r["backtest"]["candidates"]["ranges"]["acceptance"]
        a["stretched_side"] = "both" if a["stretched_side"] != "both" else "lower"

    assert any(
        "stretched side is not what the factors say" in p
        for p in broken(stretched, side)
    )


def test_the_method_text_states_the_rank_convention_and_the_six_month_noise(decided):
    m = decided["backtest"]["candidates"]["ranges"]["method"]
    assert "plain empirical rule, not a finite-sample guarantee" in m
    assert "overlapping forecasts" in m and "noisier" in m
    six = row(decided, 6)
    assert (
        f"{six['eligible_folds']} past six-month forecasts to learn from, {six['scored_folds']} scored"
        in m
    )
    assert any(
        "method text" in p
        for p in broken(
            decided, lambda r: r["backtest"]["candidates"]["ranges"].update(method="x")
        )
    )


def test_a_lower_edge_floored_at_zero_says_so_in_words_and_in_the_acceptance(world):
    # a shift deep enough that a stretched lower edge reaches zero
    root = Path(world[0]).parent
    profile = write_profile(
        root / "deep-profile", {f"Q{q}FY26": 2_000_000 for q in range(1, 5)}
    )
    (profile / "capacity.yaml").write_text(staffed.CAPACITY_YAML)
    data = root / "deep-data"
    company = replace(
        staffed.company(1.5, 4), conversion_change=(date(2025, 3, 1), 0.35)
    )
    write_company_files(generate(company), data)
    r = forced((profile, data, None), ADOPTED, plan=False)
    flagged = [
        q
        for q in r["gap"]["quarters"]
        if q.get("range_basis") and q["range_basis"]["floored_at_zero_80"]
    ] + [
        n
        for n, v in r["forecasts"]["fitted_ranges"]["horizons"].items()
        if v["basis"] and v["basis"]["floored_at_zero_80"]
    ]
    assert flagged, "the deep shift should floor at least one range"
    texts = [q["label_short"] for q in flagged if isinstance(q, dict)] + [
        r["forecasts"]["fitted_ranges"]["horizons"][n]["label_short"]
        for n in flagged
        if isinstance(n, str)
    ]
    assert all(t.endswith("; floored at zero") for t in texts)
    assert r["backtest"]["candidates"]["ranges"]["acceptance"]["floored_at_zero"]
    assert (
        "floored at zero for:"
        in r["backtest"]["candidates"]["ranges"]["acceptance"]["sentence"]
    )
