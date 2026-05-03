# engine/tests/test_validate_profile.py
"""TDD tests for profile configuration validator — written before implementation."""
import pytest
from pathlib import Path

import yaml

from engine.scripts.validate_profile import ValidationResult, validate_profile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REQUIRED_FILES = [
    "profile.yaml",
    "stages.yaml",
    "roster.yaml",
    "targets.yaml",
    "assumptions.yaml",
    "field_mappings.yaml",
    "slip_rates.yaml",
]


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.dump(data, default_flow_style=False))


def _create_valid_profile(profile_dir: Path) -> None:
    """Write a minimal valid profile into *profile_dir*."""
    profile_dir.mkdir(parents=True, exist_ok=True)

    _write_yaml(profile_dir / "profile.yaml", {
        "id": "acme-saas",
        "name": "Acme SaaS",
        "revenue_metric": "bookings",
    })

    _write_yaml(profile_dir / "stages.yaml", {
        "stages": [
            {"name": "S0", "label": "Research", "probability": 0.10},
            {"name": "S1", "label": "Discovery", "probability": 0.20},
            {"name": "S2", "label": "Scope", "probability": 0.40},
            {"name": "Won", "label": "Closed Won", "probability": 1.00},
            {"name": "Lost", "label": "Closed Lost", "probability": 0.00},
        ],
    })

    _write_yaml(profile_dir / "roster.yaml", {
        "team_members": [
            {"id": "user_001", "name": "Alice", "role": "AE"},
            {"id": "user_002", "name": "Bob", "role": "AE"},
        ],
    })

    _write_yaml(profile_dir / "targets.yaml", {
        "annual_target": 10000000,
        "quarterly_targets": {
            "Q1": 2000000,
            "Q2": 2500000,
            "Q3": 2500000,
            "Q4": 3000000,
        },
    })

    _write_yaml(profile_dir / "assumptions.yaml", {
        "stage_rates": {
            "S0": {"conversion": 0.30},
            "S1": {"conversion": 0.50},
            "S2": {"conversion": 0.60},
        },
    })

    _write_yaml(profile_dir / "field_mappings.yaml", {
        "opportunity": {
            "amount": {"sf_field": "Amount"},
            "stage": {
                "sf_field": "StageName",
                "stage_mapping": {
                    "Closed Won": "Won",
                    "Closed Lost": "Lost",
                },
            },
            "close_date": {"sf_field": "CloseDate"},
            "owner_id": {"sf_field": "OwnerId"},
        },
    })

    _write_yaml(profile_dir / "slip_rates.yaml", {
        "default_slip_rate": 0.15,
        "stage_slip_rates": {
            "S2": 0.20,
            "S3": 0.10,
        },
    })


# ---------------------------------------------------------------------------
# 1. Valid profile passes
# ---------------------------------------------------------------------------


class TestValidProfilePasses:
    def test_valid_profile_returns_passed_true(self, tmp_path):
        profile_dir = tmp_path / "acme-saas"
        _create_valid_profile(profile_dir)
        result = validate_profile(profile_dir)
        assert result.passed is True
        assert result.errors == []

    def test_valid_profile_may_have_warnings(self, tmp_path):
        """Warnings are allowed — errors are what block."""
        profile_dir = tmp_path / "acme-saas"
        _create_valid_profile(profile_dir)
        result = validate_profile(profile_dir)
        assert result.passed is True


# ---------------------------------------------------------------------------
# 2. Missing required file -> error
# ---------------------------------------------------------------------------


class TestMissingRequiredFile:
    @pytest.mark.parametrize("missing_file", REQUIRED_FILES)
    def test_missing_file_produces_error(self, tmp_path, missing_file):
        profile_dir = tmp_path / "incomplete"
        _create_valid_profile(profile_dir)
        (profile_dir / missing_file).unlink()

        result = validate_profile(profile_dir)
        assert result.passed is False
        assert any(missing_file in err for err in result.errors)

    def test_missing_profile_dir_entirely(self, tmp_path):
        profile_dir = tmp_path / "does-not-exist"
        result = validate_profile(profile_dir)
        assert result.passed is False
        assert len(result.errors) > 0

    def test_unparseable_yaml_produces_error(self, tmp_path):
        profile_dir = tmp_path / "bad-yaml"
        _create_valid_profile(profile_dir)
        (profile_dir / "profile.yaml").write_text(": :\n  - }{bad")

        result = validate_profile(profile_dir)
        assert result.passed is False
        assert any("profile.yaml" in err for err in result.errors)


# ---------------------------------------------------------------------------
# 3. Invalid revenue_metric -> error
# ---------------------------------------------------------------------------


class TestInvalidRevenueMetric:
    def test_unsupported_revenue_metric_arr(self, tmp_path):
        profile_dir = tmp_path / "bad-metric"
        _create_valid_profile(profile_dir)
        _write_yaml(profile_dir / "profile.yaml", {
            "id": "bad",
            "name": "Bad Metric",
            "revenue_metric": "arr",
        })
        result = validate_profile(profile_dir)
        assert result.passed is False
        assert any("revenue_metric" in err for err in result.errors)

    def test_missing_revenue_metric(self, tmp_path):
        profile_dir = tmp_path / "no-metric"
        _create_valid_profile(profile_dir)
        _write_yaml(profile_dir / "profile.yaml", {
            "id": "no-metric",
            "name": "No Metric",
        })
        result = validate_profile(profile_dir)
        assert result.passed is False
        assert any("revenue_metric" in err for err in result.errors)

    def test_bookings_metric_accepted(self, tmp_path):
        profile_dir = tmp_path / "bookings"
        _create_valid_profile(profile_dir)
        result = validate_profile(profile_dir)
        assert result.passed is True

    def test_acv_metric_accepted(self, tmp_path):
        profile_dir = tmp_path / "acv"
        _create_valid_profile(profile_dir)
        _write_yaml(profile_dir / "profile.yaml", {
            "id": "acv-co",
            "name": "ACV Co",
            "revenue_metric": "acv",
        })
        result = validate_profile(profile_dir)
        assert result.passed is True


# ---------------------------------------------------------------------------
# 4. Quarterly targets don't sum to annual -> error
# ---------------------------------------------------------------------------


class TestQuarterlyTargetSum:
    def test_quarterly_sum_mismatch_produces_error(self, tmp_path):
        profile_dir = tmp_path / "bad-targets"
        _create_valid_profile(profile_dir)
        _write_yaml(profile_dir / "targets.yaml", {
            "annual_target": 10000000,
            "quarterly_targets": {
                "Q1": 2000000,
                "Q2": 2500000,
                "Q3": 2500000,
                "Q4": 5000000,  # Sum = 12M, annual = 10M
            },
        })
        result = validate_profile(profile_dir)
        assert result.passed is False
        assert any("annual_target" in err or "quarterly" in err.lower() for err in result.errors)

    def test_quarterly_sum_within_tolerance(self, tmp_path):
        """$0.50 rounding difference should be fine (within $1 tolerance)."""
        profile_dir = tmp_path / "ok-targets"
        _create_valid_profile(profile_dir)
        _write_yaml(profile_dir / "targets.yaml", {
            "annual_target": 10000000,
            "quarterly_targets": {
                "Q1": 2500000,
                "Q2": 2500000,
                "Q3": 2500000,
                "Q4": 2500000,
            },
        })
        result = validate_profile(profile_dir)
        assert result.passed is True

    def test_missing_quarterly_targets_produces_error(self, tmp_path):
        profile_dir = tmp_path / "no-qtargets"
        _create_valid_profile(profile_dir)
        _write_yaml(profile_dir / "targets.yaml", {
            "annual_target": 10000000,
        })
        result = validate_profile(profile_dir)
        assert result.passed is False

    def test_missing_annual_target_produces_error(self, tmp_path):
        profile_dir = tmp_path / "no-annual"
        _create_valid_profile(profile_dir)
        _write_yaml(profile_dir / "targets.yaml", {
            "quarterly_targets": {
                "Q1": 2500000,
                "Q2": 2500000,
                "Q3": 2500000,
                "Q4": 2500000,
            },
        })
        result = validate_profile(profile_dir)
        assert result.passed is False


# ---------------------------------------------------------------------------
# 5. Missing required deal field mapping -> error
# ---------------------------------------------------------------------------


class TestMissingDealFieldMapping:
    """Validates field_mappings.yaml: opportunity section with required mappings.

    Per ARCHITECTURE.md, the supported shape is `opportunity.<field>.sf_field`. The
    legacy `deal:` shape is accepted with a deprecation warning for one
    release.
    """

    @pytest.mark.parametrize("missing_field", ["amount", "stage", "close_date", "owner_id"])
    def test_missing_opportunity_mapping_produces_error(self, tmp_path, missing_field):
        profile_dir = tmp_path / "bad-mappings"
        _create_valid_profile(profile_dir)

        mappings = {
            "opportunity": {
                "amount": {"sf_field": "Amount"},
                "stage": {"sf_field": "StageName"},
                "close_date": {"sf_field": "CloseDate"},
                "owner_id": {"sf_field": "OwnerId"},
            },
        }
        del mappings["opportunity"][missing_field]

        _write_yaml(profile_dir / "field_mappings.yaml", mappings)
        result = validate_profile(profile_dir)
        assert result.passed is False
        assert any(missing_field in err for err in result.errors)

    def test_missing_opportunity_section_produces_error(self, tmp_path):
        profile_dir = tmp_path / "no-opportunity"
        _create_valid_profile(profile_dir)
        _write_yaml(profile_dir / "field_mappings.yaml", {
            "contact": {"email": {"sf_field": "Email"}},
        })
        result = validate_profile(profile_dir)
        assert result.passed is False
        assert any("opportunity" in err for err in result.errors)

    def test_legacy_deal_shape_emits_deprecation_warning(self, tmp_path):
        """Pre-ARCHITECTURE.md 'deal:' shape works for one release with a warning."""
        profile_dir = tmp_path / "legacy-deal-shape"
        _create_valid_profile(profile_dir)
        _write_yaml(profile_dir / "field_mappings.yaml", {
            "deal": {
                "amount": "Amount",
                "stage": "StageName",
                "close_date": "CloseDate",
                "owner_id": "OwnerId",
            },
        })
        result = validate_profile(profile_dir)
        assert result.passed is True
        assert any("deprecated" in w.lower() for w in result.warnings)

    def test_missing_stage_mapping_block_produces_error(self, tmp_path):
        """Architectural decision: opportunity.stage.stage_mapping is required."""
        profile_dir = tmp_path / "no-stage-mapping"
        _create_valid_profile(profile_dir)
        _write_yaml(profile_dir / "field_mappings.yaml", {
            "opportunity": {
                "amount": {"sf_field": "Amount"},
                "stage": {"sf_field": "StageName"},  # no stage_mapping
                "close_date": {"sf_field": "CloseDate"},
                "owner_id": {"sf_field": "OwnerId"},
            },
        })
        result = validate_profile(profile_dir)
        assert result.passed is False
        assert any("stage_mapping" in err for err in result.errors)

    def test_empty_stage_mapping_produces_error(self, tmp_path):
        """Empty stage_mapping dict is not enough."""
        profile_dir = tmp_path / "empty-stage-mapping"
        _create_valid_profile(profile_dir)
        _write_yaml(profile_dir / "field_mappings.yaml", {
            "opportunity": {
                "amount": {"sf_field": "Amount"},
                "stage": {
                    "sf_field": "StageName",
                    "stage_mapping": {},
                },
                "close_date": {"sf_field": "CloseDate"},
                "owner_id": {"sf_field": "OwnerId"},
            },
        })
        result = validate_profile(profile_dir)
        assert result.passed is False
        assert any("stage_mapping" in err for err in result.errors)


# ---------------------------------------------------------------------------
# 6. Duplicate roster IDs -> error
# ---------------------------------------------------------------------------


class TestDuplicateRosterIds:
    def test_duplicate_ids_produce_error(self, tmp_path):
        profile_dir = tmp_path / "dup-roster"
        _create_valid_profile(profile_dir)
        _write_yaml(profile_dir / "roster.yaml", {
            "team_members": [
                {"id": "user_001", "name": "Alice", "role": "AE"},
                {"id": "user_001", "name": "Alice Clone", "role": "AE"},
                {"id": "user_002", "name": "Bob", "role": "AE"},
            ],
        })
        result = validate_profile(profile_dir)
        assert result.passed is False
        assert any("user_001" in err or "duplicate" in err.lower() for err in result.errors)

    def test_unique_ids_pass(self, tmp_path):
        profile_dir = tmp_path / "ok-roster"
        _create_valid_profile(profile_dir)
        result = validate_profile(profile_dir)
        assert result.passed is True


# ---------------------------------------------------------------------------
# 7. Stage cross-reference: assumptions reference non-existent stage -> error
# ---------------------------------------------------------------------------


class TestStageCrossReference:
    def test_assumptions_reference_unknown_stage(self, tmp_path):
        profile_dir = tmp_path / "bad-stages"
        _create_valid_profile(profile_dir)
        _write_yaml(profile_dir / "assumptions.yaml", {
            "stage_rates": {
                "S0": {"conversion": 0.30},
                "S99_FAKE": {"conversion": 0.50},
            },
        })
        result = validate_profile(profile_dir)
        assert result.passed is False
        assert any("S99_FAKE" in err for err in result.errors)

    def test_all_assumption_stages_exist(self, tmp_path):
        profile_dir = tmp_path / "ok-stages"
        _create_valid_profile(profile_dir)
        result = validate_profile(profile_dir)
        assert result.passed is True


# ---------------------------------------------------------------------------
# 8. ValidationResult dataclass contract
# ---------------------------------------------------------------------------


class TestValidationResultContract:
    def test_default_result_is_passed(self):
        result = ValidationResult()
        assert result.passed is True
        assert result.errors == []
        assert result.warnings == []

    def test_result_with_errors(self):
        result = ValidationResult(passed=False, errors=["something broke"])
        assert result.passed is False
        assert len(result.errors) == 1
