"""Stable BAP launcher that resolves the active version at runtime."""

from __future__ import annotations

import argparse
import ctypes
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

from bap_desktop.update_runtime.models import (
    ActiveReleaseState,
    ReleaseManifest,
    UpdateContractError,
    UpdatePaths,
    atomic_write_json,
    utc_now_text,
)


class LauncherError(RuntimeError):
    """No safe Desktop release could be started."""


@dataclass(frozen=True, slots=True)
class LauncherSelection:
    version: str
    release_dir: Path
    executable: Path
    used_fallback: bool = False


ProcessLauncher = Callable[[Sequence[str], Path, Mapping[str, str]], object]


def _spawn(
    command: Sequence[str], cwd: Path, environment: Mapping[str, str]
) -> subprocess.Popen:
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    return subprocess.Popen(
        list(command),
        cwd=str(cwd),
        env=dict(environment),
        close_fds=True,
        creationflags=creationflags,
    )


def _append_log(paths: UpdatePaths, message: str) -> None:
    paths.log_dir.mkdir(parents=True, exist_ok=True)
    with (paths.log_dir / "bap-launcher.log").open("a", encoding="utf-8") as stream:
        stream.write(f"{utc_now_text()} {message}\n")


def _release_selection(paths: UpdatePaths, version: str, *, fallback: bool) -> LauncherSelection:
    release_dir = paths.release_dir(version)
    manifest = ReleaseManifest.load(release_dir)
    if manifest.version != version:
        raise UpdateContractError("Release directory and manifest versions differ")
    return LauncherSelection(
        version=version,
        release_dir=release_dir,
        executable=manifest.entry_path(release_dir),
        used_fallback=fallback,
    )


def select_active_release(paths: UpdatePaths) -> LauncherSelection:
    try:
        state = ActiveReleaseState.load(paths.state_file)
    except UpdateContractError as error:
        _append_log(paths, f"active state invalid: {error}")
        raise LauncherError(
            "找不到可用的 BAP 版本。請重新執行最新版安裝程式進行修復。"
        ) from error

    try:
        return _release_selection(paths, state.active_version, fallback=False)
    except UpdateContractError as active_error:
        _append_log(paths, f"active release {state.active_version} invalid: {active_error}")

    if state.previous_version:
        try:
            selection = _release_selection(paths, state.previous_version, fallback=True)
        except UpdateContractError as previous_error:
            _append_log(
                paths,
                f"previous release {state.previous_version} invalid: {previous_error}",
            )
        else:
            ActiveReleaseState(
                active_version=selection.version,
                previous_version=None,
                operation_id=state.operation_id,
            ).save(paths.state_file)
            _append_log(paths, f"fell back to previous release {selection.version}")
            return selection

    raise LauncherError(
        "目前版本與上一個版本都無法啟動。請重新執行最新版 BAP 安裝程式進行修復。"
    )


def launch_active_release(
    paths: UpdatePaths,
    app_arguments: Sequence[str] = (),
    *,
    process_launcher: ProcessLauncher = _spawn,
) -> tuple[LauncherSelection, object]:
    selection = select_active_release(paths)
    environment = os.environ.copy()
    environment["BAP_DATA_DIR"] = str(paths.user_data_root)
    process = process_launcher(
        [str(selection.executable), *app_arguments], selection.release_dir, environment
    )
    return selection, process


def _show_error(message: str) -> None:
    if os.name == "nt":
        try:
            ctypes.windll.user32.MessageBoxW(0, message, "BAP 無法啟動", 0x10)
            return
        except (AttributeError, OSError):
            pass
    print(message, file=sys.stderr)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="啟動目前可用的 BAP Desktop App")
    parser.add_argument("--program-root", type=Path)
    parser.add_argument("--user-data-root", type=Path)
    parser.add_argument("--result-file", type=Path)
    parser.add_argument("--print-selected-version", action="store_true")
    parser.add_argument("app_arguments", nargs=argparse.REMAINDER)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    paths = UpdatePaths.from_environment(
        program_root=args.program_root,
        user_data_root=args.user_data_root,
    )
    app_arguments = list(args.app_arguments)
    if app_arguments and app_arguments[0] == "--":
        app_arguments.pop(0)
    try:
        selection, process = launch_active_release(paths, app_arguments)
    except (LauncherError, OSError) as error:
        _show_error(str(error))
        return 1
    pid = getattr(process, "pid", None)
    if args.result_file is not None:
        atomic_write_json(
            args.result_file,
            {
                "schema_version": 1,
                "version": selection.version,
                "pid": pid,
                "used_fallback": selection.used_fallback,
            },
        )
    if args.print_selected_version:
        print(selection.version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
