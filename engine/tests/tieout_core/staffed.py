"""Generated companies for the capacity tests: pipeline that follows headcount
and pipeline that is pure demand, written as the CSV files the report reads."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from engine.scripts.generate_data_v2 import write_company_files
from engine.scripts.synth_history import Company, Staffing, generate
from engine.tests.tieout_core.builders import write_profile

START, AS_OF = date(2024, 2, 1), date(2026, 8, 31)
HEADCOUNT = (
    (START, 4), (date(2024, 8, 1), 6), (date(2025, 2, 1), 9),
    (date(2025, 8, 1), 13), (date(2026, 2, 1), 18), (date(2026, 6, 1), 26),
)  # fmt: skip

CAPACITY_YAML = """\
roles:
  quota_carrying: [ae]
  other: [sdr]
ramp:
  months: [0.17, 0.5, 0.83]
attrition:
  monthly_per_ae: 0.01
costs:
  loaded_cost_per_ae_month: 12000
  programme_cost_per_dollar_of_pipeline: 0.05
"""


def company(rep_rate: float, demand: float, seed: int = 7) -> Company:
    return Company(
        slug="gen", prefix="GEN", start=START, as_of=AS_OF, seed=seed, deals_per_month=0,
        advance=(0.6, 0.7, 0.72, 0.78, 0.88), dwell_days=(20, 25, 25, 20, 15),
        segments=(("mid_market", 1.0, 50_000),), size_sigma=0.5,
        staffing=Staffing(
            headcount=HEADCOUNT, monthly_attrition=0.01, deals_per_ramped_ae_month=rep_rate,
            ramp_months=3, demand_deals_per_month=demand,
            annual_quota=(("mid_market", 1_000_000),), other_roles=(("sdr", 2),),
        ),
    )  # fmt: skip


def write(
    root: Path, rep_rate: float, demand: float, capacity: bool = True, targets=None
):
    """A profile and a data directory under ``root``; returns (profile, data)."""
    profile = write_profile(
        root / "profile", targets or {f"Q{q}FY26": 2_000_000 for q in range(1, 5)}
    )
    if capacity:
        (profile / "capacity.yaml").write_text(CAPACITY_YAML)
    data = root / "data"
    write_company_files(generate(company(rep_rate, demand)), data)
    return profile, data
