"""Top-down target extraction and derivation facade for Planning Tie-Out."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from gtm_model.tieout.targets.derivation import TieoutWeeklyTargetDeriver
from gtm_model.tieout.targets.rebalance import TieoutPipelineRebalancer


@dataclass
class TieoutTargetResolver:
    """Resolve configured and runtime-derived top-down targets."""

    quarters: list[str]
    get_targets: Callable[[], dict]
    get_assumptions: Callable[[], dict]
    get_runtime_funnel_rates: Callable[[], dict[str, float]]
    get_registered_funnel_rate: Callable[[str, float], float]
    weekly_targets: TieoutWeeklyTargetDeriver = field(init=False, repr=False)
    pipeline_rebalancer: TieoutPipelineRebalancer = field(init=False, repr=False)

    def __post_init__(self):
        self.weekly_targets = TieoutWeeklyTargetDeriver(
            quarters=self.quarters,
            get_targets=self.get_targets,
            get_assumptions=self.get_assumptions,
            get_runtime_funnel_rates=self.get_runtime_funnel_rates,
            get_td_quarter_cb=lambda quarter: self.get_td_quarter(quarter),
            get_source_mix_shares_cb=lambda quarter: self.get_source_mix_shares(quarter),
            allocate_integer_mix_cb=lambda total_count, allocations: self.allocate_integer_mix(
                total_count,
                allocations,
            ),
            resolve_s0_source_mix_cb=lambda quarter, td: self.resolve_s0_source_mix(quarter, td),
            get_config_conversion_rates_cb=lambda quarter, td: self.get_config_conversion_rates(
                quarter,
                td,
            ),
        )
        self.pipeline_rebalancer = TieoutPipelineRebalancer(
            get_registered_funnel_rate=self.get_registered_funnel_rate,
        )

    def default_target_provenance(self, quarter: str, wt: dict) -> dict:
        return self.weekly_targets.default_target_provenance(quarter, wt)

    def annotate_target_coherence(self, td: dict, provenance: dict) -> dict:
        return self.weekly_targets.annotate_target_coherence(td, provenance)

    @staticmethod
    def normalize_s1_pipeline_by_source(wt: dict) -> dict:
        return TieoutWeeklyTargetDeriver.normalize_s1_pipeline_by_source(wt)

    def get_td_quarter(self, quarter: str) -> dict:
        return self.weekly_targets.get_td_quarter(quarter)

    def get_source_mix_shares(self, quarter: str) -> dict:
        return self.weekly_targets.get_source_mix_shares(quarter)

    @staticmethod
    def allocate_integer_mix(total_count: int, allocations: list[tuple[str, float]]) -> dict:
        return TieoutWeeklyTargetDeriver.allocate_integer_mix(total_count, allocations)

    def resolve_s0_source_mix(self, quarter: str, td: dict) -> dict:
        return self.weekly_targets.resolve_s0_source_mix(quarter, td)

    def estimate_ae_selfgen_s0_weekly(self, td: dict) -> int:
        return self.weekly_targets.estimate_ae_selfgen_s0_weekly(td)

    def get_config_conversion_rates(self, quarter: str, td: dict) -> dict:
        return self.weekly_targets.get_config_conversion_rates(quarter, td)

    def latest_explicit_weekly_target_quarter(self, quarter: str) -> Optional[str]:
        return self.weekly_targets.latest_explicit_weekly_target_quarter(quarter)

    def derive_weekly_targets_from_pipeline_driver_tree(self, quarter: str, td: dict) -> Optional[dict]:
        return self.weekly_targets.derive_weekly_targets_from_pipeline_driver_tree(quarter, td)

    def derive_weekly_targets(self, quarter: str, td: dict) -> tuple[dict, bool]:
        return self.weekly_targets.derive_weekly_targets(quarter, td)

    def rebalance_projection_pipeline_values(self, projection: dict, td: dict) -> dict:
        return self.pipeline_rebalancer.rebalance_projection_pipeline_values(projection, td)
