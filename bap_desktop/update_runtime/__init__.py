"""Versioned Desktop installation, launcher, and rollback support."""

from bap_desktop.update_runtime.models import (
    ActiveReleaseState,
    OperationJournal,
    ReleaseManifest,
    UpdatePaths,
    atomic_write_json,
)

__all__ = [
    "ActiveReleaseState",
    "OperationJournal",
    "ReleaseManifest",
    "UpdatePaths",
    "atomic_write_json",
]
