"""Backend delivery contracts, loaded lazily for dependency-free scope checks."""

from __future__ import annotations

from typing import Any


__all__ = ["ArtifactReference", "DeliveryManifest", "DeploymentManifest", "PromotionRecord"]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(name)
    from . import manifest

    return getattr(manifest, name)
