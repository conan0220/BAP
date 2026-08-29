from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from bap_desktop.api_client import ApiUnavailableError, ReleaseApiClient, ReleaseData
from bap_desktop.resources import text
from bap_desktop.services.update import UpdateResult, UpdateService, UpdateStatus
from bap_desktop.ui.main_window import MainWindow


DOWNLOAD_URL = "https://github.com/conan0220/BAP/releases/download/desktop-v0.2.0/BAP-Setup-0.2.0.exe"


class _ReleaseClient:
    def __init__(self, release: ReleaseData | None = None, error: Exception | None = None) -> None:
        self.release = release
        self.error = error
        self.platforms: list[str] = []

    def latest(self, platform: str) -> ReleaseData:
        self.platforms.append(platform)
        if self.error:
            raise self.error
        assert self.release is not None
        return self.release


class _Session:
    api = object()

    def restore(self) -> bool:
        return False

    def logout(self) -> None:
        pass

    def close(self) -> None:
        pass


def _release(**overrides) -> ReleaseData:
    values = {
        "platform": "windows",
        "version": "0.2.0",
        "download_url": DOWNLOAD_URL,
        "sha256": "a" * 64,
        "published_at": datetime.now(UTC),
    }
    values.update(overrides)
    return ReleaseData(**values)


@pytest.mark.scenario("desktop-app-update-check", "Windows App 要求更新資訊")
def test_release_api_client_uses_platform_query_and_typed_contract() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/releases/latest"
        assert request.url.params["platform"] == "windows"
        return httpx.Response(
            200,
            json={
                "platform": "windows",
                "version": "0.2.0",
                "download_url": DOWNLOAD_URL,
                "sha256": "a" * 64,
                "published_at": "2026-08-29T00:00:00Z",
            },
        )

    client = ReleaseApiClient(
        "https://imuapp.lab2312.cs.nthu.edu.tw/api/",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    release = client.latest("windows")

    assert release.version == "0.2.0"
    assert release.download_url == DOWNLOAD_URL


@pytest.mark.scenario("desktop-app-update-check", "更新服務正常回應")
@pytest.mark.scenario("desktop-app-update-check", "發現適用的 Windows 新版")
def test_update_service_reports_newer_supported_windows_release() -> None:
    client = _ReleaseClient(_release())
    result = UpdateService(client, current_version="0.1.0", platform="windows").check()  # type: ignore[arg-type]

    assert result.status is UpdateStatus.AVAILABLE
    assert result.download_url == DOWNLOAD_URL
    assert client.platforms == ["windows"]


@pytest.mark.scenario("desktop-app-update-check", "已安裝最新版本")
def test_update_service_is_quiet_when_current_version_is_latest() -> None:
    result = UpdateService(
        _ReleaseClient(_release(version="0.1.0")),  # type: ignore[arg-type]
        current_version="0.1.0",
        platform="windows",
    ).check()
    assert result.status is UpdateStatus.LATEST
    assert result.download_url is None


@pytest.mark.scenario("desktop-app-update-check", "更新資訊缺少適用下載位置")
def test_update_service_rejects_wrong_platform_non_https_and_invalid_version() -> None:
    releases = (
        _release(platform="linux"),
        _release(download_url="http://github.com/conan0220/BAP/releases/download/v/BAP.exe"),
        _release(version="not-a-version"),
    )
    for release in releases:
        result = UpdateService(
            _ReleaseClient(release),  # type: ignore[arg-type]
            current_version="0.1.0",
            platform="windows",
        ).check()
        assert result.status is UpdateStatus.INVALID
        assert result.download_url is None


@pytest.mark.scenario("desktop-app-update-check", "更新服務無法連線")
def test_update_service_offline_does_not_raise() -> None:
    result = UpdateService(
        _ReleaseClient(error=ApiUnavailableError("offline")),  # type: ignore[arg-type]
        current_version="0.1.0",
        platform="windows",
    ).check()
    assert result.status is UpdateStatus.OFFLINE


class _ImmediateUpdateService:
    def __init__(self, result: UpdateResult) -> None:
        self.result = result
        self.calls = 0

    def check(self) -> UpdateResult:
        self.calls += 1
        return self.result


@pytest.mark.scenario("desktop-app-update-check", "user 選擇下載更新")
def test_update_banner_does_not_block_login_and_opens_only_user_selected_url(qtbot) -> None:
    opened = []
    service = _ImmediateUpdateService(
        UpdateResult(UpdateStatus.AVAILABLE, "0.1.0", "0.2.0", DOWNLOAD_URL)
    )
    window = MainWindow(
        _Session(),  # type: ignore[arg-type]
        update_service=service,  # type: ignore[arg-type]
        url_opener=lambda url: opened.append(url.toString()),
        restore_session=False,
    )
    qtbot.addWidget(window)
    window.show()

    assert window.stack.currentWidget() is window.auth_page
    qtbot.waitUntil(
        lambda: service.calls == 1
        and "目前版本：0.1.0" in window.update_banner.message.text()
        and "最新版本：0.2.0" in window.update_banner.message.text()
    )
    assert opened == []
    assert "目前版本：0.1.0" in window.update_banner.message.text()
    assert "最新版本：0.2.0" in window.update_banner.message.text()

    window.update_banner.download_button.click()
    assert opened == [DOWNLOAD_URL]


def test_offline_update_status_is_non_blocking_and_has_no_download(qtbot) -> None:
    service = _ImmediateUpdateService(UpdateResult(UpdateStatus.OFFLINE, "0.1.0"))
    window = MainWindow(
        _Session(),  # type: ignore[arg-type]
        update_service=service,  # type: ignore[arg-type]
        restore_session=False,
    )
    qtbot.addWidget(window)
    window.show()

    qtbot.waitUntil(lambda: service.calls == 1 and window.update_banner.message.text() == text.UPDATE_OFFLINE)
    assert window.stack.currentWidget() is window.auth_page
    assert not window.update_banner.download_button.isVisible()
