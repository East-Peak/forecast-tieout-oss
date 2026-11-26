"""python -m engine.tieout_core report --profile P --data D --as-of YYYY-MM-DD --out DIR"""

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
    args = parser.parse_args(argv)
    try:
        report = build_report(
            args.profile, args.data, args.as_of, draws=args.draws, seed=args.seed
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    md, js = write_report(report, args.out)
    v = report["verdicts"]
    print(f"wrote {md} and {js}")
    print(f"software correct: {v['software_correct']['verdict']}; "
          f"better than baselines: {v['forecast_better_than_baselines']['verdict']}")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
