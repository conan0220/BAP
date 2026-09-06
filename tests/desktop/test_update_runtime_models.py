from __future__ import annotations

import json
from pathlib import Path

import pytest

from bap_desktop.update_runtime.models import (
    ActiveReleaseState,
    OperationJournal,
    ReleaseManifest,
    UpdateContractError,
    UpdatePaths,
    atomic_write_json,
)


@pytest.mark.scenario("desktop-versioned-update-rollback", "從既有版本安裝新版")
def test_update_paths_keep_program_releases_and_user_data_separate(tmp_path) -> None:
    paths = UpdatePaths.from_environment(
        program_root=tmp_path / "Programs" / "BAP",
        user_data_root=tmp_path / "BAP",
    )
    paths.prepare()

    assert paths.release_dir("0.1.7") == tmp_path / "Programs" / "BAP" / "releases" / "0.1.7"
    assert paths.operation_dir("operation-1") == tmp_path / "BAP" / "updates" / "operation-1"
    assert paths.releases_dir.is_dir()
    assert paths.update_root.is_dir()
    assert paths.program_root not in paths.user_data_root.parents
    assert paths.user_data_root not in paths.program_root.parents


def test_update_paths_reject_nested_or_equal_roots(tmp_path) -> None:
    with pytest.raises(UpdateContractError, match="must be separate"):
        UpdatePaths.from_environment(program_root=tmp_path / "BAP", user_data_root=tmp_path / "BAP")
    with pytest.raises(UpdateContractError, match="must be separate"):
        UpdatePaths.from_environment(
            program_root=tmp_path / "BAP",
            user_data_root=tmp_path / "BAP" / "data",
        )


def test_release_manifest_round_trip_and_fail_closed_validation(tmp_path) -> None:
    release = tmp_path / "releases" / "0.1.7"
    release.mkdir(parents=True)
    (release / "BAP.exe").write_bytes(b"runtime")
    manifest = ReleaseManifest(
        version="0.1.7",
        source_tree_sha="a" * 40,
        entry_point="BAP.exe",
    )
    manifest.save(release)

    assert ReleaseManifest.load(release) == manifest

    bad_values = [
        {**json.loads((release / "release-manifest.json").read_text()), "version": "../bad"},
        {**json.loads((release / "release-manifest.json").read_text()), "source_tree_sha": "short"},
        {**json.loads((release / "release-manifest.json").read_text()), "entry_point": "../BAP.exe"},
    ]
    for value in bad_values:
        (release / "release-manifest.json").write_text(json.dumps(value), encoding="utf-8")
        with pytest.raises(UpdateContractError):
            ReleaseManifest.load(release)


def test_release_manifest_rejects_missing_entry_point(tmp_path) -> None:
    release = tmp_path / "0.1.7"
    release.mkdir()
    ReleaseManifest(version="0.1.7", source_tree_sha="b" * 40).save(release)
    with pytest.raises(UpdateContractError, match="does not exist"):
        ReleaseManifest.load(release)


def test_active_state_round_trip_and_rejects_corruption(tmp_path) -> None:
    state_file = tmp_path / "active-release.json"
    state = ActiveReleaseState(
        active_version="0.1.7",
        previous_version="0.1.6",
        operation_id="operation-1",
    )
    state.save(state_file)
    assert ActiveReleaseState.load(state_file) == state

    state_file.write_text("{not-json", encoding="utf-8")
    with pytest.raises(UpdateContractError, match="Unable to read"):
        ActiveReleaseState.load(state_file)


def test_atomic_write_keeps_previous_state_when_replace_fails(tmp_path, monkeypatch) -> None:
    target = tmp_path / "state.json"
    target.write_text('{"old": true}\n', encoding="utf-8")

    def fail_replace(_source, _target):
        raise OSError("simulated interruption")

    monkeypatch.setattr("bap_desktop.update_runtime.models.os.replace", fail_replace)
    with pytest.raises(OSError, match="interruption"):
        atomic_write_json(target, {"new": True})

    assert json.loads(target.read_text()) == {"old": True}
    assert not tuple(tmp_path.glob(".*.tmp"))


def test_operation_journal_records_success_failures_and_cleanup_warning(tmp_path) -> None:
    paths = UpdatePaths.from_environment(
        program_root=tmp_path / "program",
        user_data_root=tmp_path / "data",
    )
    journal = OperationJournal.create(paths, "op-123", "0.1.7")
    journal.transition("health_failed", "Qt plugin missing", error_code="qt_plugin_missing")
    journal.append_cleanup_warning("old release is locked")

    value = json.loads(journal.path.read_text(encoding="utf-8"))
    assert value["status"] == "health_failed"
    assert value["error_code"] == "qt_plugin_missing"
    assert [event["status"] for event in value["events"]] == [
        "accepted",
        "health_failed",
        "cleanup_warning",
    ]
