"""Adapter factory: build_backend(data_access_config, profile) -> ProfileBackend.

Per ARCHITECTURE.md, profile.yaml declares a `data_access` block:

    data_access:
      type: csv | snowflake | salesforce | <forker-defined>
      params:
        path: engine/data/acme-saas    # for csv (repo-root-relative)
        warehouse: prod_dw             # for snowflake
        instance_url: ...              # for salesforce

The factory resolves the type to a registered backend and instantiates it
with the params + the profile's resolved field_mappings.yaml path.

Forkers register custom backend types via `register_backend("type", builder_fn)`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from engine.profile_backend.protocol import ProfileBackend


# Type for backend builder functions:
#   (params: dict, field_mapping_path: Optional[Path]) -> ProfileBackend
BackendBuilder = Callable[[dict, Optional[Path]], ProfileBackend]


_REGISTRY: dict[str, BackendBuilder] = {}


def register_backend(type_name: str, builder: BackendBuilder) -> None:
    """Register a backend builder for a given type string.

    Forkers call this to add custom backend types. Standard backends
    (csv / snowflake / salesforce) are registered by this module on
    import.

    Args:
        type_name: The string used in profile.yaml's data_access.type
        builder: Callable that takes (params_dict, field_mapping_path)
            and returns a ProfileBackend instance.
    """
    _REGISTRY[type_name] = builder


def build_backend(
    data_access_config: dict,
    field_mapping_path: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> ProfileBackend:
    """Construct a ProfileBackend from a profile.yaml's data_access block.

    Args:
        data_access_config: The {type, params} dict from profile.yaml.
        field_mapping_path: Resolved path to field_mappings.yaml. Per
            ARCHITECTURE.md, connectors apply stage normalization at this path.
        repo_root: Used to resolve relative CSV paths per ARCHITECTURE.md.
            Defaults to the repository root inferred from this file's
            location (engine/profile_backend/factory.py → up 3 dirs).

    Returns:
        A ProfileBackend instance ready for the engine to consume.

    Raises:
        ValueError: if the type is unknown (lists registered types).
        KeyError: if required params are missing for the chosen type.
    """
    if not isinstance(data_access_config, dict):
        raise ValueError(
            "data_access must be a dict with 'type' and 'params' fields"
        )
    type_name = data_access_config.get("type")
    if not type_name:
        raise ValueError(
            "data_access.type is required. Registered types: "
            f"{sorted(_REGISTRY.keys())}"
        )
    builder = _REGISTRY.get(type_name)
    if builder is None:
        raise ValueError(
            f"Unknown data_access.type {type_name!r}. Registered types: "
            f"{sorted(_REGISTRY.keys())}. Forkers can add custom types via "
            f"engine.profile_backend.register_backend()."
        )
    params = dict(data_access_config.get("params") or {})

    # Resolve relative CSV paths Per ARCHITECTURE.md (repo-root-relative)
    if "path" in params and not Path(params["path"]).is_absolute():
        params["path"] = str(_resolve_relative(params["path"], repo_root))

    return builder(params, field_mapping_path)


def _resolve_relative(rel_path: str, repo_root: Optional[Path]) -> Path:
    """Resolve a relative path per ARCHITECTURE.md."""
    base = repo_root or _infer_repo_root()
    return (base / rel_path).resolve()


def _infer_repo_root() -> Path:
    """engine/profile_backend/factory.py → up 3 dirs to repo root."""
    return Path(__file__).resolve().parents[2]


# ── Default backend registrations ─────────────────────────────────


def _build_csv(params: dict, field_mapping_path: Optional[Path]) -> ProfileBackend:
    from engine.profile_backend.csv_backend import CSVBackend

    if "path" not in params:
        raise KeyError("CSV backend requires data_access.params.path")
    return CSVBackend(
        data_dir=params["path"],
        field_mapping_path=field_mapping_path,
    )


# Salesforce / Snowflake are extension points: implement
# ConnectorInterface for your source, subclass ProfileBackendBase if you
# want source-specific compute_* fast paths, and register a builder via
# `register_backend("salesforce" | "snowflake" | "your-source", builder)`.
# See ARCHITECTURE.md.


register_backend("csv", _build_csv)
