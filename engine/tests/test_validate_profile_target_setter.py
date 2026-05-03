"""validate_profile rejects malformed TargetSetter config."""
import subprocess, shutil, yaml
from pathlib import Path


def _profile(tmp_path):
    src = Path("engine/config/profiles/acme-saas")
    dst = tmp_path / "acme-saas"
    shutil.copytree(src, dst)
    return dst


def _validate(profile_dir):
    return subprocess.run(
        ["python3", "-m", "engine.scripts.validate_profile",
         "--profile-dir", str(profile_dir)],
        capture_output=True, text=True,
    )


def test_valid_passes(tmp_path):
    r = _validate(_profile(tmp_path))
    assert r.returncode == 0, r.stderr


def test_scenario_missing_required_field(tmp_path):
    p = _profile(tmp_path)
    raw = yaml.safe_load((p / "scenarios.yaml").read_text())
    del raw["scenarios"][0]["mql_to_s0"]
    (p / "scenarios.yaml").write_text(yaml.dump(raw))
    r = _validate(p)
    assert r.returncode != 0
    assert "mql_to_s0" in (r.stdout + r.stderr)


def test_segment_acv_key_mismatch_fails(tmp_path):
    p = _profile(tmp_path)
    raw = yaml.safe_load((p / "scenarios.yaml").read_text())
    raw["scenarios"][0]["segment_share"] = {"enterprise": 0.7, "commercial": 0.3}
    raw["scenarios"][0]["acv"] = {"enterprise": 250000, "smb": 30000}  # commercial gone, smb new
    (p / "scenarios.yaml").write_text(yaml.dump(raw))
    r = _validate(p)
    assert r.returncode != 0
    assert "segment_share" in (r.stdout + r.stderr) or "acv" in (r.stdout + r.stderr)


def test_rate_out_of_bounds_fails(tmp_path):
    p = _profile(tmp_path)
    raw = yaml.safe_load((p / "scenarios.yaml").read_text())
    raw["scenarios"][0]["mql_to_s0"] = 1.5
    (p / "scenarios.yaml").write_text(yaml.dump(raw))
    r = _validate(p)
    assert r.returncode != 0
    assert "mql_to_s0" in (r.stdout + r.stderr) or "0..1" in (r.stdout + r.stderr)


def test_negative_acv_fails(tmp_path):
    p = _profile(tmp_path)
    raw = yaml.safe_load((p / "assumptions.yaml").read_text())
    raw["target_setter_defaults"]["acv"]["enterprise"] = -1
    (p / "assumptions.yaml").write_text(yaml.dump(raw))
    r = _validate(p)
    assert r.returncode != 0
    assert "acv" in (r.stdout + r.stderr) or "positive" in (r.stdout + r.stderr)


def test_target_setter_defaults_missing_field_fails(tmp_path):
    p = _profile(tmp_path)
    raw = yaml.safe_load((p / "assumptions.yaml").read_text())
    del raw["target_setter_defaults"]["ae_self_gen_pct"]
    (p / "assumptions.yaml").write_text(yaml.dump(raw))
    r = _validate(p)
    assert r.returncode != 0
    assert "ae_self_gen_pct" in (r.stdout + r.stderr)


def test_unknown_field_rejected(tmp_path):
    """Typo defense: unknown scenario field fails validation."""
    p = _profile(tmp_path)
    raw = yaml.safe_load((p / "scenarios.yaml").read_text())
    raw["scenarios"][0]["mql_to_s_zero"] = 0.20  # typo
    (p / "scenarios.yaml").write_text(yaml.dump(raw))
    r = _validate(p)
    assert r.returncode != 0
    assert "unknown" in (r.stdout + r.stderr).lower() or "mql_to_s_zero" in (r.stdout + r.stderr)


def test_non_dict_segment_share_handled(tmp_path):
    """isinstance guard: segment_share as string doesn't crash validator."""
    p = _profile(tmp_path)
    raw = yaml.safe_load((p / "assumptions.yaml").read_text())
    raw["target_setter_defaults"]["segment_share"] = "not a dict"
    (p / "assumptions.yaml").write_text(yaml.dump(raw))
    r = _validate(p)
    assert r.returncode != 0
    assert "mapping" in (r.stdout + r.stderr).lower() or "segment_share" in (r.stdout + r.stderr)


def test_segment_share_value_out_of_bounds_fails(tmp_path):
    """segment_share values must be 0..1."""
    p = _profile(tmp_path)
    raw = yaml.safe_load((p / "scenarios.yaml").read_text())
    raw["scenarios"][0]["segment_share"]["enterprise"] = 1.7
    raw["scenarios"][0]["segment_share"]["commercial"] = -0.7
    (p / "scenarios.yaml").write_text(yaml.dump(raw))
    r = _validate(p)
    assert r.returncode != 0
    assert "segment_share" in (r.stdout + r.stderr) or "0..1" in (r.stdout + r.stderr)


def test_root_key_typo_rejected(tmp_path):
    """`scenarioz:` at root must NOT silently pass."""
    p = _profile(tmp_path)
    (p / "scenarios.yaml").write_text("scenarioz:\n  - id: foo\n    label: Foo\n")
    r = _validate(p)
    assert r.returncode != 0
    assert "unknown" in (r.stdout + r.stderr).lower() or "scenarioz" in (r.stdout + r.stderr)


def test_non_mapping_root_rejected(tmp_path):
    """A list at the YAML root crashes raw.get() without isinstance guard."""
    p = _profile(tmp_path)
    (p / "scenarios.yaml").write_text("- id: foo\n  label: Foo\n")
    r = _validate(p)
    assert r.returncode != 0
    assert "mapping" in (r.stdout + r.stderr).lower() or "list" in (r.stdout + r.stderr).lower()


def test_description_drift_rejected(tmp_path):
    """Unknown field in description block fails."""
    p = _profile(tmp_path)
    raw = yaml.safe_load((p / "scenarios.yaml").read_text())
    raw["scenarios"][0]["description"] = {"primary": "x", "secondary": "y", "tertiary": "z"}
    (p / "scenarios.yaml").write_text(yaml.dump(raw))
    r = _validate(p)
    assert r.returncode != 0
    assert "tertiary" in (r.stdout + r.stderr) or "unknown" in (r.stdout + r.stderr).lower()


def test_no_target_setter_config_passes(tmp_path):
    """Profile without scenarios.yaml + target_setter_defaults validates OK."""
    p = _profile(tmp_path)
    (p / "scenarios.yaml").unlink()
    raw = yaml.safe_load((p / "assumptions.yaml").read_text())
    raw.pop("target_setter_defaults", None)
    (p / "assumptions.yaml").write_text(yaml.dump(raw))
    r = _validate(p)
    assert r.returncode == 0, r.stderr
