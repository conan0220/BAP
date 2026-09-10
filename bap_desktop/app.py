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


def _wait_for_api_e2e_analysis(
    analysis,
    session_id: str,
    analysis_id: str,
    access_token: str,
    *,
    timeout_seconds: float = 30.0,
    poll_interval_seconds: float = 0.25,
    monotonic=None,
    sleep=None,
) -> dict:
    """Wait for the asynchronous CI reference analysis to reach a terminal state."""

    import time

    monotonic = monotonic or time.monotonic
    sleep = sleep or time.sleep
    deadline = monotonic() + timeout_seconds
    last_status = "unknown"
    while True:
        result = analysis.analysis_status(session_id, analysis_id, access_token)
        last_status = str(result.get("status", "unknown"))
        if last_status == "completed":
            return result
        if last_status == "failed":
            code = result.get("error_code") or "analysis_failed"
            message = result.get("safe_error_message") or "Backend analysis failed"
            raise RuntimeError(f"Backend analysis failed ({code}): {message}")
        if last_status not in {"pending", "processing"}:
            raise RuntimeError(f"Backend returned an unexpected analysis status: {last_status}")
        if monotonic() >= deadline:
            raise RuntimeError(
                f"Timed out after {timeout_seconds:g} seconds waiting for analysis; "
                f"last status: {last_status}"
            )
        sleep(poll_interval_seconds)

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
        SessionStopReason,
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
    punch_speed = next(
        item
        for item in capabilities
        if item.specification.analysis_type == "punch_speed"
        and item.specification.spec_version == 2
    )
    if not punch_count.executable:
        raise RuntimeError("Production punch-count Executor is not available")
    if not punch_speed.executable:
        raise RuntimeError("Production punch-speed Executor version 2 is not available")

    def punch_csv(peak_index: int) -> bytes:
        output = io.StringIO(newline="")
        writer = write_header(output)
        for index in range(500):
            distance = abs(index - peak_index)
            amplitude = {0: 7.0, 1: 4.0, 2: 1.0}.get(distance, 0.0)
            frame = AnrotFrame()
            frame.frame_type = 0x91
            frame.system_time_ms = index * 10
            frame.acc = (amplitude, 0.0, 1.0)
            frame.gyr = (amplitude * 100.0, 0.0, 0.0)
            frame.mag = (0.0, 0.0, 0.0)
            frame.quat = (1.0, 0.0, 0.0, 0.0)
            frame.roll = frame.pitch = frame.yaw = 0.0
            writer.writerow(
                frame_csv_row(
                    frame,
                    sample_index=index,
                    packet_index=index,
                    elapsed_us=index * 10_000,
                )
            )
        return output.getvalue().encode("utf-8")

    with tempfile.TemporaryDirectory(prefix="bap-installed-e2e-") as temp:
        root = Path(temp)
        descriptors = []
        for name, peak_index in (("left.csv", 260), ("right.csv", 265)):
            data = punch_csv(peak_index)
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
        count_job = AnalysisJobRequest(
            analysis_id=uuid4(), analysis_type="punch_count", spec_version=1,
            input_bindings=(
                AnalysisInputBinding(input_role="left_wrist", csv_id=descriptors[0].csv_id),
                AnalysisInputBinding(input_role="right_wrist", csv_id=descriptors[1].csv_id),
            ),
        )
        speed_job = AnalysisJobRequest(
            analysis_id=uuid4(), analysis_type="punch_speed", spec_version=2,
            input_bindings=(
                AnalysisInputBinding(input_role="left_wrist", csv_id=descriptors[0].csv_id),
                AnalysisInputBinding(input_role="right_wrist", csv_id=descriptors[1].csv_id),
            ),
            parameters={"measurement_start_elapsed_us": 2_000_000},
        )
        now = datetime.now(timezone.utc)
        metadata = SessionMetadata(
            session_id=uuid4(), metadata_schema_version=2,
            desktop_version=__version__, started_at=now, ended_at=now,
            requested_duration_seconds=5,
            actual_duration_seconds=3.0,
            stop_reason=SessionStopReason.ENDED_BY_USER,
            csv_files=tuple(descriptors), analyses=(count_job, speed_job),
        )
        report("upload_session")
        accepted = analysis.upload(root, metadata, tokens.access_token)
        report("analysis_status")
        count_result = _wait_for_api_e2e_analysis(
            analysis,
            accepted["session_id"],
            str(count_job.analysis_id),
            tokens.access_token,
        )
        if count_result.get("result", {}).get("total_punch_count") != 2:
            raise RuntimeError("installed Desktop Session-to-Result E2E returned an unexpected Result")
        speed_result = _wait_for_api_e2e_analysis(
            analysis,
            accepted["session_id"],
            str(speed_job.analysis_id),
            tokens.access_token,
        )
        speed_payload = speed_result.get("result", {})
        if speed_payload.get("total_punch_count") != 2:
            raise RuntimeError("installed Desktop punch-speed E2E returned an unexpected count")
        if not float(speed_payload.get("left_max_speed_mps", 0)) > 0:
            raise RuntimeError("installed Desktop punch-speed E2E returned no positive speed")
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
        benchmark_recordings_dir=settings.benchmark_recordings_dir,
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
