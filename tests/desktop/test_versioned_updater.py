from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from bap_desktop.update_runtime.models import (
    ActiveReleaseState,
    OperationJournal,
    ReleaseManifest,
    UpdatePaths,
)
from bap_desktop.update_runtime.updater import (
    UpdateRuntimeError,
    _helper_command,
    _reserve_update,
    apply_update,
    cleanup_old_releases,
    finalize_installed_release,
    handoff_update,
    migrate_legacy_install,
    wait_for_ready_signal,
)


def _paths(tmp_path: Path) -> UpdatePaths:
    paths = UpdatePaths.from_environment(
        program_root=tmp_path / "program",
        user_data_root=tmp_path / "data",
    )
    paths.prepare()
    return paths


def _release(paths: UpdatePaths, version: str) -> Path:
    root = paths.release_dir(version)
    root.mkdir(parents=True, exist_ok=True)
    (root / "BAP.exe").write_bytes(version.encode())
    ReleaseManifest(version=version, source_tree_sha="a" * 40).save(root)
    return root


@pytest.mark.scenario("desktop-versioned-update-rollback", "Candidate 通過 Health Check")
@pytest.mark.scenario("desktop-versioned-update-rollback", "新版成功送出 Ready Signal")
@pytest.mark.scenario("desktop-versioned-update-rollback", "新版確認成功後清理")
def test_finalize_switches_only_after_health_and_ready_then_cleans_old_versions(tmp_path) -> None:
    paths = _paths(tmp_path)
    _release(paths, "0.1.5")
    _release(paths, "0.1.6")
    _release(paths, "0.1.7")
    ActiveReleaseState(active_version="0.1.6", previous_version="0.1.5").save(paths.state_file)
    launch_calls = []

    state = finalize_installed_release(
        paths,
        version="0.1.7",
        operation_id="op-success",
        launch_and_wait=True,
        health_runner=lambda exe, result, version, data: exe.name == "BAP.exe"
        and version == "0.1.7"
        and data == paths.user_data_root,
        launcher_runner=lambda p, op, result: launch_calls.append((op, ActiveReleaseState.load(p.state_file))) or 42,
        ready_waiter=lambda ready, op, pid, timeout: (op, pid, timeout) == ("op-success", 42, 30.0),
        process_terminator=lambda _pid: None,
    )

    assert state.active_version == "0.1.7"
    assert state.previous_version == "0.1.6"
    assert launch_calls[0][0] == "op-success"
    assert launch_calls[0][1].active_version == "0.1.7"
    assert not paths.release_dir("0.1.5").exists()
    assert paths.release_dir("0.1.6").is_dir()
    journal = json.loads((paths.operation_dir("op-success") / "operation.json").read_text(encoding="utf-8"))
    assert journal["status"] == "succeeded"


@pytest.mark.scenario("desktop-versioned-update-rollback", "Candidate 未通過 Health Check")
def test_health_failure_never_switches_active_release(tmp_path) -> None:
    paths = _paths(tmp_path)
    _release(paths, "0.1.6")
    _release(paths, "0.1.7")
    ActiveReleaseState(active_version="0.1.6").save(paths.state_file)
    launches = []

    with pytest.raises(UpdateRuntimeError, match="保留原本版本"):
        finalize_installed_release(
            paths,
            version="0.1.7",
            operation_id="op-health-fail",
            launch_and_wait=True,
            health_runner=lambda *_args: False,
            launcher_runner=lambda _p, op, _r: launches.append(op) or 12,
        )

    assert ActiveReleaseState.load(paths.state_file).active_version == "0.1.6"
    assert launches == [None]
    journal = json.loads((paths.operation_dir("op-health-fail") / "operation.json").read_text(encoding="utf-8"))
    assert journal["status"] == "health_failed"


@pytest.mark.scenario("desktop-versioned-update-rollback", "新版切換後無法正常啟動")
@pytest.mark.scenario("desktop-versioned-update-rollback", "更新失敗並 Rollback")
def test_ready_timeout_terminates_candidate_and_rolls_back(tmp_path) -> None:
    paths = _paths(tmp_path)
    _release(paths, "0.1.6")
    _release(paths, "0.1.7")
    ActiveReleaseState(active_version="0.1.6").save(paths.state_file)
    launches = []
    terminated = []

    def launcher(p, operation, _result):
        launches.append((operation, ActiveReleaseState.load(p.state_file).active_version))
        return 71 if operation else 61

    with pytest.raises(UpdateRuntimeError, match="已恢復 BAP 0.1.6"):
        finalize_installed_release(
            paths,
            version="0.1.7",
            operation_id="op-timeout",
            launch_and_wait=True,
            health_runner=lambda *_args: True,
            launcher_runner=launcher,
            ready_waiter=lambda *_args: False,
            process_terminator=terminated.append,
        )

    assert terminated == [71]
    assert launches == [("op-timeout", "0.1.7"), (None, "0.1.6")]
    assert ActiveReleaseState.load(paths.state_file).active_version == "0.1.6"
    journal = json.loads((paths.operation_dir("op-timeout") / "operation.json").read_text(encoding="utf-8"))
    assert journal["status"] == "rolled_back"


@pytest.mark.scenario("desktop-versioned-update-rollback", "Rollback 本身失敗")
def test_rollback_failure_preserves_both_releases_and_reports_direct_path(tmp_path) -> None:
    paths = _paths(tmp_path)
    _release(paths, "0.1.6")
    _release(paths, "0.1.7")
    ActiveReleaseState(active_version="0.1.6").save(paths.state_file)

    def launcher(_paths, operation, _result):
        if operation is None:
            raise OSError("cannot start old version")
        return 77

    with pytest.raises(UpdateRuntimeError, match=r"releases.0.1.6.BAP.exe"):
        finalize_installed_release(
            paths,
            version="0.1.7",
            operation_id="op-rollback-fail",
            launch_and_wait=True,
            health_runner=lambda *_args: True,
            launcher_runner=launcher,
            ready_waiter=lambda *_args: False,
            process_terminator=lambda _pid: None,
        )

    assert paths.release_dir("0.1.6").is_dir()
    assert paths.release_dir("0.1.7").is_dir()
    assert ActiveReleaseState.load(paths.state_file).active_version == "0.1.6"
    journal = json.loads((paths.operation_dir("op-rollback-fail") / "operation.json").read_text(encoding="utf-8"))
    assert journal["status"] == "rollback_failed"


@pytest.mark.scenario("desktop-versioned-update-rollback", "舊版本暫時無法刪除")
def test_cleanup_failure_is_nonfatal_and_journaled(tmp_path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    for version in ("0.1.5", "0.1.6", "0.1.7"):
        _release(paths, version)
    state = ActiveReleaseState(active_version="0.1.7", previous_version="0.1.6")
    state.save(paths.state_file)
    journal = OperationJournal.create(paths, "op-cleanup", "0.1.7")

    monkeypatch.setattr(
        "bap_desktop.update_runtime.updater.shutil.rmtree",
        lambda _path: (_ for _ in ()).throw(PermissionError("locked")),
    )
    assert cleanup_old_releases(paths, state, journal=journal) == []
    assert paths.release_dir("0.1.5").is_dir()
    value = json.loads(journal.path.read_text(encoding="utf-8"))
    assert value["events"][-1]["status"] == "cleanup_warning"


@pytest.mark.scenario("desktop-app-update-check", "Updater 成功接手")
def test_handoff_verifies_installer_reserves_one_operation_and_writes_ack(tmp_path) -> None:
    paths = _paths(tmp_path)
    operation = paths.operation_dir("op-handoff")
    operation.mkdir(parents=True)
    installer = operation / "BAP-Setup-0.1.7.exe"
    installer.write_bytes(b"candidate")
    digest = hashlib.sha256(b"candidate").hexdigest()
    calls = []

    class Process:
        pid = 123

        @staticmethod
        def poll():
            return None

    accepted_file = paths.operation_dir("op-handoff") / "accepted.json"

    def launch(command, cwd):
        calls.append((command, cwd))
        accepted_file.write_text(
            json.dumps({"operation_id": "op-handoff", "helper_pid": 123}),
            encoding="utf-8",
        )
        return Process()

    accepted = handoff_update(
        paths,
        installer=installer,
        version="0.1.7",
        sha256=digest,
        old_pid=99,
        operation_id="op-handoff",
        process_launcher=launch,
    )
    assert json.loads(accepted.read_text(encoding="utf-8"))["helper_pid"] == 123
    assert calls and "apply" in calls[0][0]
    with pytest.raises(UpdateRuntimeError, match="另一個"):
        _reserve_update(paths, "op-second")


@pytest.mark.scenario("desktop-app-update-check", "Updater 未成功接手")
def test_handoff_launch_failure_releases_reservation(tmp_path) -> None:
    paths = _paths(tmp_path)
    operation = paths.operation_dir("op-fail")
    operation.mkdir(parents=True)
    installer = operation / "BAP-Setup-0.1.7.exe"
    installer.write_bytes(b"candidate")

    with pytest.raises(OSError, match="blocked"):
        handoff_update(
            paths,
            installer=installer,
            version="0.1.7",
            sha256=hashlib.sha256(b"candidate").hexdigest(),
            old_pid=99,
            operation_id="op-fail",
            process_launcher=lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("blocked")),
        )
    assert not paths.lock_file.exists()


def test_handoff_requires_acknowledgement_from_the_helper(tmp_path) -> None:
    paths = _paths(tmp_path)
    operation = paths.operation_dir("op-no-ack")
    operation.mkdir(parents=True)
    installer = operation / "BAP-Setup-0.1.7.exe"
    installer.write_bytes(b"candidate")

    class ExitedProcess:
        pid = 321

        @staticmethod
        def poll():
            return 1

    with pytest.raises(UpdateRuntimeError, match="helper 未成功啟動"):
        handoff_update(
            paths,
            installer=installer,
            version="0.1.7",
            sha256=hashlib.sha256(b"candidate").hexdigest(),
            old_pid=99,
            operation_id="op-no-ack",
            process_launcher=lambda *_args, **_kwargs: ExitedProcess(),
            helper_timeout=0.1,
        )
    assert not paths.lock_file.exists()


def test_frozen_handoff_copies_the_updater_executable_and_its_runtime(
    tmp_path, monkeypatch
) -> None:
    paths = _paths(tmp_path)
    installed = tmp_path / "installed"
    installed.mkdir()
    executable = installed / "BAPUpdater.exe"
    executable.write_bytes(b"updater")
    runtime = installed / "updater_runtime"
    runtime.mkdir()
    (runtime / "python312.dll").write_bytes(b"runtime")
    monkeypatch.setattr("bap_desktop.update_runtime.updater.sys.frozen", True, raising=False)
    monkeypatch.setattr("bap_desktop.update_runtime.updater.sys.executable", str(executable))

    command = _helper_command(
        paths,
        installer=paths.operation_dir("op-frozen") / "candidate.exe",
        version="0.1.7",
        sha256="a" * 64,
        old_pid=1,
        operation_id="op-frozen",
    )

    copied = paths.operation_dir("op-frozen")
    assert Path(command[0]) == copied / "BAPUpdater.exe"
    assert (copied / "BAPUpdater.exe").read_bytes() == b"updater"
    assert (copied / "updater_runtime" / "python312.dll").read_bytes() == b"runtime"


def test_wait_for_ready_signal_handles_success_early_exit_and_timeout(tmp_path, monkeypatch) -> None:
    ready = tmp_path / "ready.json"
    ready.write_text(json.dumps({"operation_id": "op", "pid": 7}), encoding="utf-8")
    assert wait_for_ready_signal(ready, "op", 7, 1.0) is True

    ready.unlink()
    monkeypatch.setattr("bap_desktop.update_runtime.updater.process_is_running", lambda _pid: False)
    assert wait_for_ready_signal(ready, "op", 7, 1.0) is False

    monkeypatch.setattr("bap_desktop.update_runtime.updater.process_is_running", lambda _pid: True)
    assert wait_for_ready_signal(ready, "op", 7, 0.0) is False


@pytest.mark.scenario("desktop-versioned-update-rollback", "Legacy Install 成功轉成 Previous Release")
def test_legacy_install_is_copied_and_verified_before_activation(tmp_path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    (paths.program_root / "BAP.exe").write_bytes(b"legacy")
    internal = paths.program_root / "_internal"
    internal.mkdir()
    (internal / "runtime.dll").write_bytes(b"dll")
    monkeypatch.setattr(
        "bap_desktop.update_runtime.updater._probe_runtime_version",
        lambda _exe, _output: "0.1.6",
    )

    assert migrate_legacy_install(paths, "op-legacy") == "0.1.6"

    copied = paths.release_dir("0.1.6")
    assert (copied / "BAP.exe").read_bytes() == b"legacy"
    assert (copied / "_internal" / "runtime.dll").read_bytes() == b"dll"
    assert ReleaseManifest.load(copied).legacy is True
    assert ActiveReleaseState.load(paths.state_file).active_version == "0.1.6"


def test_legacy_migration_falls_back_when_windows_blocks_directory_replace(
    tmp_path, monkeypatch
) -> None:
    paths = _paths(tmp_path)
    (paths.program_root / "BAP.exe").write_bytes(b"legacy")
    (paths.program_root / "_internal").mkdir()
    (paths.program_root / "_internal" / "runtime.dll").write_bytes(b"dll")
    monkeypatch.setattr(
        "bap_desktop.update_runtime.updater._probe_runtime_version",
        lambda _exe, _output: "0.1.6",
    )
    real_replace = os.replace

    def block_only_staging_directory(source, destination):
        if Path(source).name.startswith("legacy-"):
            raise PermissionError("scanner still holds the probed runtime")
        return real_replace(source, destination)

    monkeypatch.setattr(
        "bap_desktop.update_runtime.updater.os.replace", block_only_staging_directory
    )

    assert migrate_legacy_install(paths, "op-legacy-copy-fallback") == "0.1.6"
    copied = paths.release_dir("0.1.6")
    assert (copied / "BAP.exe").read_bytes() == b"legacy"
    assert ReleaseManifest.load(copied).legacy is True
    assert not (paths.staging_dir / "legacy-op-legacy-copy-fallback").exists()


@pytest.mark.scenario("desktop-versioned-update-rollback", "Legacy Install 無法建立可用副本")
def test_legacy_migration_failure_keeps_original_install(tmp_path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    original = paths.program_root / "BAP.exe"
    original.write_bytes(b"legacy")
    calls = 0

    def probe(_exe, _output):
        nonlocal calls
        calls += 1
        if calls == 1:
            return "0.1.6"
        raise UpdateRuntimeError("copy does not start")

    monkeypatch.setattr("bap_desktop.update_runtime.updater._probe_runtime_version", probe)
    with pytest.raises(UpdateRuntimeError, match="copy does not start"):
        migrate_legacy_install(paths, "op-legacy-fail")

    assert original.read_bytes() == b"legacy"
    assert not paths.release_dir("0.1.6").exists()
    assert not paths.state_file.exists()


@pytest.mark.scenario("desktop-versioned-update-rollback", "Candidate 安裝中斷")
def test_missing_candidate_manifest_keeps_existing_active_release(tmp_path) -> None:
    paths = _paths(tmp_path)
    _release(paths, "0.1.6")
    ActiveReleaseState(active_version="0.1.6").save(paths.state_file)
    paths.release_dir("0.1.7").mkdir()

    with pytest.raises(UpdateRuntimeError, match="安裝不完整"):
        finalize_installed_release(
            paths,
            version="0.1.7",
            operation_id="op-incomplete",
            launch_and_wait=False,
        )
    assert ActiveReleaseState.load(paths.state_file).active_version == "0.1.6"


def test_apply_wait_timeout_cancels_before_installer_runs(tmp_path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    installer = paths.update_root / "op-wait" / "BAP-Setup-0.1.7.exe"
    installer.parent.mkdir(parents=True)
    installer.write_bytes(b"candidate")
    called = []
    monkeypatch.setattr("bap_desktop.update_runtime.updater.wait_for_process_exit", lambda *_args: False)
    monkeypatch.setattr("bap_desktop.update_runtime.updater._run_installer", lambda *_args: called.append(True))

    with pytest.raises(UpdateRuntimeError, match="尚未關閉"):
        apply_update(
            paths,
            installer=installer,
            version="0.1.7",
            sha256=hashlib.sha256(b"candidate").hexdigest(),
            old_pid=999,
            operation_id="op-wait",
        )
    assert called == []
    assert not paths.lock_file.exists()


def test_apply_installs_candidate_without_overwriting_active_release(tmp_path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    _release(paths, "0.1.6")
    ActiveReleaseState("0.1.6").save(paths.state_file)
    old_bytes = (paths.release_dir("0.1.6") / "BAP.exe").read_bytes()
    installer = tmp_path / "candidate.exe"
    installer.write_bytes(b"candidate-installer")
    digest = hashlib.sha256(installer.read_bytes()).hexdigest()
    finalized = []

    def install(_installer, install_paths):
        _release(install_paths, "0.1.7")

    monkeypatch.setattr("bap_desktop.update_runtime.updater._run_installer", install)
    monkeypatch.setattr(
        "bap_desktop.update_runtime.updater.finalize_installed_release",
        lambda install_paths, **kwargs: finalized.append((install_paths, kwargs["version"])),
    )

    apply_update(
        paths,
        installer=installer,
        version="0.1.7",
        sha256=digest,
        old_pid=0,
        operation_id="op-install-success",
    )

    assert finalized == [(paths, "0.1.7")]
    assert (paths.release_dir("0.1.6") / "BAP.exe").read_bytes() == old_bytes
    assert (paths.release_dir("0.1.7") / "BAP.exe").is_file()


def test_apply_installer_interruption_keeps_active_release(tmp_path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    _release(paths, "0.1.6")
    ActiveReleaseState("0.1.6").save(paths.state_file)
    installer = tmp_path / "candidate.exe"
    installer.write_bytes(b"candidate-installer")
    digest = hashlib.sha256(installer.read_bytes()).hexdigest()

    def interrupt(*_args, **_kwargs):
        raise OSError("interrupted")

    monkeypatch.setattr("bap_desktop.update_runtime.updater._run_installer", interrupt)

    with pytest.raises(UpdateRuntimeError, match="原本版本不受影響"):
        apply_update(
            paths,
            installer=installer,
            version="0.1.7",
            sha256=digest,
            old_pid=0,
            operation_id="op-install-interrupted",
        )

    assert ActiveReleaseState.load(paths.state_file).active_version == "0.1.6"
    journal = json.loads(
        (paths.operation_dir("op-install-interrupted") / "operation.json").read_text(
            encoding="utf-8"
        )
    )
    assert journal["status"] == "install_failed"
