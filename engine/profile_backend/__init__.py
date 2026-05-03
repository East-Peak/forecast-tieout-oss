"""ProfileBackend abstraction — the wiring seam between engine and connector.

A ProfileBackend bundles:
- A ConnectorInterface (raw domain data)
- An EnvironmentHealth surface (default no-op)
- compute_* methods for derived analytics (default Python implementations
  from `engine.gtm_model.derived.*`)

A working CSVBackend ships as a reference. Add your own backend by
subclassing ProfileBackendBase and registering with the factory.
See ARCHITECTURE.md.
"""
from engine.profile_backend.protocol import (
    EnvironmentHealth,
    NoOpHealth,
    ProfileBackend,
    ProfileBackendBase,
)
from engine.profile_backend.factory import build_backend, register_backend

__all__ = [
    "EnvironmentHealth",
    "NoOpHealth",
    "ProfileBackend",
    "ProfileBackendBase",
    "build_backend",
    "register_backend",
]
