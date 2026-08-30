from __future__ import annotations

import subprocess
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).parents[2]
SCRIPTS = ROOT / "deployment/windows/backend"
POWERSHELL = Path(r"C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe")


def _parse(script: Path) -> None:
    command = (
        "$tokens=$null; $errors=$null; "
        f"[System.Management.Automation.Language.Parser]::ParseFile('{script}',[ref]$tokens,[ref]$errors)|Out-Null; "
        "if($errors.Count){$errors|ForEach-Object{Write-Error $_}; exit 1}"
    )
    subprocess.run([POWERSHELL, "-NoProfile", "-Command", command], check=True, capture_output=True, text=True)


def test_deployment_scripts_parse_on_windows_powershell_51() -> None:
    scripts = tuple(SCRIPTS.glob("*.ps1"))
    assert scripts
    for script in scripts:
        _parse(script)


def test_initialize_is_repeatable_and_preserves_persistent_files(tmp_path) -> None:
    root = tmp_path / "BAP"
    command = [
        POWERSHELL,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        SCRIPTS / "Initialize-BapBackendHost.ps1",
        "-Root",
        root,
        "-SkipHostChecks",
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    env_file = root / "config/.env"
    env_file.write_text("BAP_ENV=production\n", encoding="utf-8")
    subprocess.run(command, check=True, capture_output=True, text=True)

    assert env_file.read_text(encoding="utf-8") == "BAP_ENV=production\n"
    assert {path.name for path in root.iterdir()} >= {
        "releases",
        "incoming",
        "config",
        "data",
        "logs",
        "backups",
        "scripts",
        "scripts-releases",
        "bootstrap",
        "run",
    }


def test_initialize_validates_public_key_format_and_authorized_keys_acl() -> None:
    initialize = (SCRIPTS / "Initialize-BapBackendHost.ps1").read_text(encoding="utf-8")
    assert "ssh-(rsa|ed25519)" in initialize
    assert "Get-Acl -LiteralPath $AuthorizedKeys" in initialize
    assert '"S-1-5-18", "S-1-5-32-544"' in initialize
    assert "Set-Acl" not in initialize
    assert "icacls" not in initialize.lower()


def test_initialize_requires_uv_without_fixed_global_python() -> None:
    initialize = (SCRIPTS / "Initialize-BapBackendHost.ps1").read_text(encoding="utf-8")
    assert "$UvPath --version" in initialize
    assert "$PythonPath" not in initialize
    assert "C:\\Python312\\python.exe" not in initialize
    assert "Python 3.12 is required" not in initialize


def test_process_scripts_use_pid_and_verify_command_before_stopping() -> None:
    start = (SCRIPTS / "Start-BapBackend.ps1").read_text(encoding="utf-8")
    stop = (SCRIPTS / "Stop-BapBackend.ps1").read_text(encoding="utf-8")
    assert "bap-backend.pid" in start and "bap-backend.pid" in stop
    assert "-WindowStyle Hidden" in start
    assert "$Foreground" in start
    assert "ExecutablePath" in stop
    assert "bap_backend.app.main" in stop
    assert "Get-Process -Name python" not in stop


def test_build_uses_clean_git_archive_and_excludes_tests_from_stage() -> None:
    build = (SCRIPTS / "Build-BapBackendArtifact.ps1").read_text(encoding="utf-8")
    assert "git" not in build.lower() or "archive" in build.lower()
    assert "archive --format=zip" in build
    assert "deployment-manifest.json" in build
    stage_copy = build.split("foreach ($Path", 1)[1]
    assert '"tests"' not in stage_copy.split(")", 1)[0]


def _manifest(sha: str, component: str) -> dict:
    return {
        "project": "BAP",
        "component": component,
        "commit_sha": sha,
        "version": "0.1.0",
        "created_at": datetime.now(UTC).isoformat(),
        "python_requires": ">=3.12,<3.13",
        "application_entry_point": "none" if component == "deployment-scripts" else "bap_backend.app.main:app",
        "alembic_revision": "none" if component == "deployment-scripts" else "0001_initial",
        "files": [],
    }


def _checksum(path: Path) -> Path:
    checksum = path.with_suffix(path.suffix + ".sha256")
    checksum.write_text(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n", encoding="ascii")
    return checksum


def test_bootstrap_updates_versioned_deployment_scripts_and_switches_junction(tmp_path) -> None:
    sha = "c" * 40
    artifact = tmp_path / f"bap-deployment-scripts-{sha}.zip"
    names = (
        "Common-BapDeployment.ps1",
        "Deploy-BapBackendRelease.ps1",
        "Rollback-BapBackendRelease.ps1",
        "Start-BapBackend.ps1",
        "Stop-BapBackend.ps1",
        "Get-BapBackendStatus.ps1",
        "Test-BapBackendHealth.ps1",
    )
    with ZipFile(artifact, "w") as archive:
        archive.writestr("deployment-manifest.json", json.dumps(_manifest(sha, "deployment-scripts")))
        for name in names:
            archive.writestr(name, 'Write-Output "ok"\n')
    checksum = _checksum(artifact)
    root = tmp_path / "host"
    (root / "incoming").mkdir(parents=True)
    (root / "scripts-releases").mkdir()
    (root / "scripts").mkdir()
    subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            SCRIPTS / "Update-BapDeploymentScripts.ps1",
            "-ArtifactPath",
            artifact,
            "-ChecksumPath",
            checksum,
            "-ExpectedCommitSha",
            sha,
            "-Root",
            root,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert (root / "scripts/Deploy-BapBackendRelease.ps1").is_file()
    assert (root / f"scripts-releases/{sha}/deployment-manifest.json").is_file()


def test_deploy_prepares_immutable_release_after_checksum_filename_and_manifest_validation(tmp_path) -> None:
    sha = "d" * 40
    artifact = tmp_path / f"bap-backend-{sha}.zip"
    with ZipFile(artifact, "w") as archive:
        archive.writestr("deployment-manifest.json", json.dumps(_manifest(sha, "backend")))
        archive.writestr("bap_backend/VERSION", "0.1.0")
        archive.writestr("bap_common/__init__.py", "")
        archive.writestr("migrations/env.py", "")
        archive.writestr("alembic.ini", "")
        archive.writestr("pyproject.toml", "")
        archive.writestr("uv.lock", "")
        archive.writestr(".python-version", "3.12")
    checksum = _checksum(artifact)
    root = tmp_path / "host"
    for name in ("incoming", "releases", "run", "logs", "config", "data", "backups"):
        (root / name).mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            SCRIPTS / "Deploy-BapBackendRelease.ps1",
            "-ArtifactPath",
            artifact,
            "-ChecksumPath",
            checksum,
            "-ExpectedCommitSha",
            sha,
            "-Root",
            root,
            "-SkipDependencyInstallForTesting",
            "-PrepareOnlyForTesting",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    release = root / f"releases/{sha}"
    assert release.is_dir()
    assert json.loads((release / "deployment-manifest.json").read_text(encoding="utf-8"))["commit_sha"] == sha


def test_publish_interfaces_require_clean_pushed_git_and_key_only_ssh() -> None:
    for name in ("Publish-BapBackend.ps1", "Publish-BapDeploymentScripts.ps1"):
        source = (SCRIPTS / name).read_text(encoding="utf-8")
        assert "status --porcelain" in source
        assert 'rev-parse "@{u}"' in source
        assert "BatchMode=yes" in source
        assert "StrictHostKeyChecking=yes" in source
        assert "ssh-keygen.exe" in source
        assert "password" not in source.lower()


def test_deploy_and_rollback_define_safe_sequence_and_database_restore() -> None:
    deploy = (SCRIPTS / "Deploy-BapBackendRelease.ps1").read_text(encoding="utf-8")
    rollback = (SCRIPTS / "Rollback-BapBackendRelease.ps1").read_text(encoding="utf-8")
    assert deploy.index("Stop-BapBackend.ps1") < deploy.index("Copy-Item -LiteralPath $Database")
    assert deploy.index("Copy-Item -LiteralPath $Database") < deploy.index("-m alembic")
    assert deploy.index("-m alembic") < deploy.index("mklink /J")
    assert deploy.index("mklink /J") < deploy.index("Start-BapBackend.ps1")
    assert "Rollback-BapBackendRelease.ps1" in deploy
    assert "Copy-Item -LiteralPath $DatabaseBackup" in rollback
    assert "Assert-BapReleasePath" in rollback


def test_rollback_switches_current_to_previous_release_and_restores_database(tmp_path) -> None:
    root = tmp_path / "host"
    previous = root / ("releases/" + "1" * 40)
    failed = root / ("releases/" + "2" * 40)
    previous.mkdir(parents=True)
    failed.mkdir(parents=True)
    (root / "run").mkdir()
    (root / "data").mkdir()
    (root / "backups").mkdir()
    (root / "data/bap.db").write_text("new database", encoding="utf-8")
    backup = root / "backups/previous.db"
    backup.write_text("old database", encoding="utf-8")
    subprocess.run(
        [r"C:\WINDOWS\system32\cmd.exe", "/d", "/c", "mklink", "/J", str(root / "current"), str(failed)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            SCRIPTS / "Rollback-BapBackendRelease.ps1",
            "-Root",
            root,
            "-PreviousRelease",
            previous,
            "-DatabaseBackup",
            backup,
            "-SkipRestartForTesting",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert (root / "current").resolve() == previous.resolve()
    assert (root / "data/bap.db").read_text(encoding="utf-8") == "old database"


def test_script_artifact_excludes_bootstrap_secrets_and_backend_source() -> None:
    publish = (SCRIPTS / "Publish-BapDeploymentScripts.ps1").read_text(encoding="utf-8")
    allowed_block = publish.split("$Allowed = @(", 1)[1].split(")", 1)[0]
    assert "Update-BapDeploymentScripts.ps1" not in allowed_block
    assert "Initialize-BapBackendHost.ps1" not in allowed_block
    assert "bap_backend" not in allowed_block
    for sensitive in (".env", "id_rsa", "id_ed25519", "private key"):
        assert sensitive not in allowed_block.lower()


def test_no_github_action_performs_backend_production_deployment() -> None:
    workflows = ROOT / ".github/workflows"
    combined = "\n".join(path.read_text(encoding="utf-8") for path in workflows.glob("*.yml"))
    assert "Publish-BapBackend.ps1" not in combined
    assert "backend-v" not in combined
    assert "production" not in combined.lower()
