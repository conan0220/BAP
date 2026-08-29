from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from bap_backend.deployment import DeploymentManifest
from bap_backend.tools.write_deployment_manifest import main


SHA = "a" * 40


def _manifest(**overrides):
    data = {
        "project": "BAP",
        "component": "backend",
        "commit_sha": SHA,
        "version": "0.1.0",
        "created_at": datetime.now(UTC),
        "python_requires": ">=3.12,<3.13",
        "application_entry_point": "bap_backend.app.main:app",
        "alembic_revision": "0001_initial",
        "files": ["bap_backend", "migrations"],
    }
    data.update(overrides)
    return data


def test_backend_deployment_manifest_contract() -> None:
    manifest = DeploymentManifest(**_manifest())
    assert manifest.project == "BAP"
    assert manifest.commit_sha == SHA
    assert manifest.application_entry_point == "bap_backend.app.main:app"


@pytest.mark.parametrize(
    ("field", "value"),
    (("project", "Other"), ("commit_sha", "short"), ("version", "latest"), ("component", "desktop")),
)
def test_manifest_rejects_untraceable_values(field, value) -> None:
    with pytest.raises(ValidationError):
        DeploymentManifest(**_manifest(**{field: value}))


def test_manifest_cli_writes_and_validates_json(tmp_path) -> None:
    output = tmp_path / "deployment-manifest.json"
    assert main(
        [
            "--output",
            str(output),
            "--component",
            "backend",
            "--commit-sha",
            SHA,
            "--version",
            "0.1.0",
            "--file",
            "migrations",
            "--file",
            "bap_backend",
        ]
    ) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["files"] == ["bap_backend", "migrations"]
    assert main(["--validate", str(output)]) == 0

