from __future__ import annotations

import ast
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from bap_backend.app.core.config import BackendSettings
from bap_backend.app.main import create_app
from bap_backend.app.models import AppRelease
from bap_backend.app.repositories import ReleaseRepository
from bap_backend.tools.publish_desktop_release import validate_release_input


def test_latest_release_uses_semantic_version_and_platform(backend_context) -> None:
    client, factory, _, _ = backend_context
    with factory() as session:
        repository = ReleaseRepository(session)
        for version in ("1.9.0", "1.10.0"):
            repository.upsert(
                AppRelease(
                    platform="windows",
                    version=version,
                    download_url=f"https://github.com/example/BAP/{version}.exe",
                    sha256="a" * 64,
                    source_tree_sha="c" * 40,
                    published_at=datetime(2026, 1, 1),
                    is_active=True,
                )
            )
        repository.upsert(
            AppRelease(
                platform="linux",
                version="9.0.0",
                download_url="https://github.com/example/BAP/linux.tar.gz",
                sha256="b" * 64,
                source_tree_sha="c" * 40,
                published_at=datetime(2026, 1, 1),
                is_active=True,
            )
        )
        session.commit()
    response = client.get("/api/v1/releases/latest", params={"platform": "windows"})
    assert response.status_code == 200
    assert response.json()["version"] == "1.10.0"
    assert client.get("/api/v1/releases/latest", params={"platform": "macos"}).status_code == 404


def test_release_management_input_requires_semver_https_and_sha256() -> None:
    validate_release_input("1.2.3", "https://github.com/example/BAP.exe", "a" * 64, "c" * 40)
    for values in (
        ("not-version", "https://example.com/a.exe", "a" * 64, "c" * 40),
        ("1.0.0", "http://example.com/a.exe", "a" * 64, "c" * 40),
        ("1.0.0", "https://example.com/a.exe", "short", "c" * 40),
        ("1.0.0", "https://example.com/a.exe", "a" * 64, "short"),
    ):
        try:
            validate_release_input(*values)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected invalid release input: {values}")


def test_release_publisher_confirmation_is_safe_for_legacy_windows_consoles() -> None:
    source = (
        Path(__file__).parents[2] / "bap_backend/tools/publish_desktop_release.py"
    ).read_text(encoding="utf-8")
    assert 'print(f"Published {args.platform.lower()} {args.version}")' in source


def test_health_reports_database_and_commit(backend_context) -> None:
    client, _, _, _ = backend_context
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "bap-backend",
        "commit_sha": "development",
    }


def test_health_returns_503_without_exception_details_when_database_is_unavailable() -> None:
    class BrokenSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, _statement):
            raise SQLAlchemyError("database-password=do-not-leak")

    app = create_app(
        settings=BackendSettings(jwt_signing_key="test-key", _env_file=None),
        session_factory=BrokenSession,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert "do-not-leak" not in response.text


def test_repository_layer_has_no_fastapi_dependency() -> None:
    root = Path(__file__).resolve().parents[2] / "bap_backend/app/repositories"
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = {
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, (ast.ImportFrom,))
        }
        assert not any(name.startswith("fastapi") for name in imports)


def test_api_routes_do_not_execute_sql_or_define_imu_uploads() -> None:
    root = Path(__file__).resolve().parents[2] / "bap_backend/app/api"
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))
    assert "session.execute" not in text
    assert "imu_payload" not in text
    assert "csv" not in text.lower()
    assert "punch" not in text.lower()
