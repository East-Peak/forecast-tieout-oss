"""Write small profile and company directories for tests."""

from __future__ import annotations

import csv
from pathlib import Path

import yaml

STAGES = [
    ("Discovery", "S1", 1, 0.1),
    ("Qualification", "S2", 2, 0.2),
    ("Technical Evaluation", "S3", 3, 0.3),
    ("Business Case", "S4", 4, 0.5),
    ("Negotiation", "S5", 5, 0.8),
    ("Closed Won", "Won", 99, 1.0),
    ("Closed Lost", "Lost", 100, 0.0),
]

DEAL_COLUMNS = [
    "id", "name", "account", "owner", "owner_id", "segment", "source_channel",
    "stage", "amount", "arr", "created_date", "close_date", "is_closed",
    "is_won", "lost_reason", "raw_stage", "type", "forecast_category",
]  # fmt: skip


def write_profile(root: Path, targets=None, fy_start="2026-02-01") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    targets = targets or {f"Q{q}FY26": 1000 for q in range(1, 5)}
    (root / "stages.yaml").write_text(
        yaml.safe_dump(
            {
                "stages": [
                    {"name": n, "order": o, "probability": p} for n, _, o, p in STAGES
                ]
            }
        )
    )
    (root / "field_mappings.yaml").write_text(
        yaml.safe_dump(
            {"opportunity": {"stage": {"stage_mapping": {n: c for n, c, *_ in STAGES}}}}
        )
    )
    (root / "targets.yaml").write_text(
        yaml.safe_dump(
            {
                "fiscal_year_start": fy_start,
                "quarterly_targets": {
                    k: {"bookings_target": v} for k, v in targets.items()
                },
            }
        )
    )
    return root


def deal(id, stage="Discovery", arr="100", created="2026-01-01", close="", type="new_business", segment="mid_market"):  # fmt: skip
    closed = stage in ("Closed Won", "Closed Lost")
    return {
        "id": id, "name": id, "account": id, "owner": "", "owner_id": "",
        "segment": segment, "source_channel": "", "stage": stage, "amount": arr,
        "arr": arr, "created_date": created, "close_date": close,
        "is_closed": "true" if closed else "false",
        "is_won": "true" if stage == "Closed Won" else "false",
        "lost_reason": "", "raw_stage": stage, "type": type, "forecast_category": "",
    }  # fmt: skip


def write_company(root: Path, deals, history=(), observations=None, team=None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _write(root / "deals.csv", DEAL_COLUMNS, deals)
    _write(
        root / "stage_history.csv",
        ["deal_id", "from_stage", "to_stage", "transition_date"],
        [
            {"deal_id": d, "from_stage": "", "to_stage": s, "transition_date": t}
            for d, s, t in history
        ],
    )
    if observations is not None:
        _write(
            root / "deal_observations.csv",
            ["deal_id", "observed_date", "amount", "expected_close_date"],
            [
                {"deal_id": d, "observed_date": o, "amount": a, "expected_close_date": e}
                for d, o, a, e in observations
            ],
        )
    team = team if team is not None else [{"id": "AE-1", "role": "ae"}]
    _write(root / "team_members.csv", ["id", "role"], team)
    return root


def _write(path: Path, columns, rows) -> None:
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
