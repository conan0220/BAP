from __future__ import annotations

import json
from pathlib import Path

import pytest

from bap_desktop import __version__
from bap_desktop.update_runtime.health import (
    run_post_update_health_check,
    write_ready_signal,
)
from bap_desktop.update_runtime.launcher import (
    LauncherError,
    launch_active_release,
    select_active_release,
)
from bap_desktop.update_runtime.models import (
    ActiveReleaseState,
    ReleaseManifest,
    UpdatePaths,
)


def _paths(tmp_path: Path) -> UpdatePaths:
    paths = UpdatePaths.from_environment(
        program_root=tmp_path / "program",
        user_data_root=tmp_path / "data",
    )
    paths.prepare()
    return paths


def _release(paths: UpdatePaths, version: str, *, executable: bool = True) -> Path:
    root = paths.release_dir(version)
    root.mkdir(parents=True)
    if executable:
        (root / "BAP.exe").write_bytes(b"runtime")
    ReleaseManifest(version=version, source_tree_sha="a" * 40).save(root)
    return root


@pytest.mark.scenario("desktop-versioned-update-rollback", "正常啟動 BAP")
def test_launcher_starts_active_release_and_forwards_arguments(tmp_path) -> None:
    paths = _paths(tmp_path)
    release = _release(paths, "0.1.7")
    ActiveReleaseState(active_version="0.1.7").save(paths.state_file)
    calls = []

    selection, process = launch_active_release(
        paths,
        ["--write-version", "version.txt"],
        process_launcher=lambda command, cwd, environment: calls.append(
            (list(command), cwd, environment)
        )
        or object(),
    )

    assert selection.version == "0.1.7"
    assert process is not None
    assert calls[0][0] == [str(release / "BAP.exe"), "--write-version", "version.txt"]
    assert calls[0][1] == release
    assert calls[0][2]["BAP_DATA_DIR"] == str(paths.user_data_root)


@pytest.mark.scenario("desktop-versioned-update-rollback", "Active Release 不存在或無法讀取")
def test_launcher_falls_back_to_previous_and_repairs_state(tmp_path) -> None:
    paths = _paths(tmp_path)
    previous = _release(paths, "0.1.6")
    _release(paths, "0.1.7", executable=False)
    ActiveReleaseState(
        active_version="0.1.7",
        previous_version="0.1.6",
        operation_id="op-1",
    ).save(paths.state_file)

    selection = select_active_release(paths)

    assert selection.version == "0.1.6"
    assert selection.release_dir == previous
    assert selection.used_fallback is True
    repaired = ActiveReleaseState.load(paths.state_file)
    assert repaired.active_version == "0.1.6"
    assert repaired.previous_version is None
    assert "fell back" in (paths.log_dir / "bap-launcher.log").read_text(encoding="utf-8")


@pytest.mark.scenario("desktop-versioned-update-rollback", "Active Release 不存在或無法讀取")
def test_launcher_reports_repair_when_active_and_previous_are_invalid(tmp_path) -> None:
    paths = _paths(tmp_path)
    ActiveReleaseState(active_version="0.1.7", previous_version="0.1.6").save(paths.state_file)

    with pytest.raises(LauncherError, match="重新執行最新版"):
        select_active_release(paths)


@pytest.mark.scenario("desktop-versioned-update-rollback", "Candidate 通過 Health Check")
def test_post_update_health_check_is_offline_and_machine_readable(
    tmp_path, monkeypatch, qapp
) -> None:
    result = tmp_path / "data" / "updates" / "op" / "health.json"
    settings = tmp_path / "data" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text('{"sentinel": true}', encoding="utf-8")
    monkeypatch.setenv("BAP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("BAP_TEST_HEALTH_FAILURE", raising=False)

    assert run_post_update_health_check(result, expected_version=__version__) == 0

    value = json.loads(result.read_text(encoding="utf-8"))
    assert value["status"] == "ok"
    assert value["version"] == __version__
    assert set(value["checks"]) == {
        "version",
        "qt_runtime",
        "resources",
        "main_window",
        "user_data",
    }
    assert settings.read_text(encoding="utf-8") == '{"sentinel": true}'


@pytest.mark.scenario("desktop-versioned-update-rollback", "Candidate 未通過 Health Check")
@pytest.mark.parametrize(
    "failure",
    ["version", "qt_runtime", "resources", "main_window", "user_data"],
)
def test_post_update_health_check_fails_closed_for_each_required_check(
    tmp_path, monkeypatch, qapp, failure
) -> None:
    monkeypatch.setenv("BAP_ENV", "test")
    monkeypatch.setenv("BAP_TEST_HEALTH_FAILURE", failure)
    result = tmp_path / failure / "health.json"

    assert run_post_update_health_check(result, expected_version=__version__) == 1

    value = json.loads(result.read_text(encoding="utf-8"))
    assert value["status"] == "failed"
    assert value["error_code"] == f"{failure}_failed"
    assert value["checks"][failure]["ok"] is False


@pytest.mark.scenario("desktop-versioned-update-rollback", "新版成功送出 Ready Signal")
def test_ready_signal_is_atomic_and_contains_runtime_identity(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("BAP_TEST_SUPPRESS_READY_SIGNAL", raising=False)
    path = write_ready_signal(tmp_path / "updates", "operation-1")
    assert path is not None
    value = json.loads(path.read_text(encoding="utf-8"))
    assert value["operation_id"] == "operation-1"
    assert value["version"] == __version__
    assert value["pid"] > 0


def test_ready_signal_can_only_be_suppressed_in_test_environment(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BAP_TEST_SUPPRESS_READY_SIGNAL", "1")
    monkeypatch.setenv("BAP_ENV", "production")
    assert write_ready_signal(tmp_path, "operation-1") is not None

    monkeypatch.setenv("BAP_ENV", "test")
    assert write_ready_signal(tmp_path, "operation-2") is None
