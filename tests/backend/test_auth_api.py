from __future__ import annotations

from datetime import timedelta

import jwt
import pytest
from sqlalchemy import select

from bap_backend.app.core.security import (
    hash_refresh_token,
    validate_password,
    validate_username,
)
from bap_backend.app.models import RefreshSession, User


VALID = {"username": "Boxer01", "password": "boxing123"}


@pytest.mark.scenario("user-account-session", "成功註冊")
def test_register_creates_general_user(backend_context) -> None:
    client, factory, _, _ = backend_context
    response = client.post("/api/v1/auth/register", json=VALID)
    assert response.status_code == 201
    assert response.json()["role"] == "user"
    with factory() as session:
        assert session.scalar(select(User).where(User.username == "Boxer01")) is not None


@pytest.mark.scenario("user-account-session", "Username 已被使用")
def test_duplicate_username_is_rejected(backend_context) -> None:
    client, _, _, _ = backend_context
    assert client.post("/api/v1/auth/register", json=VALID).status_code == 201
    response = client.post("/api/v1/auth/register", json=VALID)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "username_taken"


@pytest.mark.parametrize(
    ("value", "valid"),
    [("abcde", True), ("A-._9", True), ("abcd", False), ("a" * 65, False), ("拳擊手01", False), ("box er", False)],
)
@pytest.mark.scenario("user-account-session", "Username 格式正確")
@pytest.mark.scenario("user-account-session", "Username 格式錯誤")
def test_username_validator(value: str, valid: bool) -> None:
    assert validate_username(value) is valid


@pytest.mark.parametrize(
    ("value", "valid"),
    [("boxing12", True), ("12345678", False), ("abcdefgh", False), ("a1short", False), ("a1" + "x" * 127, False)],
)
@pytest.mark.scenario("user-account-session", "密碼符合規則")
@pytest.mark.scenario("user-account-session", "密碼不符合規則")
def test_password_validator(value: str, valid: bool) -> None:
    assert validate_password(value) is valid


@pytest.mark.scenario("user-account-session", "Username 英文大小寫不同")
def test_username_database_comparison_is_case_sensitive(backend_context) -> None:
    client, _, _, _ = backend_context
    assert client.post("/api/v1/auth/register", json=VALID).status_code == 201
    second = client.post(
        "/api/v1/auth/register", json={"username": "boxer01", "password": "boxing123"}
    )
    assert second.status_code == 201


@pytest.mark.scenario("user-account-session", "登入成功")
def test_login_returns_30_minute_access_and_30_day_refresh(backend_context) -> None:
    client, factory, settings, now = backend_context
    client.post("/api/v1/auth/register", json=VALID)
    response = client.post("/api/v1/auth/login", json=VALID)
    assert response.status_code == 200
    body = response.json()
    assert body["access_expires_in"] == 30 * 60
    assert body["refresh_expires_in"] == 30 * 86400
    claims = jwt.decode(
        body["access_token"],
        settings.jwt_signing_key,
        algorithms=["HS256"],
        options={"verify_iat": False, "verify_exp": False},
    )
    assert claims["role"] == "user"
    with factory() as session:
        stored = session.scalar(select(RefreshSession))
        assert stored.token_hash == hash_refresh_token(body["refresh_token"])
        assert stored.token_hash != body["refresh_token"]
        assert stored.expires_at == now + timedelta(days=30)


@pytest.mark.scenario("user-account-session", "登入資料錯誤")
def test_login_error_does_not_reveal_which_field_failed(backend_context) -> None:
    client, _, _, _ = backend_context
    client.post("/api/v1/auth/register", json=VALID)
    missing = client.post(
        "/api/v1/auth/login", json={"username": "Missing1", "password": "boxing123"}
    )
    wrong = client.post(
        "/api/v1/auth/login", json={"username": "Boxer01", "password": "wrong123"}
    )
    assert missing.status_code == wrong.status_code == 401
    assert missing.json() == wrong.json()
    assert missing.json()["error"]["message"] == "Username 或密碼不正確"


def test_refresh_rotates_and_logout_revokes_current_token(backend_context) -> None:
    client, factory, _, _ = backend_context
    client.post("/api/v1/auth/register", json=VALID)
    pair = client.post("/api/v1/auth/login", json=VALID).json()
    refreshed = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]}
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["refresh_token"] != pair["refresh_token"]
    assert client.post(
        "/api/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]}
    ).status_code == 401
    new_token = refreshed.json()["refresh_token"]
    assert client.post("/api/v1/auth/logout", json={"refresh_token": new_token}).status_code == 200
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": new_token}).status_code == 401
    with factory() as session:
        assert all(item.revoked_at is not None for item in session.scalars(select(RefreshSession)))


def test_invalid_request_uses_stable_safe_error(backend_context) -> None:
    client, _, _, _ = backend_context
    response = client.post("/api/v1/auth/login", json={"password": "secret123"})
    assert response.status_code == 422
    text = response.text
    assert "secret123" not in text
    assert response.json() == {
        "error": {"code": "invalid_request", "message": "輸入資料格式不正確"}
    }
