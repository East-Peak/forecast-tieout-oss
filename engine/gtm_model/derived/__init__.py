"""Derived analytics — pure functions of raw connector data.

Per ARCHITECTURE.md (Concern B), these modules compute engine-needed analytics
from raw `list[Deal]` / `list[TeamMember]` / `list[StageTransition]` input.
No I/O, no source branching: the math is the same regardless of where the
underlying records came from.

Source-specific optimization (e.g. a warehouse backend pre-aggregating via
SQL) is the backend's responsibility, not the derived module's. Backends
override the relevant `compute_*` method on `ProfileBackend` and use the
SQL fast path when available; otherwise they call into these pure
functions with raw data.

Each module's docstring documents its current contract.
"""
