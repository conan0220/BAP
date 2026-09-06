"""Offline post-install health check and update readiness signaling."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable

from bap_desktop import __version__
from bap_desktop.update_runtime.models import (
    ReleaseManifest,
    UpdateContractError,
    atomic_write_json,
    utc_now_text,
    validate_token,
)


class _HealthSession:
    api = object()

    def restore(self) -> bool:
        return False

    def logout(self) -> None:
        return None

    def close(self) -> None:
        return None


def _source_tree_sha() -> str:
    executable_dir = Path(sys.executable).resolve().parent
    candidates = [executable_dir, Path(__file__).resolve().parents[2]]
    for root in candidates:
        try:
            return ReleaseManifest.load(root, require_entry=False).source_tree_sha
        except UpdateContractError:
            continue
    return "development"


def _injected_failure(name: str) -> bool:
    return (
        os.environ.get("BAP_ENV", "").lower() == "test"
        and os.environ.get("BAP_TEST_HEALTH_FAILURE", "").lower() == name
    )


def run_post_update_health_check(
    result_file: Path,
    *,
    expected_version: str | None = None,
) -> int:
    """Run deterministic local checks and always write a machine-readable result."""

    checks: dict[str, dict[str, str | bool]] = {}

    def run(name: str, check: Callable[[], None]) -> None:
        try:
            if _injected_failure(name):
                raise RuntimeError("test-only injected failure")
            check()
        except Exception as error:
            checks[name] = {
                "ok": False,
                "error_code": f"{name}_failed",
                "message": type(error).__name__,
            }
        else:
            checks[name] = {"ok": True, "error_code": "", "message": "ok"}

    def version_check() -> None:
        if expected_version is not None and __version__ != expected_version:
            raise RuntimeError("runtime version mismatch")

    def qt_check() -> None:
        import PySide6
        from PySide6.QtCore import QLibraryInfo

        if not PySide6.__version__ or not QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath):
            raise RuntimeError("Qt plugin path unavailable")

    def resource_check() -> None:
        from bap_desktop.resources import text

        if not text.APP_TITLE or not text.UPDATE_FAILED:
            raise RuntimeError("required UI text unavailable")

    def window_check() -> None:
        from PySide6.QtWidgets import QApplication

        from bap_desktop.ui.main_window import MainWindow

        app = QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QApplication(["BAP-health-check"])
        window = MainWindow(_HealthSession(), restore_session=False)
        window.close()
        window.deleteLater()
        app.processEvents()
        if owns_app:
            app.quit()

    def data_check() -> None:
        operation_dir = Path(result_file).resolve().parent
        operation_dir.mkdir(parents=True, exist_ok=True)
        probe = operation_dir / ".write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()

    run("version", version_check)
    run("qt_runtime", qt_check)
    run("resources", resource_check)
    run("main_window", window_check)
    run("user_data", data_check)
    ok = all(bool(value["ok"]) for value in checks.values())
    first_error = next(
        (str(value["error_code"]) for value in checks.values() if not value["ok"]),
        None,
    )
    atomic_write_json(
        Path(result_file),
        {
            "schema_version": 1,
            "status": "ok" if ok else "failed",
            "version": __version__,
            "source_tree_sha": _source_tree_sha(),
            "completed_at": utc_now_text(),
            "error_code": first_error,
            "checks": checks,
        },
    )
    return 0 if ok else 1


def write_ready_signal(update_root: Path, operation_id: str) -> Path | None:
    """Tell the detached updater that the new Qt event loop is responsive."""

    validate_token(operation_id, label="Operation ID")
    if (
        os.environ.get("BAP_ENV", "").lower() == "test"
        and os.environ.get("BAP_TEST_SUPPRESS_READY_SIGNAL") == "1"
    ):
        return None
    path = Path(update_root) / operation_id / "ready.json"
    atomic_write_json(
        path,
        {
            "schema_version": 1,
            "operation_id": operation_id,
            "version": __version__,
            "pid": os.getpid(),
            "ready_at": utc_now_text(),
        },
    )
    return path
