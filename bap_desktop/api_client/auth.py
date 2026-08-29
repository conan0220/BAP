"""Typed HTTPS client for the remote account API."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin

import httpx


class ApiUnavailableError(RuntimeError):
    pass


class ApiRejectedError(RuntimeError):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class TokenPairData:
    access_token: str
    refresh_token: str
    access_expires_in: int
    refresh_expires_in: int
    token_type: str = "bearer"


class AuthApiClient:
    def __init__(self, base_url: str, *, client: httpx.Client | None = None) -> None:
        self.base_url = base_url if base_url.endswith("/") else base_url + "/"
        self.client = client or httpx.Client(timeout=10.0)

    def _post(self, path: str, payload: dict) -> dict:
        try:
            response = self.client.post(urljoin(self.base_url, path), json=payload)
        except httpx.HTTPError as error:
            raise ApiUnavailableError("目前無法連線到伺服器") from error
        if response.is_error:
            try:
                message = response.json().get("error", {}).get("message")
            except ValueError:
                message = None
            raise ApiRejectedError(message or "伺服器拒絕要求", response.status_code)
        return response.json()

    def register(self, username: str, password: str) -> dict:
        return self._post("v1/auth/register", {"username": username, "password": password})

    def login(self, username: str, password: str) -> TokenPairData:
        return TokenPairData(**self._post("v1/auth/login", {"username": username, "password": password}))

    def refresh(self, refresh_token: str) -> TokenPairData:
        return TokenPairData(**self._post("v1/auth/refresh", {"refresh_token": refresh_token}))

    def logout(self, refresh_token: str) -> None:
        self._post("v1/auth/logout", {"refresh_token": refresh_token})
