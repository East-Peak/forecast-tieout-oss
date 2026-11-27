"""Write the demo companies' rebuilt data to ``engine/data-v2/<company>/``.

Each demo company gets 31 months of history ending at the as-of date, close dates
equal to the final stage transition, nothing dated after the as-of date, and a
``deal_observations.csv`` that records past amounts and expected close dates.

Goal 2A makes pipeline creation depend on people. Each company is staffed
(``synth_history.Staffing``): AEs are hired to the profile's headcount plan
with monthly attrition, ramp linearly, and create deals at a full-ramp rate,
while demand that ignores headcount creates the rest, in the mix stated in
``STATED_REP_SHARE``. ``team_members.csv`` is written from that roster with
start and end dates and full-ramp ``annual_quota``; every deal's owner was
employed on its creation date. The stories stay: Sprout has few reps and lumpy
deals; Sapling's heads are on plan but many are still ramping; Mighty Oak is
staffed and its conversion is the problem.

    python -m engine.scripts.generate_data_v2            # write all three
    python -m engine.scripts.generate_data_v2 --verify   # fail if a file is stale or breaks an invariant
"""

from __future__ import annotations

import argparse
import csv
import filecmp
import sys
import tempfile
from datetime import date
from pathlib import Path

from engine.scripts.synth_history import Company, Generated, Staffing, generate

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
        staffing=Staffing(
            headcount=((START, 2), (date(2024, 10, 1), 3), (date(2025, 6, 1), 4),
                       (date(2026, 3, 1), 5), (date(2026, 4, 1), 6)),
            monthly_attrition=0.02, deals_per_ramped_ae_month=4.0, ramp_months=3,
            demand_deals_per_month=9.0,
            annual_quota=(("commercial", 1_500_000), ("mid_market", 2_000_000)),
            other_roles=(("founder", 2), ("sdr", 2), ("se", 1)),
        ),
    ),
    "sapling-industries": Company(
        slug="sapling-industries", prefix="SAP", start=START, as_of=AS_OF, seed=2602,
        deals_per_month=36, growth_per_year=0.3,
        advance=(0.6, 0.7, 0.72, 0.78, 0.88), dwell_days=(20, 30, 30, 25, 15),
        segments=(("commercial", 0.35, 60_000), ("mid_market", 0.4, 250_000), ("enterprise", 0.25, 800_000)),
        size_sigma=0.6, big_deal_share=0.01, big_deal_multiplier=6,
        slip_share=0.3, stall_share=0.05, missing_history_share=0.01,
        other_motions=(("expansion", 3, 120_000),),
        staffing=Staffing(
            headcount=((START, 12), (date(2024, 8, 1), 16), (date(2025, 2, 1), 22),
                       (date(2025, 8, 1), 26), (date(2026, 2, 1), 30), (date(2026, 5, 1), 36),
                       (date(2026, 8, 1), 45)),
            monthly_attrition=0.015, deals_per_ramped_ae_month=1.5, ramp_months=10,
            demand_deals_per_month=9.0,
            annual_quota=(("commercial", 900_000), ("mid_market", 1_800_000), ("enterprise", 3_200_000)),
            other_roles=(("vp_sales", 1), ("manager", 3), ("sdr", 6), ("se", 5)),
        ),
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
        staffing=Staffing(
            headcount=((START, 80), (date(2025, 2, 1), 86), (date(2026, 2, 1), 89),
                       (date(2026, 3, 1), 93), (date(2026, 4, 1), 96), (date(2026, 5, 1), 98),
                       (date(2026, 7, 1), 99), (date(2026, 8, 1), 100)),
            monthly_attrition=0.012, deals_per_ramped_ae_month=0.25, ramp_months=6,
            demand_deals_per_month=13.0,
            annual_quota=(("Mid-Market", 700_000), ("Enterprise", 1_200_000), ("Strategic Enterprise", 1_800_000)),
            other_roles=(("vp_sales", 1), ("manager", 7), ("renewal_manager", 4), ("sdr", 18), ("se", 14)),
        ),
    ),
}  # fmt: skip

# Share of new-business deals created in the trailing twelve months that ramped
# AEs made (the rest is demand that ignores headcount). Measured from the
# generated data and stated here; a test holds the data to it.
STATED_REP_SHARE = {
    "sprout-labs": 0.50,
    "sapling-industries": 0.72,
    "mighty-oak-holdings": 0.59,
}

ROSTER_COLUMNS = [
    "id", "name", "role", "segment", "start_date", "end_date", "is_active",
    "manager_id", "annual_quota",
]  # fmt: skip

DEAL_COLUMNS = [
    "id", "name", "account", "owner", "owner_id", "segment", "source_channel",
    "stage", "amount", "arr", "created_date", "close_date", "is_closed",
    "is_won", "lost_reason", "raw_stage", "type", "forecast_category",
]  # fmt: skip


def write_company_files(generated: Generated, out: Path) -> None:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    data = generated.dataset
    names = {m.id: m.name for m in generated.roster}
    rows = []
    for d in data.deals:
        stage = STAGE_NAMES[d.stage]
        owner_id = generated.owners[d.id]
        owner = names[owner_id]
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
    _write(out / "team_members.csv", ROSTER_COLUMNS, _roster_rows(generated.roster))


def _roster_rows(roster):
    managers = [m.id for m in roster if m.role == "manager"]
    return [
        {
            "id": m.id, "name": m.name, "role": m.role, "segment": m.segment,
            "start_date": m.start.isoformat(), "end_date": m.end.isoformat() if m.end else "",
            "is_active": _flag(m.end is None),
            "manager_id": managers[i % len(managers)] if m.role == "ae" and managers else "",
            "annual_quota": m.annual_quota if m.annual_quota is not None else "",
        }
        for i, m in enumerate(roster)
    ]  # fmt: skip


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


# Columns holding facts. An open deal's close_date is an expected date, a
# forecast rather than a fact, and may lie after the cutoff.
FACT_DATES = {
    "deals.csv": ("created_date",),
    "stage_history.csv": ("transition_date",),
    "deal_observations.csv": ("observed_date",),
    "team_members.csv": ("start_date", "end_date"),
}


def check_invariants(directory: Path, cutoff: date) -> list[str]:
    """Problems in a company's files: a deal owned by someone not employed on
    its creation date, or a fact dated after the cutoff."""
    directory = Path(directory)
    problems = []
    for name, columns in FACT_DATES.items():
        for i, row in enumerate(_read(directory / name), start=2):
            for col in columns:
                if row[col] and date.fromisoformat(row[col][:10]) > cutoff:
                    problems.append(
                        f"{name} row {i}: {col} {row[col]} is after the cutoff {cutoff}"
                    )
        if name == "deals.csv":
            for i, row in enumerate(_read(directory / name), start=2):
                closed = row["is_closed"] == "true"
                if closed and date.fromisoformat(row["close_date"]) > cutoff:
                    problems.append(
                        f"deals.csv row {i}: close_date {row['close_date']} is after the cutoff {cutoff}"
                    )
    team = {r["id"]: r for r in _read(directory / "team_members.csv")}
    for row in _read(directory / "deals.csv"):
        member = team.get(row["owner_id"])
        created = row["created_date"]
        if member is None:
            problems.append(
                f"deal {row['id']}: owner {row['owner_id']!r} is not on the roster"
            )
        elif not (
            member["start_date"] <= created
            and (not member["end_date"] or created <= member["end_date"])
        ):
            problems.append(
                f"deal {row['id']}: owner {member['id']} was not employed on its creation date {created} "
                f"(employed {member['start_date']} to {member['end_date'] or 'now'})"
            )
    return problems  # fmt: skip


def _read(path: Path) -> list[dict]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--verify", action="store_true", help="check committed files instead of writing"
    )
    args = parser.parse_args(argv)
    stale = []
    for slug, company in COMPANIES.items():
        if args.verify:
            stale += [f"{slug}/{n}" for n in verify(slug)]
            for problem in check_invariants(target_dir(slug), company.as_of):
                stale.append(f"{slug}: {problem}")
        else:
            write_company_files(generate(company), target_dir(slug))
            print(f"wrote engine/{DATA_V2}/{slug}")
    if stale:
        print("data-v2 problems:\n  " + "\n  ".join(stale), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
