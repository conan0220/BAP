from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZipFile

import pytest


ROOT = Path(__file__).parents[2]
SCRIPTS = ROOT / "deployment/windows/backend"
POWERSHELL = Path(r"C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe")
TREE = "c" * 40
CI_COMMIT = "d" * 40
MASTER_COMMIT = "e" * 40


def _parse(script: Path) -> None:
    command = (
        "$tokens=$null; $errors=$null; "
        f"[System.Management.Automation.Language.Parser]::ParseFile('{script}',[ref]$tokens,[ref]$errors)|Out-Null; "
        "if($errors.Count){$errors|ForEach-Object{Write-Error $_}; exit 1}"
    )
    subprocess.run(
        [POWERSHELL, "-NoProfile", "-Command", command],
        check=True,
        capture_output=True,
        text=True,
    )


def _deployment_manifest() -> dict:
    return {
        "project": "BAP",
        "component": "backend",
        "commit_sha": CI_COMMIT,
        "source_tree_sha": TREE,
        "version": "0.1.0",
        "created_at": datetime.now(UTC).isoformat(),
        "python_requires": ">=3.12,<3.13",
        "application_entry_point": "bap_backend.app.main:app",
        "alembic_revision": "0002_app_release_source_tree_sha",
        "files": [],
    }


def _backend_artifact(
    tmp_path: Path,
    *,
    health_script: str = "Write-Output 'health ok'\n",
) -> tuple[Path, Path]:
    artifact = tmp_path / f"bap-backend-tree-{TREE}.zip"
    with ZipFile(artifact, "w") as archive:
        archive.writestr("deployment-manifest.json", json.dumps(_deployment_manifest()))
        archive.writestr("bap_backend/VERSION", "0.1.0")
        archive.writestr("bap_common/__init__.py", "")
        archive.writestr("migrations/env.py", "")
        archive.writestr("deployment/runtime/Common-BapDeployment.ps1", "Write-Output 'common'\n")
        archive.writestr("deployment/runtime/Deploy-BapBackendRelease.ps1", "Write-Output 'deploy'\n")
        archive.writestr("deployment/runtime/Test-BapBackendHealth.ps1", health_script)
        archive.writestr("alembic.ini", "")
        archive.writestr("pyproject.toml", "")
        archive.writestr("uv.lock", "")
        archive.writestr(".python-version", "3.12")
    checksum = artifact.with_suffix(".zip.sha256")
    checksum.write_text(
        f"{hashlib.sha256(artifact.read_bytes()).hexdigest()}  {artifact.name}\n",
        encoding="ascii",
    )
    return artifact, checksum


def _host(root: Path) -> None:
    for name in ("incoming", "releases", "run", "logs", "config", "data", "backups", "bootstrap"):
        (root / name).mkdir(parents=True, exist_ok=True)


@pytest.mark.scenario("backend-automatic-deployment", "Server 第一次 Initialize")
@pytest.mark.scenario("backend-automatic-deployment", "Server 再次 Initialize")
def test_initialize_is_repeatable_and_preserves_persistent_files(tmp_path) -> None:
    root = tmp_path / "BAP"
    command = [
        POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
        SCRIPTS / "Initialize-BapBackendHost.ps1", "-Root", root, "-SkipHostChecks",
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    env_file = root / "config/.env"
    database = root / "data/bap.db"
    env_file.write_text("BAP_ENV=production\n", encoding="utf-8")
    database.write_bytes(b"persistent")
    subprocess.run(command, check=True, capture_output=True, text=True)

    assert env_file.read_text(encoding="utf-8") == "BAP_ENV=production\n"
    assert database.read_bytes() == b"persistent"
    assert {path.name for path in root.iterdir()} == {
        "releases", "incoming", "config", "data", "logs", "backups", "bootstrap", "run"
    }
    assert (root / "bootstrap/Bootstrap-BapBackendCandidate.ps1").is_file()


@pytest.mark.scenario("backend-automatic-deployment", "Server 開機")
@pytest.mark.scenario("backend-automatic-deployment", "SSH session 結束")
def test_initialize_registers_persistent_scheduled_task_without_rebooting() -> None:
    source = (SCRIPTS / "Initialize-BapBackendHost.ps1").read_text(encoding="utf-8")
    assert "New-ScheduledTaskTrigger -AtStartup" in source
    assert "Register-ScheduledTask" in source
    assert "Run-BapBackendScheduledTask.ps1" in source
    assert "RestartCount 3" in source
    lowered = source.lower()
    assert "restart-computer" not in lowered
    assert "shutdown.exe" not in lowered


def test_all_supported_powershell_scripts_parse_on_windows_powershell_51() -> None:
    expected = {
        "Bootstrap-BapBackendCandidate.ps1",
        "Build-BapBackendArtifact.ps1",
        "Common-BapDeployment.ps1",
        "Deploy-BapBackendRelease.ps1",
        "Get-BapBackendStatus.ps1",
        "Initialize-BapBackendHost.ps1",
        "Rollback-BapBackendRelease.ps1",
        "Run-BapBackendScheduledTask.ps1",
        "Test-BapBackendHealth.ps1",
    }
    assert {path.name for path in SCRIPTS.glob("*.ps1")} == expected
    for script in SCRIPTS.glob("*.ps1"):
        _parse(script)


@pytest.mark.scenario("backend-automatic-deployment", "CI 建立 Backend ZIP")
@pytest.mark.scenario("backend-automatic-deployment", "ZIP 含敏感或非正式檔案")
def test_builder_creates_one_clean_tree_named_artifact_with_runtime_code() -> None:
    source = (SCRIPTS / "Build-BapBackendArtifact.ps1").read_text(encoding="utf-8")
    assert "archive --format=zip" in source
    assert "bap-backend-tree-" in source
    assert "$env:RUNNER_TEMP" in source
    assert '"deployment-manifest.json"' in source
    assert '"Run-BapBackendScheduledTask.ps1"' in source
    assert '"Start-BapBackend.ps1"' not in source
    assert '"tests"' not in source.split("$Inputs = @(", 1)[1].split(")", 1)[0]


@pytest.mark.scenario("backend-automatic-deployment", "Server 收到 Backend ZIP")
@pytest.mark.scenario("backend-automatic-deployment", "正常部署")
@pytest.mark.scenario("backend-automatic-deployment", "Deployment 重複執行")
def test_deploy_prepares_immutable_master_release_and_is_idempotent(tmp_path) -> None:
    artifact, checksum = _backend_artifact(tmp_path)
    root = tmp_path / "host"
    _host(root)
    promotion = tmp_path / "promotion-record.json"
    promotion.write_text(
        json.dumps({"master_commit_sha": MASTER_COMMIT, "source_tree_sha": TREE}),
        encoding="utf-8",
    )
    command = [
        POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
        SCRIPTS / "Deploy-BapBackendRelease.ps1",
        "-ArtifactPath", artifact,
        "-ChecksumPath", checksum,
        "-ExpectedSourceTreeSha", TREE,
        "-MasterCommitSha", MASTER_COMMIT,
        "-PromotionRecordPath", promotion,
        "-Root", root,
        "-SkipDependencyInstallForTesting",
        "-PrepareOnlyForTesting",
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    subprocess.run(command, check=True, capture_output=True, text=True)

    release = root / f"releases/{MASTER_COMMIT}"
    assert release.is_dir()
    assert json.loads((release / "deployment-manifest.json").read_text(encoding="utf-8"))[
        "source_tree_sha"
    ] == TREE
    assert json.loads((release / "promotion-record.json").read_text(encoding="utf-8"))[
        "master_commit_sha"
    ] == MASTER_COMMIT


@pytest.mark.scenario("backend-automatic-deployment", "兩個部署同時到達")
def test_deploy_uses_exclusive_lock_and_rejects_bad_checksum(tmp_path) -> None:
    artifact, checksum = _backend_artifact(tmp_path)
    checksum.write_text("0" * 64 + f"  {artifact.name}\n", encoding="ascii")
    root = tmp_path / "host"
    _host(root)
    promotion = tmp_path / "promotion-record.json"
    promotion.write_text(
        json.dumps({"master_commit_sha": MASTER_COMMIT, "source_tree_sha": TREE}),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            SCRIPTS / "Deploy-BapBackendRelease.ps1",
            "-ArtifactPath", artifact,
            "-ChecksumPath", checksum,
            "-ExpectedSourceTreeSha", TREE,
            "-MasterCommitSha", MASTER_COMMIT,
            "-PromotionRecordPath", promotion,
            "-Root", root,
            "-SkipDependencyInstallForTesting",
            "-PrepareOnlyForTesting",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "checksum does not match" in (result.stdout + result.stderr)
    source = (SCRIPTS / "Deploy-BapBackendRelease.ps1").read_text(encoding="utf-8")
    assert "[IO.FileMode]::CreateNew" in source
    assert "Another Backend deployment is already running." in source


def test_deploy_rejects_an_unexpected_artifact_path(tmp_path) -> None:
    artifact, checksum = _backend_artifact(tmp_path)
    with ZipFile(artifact, "a") as archive:
        archive.writestr("unexpected/file.txt", "not allowed")
    checksum.write_text(
        f"{hashlib.sha256(artifact.read_bytes()).hexdigest()}  {artifact.name}\n",
        encoding="ascii",
    )
    root = tmp_path / "host"
    _host(root)
    promotion = tmp_path / "promotion-record.json"
    promotion.write_text(
        json.dumps({"master_commit_sha": MASTER_COMMIT, "source_tree_sha": TREE}),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            SCRIPTS / "Deploy-BapBackendRelease.ps1",
            "-ArtifactPath", artifact,
            "-ChecksumPath", checksum,
            "-ExpectedSourceTreeSha", TREE,
            "-MasterCommitSha", MASTER_COMMIT,
            "-PromotionRecordPath", promotion,
            "-Root", root,
            "-SkipDependencyInstallForTesting",
            "-PrepareOnlyForTesting",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "unexpected top-level path" in (result.stdout + result.stderr)


@pytest.mark.scenario("backend-automatic-deployment", "Migration 失敗")
@pytest.mark.scenario("backend-automatic-deployment", "Scheduled Task 或 Health 失敗")
def test_deploy_orders_backup_migration_cutover_task_and_health_with_rollback() -> None:
    deploy = (SCRIPTS / "Deploy-BapBackendRelease.ps1").read_text(encoding="utf-8")
    assert deploy.index("Copy-Item -LiteralPath $Database") < deploy.index("-m alembic")
    assert deploy.index("-m alembic") < deploy.index("mklink /J")
    assert deploy.index("mklink /J") < deploy.index("Start-ScheduledTask")
    assert deploy.index("Start-ScheduledTask") < deploy.index("Test-BapBackendHealth.ps1")
    assert "last-known-good.json" in deploy
    assert "catch {" in deploy
    assert "Copy-Item -LiteralPath $Backup" in deploy
    assert "Alembic migration failed." in deploy
    assert "Unable to switch the current junction." in deploy
    assert "Backend health check failed." in deploy
    assert "Deployment failed and rollback also failed." in deploy
    catch_section = deploy.split("} catch {", 1)[1]
    assert catch_section.index("Stop-BapBackendTaskAndListener") < catch_section.index(
        "Remove-BapCurrentJunction"
    )
    assert "Stop-BapBackendTaskAndListener -Root $Root -TaskName $TaskName" in deploy
    assert "Remove-BapCurrentJunction -Root $Root" in deploy


@pytest.mark.scenario("backend-automatic-deployment", "Scheduled Task 或 Health 失敗")
@pytest.mark.scenario("ci-cd-status-reporting", "Backend Rollback 成功")
def test_injected_health_failure_rolls_back_release_database_and_lkg(tmp_path) -> None:
    root = tmp_path / "host"
    _host(root)
    previous = root / ("releases/" + "1" * 40)
    previous_runtime = previous / "deployment/runtime"
    previous_runtime.mkdir(parents=True)
    (previous_runtime / "Test-BapBackendHealth.ps1").write_text(
        "Write-Output 'rollback health ok'\n",
        encoding="utf-8",
    )
    subprocess.run(
        [
            r"C:\WINDOWS\system32\cmd.exe",
            "/d",
            "/c",
            "mklink",
            "/J",
            str(root / "current"),
            str(previous),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    database = root / "data/bap.db"
    database.write_text("last-known-good database", encoding="utf-8")
    lkg = root / "run/last-known-good.json"
    lkg_payload = {"master_commit_sha": "1" * 40, "backend_result": "succeeded"}
    lkg.write_text(json.dumps(lkg_payload), encoding="utf-8")

    escaped_database = str(database).replace("'", "''")
    artifact, checksum = _backend_artifact(
        tmp_path,
        health_script=(
            f"Set-Content -LiteralPath '{escaped_database}' -Value 'failed database'\n"
            "throw 'Injected production health failure.'\n"
        ),
    )
    promotion = tmp_path / "promotion-record.json"
    promotion.write_text(
        json.dumps(
            {
                "master_commit_sha": MASTER_COMMIT,
                "source_tree_sha": TREE,
                "backend_result": "pending",
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
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
            "-ExpectedSourceTreeSha",
            TREE,
            "-MasterCommitSha",
            MASTER_COMMIT,
            "-PromotionRecordPath",
            promotion,
            "-Root",
            root,
            "-SkipDependencyInstallForTesting",
            "-SkipMigrationForTesting",
            "-SkipScheduledTaskForTesting",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "Injected production health failure" in (result.stdout + result.stderr)
    assert (root / "current").resolve() == previous.resolve()
    assert database.read_text(encoding="utf-8").strip() == "last-known-good database"
    assert json.loads(lkg.read_text(encoding="utf-8")) == lkg_payload
    assert json.loads(promotion.read_text(encoding="utf-8-sig"))["backend_result"] == "failed"


def test_current_junction_removal_uses_dotnet_and_validates_release_target() -> None:
    common = (SCRIPTS / "Common-BapDeployment.ps1").read_text(encoding="utf-8")
    rollback = (SCRIPTS / "Rollback-BapBackendRelease.ps1").read_text(
        encoding="utf-8"
    )
    assert "function Remove-BapCurrentJunction" in common
    assert "[IO.Directory]::Delete($Current)" in common
    assert "Current junction target is outside the releases directory." in common
    assert "Remove-Item -LiteralPath $Current" not in common


def test_backend_stop_helper_only_terminates_verified_bap_uvicorn_tree() -> None:
    common = (SCRIPTS / "Common-BapDeployment.ps1").read_text(encoding="utf-8")
    rollback = (SCRIPTS / "Rollback-BapBackendRelease.ps1").read_text(encoding="utf-8")
    assert "function Stop-BapBackendTaskAndListener" in common
    assert '$Task.State -eq "Running"' in common
    assert "Stop-ScheduledTask -TaskName $TaskName -ErrorAction Stop" in common
    assert "bap_backend\\.app\\.main:app" in common
    assert "Backend port belongs to an unrecognized process" in common
    assert "Stop-Process -Id ([int]$Owner.ProcessId) -Force" in common
    assert "Stop-BapBackendTaskAndListener -Root $Root -TaskName $TaskName" in rollback
    assert "Remove-BapCurrentJunction -Root $Root" in rollback


@pytest.mark.scenario("backend-automatic-deployment", "管理者查詢狀態")
def test_status_reports_task_port_health_and_promotion_identity() -> None:
    status = (SCRIPTS / "Get-BapBackendStatus.ps1").read_text(encoding="utf-8")
    for field in (
        "task_state", "port_12345", "health", "master_commit_sha",
        "source_tree_sha", "checksum", "current_release",
    ):
        assert field in status
    assert "Invoke-RestMethod" in status
    assert "Get-NetTCPConnection" in status


@pytest.mark.scenario("backend-automatic-deployment", "Cutover 後檢查舊 Process Scripts")
def test_legacy_process_and_manual_publish_scripts_are_removed() -> None:
    removed = {
        "Publish-BapBackend.ps1",
        "Publish-BapDeploymentScripts.ps1",
        "Update-BapDeploymentScripts.ps1",
        "Start-BapBackend.ps1",
        "Stop-BapBackend.ps1",
    }
    assert not ({path.name for path in SCRIPTS.glob("*.ps1")} & removed)


@pytest.mark.scenario("backend-automatic-deployment", "Scheduled Task 或 Health 失敗")
def test_rollback_switches_current_and_restores_database(tmp_path) -> None:
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
            POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            SCRIPTS / "Rollback-BapBackendRelease.ps1",
            "-Root", root,
            "-PreviousRelease", previous,
            "-DatabaseBackup", backup,
            "-SkipScheduledTaskForTesting",
            "-SkipHealthCheckForTesting",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert (root / "current").resolve() == previous.resolve()
    assert (root / "data/bap.db").read_text(encoding="utf-8") == "old database"


@pytest.mark.scenario("backend-automatic-deployment", "SSH 或 SCP 失敗")
def test_cd_uses_environment_scoped_key_and_fail_closed_ssh() -> None:
    workflow = (ROOT / ".github/workflows/continuous-delivery.yml").read_text(encoding="utf-8")
    assert "environment: production-backend" in workflow
    assert "BAP_BACKEND_SSH_PRIVATE_KEY" in workflow
    assert "BatchMode=yes" in workflow
    assert "StrictHostKeyChecking=no" in workflow
    assert "Restart-Computer" not in workflow
