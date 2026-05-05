"""Guardrails on demo persona funnel rates.

These exist because v1 of the OSS demo shipped Mighty Oak with
funnel.mql_to_s0 = 0.006, which made Target Setter ask for 276K MQLs
to produce 1,661 S0 meetings — a number that read to analysts as a bug
rather than a finding. The tests below would have caught that.

Three layers:
    1. Per-persona band on funnel.mql_to_s0 — each persona's narrative
       implies a different plausible range; a global band would let a
       0.04 number pass on Mighty Oak that reads as broken.
    2. Relational checks vs. waterfall_rates — observed must be lower
       than (and not too distant from) the forward-looking planning rate.
    3. Net MQL→S2 falls in a B2B-SaaS-credible band, and the snapshot
       surfaces (observed_scenario, funnel_rates, funnel_rate_descriptions)
       agree on the same number.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILES_CFG = REPO_ROOT / "engine" / "config" / "profiles"

# Per-persona observed-rate bands. Lower bound = "below this reads as broken."
# Upper bound = "above this means the gap to waterfall has collapsed."
PERSONA_OBSERVED_BANDS: dict[str, tuple[float, float]] = {
    "sprout-labs": (0.04, 0.10),
    "sapling-industries": (0.08, 0.16),
    "mighty-oak-holdings": (0.04, 0.16),
}

# Relational floor: observed/waterfall ratio. Below this and the gap
# reads as "data is broken" rather than "we have headroom."
OBSERVED_TO_WATERFALL_FLOOR = 0.30

# Net MQL→S2 band. B2B SaaS credible range across all personas.
NET_MQL_TO_S2_BAND = (0.005, 0.05)


def _load_assumptions(persona: str) -> dict:
    path = PROFILES_CFG / persona / "assumptions.yaml"
    return yaml.safe_load(path.read_text())


@pytest.mark.parametrize("persona", list(PERSONA_OBSERVED_BANDS))
def test_observed_mql_to_s0_in_persona_band(persona: str) -> None:
    cfg = _load_assumptions(persona)
    rate = float(cfg["funnel"]["mql_to_s0"])
    lo, hi = PERSONA_OBSERVED_BANDS[persona]
    assert lo <= rate <= hi, (
        f"{persona} funnel.mql_to_s0={rate} outside narrative band [{lo}, {hi}]. "
        f"Below {lo} reads as broken to an analyst; above {hi} collapses the "
        f"observed↔waterfall gap that carries the persona story."
    )


@pytest.mark.parametrize("persona", list(PERSONA_OBSERVED_BANDS))
def test_observed_below_waterfall(persona: str) -> None:
    cfg = _load_assumptions(persona)
    observed = float(cfg["funnel"]["mql_to_s0"])
    waterfall = float(cfg["waterfall_rates"]["mql_to_s0"])
    assert observed < waterfall, (
        f"{persona}: observed mql_to_s0 ({observed}) must be < waterfall "
        f"({waterfall}). The gap is the persona story; equal/inverted means "
        f"there is no headroom narrative."
    )
    ratio = observed / waterfall
    assert ratio >= OBSERVED_TO_WATERFALL_FLOOR, (
        f"{persona}: observed/waterfall ratio {ratio:.2f} below floor "
        f"{OBSERVED_TO_WATERFALL_FLOOR}. The gap is too wide; reads as "
        f"broken data rather than reachable upside."
    )


@pytest.mark.parametrize("persona", list(PERSONA_OBSERVED_BANDS))
def test_net_mql_to_s2_in_industry_band(persona: str) -> None:
    cfg = _load_assumptions(persona)
    funnel = cfg["funnel"]
    net = (
        float(funnel["mql_to_s0"])
        * float(funnel["s0_to_s1"])
        * float(funnel["s1_to_s2"])
    )
    lo, hi = NET_MQL_TO_S2_BAND
    assert lo <= net <= hi, (
        f"{persona}: net MQL→S2 product = {net:.4f} outside B2B SaaS "
        f"credible band [{lo}, {hi}]. Below {lo} produces absurd MQL asks; "
        f"above {hi} reads as fantasy."
    )


# Snapshot-level cross-surface consistency. Codex round 1 #9: simple band
# tests on YAML can pass while observed_scenario, funnel_rates, and
# funnel_rate_descriptions drift apart, producing contradictory UI states.
# We regenerate one persona's snapshot here and assert all four surfaces
# agree on the same MQL→S0 number.

@pytest.fixture(scope="module")
def mighty_oak_snapshot(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("snap")
    output = tmp / "snapshot.json"
    profiles_out = tmp / "profiles"
    profiles_out.mkdir()
    subprocess.run(
        [
            "python3", "-m", "engine.scripts.generate_snapshot",
            "--profile-id", "mighty-oak-holdings",
            "--as-of", "2026-04-06",
            "--output", str(output),
            "--profiles-output-dir", str(profiles_out),
        ],
        check=True,
        cwd=str(REPO_ROOT),
    )
    return json.loads(output.read_text())


def test_snapshot_surfaces_agree_on_mql_to_s0(mighty_oak_snapshot) -> None:
    snap = mighty_oak_snapshot

    rates_funnel = snap["rates"]["funnel_rates"]["mql_to_s0"]
    obs_scenario = snap["target_setter"]["observed_scenario"]["mql_to_s0"]
    health_funnel = snap["model_output"]["funnel_health"]["funnel_rates"][
        "mql_to_s0"
    ]
    desc = snap["model_output"]["funnel_health"]["funnel_rate_descriptions"][
        "mql_to_s0"
    ]
    desc_value = desc["value"] if isinstance(desc, dict) else desc

    surfaces = {
        "rates.funnel_rates": rates_funnel,
        "target_setter.observed_scenario": obs_scenario,
        "model_output.funnel_health.funnel_rates": health_funnel,
        "model_output.funnel_health.funnel_rate_descriptions.value": desc_value,
    }
    distinct = set(round(float(v), 6) for v in surfaces.values())
    assert len(distinct) == 1, (
        f"Cross-surface mql_to_s0 disagreement: {surfaces}. "
        f"Target Setter, Funnel Health pill, and edge provenance must all "
        f"show the same number or the UI tells contradictory stories."
    )
