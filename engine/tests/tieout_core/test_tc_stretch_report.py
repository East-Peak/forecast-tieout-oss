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
from engine.tieout_core.stretch_rules import ADOPTED, NOT_ADOPTED, Decision

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


def forced(world, outcome):
    """The report with the decision forced. The suite's wrapper validates every report against
    the contract, and a forced decision breaks the contract's rule on purpose, so the check is
    lifted for this build only."""
    original, checked = stretch_report.evaluate, contract.validate

    def evaluate(bt, as_of):
        ev = original(bt, as_of)
        return replace(
            ev, decision=Decision(outcome, "forced for the test", None, None)
        )

    stretch_report.evaluate, contract.validate = evaluate, lambda r: []
    try:
        return build(world)
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
    "range95_label", "label80", "label95", "by_window_label", "fitted_ranges",
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


def test_every_range_is_labeled(stretched):
    f = stretched["forecasts"]["fitted_ranges"]
    assert f["by_window_label"].startswith("stretched by past misses")
    assert f["horizons"]["rest of fiscal year"]["label80"].startswith(
        "stretched by past misses; held "
    )
    for h in f["horizons"].values():
        assert h["label80"].startswith("stretched by past misses")
        assert h["label95"] == "stretched, not separately tested"
    year = stretched["gap"]["fiscal_year"]
    assert year["range80_label"].startswith("stretched by past misses")
    assert year["range95_label"] == "stretched, not separately tested"
    for q in stretched["gap"]["quarters"]:
        assert q["range80_label"].startswith(("stretched", "closed"))


def test_the_labels_say_how_many_past_forecasts_the_range_held(stretched):
    ev = stretched["backtest"]["candidates"]["ranges"]["horizons"]
    six = next(h for h in ev if h["horizon_months"] == 6)
    nxt = stretched["forecasts"]["fitted_ranges"]["horizons"]["next twelve months"]
    assert (
        "six-month factors" in nxt["label80"]
        and "longer than six months" in nxt["label80"]
    )
    assert f"held {six['inside_stretched']} of {six['scored_folds']}" in nxt["label80"]


def test_not_adopted_keeps_the_simulated_labels(unstretched):
    f = unstretched["forecasts"]["fitted_ranges"]
    assert not f["by_window_label"].startswith("stretched")
    for h in f["horizons"].values():
        assert not h["label80"].startswith("stretched")
        assert h["label95"] == "simulated, not separately tested"
    assert not unstretched["gap"]["fiscal_year"]["range80_label"].startswith(
        "stretched"
    )


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
    assert "stretched by past misses; held" in text
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
            range80_label="stretched by past misses; held 1 of 2"
        ),
    )
    assert any("labeled stretched" in p for p in problems)


def test_a_range_not_labeled_stretched_after_adoption_is_refused(stretched):
    problems = broken(
        stretched, lambda r: r["gap"]["fiscal_year"].update(range80_label="simulated")
    )
    assert any("not labeled stretched" in p for p in problems)


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
