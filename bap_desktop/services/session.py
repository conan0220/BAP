"""Desktop login state and current-device token lifecycle."""

from __future__ import annotations

import time
from collections.abc import Callable

from bap_desktop.api_client import ApiRejectedError, ApiUnavailableError, AuthApiClient, TokenPairData
from bap_desktop.services.credential_store import CredentialStore


class SessionService:
    def __init__(
        self,
        api: AuthApiClient,
        credentials: CredentialStore | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.api = api
        self.credentials = credentials or CredentialStore()
        self.clock = clock
        self.access_token: str | None = None
        self._access_expires_at = 0.0
        self._refresh_token: str | None = None
        self._remember = False

    @property
    def is_authenticated(self) -> bool:
        return self.access_token is not None

    def login(self, username: str, password: str, *, remember: bool) -> None:
        self._remember = remember
        if not remember:
            # A previous remembered login must not survive a later explicit
            # login where the user leaves "remember" unchecked.
            self.credentials.delete_refresh_token()
        self._store_pair(self.api.login(username, password))

    def restore(self) -> bool:
        token = self.credentials.load_refresh_token()
        if not token:
            return False
        self._remember = True
        self._refresh_token = token
        try:
            self._store_pair(self.api.refresh(token))
        except ApiRejectedError:
            self.clear_local()
            return False
        except ApiUnavailableError:
            self.access_token = None
            self._refresh_token = None
            raise
        return True

    def refresh_access_token(self) -> bool:
        if self._refresh_token is None:
            return False
        try:
            self._store_pair(self.api.refresh(self._refresh_token))
        except ApiRejectedError:
            self.clear_local()
            return False
        return True

    def ensure_access_token(self) -> str | None:
        """Refresh just before expiry and return the token for an authenticated request."""

        if self.access_token is not None and self.clock() < self._access_expires_at:
            return self.access_token
        return self.access_token if self.refresh_access_token() else None

    def logout(self) -> None:
        token = self._refresh_token
        self.clear_local()
        if token:
            try:
                self.api.logout(token)
            except (ApiUnavailableError, ApiRejectedError):
                pass

    def close(self) -> None:
        if not self._remember:
            self.access_token = None
            self._access_expires_at = 0.0
            self._refresh_token = None

    def clear_local(self) -> None:
        self.access_token = None
        self._access_expires_at = 0.0
        self._refresh_token = None
        self._remember = False
        self.credentials.delete_refresh_token()

    def _store_pair(self, pair: TokenPairData) -> None:
        self.access_token = pair.access_token
        self._access_expires_at = self.clock() + max(0, pair.access_expires_in - 5)
        self._refresh_token = pair.refresh_token
        if self._remember:
            self.credentials.save_refresh_token(pair.refresh_token)
