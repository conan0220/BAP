"""Content validation for Backend and deployment-script ZIP artifacts."""

from __future__ import annotations

import json
from pathlib import PurePosixPath
from zipfile import ZipFile

from bap_backend.deployment.manifest import DeploymentManifest


BACKEND_ROOTS = {
    "bap_backend",
    "bap_common",
    "migrations",
    "alembic.ini",
    "pyproject.toml",
    "uv.lock",
    ".python-version",
    "deployment-manifest.json",
}
SCRIPT_ROOTS = {"deployment-manifest.json"}
SENSITIVE_PARTS = {
    ".env",
    ".venv",
    "__pycache__",
    "data",
    "logs",
    "backups",
    "tests",
    "bap_desktop",
    "private_key",
    "id_rsa",
    "id_ed25519",
}


def validate_zip(path, *, component: str, expected_sha: str | None = None) -> DeploymentManifest:
    allowed_roots = BACKEND_ROOTS if component == "backend" else SCRIPT_ROOTS
    with ZipFile(path) as archive:
        members = archive.namelist()
        for name in members:
            member = PurePosixPath(name.replace("\\", "/"))
            if member.is_absolute() or ".." in member.parts or not member.parts:
                raise ValueError("artifact contains an unsafe path")
            lowered = {part.lower() for part in member.parts}
            if lowered & SENSITIVE_PARTS:
                raise ValueError("artifact contains a forbidden path")
            root = member.parts[0]
            if component == "backend" and root not in allowed_roots:
                raise ValueError(f"unexpected Backend artifact path: {root}")
            if component == "deployment-scripts" and root != "deployment-manifest.json" and not root.endswith(".ps1"):
                raise ValueError(f"unexpected deployment script artifact path: {root}")
        if "deployment-manifest.json" not in members:
            raise ValueError("artifact is missing deployment-manifest.json")
        manifest = DeploymentManifest.model_validate(
            json.loads(archive.read("deployment-manifest.json").decode("utf-8-sig"))
        )
    if manifest.component != component:
        raise ValueError("artifact component does not match")
    if expected_sha and manifest.commit_sha != expected_sha.lower():
        raise ValueError("artifact commit SHA does not match")
    return manifest

