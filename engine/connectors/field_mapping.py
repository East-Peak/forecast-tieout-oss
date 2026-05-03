"""
Field mapping utilities for GTM Intelligence Platform.

Translates between Salesforce field names and GTM Model concepts.
"""

from pathlib import Path
from typing import Optional
import yaml

from gtm_model.tieout.runtime.env import resolve_config_resource_path


# Stage mapping: SF StageName -> Model Stage
# Default stage mapping — override via field_mappings.yaml in your profile
SF_TO_MODEL_STAGE = {
    # New business stages (current Salesforce names)
    "0 - Research": "S0",
    "0 - Interested": "S0",  # Legacy name
    "1 - Discovery": "S1",
    "01 Discovery": "S1",  # Older legacy name
    "2 - Scope": "S2",
    "02 Qualification": "S2",  # Older legacy name
    "2 - Technical Fit": "S2",  # Legacy name
    "3 - Tech Validation": "S3",
    "03 POC Pre-Reqs": "S3",  # Older legacy name
    "3 - Business Case": "S3",  # Legacy name
    "4 - Business Case Alignment": "S4",
    "04 POC": "S4",  # Older legacy name
    "4 - Business Case": "S4",  # Legacy name
    "4 - Negotiation": "S4",  # Legacy name
    "5 - Vendor of Choice": "S5",
    "05 Procurement": "S5",  # Older legacy name
    "5 - Verbal Commit": "S5",  # Legacy name
    "Negotiation": "S5",  # Alternate name
    "Closed Won": "Won",
    "Closed Lost": "Lost",
    # Renewal stages (map to separate category)
    "R1 - Renewal Tracking": "Renewal",
    "R2 - Early Engagement": "Renewal",
}

# Reverse mapping: Model Stage -> SF StageName
MODEL_TO_SF_STAGE = {v: k for k, v in SF_TO_MODEL_STAGE.items()}

# Stage probabilities for weighted pipeline
STAGE_PROBABILITIES = {
    "S0": 0.10,
    "S1": 0.20,
    "S2": 0.40,
    "S3": 0.60,
    "S4": 0.80,
    "S5": 0.90,
    "Won": 1.00,
    "Lost": 0.00,
}

# Stages considered "pipeline" for coverage calculation
PIPELINE_STAGES = ["S2", "S3", "S4", "S5"]


def get_stage_mapping(sf_stage: str) -> str:
    """
    Convert SF stage name to model stage.

    Args:
        sf_stage: Salesforce StageName value

    Returns:
        Model stage (S0-S5, Won, Lost)
    """
    return SF_TO_MODEL_STAGE.get(sf_stage, sf_stage)


def get_stage_probability(model_stage: str) -> float:
    """
    Get probability weight for a model stage.

    Args:
        model_stage: Model stage (S0-S5)

    Returns:
        Probability as decimal (0.0 - 1.0)
    """
    return STAGE_PROBABILITIES.get(model_stage, 0.0)


def is_pipeline_stage(model_stage: str) -> bool:
    """Check if stage counts as pipeline for coverage calculation."""
    return model_stage in PIPELINE_STAGES


def calculate_weighted_arr(arr: float, model_stage: str) -> float:
    """
    Calculate weighted ARR based on stage probability.

    Args:
        arr: Raw ARR value
        model_stage: Model stage (S0-S5)

    Returns:
        Weighted ARR value
    """
    probability = get_stage_probability(model_stage)
    return arr * probability


class FieldMapper:
    """
    Maps between Salesforce fields and GTM Model concepts.

    Loads mappings from config/field_mappings.yaml.
    """

    def __init__(self, config_path: Optional[Path] = None, profile_id: Optional[str] = None):
        """
        Initialize field mapper.

        Args:
            config_path: Path to field_mappings.yaml (uses default if not specified)
        """
        if config_path is None:
            config_path = resolve_config_resource_path(
                "field_mappings.yaml",
                profile_id=profile_id,
            )

        self.config_path = Path(config_path)
        self._mappings = None

    @property
    def mappings(self) -> dict:
        """Lazy load mappings from YAML."""
        if self._mappings is None:
            self._mappings = self._load_mappings()
        return self._mappings

    def _load_mappings(self) -> dict:
        """Load field mappings from YAML config."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Field mappings not found: {self.config_path}")

        with open(self.config_path) as f:
            return yaml.safe_load(f)

    def get_sf_field(self, object_name: str, model_field: str) -> Optional[str]:
        """
        Get Salesforce field name for a model concept.

        Args:
            object_name: SF object (opportunity, lead, contact, account)
            model_field: Model field name (e.g., 'arr', 'mql_date')

        Returns:
            SF API field name or None if not mapped
        """
        object_mappings = self.mappings.get(object_name.lower(), {})
        field_mapping = object_mappings.get(model_field, {})
        return field_mapping.get("sf_field")

    def get_query(self, query_name: str, **params) -> str:
        """
        Get a pre-built SOQL query from config.

        Args:
            query_name: Name of query template (e.g., 'pipeline_by_stage')
            **params: Parameters to substitute in query

        Returns:
            SOQL query string with parameters substituted
        """
        queries = self.mappings.get("queries", {})
        query_template = queries.get(query_name)

        if query_template is None:
            raise ValueError(f"Query not found: {query_name}")

        # Substitute parameters
        return query_template.format(**params)

    def field_exists(self, object_name: str, model_field: str) -> bool:
        """
        Check if a field is confirmed to exist in Salesforce.

        Args:
            object_name: SF object
            model_field: Model field name

        Returns:
            True if field exists (or not marked as missing)
        """
        object_mappings = self.mappings.get(object_name.lower(), {})
        field_mapping = object_mappings.get(model_field, {})
        # Fields are assumed to exist unless explicitly marked as not existing
        return field_mapping.get("exists", True)

    def get_stage_mapping(self) -> dict:
        """Get the stage mapping from config."""
        opp_mappings = self.mappings.get("opportunity", {})
        stage_mapping = opp_mappings.get("stage", {})
        return stage_mapping.get("stage_mapping", SF_TO_MODEL_STAGE)

    def translate_stage(self, sf_stage: str) -> str:
        """
        Translate SF stage to model stage.

        Args:
            sf_stage: Salesforce StageName value

        Returns:
            Model stage (S0-S5, Won, Lost)
        """
        mapping = self.get_stage_mapping()
        return mapping.get(sf_stage, sf_stage)


def create_pipeline_summary(opps_data: list[dict], mapper: Optional[FieldMapper] = None) -> dict:
    """
    Create a pipeline summary from opportunity data.

    Args:
        opps_data: List of opportunity records with StageName and ARR__c
        mapper: Optional field mapper (uses defaults if not provided)

    Returns:
        Dict with pipeline totals by stage and overall metrics
    """
    if mapper is None:
        mapper = FieldMapper()

    summary = {
        "by_stage": {},
        "total_pipeline": 0.0,
        "weighted_pipeline": 0.0,
        "s2_plus_pipeline": 0.0,
        "opp_count": len(opps_data),
    }

    for opp in opps_data:
        sf_stage = opp.get("StageName", "")
        arr = float(opp.get("ARR__c") or opp.get("Amount") or 0)

        model_stage = get_stage_mapping(sf_stage)

        # Initialize stage in summary if needed
        if model_stage not in summary["by_stage"]:
            summary["by_stage"][model_stage] = {
                "count": 0,
                "arr": 0.0,
                "weighted_arr": 0.0,
            }

        # Update stage totals
        summary["by_stage"][model_stage]["count"] += 1
        summary["by_stage"][model_stage]["arr"] += arr
        summary["by_stage"][model_stage]["weighted_arr"] += calculate_weighted_arr(arr, model_stage)

        # Update overall totals
        summary["total_pipeline"] += arr
        summary["weighted_pipeline"] += calculate_weighted_arr(arr, model_stage)

        if is_pipeline_stage(model_stage):
            summary["s2_plus_pipeline"] += arr

    return summary
