"""Org-profile contracts for Forecast Tieout config resolution.

This module turns the current repo-specific config bundle into an explicit
profile that can later be swapped per customer/org without rewriting the
engine. The initial profile still points at the existing config files.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

# profile.py lives at gtm_model/tieout/runtime/profile.py — repo root is 4 levels up
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DEFAULT_CONFIG_DIR = _REPO_ROOT / "config"
_DEFAULT_PROFILE_ID = "default"

_RESOURCE_ALIASES = {
    "assumptions": "assumptions",
    "assumptions.yaml": "assumptions",
    "targets": "targets",
    "fy_targets.yaml": "targets",
    "roster": "roster",
    "roster.yaml": "roster",
    "field_mappings": "field_mappings",
    "field_mappings.yaml": "field_mappings",
    "bowtie_stages": "bowtie_stages",
    "bowtie_stages.yaml": "bowtie_stages",
    "slip_rates": "slip_rates",
    "slip_rates.yaml": "slip_rates",
}


@dataclass
class OrgProfileResources:
    """Logical config resources required by the engine."""

    assumptions: str = "assumptions.yaml"
    targets: str = "targets.yaml"
    roster: str = "roster.yaml"
    field_mappings: str = "field_mappings.yaml"
    bowtie_stages: str = "bowtie_stages.yaml"
    slip_rates: str = "slip_rates.yaml"

    def resolve(self, resource: str) -> str:
        key = _RESOURCE_ALIASES.get(resource, resource)
        if hasattr(self, key):
            return str(getattr(self, key))
        return str(resource)


@dataclass
class OrgConnectorPolicy:
    """Connector and fallback expectations for an org."""

    crm: str = "CSV"
    warehouse: str = "CSV"
    fallback_order: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class OrgProfileDataAssets:
    """Static frontend asset locations for an org profile."""

    snapshot: str = "./snapshot.json"
    plan_manifest: str = "./plans/index.json"


@dataclass
class OrgProfileBundleStore:
    """How backend services should read profile-scoped frontend bundles."""

    kind: str = "local"
    base_url: str = ""
    cache_dir: str = ""


@dataclass
class OrgTimingSemantics:
    """Timing semantics surfaced on frontend trust pages."""

    wins: str = "CloseDate"
    losses: str = "Closed At"
    pipeline_actuals: str = "First S2 entry"


@dataclass
class OrgProfileTrust:
    """Finance/trust metadata surfaced in the frontend."""

    finance_motion: str = "Sales-led"
    timing_semantics: OrgTimingSemantics = field(default_factory=OrgTimingSemantics)


@dataclass
class OrgProfile:
    """Profile manifest loaded from config/profiles/<id>/profile.yaml."""

    id: str
    slug: str
    name: str
    description: str
    version: int
    config_dir: Path
    manifest_path: Optional[Path]
    resources: OrgProfileResources
    connectors: OrgConnectorPolicy
    data: OrgProfileDataAssets
    bundle_store: OrgProfileBundleStore
    trust: OrgProfileTrust
    metadata: dict[str, Any] = field(default_factory=dict)
    # Architectural decision: declarative backend selection. None when profile uses the
    # legacy `connector` + `data_dir` fields and hasn't migrated yet.
    data_access: Optional[dict] = None

    def resolve_resource_location(self, resource: str) -> str:
        return self.resources.resolve(resource)

    def build_backend(self):
        """Construct the ProfileBackend from this profile's data_access block.

        Returns None if the profile hasn't declared data_access (legacy mode).
        Raises if data_access is declared but malformed.
        """
        if not self.data_access:
            return None
        from engine.profile_backend import build_backend

        field_mapping_path = self.resolve_resource_path("field_mappings.yaml")
        if not field_mapping_path.exists():
            field_mapping_path = None
        return build_backend(
            self.data_access,
            field_mapping_path=field_mapping_path,
        )

    def resolve_resource_path(self, resource: str) -> Path:
        location = self.resolve_resource_location(resource)
        path = Path(location).expanduser()
        if path.is_absolute():
            return path
        # Prefer per-profile subdir if it exists, fall back to the config root.
        # This lets profile YAML files keep simple `targets.yaml` resource refs
        # while actually living under `<config_dir>/profiles/<id>/targets.yaml`.
        per_profile = (self.config_dir / "profiles" / self.id / path).resolve()
        if per_profile.exists():
            return per_profile
        return (self.config_dir / path).resolve()


def get_default_config_dir() -> Path:
    override = os.getenv("GTM_TIEOUT_CONFIG_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return _DEFAULT_CONFIG_DIR


def get_active_profile_id(profile_id: Optional[str] = None) -> str:
    """Resolve the active org profile id from args/env/defaults."""
    explicit = str(profile_id or "").strip()
    if explicit:
        return explicit

    for env_key in ("GTM_TIEOUT_PROFILE_ID", "GTM_TIEOUT_PROFILE"):
        value = str(os.getenv(env_key, "")).strip()
        if value:
            return value

    return _DEFAULT_PROFILE_ID


def get_profile_manifest_path(
    config_dir: Optional[Path] = None,
    profile_id: Optional[str] = None,
) -> Path:
    """Return the manifest path for a profile, whether or not it exists."""
    cfg_dir = Path(config_dir or get_default_config_dir()).expanduser().resolve()
    active_profile = get_active_profile_id(profile_id)
    return cfg_dir / "profiles" / active_profile / "profile.yaml"


def load_org_profile(
    config_dir: Optional[Path] = None,
    profile_id: Optional[str] = None,
) -> OrgProfile:
    """Load the active org profile manifest, or synthesize the legacy default."""
    cfg_dir = Path(config_dir or get_default_config_dir()).expanduser().resolve()
    manifest_path = get_profile_manifest_path(cfg_dir, profile_id)
    active_profile = get_active_profile_id(profile_id)

    raw: dict[str, Any] = {}
    if manifest_path.exists():
        loaded = yaml.safe_load(manifest_path.read_text()) or {}
        if isinstance(loaded, dict):
            raw = loaded

    resources = OrgProfileResources(**(raw.get("resources") or {}))
    connectors = OrgConnectorPolicy(**(raw.get("connectors") or {}))
    trust_raw = dict(raw.get("trust") or {})
    timing_semantics = OrgTimingSemantics(**(trust_raw.get("timing_semantics") or {}))
    trust = OrgProfileTrust(
        finance_motion=str(trust_raw.get("finance_motion") or OrgProfileTrust().finance_motion),
        timing_semantics=timing_semantics,
    )
    profile_slug = str(raw.get("slug") or active_profile)
    data_raw = dict(raw.get("data") or {})
    data = OrgProfileDataAssets(
        snapshot=str(data_raw.get("snapshot") or f"./{profile_slug}/snapshot.json"),
        plan_manifest=str(data_raw.get("plan_manifest") or f"./{profile_slug}/plans/index.json"),
    )
    bundle_store_raw = dict(data_raw.get("bundle_store") or {})
    bundle_store = OrgProfileBundleStore(
        kind=str(bundle_store_raw.get("kind") or "local"),
        base_url=str(bundle_store_raw.get("base_url") or ""),
        cache_dir=str(bundle_store_raw.get("cache_dir") or ""),
    )

    data_access_raw = raw.get("data_access")
    data_access = (
        dict(data_access_raw) if isinstance(data_access_raw, dict) else None
    )

    return OrgProfile(
        id=str(raw.get("id") or active_profile),
        slug=str(raw.get("slug") or active_profile),
        name=str(raw.get("name") or raw.get("org_name") or active_profile.replace("-", " ").title()),
        description=str(raw.get("description") or ""),
        version=int(raw.get("version") or 1),
        config_dir=cfg_dir,
        manifest_path=manifest_path if manifest_path.exists() else None,
        resources=resources,
        connectors=connectors,
        data=data,
        bundle_store=bundle_store,
        trust=trust,
        metadata=dict(raw.get("metadata") or {}),
        data_access=data_access,
    )


def list_org_profiles(config_dir: Optional[Path] = None) -> list[OrgProfile]:
    """Load all manifest-backed profiles, or synthesize the active default."""
    cfg_dir = Path(config_dir or get_default_config_dir()).expanduser().resolve()
    profiles_dir = cfg_dir / "profiles"
    manifest_paths = sorted(profiles_dir.glob("*/profile.yaml"))
    if manifest_paths:
        return [load_org_profile(config_dir=cfg_dir, profile_id=path.parent.name) for path in manifest_paths]
    return [load_org_profile(config_dir=cfg_dir, profile_id=get_active_profile_id())]


def frontend_profile_filename(profile: OrgProfile) -> str:
    slug = str(profile.slug or profile.id or "profile").strip()
    return f"{slug}.json"


def resolve_frontend_profile_data_path(
    output_dir: Path,
    profile: OrgProfile,
    relative_location: str,
) -> Path:
    """Resolve a frontend data asset path relative to a generated profile payload."""
    profile_payload_path = Path(output_dir).expanduser().resolve() / frontend_profile_filename(profile)
    location = Path(relative_location).expanduser()
    if location.is_absolute():
        return location
    return (profile_payload_path.parent / location).resolve()


def build_frontend_org_profile_payload(profile: OrgProfile) -> dict[str, Any]:
    """Serialize a backend org profile into the frontend JSON contract."""
    return {
        "id": profile.id,
        "slug": profile.slug,
        "name": profile.name,
        "description": profile.description,
        "version": profile.version,
        "data": {
            "snapshot": profile.data.snapshot,
            "plan_manifest": profile.data.plan_manifest,
        },
        "connectors": {
            "crm": profile.connectors.crm,
            "warehouse": profile.connectors.warehouse,
            "fallback_order": dict(profile.connectors.fallback_order or {}),
        },
        "metadata": dict(profile.metadata or {}),
        "trust": {
            "finance_motion": profile.trust.finance_motion,
            "timing_semantics": {
                "wins": profile.trust.timing_semantics.wins,
                "losses": profile.trust.timing_semantics.losses,
                "pipeline_actuals": profile.trust.timing_semantics.pipeline_actuals,
            },
        },
    }


def build_frontend_org_profile_manifest(profiles: list[OrgProfile]) -> dict[str, list[dict[str, str]]]:
    """Build the frontend profile index manifest."""
    return {
        "profiles": [
            {
                "id": profile.id,
                "path": f"./{frontend_profile_filename(profile)}",
            }
            for profile in profiles
        ]
    }


def write_frontend_org_profile_assets(
    output_dir: Path,
    config_dir: Optional[Path] = None,
    indent: int = 2,
) -> list[Path]:
    """Write frontend profile assets from canonical backend manifests."""
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    indent_value = indent if indent > 0 else None

    profiles = list_org_profiles(config_dir=config_dir)
    kept_files = {"index.json"}
    written_paths: list[Path] = []

    manifest_payload = build_frontend_org_profile_manifest(profiles)
    manifest_path = output_dir / "index.json"
    manifest_path.write_text(json.dumps(manifest_payload, indent=indent_value) + "\n", encoding="utf-8")
    written_paths.append(manifest_path)

    for profile in profiles:
        filename = frontend_profile_filename(profile)
        kept_files.add(filename)
        payload_path = output_dir / filename
        payload_path.write_text(
            json.dumps(build_frontend_org_profile_payload(profile), indent=indent_value) + "\n",
            encoding="utf-8",
        )
        written_paths.append(payload_path)

    for existing in output_dir.glob("*.json"):
        if existing.name not in kept_files:
            existing.unlink()

    return written_paths


def write_frontend_profile_bundle_assets(
    output_dir: Path,
    config_dir: Optional[Path] = None,
    indent: int = 2,
) -> list[Path]:
    """Write frontend profile payloads plus any profile-scoped data bundles."""
    from gtm_model.tieout.infra.plan_config import write_frontend_plan_assets

    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    written_paths = write_frontend_org_profile_assets(output_dir, config_dir=config_dir, indent=indent)
    profiles = list_org_profiles(config_dir=config_dir)
    for profile in profiles:
        plan_manifest_path = resolve_frontend_profile_data_path(
            output_dir,
            profile,
            profile.data.plan_manifest,
        )
        written_paths.extend(
            write_frontend_plan_assets(
                plan_manifest_path.parent,
                config_dir=config_dir,
                profile_id=profile.id,
                indent=indent,
            )
        )

    return written_paths


def resolve_profile_resource_location(
    resource: str,
    config_dir: Optional[Path] = None,
    profile_id: Optional[str] = None,
) -> str:
    """Return the config-root-relative resource location for the active profile."""
    return load_org_profile(config_dir=config_dir, profile_id=profile_id).resolve_resource_location(resource)


def resolve_profile_resource_path(
    resource: str,
    config_dir: Optional[Path] = None,
    profile_id: Optional[str] = None,
) -> Path:
    """Return the fully resolved filesystem path for a profile resource."""
    return load_org_profile(config_dir=config_dir, profile_id=profile_id).resolve_resource_path(resource)
