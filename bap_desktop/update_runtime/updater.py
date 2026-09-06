"""Transactional installer handoff, version cutover, and rollback."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from bap_desktop.update_runtime.models import (
    ActiveReleaseState,
    OperationJournal,
    ReleaseManifest,
    UpdateContractError,
    UpdatePaths,
    atomic_write_json,
    read_json,
    utc_now_text,
    validate_token,
    validate_version,
)
from bap_desktop.update_runtime.processes import (
    process_is_running,
    spawn_detached,
    terminate_process,
    wait_for_process_exit,
)


class UpdateRuntimeError(RuntimeError):
    """An update could not preserve a known-good Desktop release."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_installer(path: Path, expected_sha256: str) -> None:
    if not Path(path).is_file():
        raise UpdateRuntimeError("找不到已下載的更新安裝檔")
    expected = expected_sha256.strip().lower()
    if len(expected) != 64 or any(character not in "0123456789abcdef" for character in expected):
        raise UpdateRuntimeError("更新安裝檔的 SHA-256 格式不正確")
    if not hmac.compare_digest(sha256_file(path), expected):
        raise UpdateRuntimeError("更新安裝檔 SHA-256 驗證失敗")


def _reserve_update(paths: UpdatePaths, operation_id: str) -> None:
    paths.update_root.mkdir(parents=True, exist_ok=True)
    if paths.lock_file.exists():
        try:
            value = read_json(paths.lock_file)
            existing_operation = str(value.get("operation_id", ""))
            journal_path = paths.operation_dir(existing_operation) / "operation.json"
            terminal = (
                read_json(journal_path).get("status")
                in {"succeeded", "install_failed", "health_failed", "rolled_back", "rollback_failed"}
                if journal_path.is_file()
                else False
            )
            stale = time.time() - paths.lock_file.stat().st_mtime > 3600
        except (OSError, UpdateContractError):
            terminal = False
            stale = False
        if terminal or stale:
            paths.lock_file.unlink(missing_ok=True)
        else:
            raise UpdateRuntimeError("另一個 BAP 更新正在進行中")
    try:
        descriptor = os.open(paths.lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise UpdateRuntimeError("另一個 BAP 更新正在進行中") from error
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(
            {
                "schema_version": 1,
                "operation_id": operation_id,
                "reserved_at": utc_now_text(),
            },
            stream,
        )
        stream.flush()
        os.fsync(stream.fileno())


def _release_update(paths: UpdatePaths, operation_id: str) -> None:
    try:
        value = read_json(paths.lock_file)
    except UpdateContractError:
        return
    if value.get("operation_id") == operation_id:
        paths.lock_file.unlink(missing_ok=True)


def _helper_command(
    paths: UpdatePaths,
    *,
    installer: Path,
    version: str,
    sha256: str,
    old_pid: int,
    operation_id: str,
) -> list[str]:
    accepted_file = paths.operation_dir(operation_id) / "accepted.json"
    common = [
        "apply",
        "--installer",
        str(installer),
        "--version",
        version,
        "--sha256",
        sha256,
        "--old-pid",
        str(old_pid),
        "--operation-id",
        operation_id,
        "--accepted-file",
        str(accepted_file),
        "--program-root",
        str(paths.program_root),
        "--user-data-root",
        str(paths.user_data_root),
        "--reserved",
    ]
    if getattr(sys, "frozen", False):
        helper_dir = paths.operation_dir(operation_id)
        helper = helper_dir / "BAPUpdater.exe"
        helper_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(sys.executable, helper)
        runtime_source = Path(sys.executable).parent / "updater_runtime"
        runtime_target = helper_dir / "updater_runtime"
        if not runtime_source.is_dir():
            raise UpdateRuntimeError("Updater Runtime 不完整，無法安全開始更新")
        if runtime_target.exists():
            shutil.rmtree(runtime_target)
        shutil.copytree(runtime_source, runtime_target)
        return [str(helper), *common]
    return [sys.executable, "-m", "bap_desktop.update_runtime.updater", *common]


def handoff_update(
    paths: UpdatePaths,
    *,
    installer: Path,
    version: str,
    sha256: str,
    old_pid: int,
    operation_id: str,
    process_launcher: Callable[..., object] = spawn_detached,
    helper_timeout: float = 5.0,
) -> Path:
    validate_version(version)
    validate_token(operation_id, label="Operation ID")
    paths.prepare()
    installer = Path(installer).resolve()
    try:
        installer.relative_to(paths.update_root.resolve())
    except ValueError as error:
        raise UpdateRuntimeError("更新安裝檔不在 BAP 更新暫存目錄") from error
    verify_installer(installer, sha256)
    _reserve_update(paths, operation_id)
    accepted = paths.operation_dir(operation_id) / "accepted.json"
    command = _helper_command(
        paths,
        installer=installer,
        version=version,
        sha256=sha256,
        old_pid=old_pid,
        operation_id=operation_id,
    )
    try:
        process = process_launcher(command, cwd=paths.operation_dir(operation_id))
        deadline = time.monotonic() + helper_timeout
        while not accepted.is_file():
            poll = getattr(process, "poll", None)
            if callable(poll) and poll() is not None:
                raise UpdateRuntimeError("Updater helper 未成功啟動")
            if time.monotonic() >= deadline:
                helper_pid = getattr(process, "pid", None)
                if isinstance(helper_pid, int) and helper_pid > 0:
                    terminate_process(helper_pid)
                raise UpdateRuntimeError("Updater helper 未在時間內確認接手")
            time.sleep(0.05)
        acknowledgement = read_json(accepted)
        if acknowledgement.get("operation_id") != operation_id:
            raise UpdateRuntimeError("Updater helper 接手訊號不正確")
    except Exception:
        _release_update(paths, operation_id)
        raise
    return accepted


HealthRunner = Callable[[Path, Path, str, Path], bool]
LauncherRunner = Callable[[UpdatePaths, str | None, Path], int]
ReadyWaiter = Callable[[Path, str, int, float], bool]


def _run_health(
    executable: Path,
    result_file: Path,
    expected_version: str,
    user_data_root: Path,
) -> bool:
    environment = os.environ.copy()
    environment.setdefault("BAP_ENV", "production")
    environment["BAP_DATA_DIR"] = str(user_data_root)
    completed = subprocess.run(
        [
            str(executable),
            "--post-update-health-check",
            "--result-file",
            str(result_file),
            "--expected-version",
            expected_version,
            "--isolated-check",
        ],
        cwd=str(executable.parent),
        env=environment,
        timeout=120,
        check=False,
    )
    return completed.returncode == 0 and result_file.is_file()


def _run_launcher(paths: UpdatePaths, operation_id: str | None, result_file: Path) -> int:
    command = [
        str(paths.launcher_exe),
        "--program-root",
        str(paths.program_root),
        "--user-data-root",
        str(paths.user_data_root),
        "--result-file",
        str(result_file),
        "--",
    ]
    if operation_id:
        command.extend(["--update-operation", operation_id])
    completed = subprocess.run(command, timeout=30, check=False)
    if completed.returncode != 0 or not result_file.is_file():
        raise UpdateRuntimeError("Stable Launcher 無法啟動 BAP")
    value = read_json(result_file)
    pid = value.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        raise UpdateRuntimeError("Stable Launcher 未回報 BAP PID")
    return pid


def wait_for_ready_signal(
    ready_file: Path,
    operation_id: str,
    pid: int,
    timeout_seconds: float,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if ready_file.is_file():
            try:
                value = read_json(ready_file)
            except UpdateContractError:
                return False
            return value.get("operation_id") == operation_id and value.get("pid") == pid
        if not process_is_running(pid):
            return False
        time.sleep(0.1)
    return False


def _probe_runtime_version(executable: Path, output: Path) -> str:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    completed = subprocess.run(
        [str(executable), "--write-version", str(output)],
        cwd=str(executable.parent),
        timeout=60,
        check=False,
    )
    if completed.returncode != 0 or not output.is_file():
        raise UpdateRuntimeError("無法讀取既有 BAP 版本")
    return validate_version(output.read_text(encoding="utf-8").strip())


def migrate_legacy_install(paths: UpdatePaths, operation_id: str) -> str | None:
    """Copy an in-place installation into a verified previous release."""

    if paths.state_file.exists():
        try:
            return ActiveReleaseState.load(paths.state_file).active_version
        except UpdateContractError as error:
            raise UpdateRuntimeError("既有版本狀態損壞，無法安全更新") from error

    legacy_executable = paths.program_root / "BAP.exe"
    if not legacy_executable.is_file():
        return None

    operation_dir = paths.operation_dir(operation_id)
    version = _probe_runtime_version(legacy_executable, operation_dir / "legacy-version.txt")
    destination = paths.release_dir(version)
    if destination.is_dir():
        manifest = ReleaseManifest.load(destination)
        if manifest.version != version:
            raise UpdateRuntimeError("既有版本目錄與版本資訊不一致")
    else:
        staging = paths.staging_dir / f"legacy-{operation_id}"
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        excluded = {
            "releases",
            "staging",
            "BAPLauncher.exe",
            "BAPUpdater.exe",
            "active-release.json",
        }
        try:
            for child in paths.program_root.iterdir():
                if child.name in excluded or child.name.lower().startswith("unins"):
                    continue
                target = staging / child.name
                if child.is_dir():
                    shutil.copytree(child, target)
                elif child.is_file():
                    shutil.copy2(child, target)
            copied_version = _probe_runtime_version(
                staging / "BAP.exe",
                operation_dir / "legacy-copy-version.txt",
            )
            if copied_version != version:
                raise UpdateRuntimeError("既有 BAP 副本版本驗證失敗")
            ReleaseManifest(
                version=version,
                source_tree_sha="0" * 40,
                legacy=True,
            ).save(staging)
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.replace(staging, destination)
            except PermissionError:
                # Windows virus scanners can briefly hold a handle after the
                # version probe. Copy to the final directory, verify it, then
                # remove staging instead of asking the user to uninstall.
                if destination.exists():
                    raise
                try:
                    shutil.copytree(staging, destination)
                    ReleaseManifest.load(destination)
                except Exception:
                    shutil.rmtree(destination, ignore_errors=True)
                    raise
                shutil.rmtree(staging, ignore_errors=True)
        except Exception:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            raise

    ActiveReleaseState(
        active_version=version,
        previous_version=None,
        operation_id=operation_id,
    ).save(paths.state_file)
    return version


def cleanup_old_releases(
    paths: UpdatePaths,
    state: ActiveReleaseState,
    *,
    journal: OperationJournal | None = None,
    running_version: str | None = None,
) -> list[Path]:
    keep = {state.active_version}
    if state.previous_version:
        keep.add(state.previous_version)
    if running_version:
        keep.add(running_version)
    removed: list[Path] = []
    if not paths.releases_dir.is_dir():
        return removed
    for release in sorted(paths.releases_dir.iterdir(), key=lambda item: item.stat().st_mtime):
        if not release.is_dir() or release.name in keep:
            continue
        try:
            validate_version(release.name)
            shutil.rmtree(release)
            removed.append(release)
        except (OSError, UpdateContractError) as error:
            if journal is not None:
                journal.append_cleanup_warning(f"{release.name}: {type(error).__name__}")
    return removed


def finalize_installed_release(
    paths: UpdatePaths,
    *,
    version: str,
    operation_id: str,
    launch_and_wait: bool,
    ready_timeout: float = 30.0,
    health_runner: HealthRunner = _run_health,
    launcher_runner: LauncherRunner = _run_launcher,
    ready_waiter: ReadyWaiter = wait_for_ready_signal,
    process_terminator: Callable[[int], None] = terminate_process,
    journal: OperationJournal | None = None,
) -> ActiveReleaseState:
    validate_version(version)
    validate_token(operation_id, label="Operation ID")
    paths.prepare()
    journal = journal or OperationJournal.create(paths, operation_id, version)
    previous = migrate_legacy_install(paths, operation_id)
    try:
        old_state = ActiveReleaseState.load(paths.state_file)
        previous = old_state.active_version
    except UpdateContractError:
        old_state = None

    release_dir = paths.release_dir(version)
    try:
        manifest = ReleaseManifest.load(release_dir)
    except UpdateContractError as error:
        journal.transition(
            "install_failed",
            "Candidate Release Manifest 驗證失敗",
            error_code="candidate_manifest_invalid",
            previous_version=previous,
        )
        raise UpdateRuntimeError("新版安裝不完整，原本版本不受影響") from error
    if manifest.version != version:
        raise UpdateRuntimeError("Candidate 版本與 Release Manifest 不一致")

    journal.transition("health_check", "正在執行 Candidate Health Check", previous_version=previous)
    health_result = paths.operation_dir(operation_id) / "health.json"
    if not health_runner(
        manifest.entry_path(release_dir), health_result, version, paths.user_data_root
    ):
        journal.transition(
            "health_failed",
            "Candidate 未通過 Health Check",
            error_code="candidate_health_failed",
            previous_version=previous,
        )
        if previous:
            launcher_runner(paths, None, paths.operation_dir(operation_id) / "previous-launch.json")
        raise UpdateRuntimeError("新版未通過檢查，已保留原本版本")

    next_state = ActiveReleaseState(
        active_version=version,
        previous_version=previous if previous != version else None,
        operation_id=operation_id,
    )
    journal.transition("switching", "正在切換 Active Release", previous_version=previous)
    next_state.save(paths.state_file)

    if launch_and_wait:
        journal.transition("waiting_for_ready", "正在等待新版啟動", previous_version=previous)
        launcher_result = paths.operation_dir(operation_id) / "candidate-launch.json"
        candidate_pid = launcher_runner(paths, operation_id, launcher_result)
        ready_file = paths.operation_dir(operation_id) / "ready.json"
        if not ready_waiter(ready_file, operation_id, candidate_pid, ready_timeout):
            process_terminator(candidate_pid)
            journal.transition(
                "ready_timeout",
                "新版未在期限內完成啟動",
                error_code="candidate_ready_timeout",
                previous_version=previous,
            )
            if not previous:
                paths.state_file.unlink(missing_ok=True)
                journal.transition(
                    "rollback_failed",
                    "沒有可回復的舊版本",
                    error_code="no_previous_release",
                )
                raise UpdateRuntimeError("新版無法啟動，且沒有可回復的舊版本")
            ActiveReleaseState(
                active_version=previous,
                previous_version=None,
                operation_id=operation_id,
            ).save(paths.state_file)
            try:
                launcher_runner(paths, None, paths.operation_dir(operation_id) / "rollback-launch.json")
            except Exception as error:
                manual_path = paths.release_dir(previous) / "BAP.exe"
                journal.transition(
                    "rollback_failed",
                    f"自動恢復失敗。請直接執行 {manual_path}",
                    error_code="rollback_launch_failed",
                    previous_version=previous,
                )
                raise UpdateRuntimeError(
                    f"自動恢復失敗。請直接執行 {manual_path}"
                ) from error
            journal.transition("rolled_back", f"已恢復 BAP {previous}", previous_version=previous)
            raise UpdateRuntimeError(f"新版無法啟動，已恢復 BAP {previous}")

    journal.transition("succeeded", f"BAP {version} 更新成功", previous_version=previous)
    cleanup_old_releases(paths, next_state, journal=journal, running_version=version)
    return next_state


def _run_installer(installer: Path, paths: UpdatePaths) -> None:
    completed = subprocess.run(
        [
            str(installer),
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/CURRENTUSER",
            "/BAPMANAGED=1",
            f"/DIR={paths.program_root}",
        ],
        timeout=600,
        check=False,
    )
    if completed.returncode != 0:
        raise UpdateRuntimeError(f"Installer 執行失敗：{completed.returncode}")


def apply_update(
    paths: UpdatePaths,
    *,
    installer: Path,
    version: str,
    sha256: str,
    old_pid: int,
    operation_id: str,
    reserved: bool = False,
    accepted_file: Path | None = None,
) -> None:
    paths.prepare()
    if not reserved:
        _reserve_update(paths, operation_id)
    if accepted_file is not None:
        accepted_file = Path(accepted_file).resolve()
        operation_dir = paths.operation_dir(operation_id).resolve()
        if accepted_file.parent != operation_dir:
            _release_update(paths, operation_id)
            raise UpdateRuntimeError("Updater helper 接手訊號路徑不安全")
        try:
            atomic_write_json(
                accepted_file,
                {
                    "schema_version": 1,
                    "operation_id": operation_id,
                    "helper_pid": os.getpid(),
                    "accepted_at": utc_now_text(),
                },
            )
        except Exception:
            _release_update(paths, operation_id)
            raise
    try:
        journal = OperationJournal.create(paths, operation_id, version)
    except Exception:
        _release_update(paths, operation_id)
        raise
    try:
        verify_installer(installer, sha256)
        journal.transition("waiting_for_app", "正在等待目前 BAP 關閉")
        if old_pid > 0 and not wait_for_process_exit(old_pid, 120):
            journal.transition(
                "install_failed",
                "目前 BAP 未在期限內關閉",
                error_code="old_process_timeout",
            )
            raise UpdateRuntimeError("目前 BAP 尚未關閉，更新已取消")
        journal.transition("installing", "正在安裝 Candidate")
        try:
            _run_installer(installer, paths)
        except Exception as error:
            journal.transition("install_failed", "Installer 執行失敗", error_code="installer_failed")
            raise UpdateRuntimeError("新版安裝失敗，原本版本不受影響") from error
        finalize_installed_release(
            paths,
            version=version,
            operation_id=operation_id,
            launch_and_wait=True,
            journal=journal,
        )
    finally:
        _release_update(paths, operation_id)


def _show_message(message: str, *, error: bool = False) -> None:
    if os.name == "nt" and os.environ.get("BAP_ENV", "").lower() != "test":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, message, "BAP 更新", 0x10 if error else 0x40)
            return
        except (AttributeError, OSError):
            pass
    print(message, file=sys.stderr if error else sys.stdout)


def _add_roots(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--program-root", type=Path)
    parser.add_argument("--user-data-root", type=Path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BAP versioned Desktop updater")
    commands = parser.add_subparsers(dest="command", required=True)

    handoff = commands.add_parser("handoff")
    handoff.add_argument("--installer", type=Path, required=True)
    handoff.add_argument("--version", required=True)
    handoff.add_argument("--sha256", required=True)
    handoff.add_argument("--old-pid", type=int, required=True)
    handoff.add_argument("--operation-id", required=True)
    _add_roots(handoff)

    apply_parser = commands.add_parser("apply")
    apply_parser.add_argument("--installer", type=Path, required=True)
    apply_parser.add_argument("--version", required=True)
    apply_parser.add_argument("--sha256", required=True)
    apply_parser.add_argument("--old-pid", type=int, required=True)
    apply_parser.add_argument("--operation-id", required=True)
    apply_parser.add_argument("--accepted-file", type=Path)
    apply_parser.add_argument("--reserved", action="store_true")
    _add_roots(apply_parser)

    finalize = commands.add_parser("finalize")
    finalize.add_argument("--version", required=True)
    finalize.add_argument("--operation-id", default=None)
    finalize.add_argument("--launch-and-wait", action="store_true")
    finalize.add_argument("--ready-timeout", type=float, default=30.0)
    _add_roots(finalize)

    cleanup = commands.add_parser("cleanup")
    _add_roots(cleanup)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    paths = UpdatePaths.from_environment(program_root=args.program_root, user_data_root=args.user_data_root)
    try:
        if args.command == "handoff":
            handoff_update(
                paths,
                installer=args.installer,
                version=args.version,
                sha256=args.sha256,
                old_pid=args.old_pid,
                operation_id=args.operation_id,
            )
        elif args.command == "apply":
            apply_update(
                paths,
                installer=args.installer,
                version=args.version,
                sha256=args.sha256,
                old_pid=args.old_pid,
                operation_id=args.operation_id,
                reserved=args.reserved,
                accepted_file=args.accepted_file,
            )
        elif args.command == "finalize":
            operation_id = args.operation_id or str(uuid.uuid4())
            finalize_installed_release(
                paths,
                version=args.version,
                operation_id=operation_id,
                launch_and_wait=args.launch_and_wait,
                ready_timeout=args.ready_timeout,
            )
        else:
            try:
                state = ActiveReleaseState.load(paths.state_file)
            except UpdateContractError:
                return 0
            cleanup_old_releases(paths, state)
    except (OSError, UpdateContractError, UpdateRuntimeError, subprocess.SubprocessError) as error:
        _show_message(str(error), error=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
