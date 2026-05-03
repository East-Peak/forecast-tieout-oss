"""Profiling helpers for Planning Tie-Out workflows."""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass, field
from io import BytesIO
from time import perf_counter
from typing import Any, Callable, Optional

from gtm_model.tieout.engine import PlanningTieout


DEFAULT_QUARTERLY_OVERRIDES = {
    "Q3FY26": {"s1_to_s2": 0.35},
    "Q4FY26": {"s1_to_s2": 0.35},
}


@dataclass(frozen=True)
class MethodTarget:
    """A bound callable to time during a higher-level operation."""

    obj: Any
    attr_name: str
    label: str


@dataclass
class PhaseTiming:
    """Timing details for one instrumented phase."""

    name: str
    elapsed_seconds: float = 0.0
    calls: int = 0


@dataclass
class OperationTiming:
    """Timing summary for one user-facing workflow."""

    name: str
    elapsed_seconds: float
    phases: list[PhaseTiming] = field(default_factory=list)


class _TimingCollector:
    """Accumulate elapsed time for instrumented method calls."""

    def __init__(self) -> None:
        self._phases: dict[str, PhaseTiming] = {}
        self._order: list[str] = []

    def record(self, label: str, elapsed_seconds: float) -> None:
        if label not in self._phases:
            self._phases[label] = PhaseTiming(name=label)
            self._order.append(label)
        phase = self._phases[label]
        phase.elapsed_seconds += elapsed_seconds
        phase.calls += 1

    def snapshot(self) -> list[PhaseTiming]:
        return [
            PhaseTiming(
                name=self._phases[label].name,
                elapsed_seconds=self._phases[label].elapsed_seconds,
                calls=self._phases[label].calls,
            )
            for label in self._order
        ]


def _wrap_method(target: MethodTarget, collector: _TimingCollector):
    """Temporarily wrap a bound method or callable attribute."""
    original = getattr(target.obj, target.attr_name)

    def wrapped(*args, **kwargs):
        start = perf_counter()
        try:
            return original(*args, **kwargs)
        finally:
            collector.record(target.label, perf_counter() - start)

    setattr(target.obj, target.attr_name, wrapped)

    def restore() -> None:
        setattr(target.obj, target.attr_name, original)

    return restore


def profile_operation(
    name: str,
    operation: Callable[[], Any],
    method_targets: Optional[list[MethodTarget]] = None,
) -> tuple[Any, OperationTiming]:
    """Time a callable and optional nested phases."""
    collector = _TimingCollector()
    method_targets = method_targets or []

    with ExitStack() as stack:
        for target in method_targets:
            stack.callback(_wrap_method(target, collector))

        started = perf_counter()
        value = operation()
        elapsed_seconds = perf_counter() - started

    return value, OperationTiming(
        name=name,
        elapsed_seconds=elapsed_seconds,
        phases=collector.snapshot(),
    )


def _default_tieout_factory(plan_case_id: Optional[str]) -> PlanningTieout:
    return PlanningTieout(plan_case_id=plan_case_id)


def _default_workbook_exporter(result: Any) -> BytesIO:
    from gtm_model.excel_export import export_tieout_workbook

    return export_tieout_workbook(result)


def profile_tieout_workflow(
    plan_case_id: Optional[str] = None,
    overflow_mode: str = "push",
    quarterly_overrides: Optional[dict] = None,
    tieout_factory: Optional[Callable[[Optional[str]], Any]] = None,
    workbook_exporter: Optional[Callable[[Any], Any]] = None,
) -> list[OperationTiming]:
    """Profile the main Planning Tie-Out workflows end to end."""
    tieout_factory = tieout_factory or _default_tieout_factory
    workbook_exporter = workbook_exporter or _default_workbook_exporter
    quarterly_overrides = quarterly_overrides or DEFAULT_QUARTERLY_OVERRIDES

    timings: list[OperationTiming] = []

    compute_tieout = tieout_factory(plan_case_id)
    result, compute_full_timing = profile_operation(
        "compute_full",
        lambda: compute_tieout.compute_full(overflow_mode=overflow_mode),
        method_targets=[
            MethodTarget(
                compute_tieout.public_api,
                "build_runtime_snapshot",
                "compute_full.build_runtime_snapshot",
            ),
            MethodTarget(compute_tieout.public_api, "compute_plan", "compute_full.compute_plan"),
            MethodTarget(compute_tieout.public_api, "compute_trajectory", "compute_full.compute_trajectory"),
            MethodTarget(compute_tieout.public_api, "run_health_checks", "compute_full.run_health_checks"),
            MethodTarget(
                compute_tieout.public_api,
                "get_beginning_arr_snapshot",
                "compute_full.get_beginning_arr_snapshot",
            ),
            MethodTarget(
                compute_tieout.public_api,
                "get_closed_won_finance_summary",
                "compute_full.get_closed_won_finance_summary",
            ),
            MethodTarget(
                compute_tieout.public_api,
                "get_observed_arr_movements",
                "compute_full.get_observed_arr_movements",
            ),
        ],
    )
    timings.append(compute_full_timing)

    flex_tieout = tieout_factory(plan_case_id)
    _, flex_timing = profile_operation(
        "flex",
        lambda: flex_tieout.flex(
            name="Profiler Flex",
            description="Profiler quarterly overrides",
            quarterly_overrides=quarterly_overrides,
            overflow_mode=overflow_mode,
        ),
        method_targets=[
            MethodTarget(flex_tieout.public_api, "compute_plan", "flex.compute_plan"),
            MethodTarget(flex_tieout.public_api, "compute_trajectory", "flex.compute_trajectory"),
        ],
    )
    timings.append(flex_timing)

    recommendations_tieout = tieout_factory(plan_case_id)
    _, recommendations_timing = profile_operation(
        "gap_closing_recommendations",
        lambda: recommendations_tieout.gap_closing_recommendations(overflow_mode=overflow_mode),
        method_targets=[
            MethodTarget(
                recommendations_tieout.recommendations,
                "compute_base",
                "gap_closing_recommendations.compute_base",
            ),
            MethodTarget(
                recommendations_tieout.recommendations,
                "flex_scenario",
                "gap_closing_recommendations.flex_scenario",
            ),
        ],
    )
    timings.append(recommendations_timing)

    _, export_timing = profile_operation(
        "export_tieout_workbook",
        lambda: workbook_exporter(result),
    )
    timings.append(export_timing)

    return timings


def format_timing_report(timings: list[OperationTiming]) -> str:
    """Format a compact human-readable timing table."""
    lines = [
        "Operation                          Seconds  Calls",
        "--------------------------------  -------  -----",
    ]
    for timing in timings:
        lines.append(f"{timing.name:<34} {timing.elapsed_seconds:>7.2f}  {'-':>5}")
        for phase in timing.phases:
            lines.append(f"  {phase.name:<32} {phase.elapsed_seconds:>7.2f}  {phase.calls:>5}")
    return "\n".join(lines)
