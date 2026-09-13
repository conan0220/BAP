from __future__ import annotations

import json
from datetime import UTC, datetime
from zipfile import ZipFile

import pytest

from bap_backend.deployment.artifact import validate_zip
from bap_backend.app.services.punch_classification import (
    PunchClassificationModelBundle,
    default_model_bundle_path,
)


COMMIT_SHA = "a" * 40
TREE_SHA = "b" * 40


def _manifest() -> dict:
    return {
        "project": "BAP",
        "component": "backend",
        "commit_sha": COMMIT_SHA,
        "source_tree_sha": TREE_SHA,
        "version": "0.1.0",
        "created_at": datetime.now(UTC).isoformat(),
        "python_requires": ">=3.12,<3.13",
        "application_entry_point": "bap_backend.app.main:app",
        "alembic_revision": "0001_initial",
        "files": [],
    }


def _zip(path, members: dict[str, str]) -> None:
    with ZipFile(path, "w") as archive:
        for name, value in members.items():
            archive.writestr(name, value)


@pytest.mark.scenario("backend-automatic-deployment", "CI 建立 Backend ZIP")
def test_backend_artifact_allows_runtime_deployment_code() -> None:
    pass


@pytest.mark.scenario("punch-classification-analysis", "部署轉換後的模型")
def test_backend_source_contains_only_the_validated_production_model_bundle() -> None:
    root = default_model_bundle_path()
    assert {path.name for path in root.iterdir()} == {
        "segmentation.onnx",
        "classifier.onnx",
        "normalization.npz",
        "reference_outputs.npz",
        "manifest.json",
    }
    PunchClassificationModelBundle(root)
    assert not tuple(root.rglob("*.pt"))
    assert not tuple(root.rglob("*.csv"))


def test_backend_artifact_allows_only_unified_production_inputs(tmp_path) -> None:
    path = tmp_path / f"bap-backend-tree-{TREE_SHA}.zip"
    _zip(
        path,
        {
            "deployment-manifest.json": json.dumps(_manifest()),
            "bap_backend/app/main.py": "app = None",
            "bap_common/logging.py": "",
            "migrations/env.py": "",
            "deployment/runtime/Deploy-BapBackendRelease.ps1": "Write-Output ok",
            "pyproject.toml": "",
            "uv.lock": "",
            ".python-version": "3.12",
            "alembic.ini": "",
        },
    )
    manifest = validate_zip(path, expected_source_tree_sha=TREE_SHA)
    assert manifest.commit_sha == COMMIT_SHA


@pytest.mark.parametrize(
    "name",
    (
        ".venv/Scripts/python.exe",
        ".env",
        "tests/test_secret.py",
        "bap_desktop/app.py",
        "data/bap.db",
        "logs/backend.log",
        "../escape.txt",
        "id_rsa",
    ),
)
@pytest.mark.scenario("backend-automatic-deployment", "ZIP 含敏感或非正式檔案")
def test_backend_artifact_rejects_sensitive_content(tmp_path, name) -> None:
    path = tmp_path / "bad.zip"
    _zip(path, {"deployment-manifest.json": json.dumps(_manifest()), name: "secret"})
    with pytest.raises(ValueError):
        validate_zip(path)
