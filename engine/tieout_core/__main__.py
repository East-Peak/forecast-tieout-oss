"""python -m engine.tieout_core report --profile P --data D --as-of YYYY-MM-DD --out DIR [--plan plan.yaml]
python -m engine.tieout_core candidates   (Goal 2A before-and-after tables on the demo data)"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from .report import build_report, write_report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m engine.tieout_core")
    sub = parser.add_subparsers(dest="command", required=True)
    rep = sub.add_parser("report", help="write report.md and report.json")
    rep.add_argument(
        "--profile", required=True, help="profile directory (stages, mapping, targets)"
    )
    rep.add_argument("--data", required=True, help="company data directory (CSV files)")
    rep.add_argument(
        "--as-of", required=True, type=date.fromisoformat, help="as-of date, YYYY-MM-DD"
    )
    rep.add_argument("--out", required=True, help="output directory")
    rep.add_argument(
        "--draws", type=int, default=2000, help="simulation draws (default 2000)"
    )
    rep.add_argument("--seed", type=int, default=0, help="simulation seed (default 0)")
    rep.add_argument(
        "--plan",
        help="plan.yaml: further hires and programme pipeline (adds section 11)",
    )
    sub.add_parser("candidates", help="score the Goal 2A candidates on the demo data")
    args = parser.parse_args(argv)
    if args.command == "candidates":
        from .candidates import render, score_ranges

        print(render(score_ranges()), end="")
        return 0
    try:
        report = build_report(
            args.profile, args.data, args.as_of, draws=args.draws, seed=args.seed,
            plan_path=args.plan,
        )  # fmt: skip
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    md, js = write_report(report, args.out)
    v = report["verdicts"]
    print(f"wrote {md} and {js}")
    print(f"software correct: {v['software_correct']['verdict']}; "
          f"better than baselines: {v['forecast_better_than_baselines']['verdict']}")  # fmt: skip
    # An honest "not better than the baselines" is a result; a failed self-check is a fault.
    return 0 if v["software_correct"]["verdict"] == "yes" else 1


if __name__ == "__main__":
    sys.exit(main())
