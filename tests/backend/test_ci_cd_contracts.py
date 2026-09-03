from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zipfile import ZipFile

import pytest
from pydantic import ValidationError

from bap_backend.deployment.artifact import sha256_file, validate_candidate
from bap_backend.deployment.manifest import ArtifactReference, DeliveryManifest
from bap_backend.deployment.scope import ChangeScope, classify_paths
from bap_backend.tools.delivery_candidate import main as delivery_candidate_main


SHA_A = "a" * 40
SHA_B = "b" * 40
TREE = "c" * 40


@pytest.mark.parametrize(
    ("paths", "expected"),
    (
        (["docs/guide.md"], ChangeScope(True, False, False)),
        (["bap_backend/app/main.py"], ChangeScope(False, True, False)),
        (["bap_desktop/app.py"], ChangeScope(False, False, True)),
        (["bap_common/rules.py"], ChangeScope(False, True, True)),
        (["deployment/windows/backend/deploy.ps1"], ChangeScope(False, True, False)),
        (["tests/backend/test_deploy.py"], ChangeScope(False, True, False)),
        (["packaging/windows/build.ps1"], ChangeScope(False, False, True)),
        (["tests/desktop/test_app.py"], ChangeScope(False, False, True)),
        ([".github/workflows/ci.yml"], ChangeScope(False, True, True)),
    ),
)
@pytest.mark.scenario("component-delivery-routing", "CI 與 CD 必須使用同一套 Scope 規則")
def test_change_scope_fixtures(paths, expected) -> None:
    assert classify_paths(paths) == expected


def _manifest(backend: ArtifactReference, desktop: ArtifactReference) -> dict:
    return {
        "schema_version": 1,
        "project": "BAP",
        "pr_number": 12,
        "pr_head_sha": SHA_A,
        "pr_base_sha": SHA_B,
        "ci_test_commit_sha": SHA_A,
        "source_tree_sha": TREE,
        "ci_workflow_run_id": 99,
        "ci_workflow_url": "https://github.com/conan0220/BAP/actions/runs/99",
        "created_at": datetime.now(UTC).isoformat(),
        "docs_only": False,
        "backend_changed": True,
        "desktop_changed": True,
        "backend": backend.model_dump(),
        "desktop": desktop.model_dump(),
        "tests": {"backend_api": "passed", "desktop_e2e": "passed"},
    }


@pytest.mark.scenario("pull-request-ci", "Candidate 上傳成功")
def test_delivery_manifest_forbids_unknown_and_missing_fields(tmp_path) -> None:
    ref = ArtifactReference(filename="a.bin", sha256="0" * 64)
    DeliveryManifest.model_validate(_manifest(ref, ref))
    with pytest.raises(ValidationError):
        DeliveryManifest.model_validate({**_manifest(ref, ref), "secret": "no"})
    invalid = _manifest(ref, ref)
    invalid.pop("source_tree_sha")
    with pytest.raises(ValidationError):
        DeliveryManifest.model_validate(invalid)


def test_delivery_candidate_create_command_writes_a_strict_manifest(tmp_path) -> None:
    backend = tmp_path / f"bap-backend-tree-{TREE}.zip"
    desktop = tmp_path / "BAP-Setup-0.1.0.exe"
    output = tmp_path / "delivery-manifest.json"
    backend.write_bytes(b"backend")
    desktop.write_bytes(b"desktop")

    result = delivery_candidate_main(
        [
            "create",
            "--output",
            str(output),
            "--pr-number",
            "12",
            "--pr-head-sha",
            SHA_A,
            "--pr-base-sha",
            SHA_B,
            "--ci-test-commit-sha",
            SHA_A,
            "--source-tree-sha",
            TREE,
            "--ci-run-id",
            "99",
            "--ci-url",
            "https://github.com/conan0220/BAP/actions/runs/99",
            "--docs-only",
            "false",
            "--backend-changed",
            "true",
            "--desktop-changed",
            "true",
            "--backend-artifact",
            str(backend),
            "--desktop-artifact",
            str(desktop),
            "--test",
            "integration=passed",
        ]
    )

    assert result == 0
    manifest = DeliveryManifest.model_validate_json(output.read_text(encoding="utf-8"))
    assert manifest.source_tree_sha == TREE
    assert manifest.backend and manifest.backend.filename == backend.name
    assert manifest.desktop and manifest.desktop.filename == desktop.name


@pytest.mark.scenario("component-delivery-routing", "找到唯一相符 Candidate")
def test_candidate_validates_tree_and_checksums(tmp_path) -> None:
    backend = tmp_path / f"bap-backend-tree-{TREE}.zip"
    deployment_manifest = {
        "project": "BAP",
        "component": "backend",
        "commit_sha": SHA_A,
        "source_tree_sha": TREE,
        "version": "0.1.0",
        "created_at": datetime.now(UTC).isoformat(),
        "python_requires": ">=3.12,<3.13",
        "application_entry_point": "bap_backend.app.main:app",
        "alembic_revision": "0002_app_release_source_tree_sha",
        "files": [],
    }
    with ZipFile(backend, "w") as archive:
        archive.writestr("deployment-manifest.json", json.dumps(deployment_manifest))
        archive.writestr("bap_backend/VERSION", "0.1.0")
    desktop = tmp_path / "BAP-Setup-0.1.0.exe"
    desktop.write_bytes(b"desktop")
    desktop_hash = sha256_file(desktop)
    (tmp_path / "BAP-Setup-0.1.0.metadata.json").write_text(
        json.dumps({
            "project": "BAP",
            "component": "desktop",
            "version": "0.1.0",
            "source_tree_sha": TREE,
            "filename": desktop.name,
            "sha256": desktop_hash,
        }),
        encoding="utf-8",
    )
    manifest = _manifest(
        ArtifactReference(filename=backend.name, sha256=sha256_file(backend)),
        ArtifactReference(filename=desktop.name, sha256=desktop_hash),
    )
    (tmp_path / "delivery-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert validate_candidate(tmp_path, expected_source_tree_sha=TREE).source_tree_sha == TREE
    desktop.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        validate_candidate(tmp_path, expected_source_tree_sha=TREE)

    desktop.write_bytes(b"desktop")
    expired = json.loads((tmp_path / "delivery-manifest.json").read_text(encoding="utf-8"))
    expired["created_at"] = (datetime.now(UTC) - timedelta(days=15)).isoformat()
    (tmp_path / "delivery-manifest.json").write_text(json.dumps(expired), encoding="utf-8")
    with pytest.raises(ValueError, match="expired"):
        validate_candidate(tmp_path, expected_source_tree_sha=TREE)


def test_candidate_validation_fails_when_candidate_is_missing(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        validate_candidate(tmp_path / "missing", expected_source_tree_sha=TREE)
