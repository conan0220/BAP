from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from bap_backend.deployment import DeploymentManifest
from bap_backend.tools.write_deployment_manifest import main


COMMIT_SHA = "a" * 40
TREE_SHA = "b" * 40


def _manifest(**overrides):
    data = {
        "project": "BAP",
        "component": "backend",
        "commit_sha": COMMIT_SHA,
        "source_tree_sha": TREE_SHA,
        "version": "0.1.0",
        "created_at": datetime.now(UTC),
        "python_requires": ">=3.12,<3.13",
        "application_entry_point": "bap_backend.app.main:app",
        "alembic_revision": "0002_app_release_source_tree_sha",
        "files": ["bap_backend", "deployment", "migrations"],
    }
    data.update(overrides)
    return data


def test_backend_deployment_manifest_contract() -> None:
    manifest = DeploymentManifest(**_manifest())
    assert manifest.commit_sha == COMMIT_SHA
    assert manifest.source_tree_sha == TREE_SHA


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("project", "Other"),
        ("commit_sha", "short"),
        ("source_tree_sha", "short"),
        ("version", "latest"),
        ("component", "deployment-scripts"),
    ),
)
def test_manifest_rejects_untraceable_values(field, value) -> None:
    with pytest.raises(ValidationError):
        DeploymentManifest(**_manifest(**{field: value}))


def test_manifest_cli_writes_and_validates_json(tmp_path) -> None:
    output = tmp_path / "deployment-manifest.json"
    assert main(
        [
            "--output", str(output),
            "--component", "backend",
            "--commit-sha", COMMIT_SHA,
            "--source-tree-sha", TREE_SHA,
            "--version", "0.1.0",
            "--file", "migrations",
            "--file", "bap_backend",
        ]
    ) == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["source_tree_sha"] == TREE_SHA
    assert data["files"] == ["bap_backend", "migrations"]
    assert main(["--validate", str(output)]) == 0


def test_promotion_record_is_strict_and_traceable() -> None:
    from bap_backend.deployment import PromotionRecord

    record = PromotionRecord(
        project="BAP",
        master_commit_sha=COMMIT_SHA,
        pr_number=12,
        ci_workflow_run_id=99,
        source_tree_sha=TREE_SHA,
        backend_sha256="c" * 64,
        desktop_sha256="d" * 64,
        backend_changed=True,
        desktop_changed=True,
        database_revision="0002_app_release_source_tree_sha",
        promoted_at=datetime.now(UTC),
        backend_result="succeeded",
        desktop_result="pending",
    )
    assert record.master_commit_sha == COMMIT_SHA
    with pytest.raises(ValidationError):
        PromotionRecord(**{**record.model_dump(), "secret": "must-not-exist"})
