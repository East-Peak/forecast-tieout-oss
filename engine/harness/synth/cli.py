"""Command line: generate one company's extracts and ground truth.

    python -m engine.harness.synth --variant demand_limited --seed 1 --out <dir>

writes `<dir>/extracts/extract_<date>/<system>/...` (what the evidence engine may
read) and `<dir>/truth/` (snapshot.json and manifest.json: parameters, named
cases; for judging only, never read by evidence or planning code).
"""

import argparse
import hashlib
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

from .cases import named_cases
from .params import VARIANTS, CompanyParams
from .people import day_of
from .records import default_extract_dates, write_extracts
from .run import Company, run_company
from .truth import save_truth

HELD_OUT_SEEDS = range(101, 121)  # reserved for later scoring: development uses 1 to 20


def generate(
    params: CompanyParams, seed: int, out: Path, dates: list[date] | None = None
) -> Company:
    out = Path(out)
    dates = default_extract_dates(params) if dates is None else dates
    company = run_company(params, seed, extract_days=tuple(day_of(d) for d in dates))
    write_extracts(company, out, dates)
    (out / "truth").mkdir(parents=True, exist_ok=True)
    save_truth(company.truth, out / "truth" / "snapshot.json")
    manifest = {
        "seed": seed,
        "variant": params.variant,
        "extract_dates": [d.isoformat() for d in dates],
        "params": params.to_dict(),
        "named_cases": named_cases(company),
        "direct_demand_turned_away": company.sim.turned_away,
        "notes": "Truth for judging only. Lanes use the attribution the business recorded.",
    }
    (out / "truth" / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return company


def tree_hash(root: Path) -> str:
    """One hash of every file under `root`: path and bytes, in sorted order."""
    digest = hashlib.sha256()
    for path in sorted(p for p in Path(root).rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def small_params(variant: str) -> CompanyParams:
    return CompanyParams.for_variant(
        variant, start=date(2024, 2, 1), end=date(2025, 3, 31)
    )


def verify(variant: str, seed: int) -> bool:
    """Generate a small company twice into scratch folders; True when the bytes are identical."""
    hashes = []
    for _ in range(2):
        with tempfile.TemporaryDirectory() as scratch:
            generate(
                small_params(variant),
                seed,
                Path(scratch),
                [date(2025, 1, 24), date(2025, 2, 28), date(2025, 3, 31)],
            )
            hashes.append(tree_hash(Path(scratch)))
    return hashes[0] == hashes[1]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m engine.harness.synth", description=__doc__.split("\n")[0]
    )
    ap.add_argument("--variant", choices=VARIANTS, default="demand_limited")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", type=Path)
    ap.add_argument(
        "--verify",
        action="store_true",
        help="determinism check: generate a small company twice and compare hashes",
    )
    ap.add_argument(
        "--allow-held-out-seed",
        action="store_true",
        help="permit seeds 101 to 120 (scoring only)",
    )
    args = ap.parse_args(argv)
    if args.seed in HELD_OUT_SEEDS and not args.allow_held_out_seed:
        ap.error("seeds 101 to 120 are held out for scoring; development uses 1 to 20")
    if args.verify:
        same = verify(args.variant, args.seed)
        print(
            "deterministic: identical bytes on two runs"
            if same
            else "NOT deterministic"
        )
        return 0 if same else 1
    if args.out is None:
        ap.error("--out is required")
    company = generate(CompanyParams.for_variant(args.variant), args.seed, args.out)
    t = company.truth
    print(
        f"{args.variant} seed {args.seed}: {len(company.sim.opps)} opportunities, {len(company.sim.leads)} leads -> {args.out}"
    )
    print(
        f"truth bookings ${t.bookings_cents.values.sum() / 100:,.0f} over {len(t.months)} months"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
