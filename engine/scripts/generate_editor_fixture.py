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
from engine.tieout_core.report import build_report

COMPANY = "sapling-industries"
OUT = REPO / "frontend/src/screens/__tests__/fixtures/your-plan"

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


def build() -> dict[str, str]:
    with in_repo(), tempfile.TemporaryDirectory() as tmp:
        plan_file = Path(tmp) / f"{YOUR_PLAN}.yaml"
        plan_file.write_text(yaml.safe_dump(PLAN, sort_keys=False))
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
        "plan.json": canonical(PLAN),
        "report.json": canonical(yours),
        "comparison-row.json": canonical(row),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m engine.scripts.generate_editor_fixture"
    )
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    files = build()
    if not args.verify:
        OUT.mkdir(parents=True, exist_ok=True)
        for name, text in files.items():
            (OUT / name).write_text(text)
        print(f"wrote {len(files)} files under {OUT.relative_to(REPO)}")
        return 0
    stale = [
        name
        for name, text in files.items()
        if not (OUT / name).exists() or (OUT / name).read_text() != text
    ]
    if stale:
        print("editor fixture is stale:", *stale, sep="\n  ", file=sys.stderr)
        return 1
    print(f"ok: {len(files)} editor fixture files are current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
