"""BAP Desktop App entry point."""

from __future__ import annotations

import json
import os
import sys
import uuid
from collections.abc import Callable
from pathlib import Path

from bap_desktop import APP_NAME, PRODUCT_NAME, __version__


def _argument_value(name: str) -> str | None:
    if name not in sys.argv:
        return None
    index = sys.argv.index(name)
    return sys.argv[index + 1] if index + 1 < len(sys.argv) else None


def _qt_arguments(arguments: list[str]) -> list[str]:
    private_with_value = {"--update-operation"}
    private_flags = {"--smoke-test"}
    filtered = [arguments[0]]
    index = 1
    while index < len(arguments):
        item = arguments[index]
        if item in private_flags:
            index += 1
            continue
        if item in private_with_value:
            index += 2
            continue
        filtered.append(item)
        index += 1
    return filtered


def _installed_program_root() -> Path | None:
    """Find Program Root from a frozen versioned Runtime; use defaults in development."""

    if not getattr(sys, "frozen", False):
        return None
    executable_dir = Path(sys.executable).resolve().parent
    if executable_dir.parent.name.lower() == "releases":
        return executable_dir.parent.parent
    return executable_dir


def _write_api_e2e_result(path: Path, payload: dict[str, object]) -> None:
    """Write machine-readable E2E progress without leaving a partial JSON file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _run_api_e2e_command(result_path: Path | None) -> int:
    """Run packaged E2E without allowing a GUI exception dialog to block CI."""

    stage = "starting"

    def report(next_stage: str) -> None:
        nonlocal stage
        stage = next_stage
        if result_path is not None:
            _write_api_e2e_result(
                result_path,
                {
                    "schema_version": 1,
                    "status": "running",
                    "stage": stage,
                    "desktop_version": __version__,
                },
            )

    report(stage)
    try:
        exit_code = _run_api_e2e(report)
    except Exception as error:
        if result_path is not None:
            _write_api_e2e_result(
                result_path,
                {
                    "schema_version": 1,
                    "status": "failed",
                    "stage": stage,
                    "desktop_version": __version__,
                    "error_type": type(error).__name__,
                    "message": str(error) or "Packaged API E2E failed",
                },
            )
        return 1
    if result_path is not None:
        _write_api_e2e_result(
            result_path,
            {
                "schema_version": 1,
                "status": "succeeded" if exit_code == 0 else "failed",
                "stage": "completed",
                "desktop_version": __version__,
                "exit_code": exit_code,
            },
        )
    return exit_code


def _run_api_e2e(report_progress: Callable[[str], None] | None = None) -> int:
    """Exercise the packaged clients against a real CI Backend over HTTP."""

    report = report_progress or (lambda _stage: None)

    import io
    import tempfile
    from datetime import datetime, timezone
    from uuid import uuid4

    from anrot_imu_driver.parsers.anrot_serial_parser import AnrotFrame
    from bap_common.analysis_session import (
        AnalysisInputBinding,
        AnalysisJobRequest,
        CsvDescriptor,
        ImuSourceDescriptor,
        SessionMetadata,
        SourceConnectionType,
    )
    from bap_common.imu_csv import frame_csv_row, inspect_common_imu_csv_bytes, write_header
    from bap_desktop.api_client import (
        AnalysisApiClient,
        ApiRejectedError,
        AuthApiClient,
        ReleaseApiClient,
    )
    from bap_desktop.settings import DesktopSettings

    report("settings")
    settings = DesktopSettings()
    base_url = str(settings.api_base_url)
    username = "E2E" + uuid.uuid4().hex[:12]
    password = "BapE2E12345"
    auth = AuthApiClient(base_url)
    report("register")
    created = auth.register(username, password)
    if created.get("username") != username:
        raise RuntimeError("register response did not contain the expected Username")
    report("invalid_login")
    try:
        auth.login(username, password + "wrong")
    except ApiRejectedError as error:
        if error.status_code != 401:
            raise
    else:
        raise RuntimeError("invalid login was unexpectedly accepted")
    report("duplicate_register")
    try:
        auth.register(username, password)
    except ApiRejectedError as error:
        if error.status_code != 409:
            raise
    else:
        raise RuntimeError("duplicate Username was unexpectedly accepted")
    report("login")
    tokens = auth.login(username, password)
    analysis = AnalysisApiClient(base_url)
    report("analysis_capabilities")
    capabilities = analysis.capabilities(tokens.access_token)
    punch_count = next(
        item for item in capabilities if item.specification.analysis_type == "punch_count"
    )
    if not punch_count.executable:
        raise RuntimeError("CI Reference Executor is not available")

    def fake_csv(seed: float) -> bytes:
        output = io.StringIO(newline="")
        writer = write_header(output)
        frame = AnrotFrame()
        frame.frame_type = 0x91
        frame.system_time_ms = 1
        frame.acc = (seed, seed + 1, seed + 2)
        frame.gyr = (3.0, 4.0, 5.0)
        frame.mag = (6.0, 7.0, 8.0)
        frame.quat = (1.0, 0.0, 0.0, 0.0)
        frame.roll = frame.pitch = frame.yaw = 0.0
        writer.writerow(frame_csv_row(frame, sample_index=0, packet_index=0, elapsed_us=0))
        return output.getvalue().encode("utf-8")

    with tempfile.TemporaryDirectory(prefix="bap-installed-e2e-") as temp:
        root = Path(temp)
        descriptors = []
        for name, seed in (("left.csv", 1.0), ("right.csv", 2.0)):
            data = fake_csv(seed)
            (root / name).write_bytes(data)
            inspected = inspect_common_imu_csv_bytes(data)
            descriptors.append(CsvDescriptor(
                csv_id=uuid4(), filename=name,
                source=ImuSourceDescriptor(
                    source_id=f"ci:{name}", port=f"FAKE-{name}",
                    connection_type=SourceConnectionType.WIRED, baud_rate=921600,
                ),
                row_count=inspected.row_count, size_bytes=inspected.size_bytes,
                sha256=inspected.sha256,
            ))
        job = AnalysisJobRequest(
            analysis_id=uuid4(), analysis_type="punch_count", spec_version=1,
            input_bindings=(
                AnalysisInputBinding(input_role="left_wrist", csv_id=descriptors[0].csv_id),
                AnalysisInputBinding(input_role="right_wrist", csv_id=descriptors[1].csv_id),
            ),
        )
        now = datetime.now(timezone.utc)
        metadata = SessionMetadata(
            session_id=uuid4(), desktop_version=__version__, started_at=now, ended_at=now,
            csv_files=tuple(descriptors), analyses=(job,),
        )
        report("upload_session")
        accepted = analysis.upload(root, metadata, tokens.access_token)
        report("analysis_status")
        result = analysis.analysis_status(
            accepted["session_id"], accepted["analysis_ids"][0], tokens.access_token
        )
        if result.get("status") != "completed" or result.get("result", {}).get("total_punch_count") != 2:
            raise RuntimeError("installed Desktop Session-to-Result E2E did not complete")
    report("refresh_token")
    refreshed = auth.refresh(tokens.refresh_token)
    report("logout")
    auth.logout(refreshed.refresh_token)
    report("release_check")
    release = ReleaseApiClient(base_url).latest("windows")
    if not release.source_tree_sha:
        raise RuntimeError("release response did not contain Source Tree SHA")
    report("completed")
    return 0


def main() -> int:
    """Start the Qt application while keeping imports lightweight for tooling."""

    if "--write-version" in sys.argv:
        index = sys.argv.index("--write-version")
        if index + 1 >= len(sys.argv):
            return 2
        Path(sys.argv[index + 1]).write_text(__version__, encoding="utf-8")
        return 0
    if "--api-e2e-test" in sys.argv:
        result_path = _argument_value("--api-e2e-result-file")
        return _run_api_e2e_command(Path(result_path) if result_path else None)
    if "--post-update-health-check" in sys.argv:
        result_path = _argument_value("--result-file")
        if result_path is None:
            return 2
        from bap_desktop.update_runtime.health import run_post_update_health_check

        return run_post_update_health_check(
            Path(result_path),
            expected_version=_argument_value("--expected-version"),
        )

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from bap_desktop.api_client import (
        AnalysisApiClient,
        AuthApiClient,
        AuthenticatedAnalysisClient,
        ReleaseApiClient,
    )
    from bap_desktop.services.analysis_flow import AnalysisFlowService
    from bap_desktop.services.imu_diagnostics import ImuDiagnosticsService
    from bap_desktop.services.session import SessionService
    from bap_desktop.services.update import UpdateInstaller, UpdateService
    from bap_desktop.settings import DesktopSettings
    from bap_desktop.ui.main_window import MainWindow
    from bap_desktop.ui.styles import apply_bap_style

    smoke_test = "--smoke-test" in sys.argv
    app = QApplication(_qt_arguments(sys.argv))
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName(PRODUCT_NAME)
    apply_bap_style(app)
    settings = DesktopSettings()
    settings.prepare_local_directories()
    base_url = str(settings.api_base_url)
    session = SessionService(AuthApiClient(base_url))
    analysis_flow = AnalysisFlowService(
        AuthenticatedAnalysisClient(AnalysisApiClient(base_url), session)
    )
    update_service = UpdateService(
        ReleaseApiClient(base_url),
        current_version=__version__,
        platform="windows",
    )
    update_installer = UpdateInstaller(
        settings.update_dir,
        program_root=_installed_program_root(),
    )
    window = MainWindow(
        session,
        diagnostic_service_factory=lambda: ImuDiagnosticsService(temp_dir=settings.temp_imu_dir),
        update_service=None if smoke_test else update_service,
        update_installer=None if smoke_test else update_installer,
        restore_session=not smoke_test,
        analysis_flow=analysis_flow,
        measurement_sessions_dir=settings.measurement_sessions_dir,
        desktop_version=__version__,
    )
    app.aboutToQuit.connect(window.shutdown)
    window.show()
    operation_id = _argument_value("--update-operation")
    if operation_id:
        from bap_desktop.update_runtime.health import write_ready_signal

        QTimer.singleShot(
            0,
            lambda: write_ready_signal(settings.update_dir, operation_id),
        )
    if smoke_test:
        app.processEvents()
        window.hide()
        return 0
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
