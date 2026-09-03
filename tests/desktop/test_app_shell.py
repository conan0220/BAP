from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from bap_desktop.resources import text
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
            return SimpleNamespace(refresh_token="first-refresh")

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

    monkeypatch.setattr(api_client, "AuthApiClient", FakeAuthClient)
    monkeypatch.setattr(api_client, "ReleaseApiClient", FakeReleaseClient)
    monkeypatch.setattr(
        desktop_settings,
        "DesktopSettings",
        lambda: SimpleNamespace(api_base_url="http://127.0.0.1:12345/api/"),
    )

    assert _run_api_e2e() == 0


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

    assert window.stack.currentWidget() is window.home_page
    assert tuple(window.home_page.punch_buttons) == text.PUNCH_ITEMS
    assert all(text.PENDING in button.text() for button in window.home_page.punch_buttons.values())


@pytest.mark.scenario("desktop-app-shell", "登入後進入主畫面")
def test_successful_login_opens_home_and_logout_returns_to_login(qtbot) -> None:
    session = _FakeSession()
    window = MainWindow(session, restore_session=False)  # type: ignore[arg-type]
    qtbot.addWidget(window)

    assert window.stack.currentWidget() is window.auth_page
    window.auth_page.authenticated.emit()
    assert window.stack.currentWidget() is window.home_page
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

    window.home_page.punch_buttons["出拳速度"].click()
    assert isinstance(window._feature_page, PunchItemPage)
    assert window._feature_page.item_name == "出拳速度"
    assert window.stack.count() == 3

    window.show_home()
    window.home_page.punch_buttons["出拳力量"].click()
    assert isinstance(window._feature_page, PunchItemPage)
    assert window._feature_page.item_name == "出拳力量"
    assert window.stack.count() == 3
    assert services[0].clears >= 1


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
    assert text.PUNCH_ITEMS == ("出拳次數", "出拳速度", "出拳力量", "出拳軌跡", "拳型辨識")
