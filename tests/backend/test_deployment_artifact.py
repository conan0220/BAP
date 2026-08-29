from __future__ import annotations

import json
from datetime import UTC, datetime
from zipfile import ZipFile

import pytest

from bap_backend.deployment.artifact import validate_zip


SHA = "b" * 40


def _manifest(component="backend") -> dict:
    return {
        "project": "BAP",
        "component": component,
        "commit_sha": SHA,
        "version": "0.1.0",
        "created_at": datetime.now(UTC).isoformat(),
        "python_requires": ">=3.12,<3.13",
        "application_entry_point": "bap_backend.app.main:app" if component == "backend" else "none",
        "alembic_revision": "0001_initial" if component == "backend" else "none",
        "files": [],
    }


def _zip(path, members: dict[str, str]) -> None:
    with ZipFile(path, "w") as archive:
        for name, value in members.items():
            archive.writestr(name, value)


def test_backend_artifact_allows_only_production_inputs(tmp_path) -> None:
    path = tmp_path / f"bap-backend-{SHA}.zip"
    _zip(
        path,
        {
            "deployment-manifest.json": json.dumps(_manifest()),
            "bap_backend/app/main.py": "app = None",
            "bap_common/logging.py": "",
            "migrations/env.py": "",
            "pyproject.toml": "",
            "uv.lock": "",
            ".python-version": "3.12",
            "alembic.ini": "",
        },
    )
    assert validate_zip(path, component="backend", expected_sha=SHA).commit_sha == SHA


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
def test_backend_artifact_rejects_runtime_desktop_test_and_sensitive_content(tmp_path, name) -> None:
    path = tmp_path / "bad.zip"
    _zip(path, {"deployment-manifest.json": json.dumps(_manifest()), name: "secret"})
    with pytest.raises(ValueError):
        validate_zip(path, component="backend")

