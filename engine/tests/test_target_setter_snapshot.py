"""Snapshot must emit target_setter.{observed_scenario, scenarios} when configured."""
import json
import subprocess


def _run(tmp_path):
    output = tmp_path / "snapshot.json"
    profiles_out = tmp_path / "profiles"
    profiles_out.mkdir()
    subprocess.run(
        [
            "python3", "-m", "engine.scripts.generate_snapshot",
            "--profile-id", "acme-saas",
            "--as-of", "2026-04-06",
            "--output", str(output),
            "--profiles-output-dir", str(profiles_out),
        ],
        check=True,
    )
    return json.loads(output.read_text())


def test_emits_observed_scenario(tmp_path):
    snap = _run(tmp_path)
    obs = snap["target_setter"]["observed_scenario"]
    # Required Scenario fields all present
    for f in [
        "id", "label", "win_rate_starting", "win_rate_created",
        "push_rate", "loss_rate", "ae_self_gen_pct",
        "mql_to_s0", "s0_to_s1", "s1_to_s2",
        "segment_share", "acv",
    ]:
        assert f in obs, f"observed_scenario missing {f}"
    assert obs["id"] == "observed"
    assert obs["label"] == "Observed"
    # Stage rates pulled from funnel_rates — engine already uses mql_to_s0 naming
    fr = snap["model_output"]["funnel_health"]["funnel_rates"]
    assert obs["mql_to_s0"] == fr["mql_to_s0"]
    assert obs["s0_to_s1"] == fr["s0_to_s1"]
    assert obs["s1_to_s2"] == fr["s1_to_s2"]
    # Engine combined target_setter_defaults into observed — calibration §3a values
    assert obs["ae_self_gen_pct"] == 0.70
    assert obs["segment_share"]["enterprise"] == 0.58
    assert obs["acv"]["commercial"] == 38000
    # Win/push/loss rates from target_setter_defaults
    assert obs["win_rate_starting"] == 0.44
    assert obs["push_rate"] == 0.20


def test_emits_scenarios(tmp_path):
    snap = _run(tmp_path)
    scenarios = snap["target_setter"]["scenarios"]
    by_id = {s["id"]: s for s in scenarios}
    assert "marketing-led" in by_id
    s = by_id["marketing-led"]
    # Calibration §3b values
    assert s["mql_to_s0"] == 0.45
    assert s["segment_share"]["enterprise"] == 0.60
    # description block passes through
    assert "primary" in s["description"]
    assert "secondary" in s["description"]


def test_target_setter_absent_when_no_config(tmp_path):
    """Profiles without scenarios.yaml + target_setter_defaults emit no target_setter block."""
    output = tmp_path / "snap.json"
    profiles_out = tmp_path / "profiles"
    profiles_out.mkdir()
    subprocess.run(
        [
            "python3", "-m", "engine.scripts.generate_snapshot",
            "--profile-id", "sprout-labs",
            "--as-of", "2026-04-06",
            "--output", str(output),
            "--profiles-output-dir", str(profiles_out),
        ],
        check=True,
    )
    snap = json.loads(output.read_text())
    assert "target_setter" not in snap


def test_observed_scenario_omitted_when_funnel_rates_missing():
    """Fail-closed: missing funnel keys -> observed_scenario is None."""
    from engine.scripts.generate_snapshot import _build_observed_scenario

    defaults = {
        "ae_self_gen_pct": 0.70,
        "win_rate_starting": 0.44,
        "win_rate_created": 0.442,
        "push_rate": 0.20,
        "loss_rate": 0.36,
        "segment_share": {"enterprise": 0.58, "mid_market": 0.35, "commercial": 0.07},
        "acv": {"enterprise": 400000, "mid_market": 145000, "commercial": 38000},
    }
    assumptions = {"target_setter_defaults": defaults}

    # Empty funnel_rates dict
    snap_no_funnel = {"model_output": {"funnel_health": {"funnel_rates": {}}}}
    assert _build_observed_scenario(assumptions, snap_no_funnel) is None

    # Partial funnel_rates (s1_to_s2 missing)
    snap_partial = {
        "model_output": {
            "funnel_health": {
                "funnel_rates": {
                    "mql_to_s0": 0.15,
                    "s0_to_s1": 0.55,
                    # s1_to_s2 intentionally missing
                }
            }
        }
    }
    assert _build_observed_scenario(assumptions, snap_partial) is None


def test_observed_scenario_has_description(tmp_path):
    snap = _run(tmp_path)
    obs = snap["target_setter"]["observed_scenario"]
    assert "description" in obs
    assert "primary" in obs["description"]
    assert "secondary" in obs["description"]


def test_acme_observed_scenario_emitted_happy_path(tmp_path):
    snap = _run(tmp_path)
    assert "target_setter" in snap
    assert "observed_scenario" in snap["target_setter"]


def test_funnel_rates_not_renamed_in_place(tmp_path):
    """Engine already emits mql_to_s0 naming; observed_scenario reads them directly.

    Verify that funnel_rates still contains its normal keys after snapshot
    generation, and that the observed_scenario does NOT contain funnel_rates
    keys like 's2_to_won' (which is not a Scenario field).
    """
    snap = _run(tmp_path)
    fr = snap["model_output"]["funnel_health"]["funnel_rates"]
    # Engine uses mql_to_s0 naming in funnel_rates
    assert "mql_to_s0" in fr
    assert "s0_to_s1" in fr
    assert "s1_to_s2" in fr
    # s2_to_won lives in funnel_rates but is NOT copied into observed_scenario
    obs = snap["target_setter"]["observed_scenario"]
    assert "s2_to_won" not in obs  # not a Scenario-level field; lives in win_rate_created
