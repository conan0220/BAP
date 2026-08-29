"""Small keyring adapter so tests never touch the real credential store."""

from __future__ import annotations

import keyring


SERVICE_NAME = "BAP"
REFRESH_TOKEN_KEY = "refresh-token"


class CredentialStore:
    def save_refresh_token(self, token: str) -> None:
        keyring.set_password(SERVICE_NAME, REFRESH_TOKEN_KEY, token)

    def load_refresh_token(self) -> str | None:
        return keyring.get_password(SERVICE_NAME, REFRESH_TOKEN_KEY)

    def delete_refresh_token(self) -> None:
        try:
            keyring.delete_password(SERVICE_NAME, REFRESH_TOKEN_KEY)
        except keyring.errors.PasswordDeleteError:
            pass
