"""Write the demo companies' rebuilt data to ``engine/data-v2/<company>/``.

Goal 1 of the rebuild needs history the old demo data cannot support (close
dates that disagree with stage history, three or four months of outcomes,
deals created after the as-of date). This rebuilds the same three companies
with 31 months of history ending at the as-of date, close dates equal to the
final stage transition, nothing dated after the as-of date, and a
``deal_observations.csv`` that records past amounts and expected close dates.

``team_members.csv`` is carried over unchanged from ``engine/data``; giving it
correct roles is Goal 2's work. The old ``engine/data`` stays untouched.

    python -m engine.scripts.generate_data_v2            # write all three
    python -m engine.scripts.generate_data_v2 --verify   # fail if any file is stale
"""

from __future__ import annotations

import argparse
import csv
import filecmp
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

from engine.scripts.synth_history import Company, Generated, generate

ENGINE = Path(__file__).resolve().parents[1]
DATA_V2 = "data-v2"
AS_OF = date(2026, 8, 31)
START = date(2024, 2, 1)

STAGE_NAMES = {
    "S1": "Discovery",
    "S2": "Qualification",
    "S3": "Technical Evaluation",
    "S4": "Business Case",
    "S5": "Negotiation",
    "Won": "Closed Won",
    "Lost": "Closed Lost",
}

COMPANIES = {
    "sprout-labs": Company(
        slug="sprout-labs", prefix="SPR", start=START, as_of=AS_OF, seed=2601,
        deals_per_month=22, growth_per_year=0.45,
        advance=(0.55, 0.65, 0.7, 0.75, 0.85), dwell_days=(20, 25, 25, 20, 15),
        segments=(("commercial", 0.6, 45_000), ("mid_market", 0.4, 90_000)),
        size_sigma=0.55, big_deal_share=0.01, big_deal_multiplier=8,
        slip_share=0.35, stall_share=0.04, missing_history_share=0.02,
    ),
    "sapling-industries": Company(
        slug="sapling-industries", prefix="SAP", start=START, as_of=AS_OF, seed=2602,
        deals_per_month=36, growth_per_year=0.3,
        advance=(0.6, 0.7, 0.72, 0.78, 0.88), dwell_days=(20, 30, 30, 25, 15),
        segments=(("commercial", 0.35, 60_000), ("mid_market", 0.4, 250_000), ("enterprise", 0.25, 800_000)),
        size_sigma=0.6, big_deal_share=0.01, big_deal_multiplier=6,
        slip_share=0.3, stall_share=0.05, missing_history_share=0.01,
        other_motions=(("expansion", 3, 120_000),),
    ),
    "mighty-oak-holdings": Company(
        slug="mighty-oak-holdings", prefix="MOH", start=START, as_of=AS_OF, seed=2603,
        deals_per_month=36, growth_per_year=0.05,
        advance=(0.55, 0.65, 0.7, 0.75, 0.85), dwell_days=(30, 45, 45, 40, 25),
        segments=(("Mid-Market", 0.4, 500_000), ("Enterprise", 0.45, 1_500_000), ("Strategic Enterprise", 0.15, 4_000_000)),
        size_sigma=0.6, big_deal_share=0.02, big_deal_multiplier=5,
        slip_share=0.45, stall_share=0.06, missing_history_share=0.01,
        conversion_change=(date(2025, 9, 1), 0.85),
        other_motions=(("expansion", 10, 300_000), ("renewal", 12, 800_000)),
    ),
}  # fmt: skip

DEAL_COLUMNS = [
    "id", "name", "account", "owner", "owner_id", "segment", "source_channel",
    "stage", "amount", "arr", "created_date", "close_date", "is_closed",
    "is_won", "lost_reason", "raw_stage", "type", "forecast_category",
]  # fmt: skip


def write_company_files(generated: Generated, out: Path) -> None:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    data = generated.dataset
    owners = _owners(generated.company.slug)
    rows = []
    for i, d in enumerate(data.deals):
        stage = STAGE_NAMES[d.stage]
        owner_id, owner = owners[i % len(owners)] if owners else ("", "")
        rows.append(
            {
                "id": d.id, "name": f"{d.id} {d.type.replace('_', ' ')}",
                "account": f"Account {d.id.split('-')[1]}", "owner": owner, "owner_id": owner_id,
                "segment": d.segment, "source_channel": "", "stage": stage,
                "amount": d.arr, "arr": d.arr, "created_date": d.created.isoformat(),
                "close_date": d.close.isoformat() if d.close else "",
                "is_closed": _flag(d.is_closed), "is_won": _flag(d.is_won),
                "lost_reason": "No decision" if d.stage == "Lost" else "", "raw_stage": stage,
                "type": d.type, "forecast_category": "Closed" if d.is_closed else "Pipeline",
            }
        )  # fmt: skip
    _write(out / "deals.csv", DEAL_COLUMNS, rows)
    _write(
        out / "stage_history.csv",
        ["deal_id", "from_stage", "to_stage", "transition_date"],
        _history_rows(data.transitions),
    )
    _write(
        out / "deal_observations.csv",
        ["deal_id", "observed_date", "amount", "expected_close_date"],
        [
            {
                "deal_id": o.deal_id,
                "observed_date": o.on.isoformat(),
                "amount": o.amount,
                "expected_close_date": o.expected_close.isoformat(),
            }
            for o in data.observations
        ],
    )
    shutil.copyfile(
        ENGINE / "data" / generated.company.slug / "team_members.csv",
        out / "team_members.csv",
    )


def _history_rows(transitions):
    rows, previous = [], {}
    for t in transitions:
        rows.append(
            {
                "deal_id": t.deal_id,
                "from_stage": STAGE_NAMES.get(previous.get(t.deal_id), ""),
                "to_stage": STAGE_NAMES[t.stage],
                "transition_date": t.on.isoformat(),
            }
        )
        previous[t.deal_id] = t.stage
    return rows


def _owners(slug: str) -> list[tuple[str, str]]:
    path = ENGINE / "data" / slug / "team_members.csv"
    with path.open(newline="") as fh:
        return [
            (r["id"], r["name"])
            for r in csv.DictReader(fh)
            if r["role"].strip().lower() == "ae"
        ]


def _flag(x: bool) -> str:
    return "true" if x else "false"


def _write(path: Path, columns, rows) -> None:
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def target_dir(slug: str) -> Path:
    return ENGINE / DATA_V2 / slug


def verify(slug: str) -> list[str]:
    """Names of files that differ from a fresh regeneration."""
    with tempfile.TemporaryDirectory() as tmp:
        write_company_files(generate(COMPANIES[slug]), Path(tmp))
        names = sorted(p.name for p in Path(tmp).iterdir())
        committed = target_dir(slug)
        return [
            n
            for n in names
            if not (committed / n).exists()
            or not filecmp.cmp(Path(tmp) / n, committed / n, shallow=False)
        ]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--verify", action="store_true", help="check committed files instead of writing"
    )
    args = parser.parse_args(argv)
    stale = []
    for slug in COMPANIES:
        if args.verify:
            stale += [f"{slug}/{n}" for n in verify(slug)]
        else:
            write_company_files(generate(COMPANIES[slug]), target_dir(slug))
            print(f"wrote engine/{DATA_V2}/{slug}")
    if stale:
        print("stale data-v2 files: " + ", ".join(stale), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
