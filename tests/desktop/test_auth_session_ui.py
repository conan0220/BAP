from __future__ import annotations

import httpx
import pytest

from bap_desktop.api_client import ApiRejectedError, ApiUnavailableError, AuthApiClient, TokenPairData
from bap_desktop.services.session import SessionService
from bap_desktop.ui.auth import AuthPage


class MemoryCredentials:
    def __init__(self, token=None):
        self.token = token

    def save_refresh_token(self, token):
        self.token = token

    def load_refresh_token(self):
        return self.token

    def delete_refresh_token(self):
        self.token = None


class FakeAuthApi:
    def __init__(self):
        self.registered = []
        self.login_error = None
        self.logout_error = None
        self.logout_tokens = []
        self.counter = 0

    def register(self, username, password):
        self.registered.append((username, password))
        return {"username": username, "role": "user"}

    def _pair(self):
        self.counter += 1
        return TokenPairData("access-" + str(self.counter), "refresh-" + str(self.counter), 1800, 2592000)

    def login(self, username, password):
        if self.login_error:
            raise self.login_error
        return self._pair()

    def refresh(self, token):
        if self.login_error:
            raise self.login_error
        return self._pair()

    def logout(self, token):
        self.logout_tokens.append(token)
        if self.logout_error:
            raise self.logout_error


@pytest.mark.scenario("desktop-app-shell", "Desktop App 呼叫遠端 API")
def test_auth_client_uses_public_contract_paths_and_json() -> None:
    requests = []

    def handler(request: httpx.Request):
        requests.append(request)
        if request.url.path.endswith("register"):
            return httpx.Response(201, json={"id": "1", "username": "Boxer01", "role": "user"})
        return httpx.Response(
            200,
            json={
                "access_token": "access",
                "refresh_token": "refresh",
                "token_type": "bearer",
                "access_expires_in": 1800,
                "refresh_expires_in": 2592000,
            },
        )

    client = AuthApiClient(
        "https://imuapp.lab2312.cs.nthu.edu.tw/api/",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    client.register("Boxer01", "boxing123")
    pair = client.login("Boxer01", "boxing123")
    assert [request.url.path for request in requests] == [
        "/api/v1/auth/register",
        "/api/v1/auth/login",
    ]
    assert pair.access_token == "access"


@pytest.mark.scenario("user-account-session", "記住登入狀態並重新啟動 App")
def test_remembered_session_rotates_credentials_and_restores() -> None:
    api = FakeAuthApi()
    credentials = MemoryCredentials()
    session = SessionService(api, credentials)
    session.login("Boxer01", "boxing123", remember=True)
    assert credentials.token == "refresh-1"
    assert session.restore()
    assert credentials.token == "refresh-2"
    assert session.access_token == "access-2"


@pytest.mark.scenario("user-account-session", "未選擇記住登入狀態")
def test_unremembered_session_disappears_on_close() -> None:
    credentials = MemoryCredentials()
    session = SessionService(FakeAuthApi(), credentials)
    session.login("Boxer01", "boxing123", remember=False)
    assert session.is_authenticated
    assert credentials.token is None
    session.close()
    assert not session.is_authenticated


@pytest.mark.scenario("user-account-session", "Access Token 到期後自動更新")
def test_access_token_is_refreshed_when_it_expires() -> None:
    now = [100.0]
    api = FakeAuthApi()
    session = SessionService(api, MemoryCredentials(), clock=lambda: now[0])
    session.login("Boxer01", "boxing123", remember=False)
    assert session.ensure_access_token() == "access-1"
    now[0] += 1800
    assert session.ensure_access_token() == "access-2"


@pytest.mark.scenario("user-account-session", "離線時登出")
def test_offline_logout_clears_local_state_first() -> None:
    api = FakeAuthApi()
    api.logout_error = ApiUnavailableError("offline")
    credentials = MemoryCredentials()
    session = SessionService(api, credentials)
    session.login("Boxer01", "boxing123", remember=True)
    session.logout()
    assert not session.is_authenticated
    assert credentials.token is None
    assert api.logout_tokens == ["refresh-1"]


@pytest.mark.scenario("user-account-session", "登入時無法連線到後端")
def test_login_ui_preserves_username_on_offline_error(qtbot) -> None:
    api = FakeAuthApi()
    api.login_error = ApiUnavailableError("offline")
    page = AuthPage(SessionService(api, MemoryCredentials()))
    qtbot.addWidget(page)
    page.login_username.setText("Boxer01")
    page.login_password.setText("boxing123")
    page.login_button.click()
    assert page.login_username.text() == "Boxer01"
    assert "無法連線" in page.login_message.text()


def test_register_ui_validates_rules_and_returns_to_login(qtbot) -> None:
    api = FakeAuthApi()
    page = AuthPage(SessionService(api, MemoryCredentials()))
    qtbot.addWidget(page)
    page.tabs.setCurrentIndex(1)
    page.register_username.setText("bad name")
    page.register_password.setText("short")
    assert not page.register_button.isEnabled()
    page.register_username.setText("Boxer01")
    page.register_password.setText("boxing123")
    assert page.register_button.isEnabled()
    page.register_button.click()
    assert api.registered == [("Boxer01", "boxing123")]
    assert page.tabs.currentIndex() == 0
    assert page.login_username.text() == "Boxer01"


@pytest.mark.scenario("user-account-session", "Refresh Token 已到期")
def test_expired_refresh_token_clears_remembered_credentials() -> None:
    api = FakeAuthApi()
    api.login_error = ApiRejectedError("expired", 401)
    credentials = MemoryCredentials("expired-refresh")
    session = SessionService(api, credentials)

    assert not session.restore()
    assert credentials.token is None
    assert not session.is_authenticated


@pytest.mark.scenario("user-account-session", "登出成功")
def test_online_logout_clears_local_state_and_revokes_current_token() -> None:
    api = FakeAuthApi()
    credentials = MemoryCredentials()
    session = SessionService(api, credentials)
    session.login("Boxer01", "boxing123", remember=True)

    session.logout()

    assert credentials.token is None
    assert api.logout_tokens == ["refresh-1"]
