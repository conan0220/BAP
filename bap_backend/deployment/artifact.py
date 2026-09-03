"""Content and checksum validation for BAP delivery artifacts."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from bap_backend.deployment.manifest import DeliveryManifest, DeploymentManifest


BACKEND_ROOTS = {
    "bap_backend",
    "bap_common",
    "migrations",
    "deployment",
    "alembic.ini",
    "pyproject.toml",
    "uv.lock",
    ".python-version",
    "deployment-manifest.json",
}
SENSITIVE_PARTS = {
    ".env", ".venv", "__pycache__", "data", "logs", "backups", "tests",
    "bap_desktop", "private_key", "id_rsa", "id_ed25519",
}


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_zip(
    path: str | Path,
    *,
    component: str = "backend",
    expected_sha: str | None = None,
    expected_source_tree_sha: str | None = None,
) -> DeploymentManifest:
    if component != "backend":
        raise ValueError("only the unified backend artifact is supported")
    with ZipFile(path) as archive:
        members = archive.namelist()
        for name in members:
            member = PurePosixPath(name.replace("\\", "/"))
            if member.is_absolute() or ".." in member.parts or not member.parts:
                raise ValueError("artifact contains an unsafe path")
            if {part.lower() for part in member.parts} & SENSITIVE_PARTS:
                raise ValueError("artifact contains a forbidden path")
            if member.parts[0] not in BACKEND_ROOTS:
                raise ValueError(f"unexpected Backend artifact path: {member.parts[0]}")
        if "deployment-manifest.json" not in members:
            raise ValueError("artifact is missing deployment-manifest.json")
        manifest = DeploymentManifest.model_validate(
            json.loads(archive.read("deployment-manifest.json").decode("utf-8-sig"))
        )
    if expected_sha and manifest.commit_sha != expected_sha.lower():
        raise ValueError("artifact commit SHA does not match")
    if expected_source_tree_sha and manifest.source_tree_sha != expected_source_tree_sha.lower():
        raise ValueError("artifact Source Tree SHA does not match")
    return manifest


def _validate_desktop_metadata(root: Path, manifest: DeliveryManifest) -> None:
    if manifest.desktop is None:
        return
    metadata_files = tuple(root.glob("BAP-Setup-*.metadata.json"))
    if len(metadata_files) != 1:
        raise ValueError("Candidate must contain exactly one Desktop metadata file")
    metadata = json.loads(metadata_files[0].read_text(encoding="utf-8-sig"))
    required = {"project", "component", "version", "source_tree_sha", "filename", "sha256"}
    if set(metadata) != required:
        raise ValueError("Desktop metadata schema is invalid")
    if metadata["project"] != "BAP" or metadata["component"] != "desktop":
        raise ValueError("Desktop metadata component is invalid")
    if metadata["source_tree_sha"] != manifest.source_tree_sha:
        raise ValueError("Desktop Source Tree SHA does not match Candidate")
    if metadata["filename"] != manifest.desktop.filename:
        raise ValueError("Desktop filename does not match Candidate")
    if metadata["sha256"] != manifest.desktop.sha256:
        raise ValueError("Desktop checksum does not match Candidate")


def validate_candidate(
    directory: str | Path,
    *,
    expected_source_tree_sha: str | None = None,
    expected_backend_changed: bool | None = None,
    expected_desktop_changed: bool | None = None,
) -> DeliveryManifest:
    root = Path(directory)
    manifest = DeliveryManifest.model_validate_json(
        (root / "delivery-manifest.json").read_text(encoding="utf-8-sig")
    )
    created_at = manifest.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    if datetime.now(UTC) - created_at.astimezone(UTC) > timedelta(days=14):
        raise ValueError("Candidate has expired")
    if expected_source_tree_sha and manifest.source_tree_sha != expected_source_tree_sha.lower():
        raise ValueError("Candidate Source Tree SHA does not match master")
    if expected_backend_changed is not None and manifest.backend_changed != expected_backend_changed:
        raise ValueError("Backend scope mismatch.")
    if expected_desktop_changed is not None and manifest.desktop_changed != expected_desktop_changed:
        raise ValueError("Desktop scope mismatch.")
    if manifest.docs_only:
        if manifest.backend_changed or manifest.desktop_changed or manifest.backend or manifest.desktop:
            raise ValueError("docs-only Candidate has an inconsistent scope")
    elif manifest.backend is None or manifest.desktop is None:
        raise ValueError("non-docs Candidate is missing a required artifact")
    for reference in (manifest.backend, manifest.desktop):
        if reference is None:
            continue
        path = root / reference.filename
        if not path.is_file():
            raise ValueError(f"Candidate file is missing: {reference.filename}")
        if sha256_file(path) != reference.sha256:
            raise ValueError(f"Candidate checksum does not match: {reference.filename}")
    if manifest.backend:
        validate_zip(root / manifest.backend.filename, expected_source_tree_sha=manifest.source_tree_sha)
    _validate_desktop_metadata(root, manifest)
    if not manifest.tests or any(result != "passed" for result in manifest.tests.values()):
        raise ValueError("Candidate is missing a passing required test")
    return manifest
