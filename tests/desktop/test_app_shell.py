from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QMessageBox

from bap_desktop.resources import text
from bap_desktop.services.benchmark_recorder import BenchmarkRecorderState
from bap_desktop.services.imu_discovery import DiscoveryResult
from bap_desktop.services.shutdown import ShutdownCoordinator
from bap_desktop.ui.main_window import MainWindow
from bap_desktop.ui.punch_items import PunchItemPage


def test_packaged_api_e2e_handles_expected_http_rejections(monkeypatch) -> None:
    import bap_desktop.api_client as api_client
    import bap_desktop.settings as desktop_settings
    from bap_desktop.app import _run_api_e2e

    class FakeAuthClient:
        registrations = 0

        def __init__(self, base_url: str) -> None:
            assert base_url == "http://127.0.0.1:12345/api/"

        def register(self, username: str, password: str) -> dict[str, str]:
            self.registrations += 1
            if self.registrations == 2:
                raise api_client.ApiRejectedError("duplicate", 409)
            return {"username": username}

        def login(self, username: str, password: str):
            if password.endswith("wrong"):
                raise api_client.ApiRejectedError("invalid", 401)
            return SimpleNamespace(access_token="access", refresh_token="first-refresh")

        def refresh(self, refresh_token: str):
            assert refresh_token == "first-refresh"
            return SimpleNamespace(refresh_token="second-refresh")

        def logout(self, refresh_token: str) -> None:
            assert refresh_token == "second-refresh"

    class FakeReleaseClient:
        def __init__(self, base_url: str) -> None:
            assert base_url == "http://127.0.0.1:12345/api/"

        def latest(self, platform: str):
            assert platform == "windows"
            return SimpleNamespace(source_tree_sha="a" * 40)

    class FakeAnalysisClient:
        def __init__(self, base_url: str) -> None:
            assert base_url == "http://127.0.0.1:12345/api/"

        def capabilities(self, access_token: str):
            from bap_common.analysis_contracts import builtin_analysis_specifications
            from bap_desktop.api_client.analysis import AnalysisCapability
            assert access_token == "access"
            return tuple(
                AnalysisCapability(specification, True)
                for specification in builtin_analysis_specifications()
                if (specification.analysis_type, specification.spec_version)
                in {("punch_count", 1), ("punch_speed", 2)}
            )

        def upload(self, directory, metadata, access_token: str):
            assert access_token == "access"
            assert len(metadata.csv_files) == 2
            self.analysis_types = {
                str(item.analysis_id): item.analysis_type for item in metadata.analyses
            }
            return {
                "session_id": str(metadata.session_id),
                "analysis_ids": [str(item.analysis_id) for item in metadata.analyses],
            }

        def analysis_status(self, session_id: str, analysis_id: str, access_token: str):
            if self.analysis_types[analysis_id] == "punch_speed":
                return {
                    "status": "completed",
                    "result": {
                        "total_punch_count": 2,
                        "left_max_speed_mps": 4.2,
                    },
                }
            return {
                "status": "completed",
                "result": {
                    "left_punch_count": 1,
                    "right_punch_count": 1,
                    "total_punch_count": 2,
                },
            }

    monkeypatch.setattr(api_client, "AuthApiClient", FakeAuthClient)
    monkeypatch.setattr(api_client, "ReleaseApiClient", FakeReleaseClient)
    monkeypatch.setattr(api_client, "AnalysisApiClient", FakeAnalysisClient)
    monkeypatch.setattr(
        desktop_settings,
        "DesktopSettings",
        lambda: SimpleNamespace(api_base_url="http://127.0.0.1:12345/api/"),
    )

    assert _run_api_e2e() == 0



def test_api_e2e_analysis_polling_waits_for_completed() -> None:
    from bap_desktop.app import _wait_for_api_e2e_analysis

    class Analysis:
        def __init__(self) -> None:
            self.statuses = iter(("pending", "processing", "completed"))
            self.calls = 0

        def analysis_status(self, session_id, analysis_id, access_token):
            assert (session_id, analysis_id, access_token) == ("session", "analysis", "token")
            self.calls += 1
            status = next(self.statuses)
            return {
                "status": status,
                "result": {"total_punch_count": 2} if status == "completed" else None,
            }

    now = [0.0]
    analysis = Analysis()
    result = _wait_for_api_e2e_analysis(
        analysis, "session", "analysis", "token",
        timeout_seconds=1.0,
        poll_interval_seconds=0.1,
        monotonic=lambda: now[0],
        sleep=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )
    assert result["status"] == "completed"
    assert analysis.calls == 3


def test_api_e2e_analysis_polling_times_out_with_last_status() -> None:
    from bap_desktop.app import _wait_for_api_e2e_analysis

    class Analysis:
        def analysis_status(self, *_args):
            return {"status": "processing", "result": None}

    now = [0.0]
    with pytest.raises(RuntimeError, match="Timed out.*last status: processing"):
        _wait_for_api_e2e_analysis(
            Analysis(), "session", "analysis", "token",
            timeout_seconds=0.2,
            poll_interval_seconds=0.1,
            monotonic=lambda: now[0],
            sleep=lambda seconds: now.__setitem__(0, now[0] + seconds),
        )


def test_api_e2e_analysis_polling_reports_backend_failure() -> None:
    from bap_desktop.app import _wait_for_api_e2e_analysis

    class Analysis:
        def analysis_status(self, *_args):
            return {
                "status": "failed",
                "error_code": "executor_unavailable",
                "safe_error_message": "此分析功能尚未提供",
                "result": None,
            }

    with pytest.raises(RuntimeError, match="executor_unavailable.*此分析功能尚未提供"):
        _wait_for_api_e2e_analysis(Analysis(), "session", "analysis", "token")

def test_packaged_api_e2e_failure_is_machine_readable(tmp_path, monkeypatch) -> None:
    import bap_desktop.app as desktop_app

    def fail_during_upload(report_progress) -> int:
        report_progress("upload_session")
        raise RuntimeError("safe packaged E2E failure")

    monkeypatch.setattr(desktop_app, "_run_api_e2e", fail_during_upload)
    result_path = tmp_path / "api-e2e-result.json"

    assert desktop_app._run_api_e2e_command(result_path) == 1
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result == {
        "schema_version": 1,
        "status": "failed",
        "stage": "upload_session",
        "desktop_version": desktop_app.__version__,
        "error_type": "RuntimeError",
        "message": "safe packaged E2E failure",
    }


@dataclass
class _FakeSession:
    restore_result: bool = False
    restored: int = 0
    logged_out: int = 0
    closed: int = 0
    api: object = object()

    def restore(self) -> bool:
        self.restored += 1
        return self.restore_result

    def logout(self) -> None:
        self.logged_out += 1

    def close(self) -> None:
        self.closed += 1


class _FakeDiscoveryService:
    duration_seconds = 0.0

    def __init__(self) -> None:
        self.discoveries = 0
        self.clears = 0

    def discover(self, *, cancel_event=None) -> DiscoveryResult:
        self.discoveries += 1
        return DiscoveryResult((), ())

    def clear(self) -> None:
        self.clears += 1


@pytest.mark.scenario("desktop-app-shell", "成功恢復登入狀態")
@pytest.mark.scenario("desktop-app-shell", "查看拳擊測量項目")
def test_successful_restore_opens_authenticated_home(qtbot) -> None:
    session = _FakeSession(restore_result=True)
    window = MainWindow(session)  # type: ignore[arg-type]
    qtbot.addWidget(window)

    assert window.stack.currentWidget() is window.app_shell
    assert window.app_shell.content_stack.currentWidget() is window.home_page
    assert tuple(window.home_page.punch_buttons) == text.PUNCH_ITEMS
    assert "可使用" in window.home_page.punch_buttons["出拳次數"].text()
    assert "可使用" in window.home_page.punch_buttons["拳頭速度"].text()
    assert all(
        text.PENDING in button.text()
        for name, button in window.home_page.punch_buttons.items()
        if name not in {"出拳次數", "拳頭速度"}
    )


@pytest.mark.scenario("desktop-app-shell", "登入後進入主畫面")
def test_successful_login_opens_home_and_logout_returns_to_login(qtbot) -> None:
    session = _FakeSession()
    window = MainWindow(session, restore_session=False)  # type: ignore[arg-type]
    qtbot.addWidget(window)

    assert window.stack.currentWidget() is window.auth_page
    window.auth_page.authenticated.emit()
    assert window.stack.currentWidget() is window.app_shell
    assert window.app_shell.content_stack.currentWidget() is window.home_page
    window.logout()
    assert session.logged_out == 1
    assert window.stack.currentWidget() is window.auth_page


@pytest.mark.scenario("desktop-app-shell", "進入單一拳擊項目")
def test_only_one_punch_item_page_is_open_at_a_time(qtbot) -> None:
    session = _FakeSession(restore_result=True)
    services: list[_FakeDiscoveryService] = []

    def factory() -> _FakeDiscoveryService:
        service = _FakeDiscoveryService()
        services.append(service)
        return service

    window = MainWindow(session, discovery_service_factory=factory)  # type: ignore[arg-type]
    qtbot.addWidget(window)
    window.show()

    window.home_page.punch_buttons["拳頭速度"].click()
    assert isinstance(window._feature_page, PunchItemPage)
    assert window._feature_page.item_name == "拳頭速度"
    assert window.stack.count() == 2
    assert window.app_shell.content_stack.count() == 2

    window.show_home()
    window.home_page.punch_buttons["出拳力量"].click()
    assert isinstance(window._feature_page, PunchItemPage)
    assert window._feature_page.item_name == "出拳力量"
    assert window.stack.count() == 2
    assert window.app_shell.content_stack.count() == 2
    assert services[0].clears >= 1


@pytest.mark.scenario("benchmark-data-recorder", "user 捨棄尚未匯出的錄製並離開頁面")
def test_discarding_unsaved_benchmark_navigates_to_home(qtbot, tmp_path, monkeypatch) -> None:
    session = _FakeSession(restore_result=True)
    window = MainWindow(
        session,
        benchmark_recordings_dir=tmp_path,
    )  # type: ignore[arg-type]
    qtbot.addWidget(window)
    window.show_benchmark_recorder()
    page = window._feature_page
    assert page is not None
    page.coordinator.capture_result = SimpleNamespace(directory=tmp_path)
    page.coordinator.state = BenchmarkRecorderState.LABELING
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args, **kwargs: int(QMessageBox.StandardButton.Discard),
    )

    window.show_home()

    assert window._feature_page is None
    assert window.app_shell.content_stack.currentWidget() is window.home_page
    assert page.coordinator.state is BenchmarkRecorderState.DISCARDED


def test_window_close_invalidates_current_device_result_and_session(qtbot) -> None:
    session = _FakeSession(restore_result=True)
    service = _FakeDiscoveryService()
    window = MainWindow(
        session,
        discovery_service_factory=lambda: service,
    )  # type: ignore[arg-type]
    qtbot.addWidget(window)
    window.show()
    window.show_punch_item("出拳次數")

    window.close()

    assert service.clears >= 1
    assert session.closed == 1


def test_shutdown_coordinator_runs_all_callbacks_once_even_if_one_fails() -> None:
    calls: list[str] = []
    coordinator = ShutdownCoordinator()
    coordinator.register(lambda: calls.append("first"))

    def failing_cleanup() -> None:
        calls.append("failing")
        raise RuntimeError("cleanup failed")

    coordinator.register(failing_cleanup)
    coordinator.register(lambda: calls.append("last"))

    coordinator.shutdown()
    coordinator.shutdown()

    assert calls == ["last", "failing", "first"]


@pytest.mark.scenario("desktop-app-shell", "顯示操作與錯誤")
def test_traditional_chinese_resource_keeps_domain_terms_consistent() -> None:
    combined = " ".join(
        value
        for name, value in vars(text).items()
        if name.isupper() and isinstance(value, str)
    )
    assert "IMU 連線狀態" in combined
    assert "Port" in combined
    assert text.PUNCH_ITEMS == ("出拳次數", "拳頭速度", "出拳力量", "出拳軌跡", "拳種辨識")
    assert "拳型辨識" not in combined
