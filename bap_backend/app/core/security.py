"""Password and token primitives for the Backend."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Callable

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from bap_common.validation import USERNAME_PATTERN, validate_password, validate_username


_PASSWORD_HASHER = PasswordHasher()


def hash_password(password: str) -> str:
    return _PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _PASSWORD_HASHER.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(
    *,
    user_id: str,
    role: str,
    signing_key: str,
    now: datetime,
    expires_minutes: int,
) -> str:
    return jwt.encode(
        {
            "sub": user_id,
            "role": role,
            "iat": now,
            "exp": now + timedelta(minutes=expires_minutes),
            "jti": secrets.token_hex(16),
        },
        signing_key,
        algorithm="HS256",
    )


def default_refresh_token_generator() -> str:
    return secrets.token_urlsafe(48)


RefreshTokenGenerator = Callable[[], str]
