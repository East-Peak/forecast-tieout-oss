"""The plan editor's expected result for one edited plan, written by a native run of the core.

The browser tests enter ``plan.json`` through the form and compare what the in-browser core returns with
``report.json`` and ``comparison-row.json`` here, which this script writes by running ``build_report`` on the
same plan as a file (not through the editor's entry), so the two sides are independent. Only the plan's
name differs: the editor calls its plan "your-plan" where a file has a path.

    python -m engine.scripts.generate_editor_fixture            # write the files
    python -m engine.scripts.generate_editor_fixture --verify   # fail if they are not what a native run writes
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import yaml

from engine.scripts.generate_app_reports import REPO, canonical, in_repo
from engine.tieout_core import (
    actions,
    driver_actions,
    lanes,
    lanes_basis,
    lanes_contract,
    lanes_files,
    lanes_text,
)
from engine.tieout_core.comparison import BASELINE, comparison_rows
from engine.tieout_core.editor import (
    AS_OF,
    DATA,
    DRAWS,
    PROFILES,
    SEED,
    YOUR_PLAN,
    YOUR_PLAN_LABEL,
)
from engine.tieout_core.plan import load_plan
from engine.tieout_core.report import build_report, prepare

COMPANY = "sapling-industries"
# the segments the plan adds hires to: their owners files are kept, with the planned-hires bucket
OWNER_SEGMENTS = ("commercial", "enterprise")
OUT = REPO / "frontend/src/screens/__tests__/fixtures/your-plan"
OUT_ACTIONS = REPO / "frontend/src/screens/__tests__/fixtures/your-plan-actions"

# An edit of Sapling's demo plan: one hire changed, one added in another segment, a program resized and
# given a cost and a ramp.
PLAN = {
    "hires": [
        {"segment": "enterprise", "start": "2026-11", "count": 3},
        {"segment": "commercial", "start": "2026-12", "count": 1},
    ],
    "programs": [
        {
            "name": "Field events",
            "pipeline": 4000000,
            "start": "2026-10",
            "cost": 500000,
            "ramp_months": 2,
        }
    ],
}


# The same edit with a win-rate action in one segment on top of it: ramping up over two months to
# a target above the worksheet's high, so the evidence reads "outside the worksheet's historical
# settings". The form has no field for an action yet, so the browser tests do not enter this plan;
# the editor's own entry is held to what a native run writes for it.
PLAN_WITH_ACTION = {
    **PLAN,
    "actions": [
        {
            "id": "enterprise-win-rate",
            "name": "Enterprise win-rate push",
            "driver": "win_rate",
            "slice": "enterprise",
            "start": "2026-10",
            "ramp_months": 2,
            "target": "0.26",
        }
    ],
}
CASES = ((OUT, PLAN), (OUT_ACTIONS, PLAN_WITH_ACTION))


def build(plan: dict = PLAN) -> dict[str, str]:
    with in_repo(), tempfile.TemporaryDirectory() as tmp:
        plan_file = Path(tmp) / f"{YOUR_PLAN}.yaml"
        plan_file.write_text(yaml.safe_dump(plan, sort_keys=False))
        kwargs = {"draws": DRAWS, "seed": SEED, "company": COMPANY}
        profile, data = PROFILES / COMPANY, DATA / COMPANY
        signed = build_report(
            profile, data, AS_OF, scenario=BASELINE, **kwargs
        )  # fmt: skip
        yours = build_report(
            profile, data, AS_OF, plan_path=plan_file, scenario=YOUR_PLAN, **kwargs
        )  # fmt: skip
    yours["plan"]["file"] = YOUR_PLAN
    row = comparison_rows(
        {BASELINE: signed, YOUR_PLAN: yours}, {YOUR_PLAN: YOUR_PLAN_LABEL}
    )[1]
    return {
        "plan.json": canonical(plan),
        "report.json": canonical(yours),
        "comparison-row.json": canonical(row),
        **native_lanes(yours, plan),
    }


def native_lanes(report: dict, plan_doc: dict = PLAN) -> dict[str, str]:
    """The edited plan's lanes as the generator writes a scenario's: the basis built from the
    company's data (not read from the committed file), the plan loaded from a file."""
    with in_repo(), tempfile.TemporaryDirectory() as tmp:
        plan_file = Path(tmp) / f"{YOUR_PLAN}.yaml"
        plan_file.write_text(yaml.safe_dump(plan_doc, sort_keys=False))
        state = prepare(PROFILES / COMPANY, DATA / COMPANY, AS_OF, DRAWS, SEED)
        plan = load_plan(plan_file, AS_OF, state.cap.members)
        basis = lanes_basis.plan_basis(state)
        digest = lanes_contract.digest(lanes_basis.document(basis, COMPANY))
        hires, inflows = actions.plan_inputs(state.ground, plan)
        doc = lanes.lanes_document(
            state,
            basis,
            report,
            hires,
            inflows,
            COMPANY,
            YOUR_PLAN,
            digest,
            driver_actions.effect_for(state, plan, hires, inflows),
        )
    mine, owners = lanes_files.split(doc)
    return {
        "lanes.json": canonical(mine),
        **{
            f"owners-{segment}.json": lanes_text.text(owners[segment])
            for segment in OWNER_SEGMENTS
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m engine.scripts.generate_editor_fixture"
    )
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    built = {out: build(plan) for out, plan in CASES}
    if not args.verify:
        for out, files in built.items():
            out.mkdir(parents=True, exist_ok=True)
            for name, text in files.items():
                (out / name).write_text(text)
            print(f"wrote {len(files)} files under {out.relative_to(REPO)}")
        return 0
    stale = [
        f"{out.name}/{name}"
        for out, files in built.items()
        for name, text in files.items()
        if not (out / name).exists() or (out / name).read_text() != text
    ]
    if stale:
        print("editor fixture is stale:", *stale, sep="\n  ", file=sys.stderr)
        return 1
    total = sum(len(files) for files in built.values())
    print(f"ok: {total} editor fixture files are current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
