"""Artifact-store abstractions for profile-scoped frontend bundles.

The current app reads snapshots and plan manifests from local checked-in files.
This module introduces a small storage seam so the same scenario service can
later read bundles from a CDN, Blob store, or other HTTP-backed artifact host
without rewriting call sites.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from gtm_model.tieout.runtime.profile import _REPO_ROOT, OrgProfile


class ProfileBundleStore(Protocol):
    """Read-only access to profile bundle artifacts."""

    def resolve(self, relative_location: str) -> Path | str:
        ...

    def read_text(self, relative_location: str, encoding: str = "utf-8") -> tuple[str, Path | str]:
        ...


def _normalize_relative_location(relative_location: str) -> str:
    value = str(relative_location or "").strip()
    if not value:
        raise ValueError("Bundle artifact location cannot be empty")
    return value


@dataclass(frozen=True)
class LocalProfileBundleStore:
    root: Path

    def resolve(self, relative_location: str) -> Path:
        location = Path(_normalize_relative_location(relative_location)).expanduser()
        if location.is_absolute():
            return location
        return (self.root / location).resolve()

    def read_text(self, relative_location: str, encoding: str = "utf-8") -> tuple[str, Path]:
        resolved = self.resolve(relative_location)
        return resolved.read_text(encoding=encoding), resolved


@dataclass(frozen=True)
class HttpProfileBundleStore:
    base_url: str
    cache_dir: Path | None = None
    timeout_seconds: float = 15.0

    def resolve(self, relative_location: str) -> str:
        location = _normalize_relative_location(relative_location)
        base = self.base_url if self.base_url.endswith("/") else f"{self.base_url}/"
        return urljoin(base, location)

    def _cache_path_for_url(self, url: str) -> Path | None:
        if self.cache_dir is None:
            return None
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return (self.cache_dir / f"{digest}.json").resolve()

    def read_text(self, relative_location: str, encoding: str = "utf-8") -> tuple[str, str]:
        resolved = self.resolve(relative_location)
        cache_path = self._cache_path_for_url(resolved)
        if cache_path and cache_path.exists():
            return cache_path.read_text(encoding=encoding), resolved

        request = Request(resolved, headers={"Accept": "application/json"})
        with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310 - caller controls URL
            payload = response.read().decode(encoding)

        if cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(payload, encoding=encoding)

        return payload, resolved


def configured_bundle_cache_dir() -> Path | None:
    override = str(os.getenv("GTM_TIEOUT_FRONTEND_BUNDLE_CACHE_DIR", "")).strip()
    if override:
        return Path(override).expanduser().resolve()
    return None


def default_frontend_profile_data_root() -> Path:
    return (_REPO_ROOT / "frontend" / "public" / "data" / "profiles").resolve()


def resolve_profile_bundle_store(
    profile: OrgProfile,
    *,
    frontend_data_root: Path | None = None,
    frontend_data_base_url: str | None = None,
) -> ProfileBundleStore:
    """Return the read store for a profile bundle.

    Precedence:
    1. Explicit local root override
    2. Explicit base URL override
    3. Profile-declared HTTP bundle store
    4. Local filesystem bundle store rooted at the repo frontend data dir
    """
    if frontend_data_root is not None:
        return LocalProfileBundleStore(Path(frontend_data_root).expanduser().resolve())

    base_url = str(frontend_data_base_url or os.getenv("GTM_TIEOUT_FRONTEND_DATA_BASE_URL", "")).strip()
    if base_url:
        return HttpProfileBundleStore(base_url=base_url, cache_dir=configured_bundle_cache_dir())

    if str(profile.bundle_store.kind).strip().lower() == "http" and str(profile.bundle_store.base_url).strip():
        cache_dir = (
            Path(profile.bundle_store.cache_dir).expanduser().resolve()
            if str(profile.bundle_store.cache_dir).strip()
            else configured_bundle_cache_dir()
        )
        return HttpProfileBundleStore(
            base_url=profile.bundle_store.base_url,
            cache_dir=cache_dir,
        )

    return LocalProfileBundleStore(default_frontend_profile_data_root())
