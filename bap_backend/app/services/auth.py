"""Account registration and current-device token lifecycle."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from bap_backend.app.core.config import BackendSettings
from bap_backend.app.core.security import (
    RefreshTokenGenerator,
    create_access_token,
    default_refresh_token_generator,
    hash_password,
    hash_refresh_token,
    validate_password,
    validate_username,
    verify_password,
)
from bap_backend.app.models import User
from bap_backend.app.repositories import RefreshSessionRepository, UserRepository
from bap_backend.app.schemas import TokenPair
from bap_backend.app.services.errors import ServiceError


def utcnow() -> datetime:
    return datetime.utcnow()


class AuthService:
    def __init__(
        self,
        session: Session,
        settings: BackendSettings,
        *,
        clock: Callable[[], datetime] = utcnow,
        refresh_token_generator: RefreshTokenGenerator = default_refresh_token_generator,
    ) -> None:
        self.session = session
        self.settings = settings
        self.clock = clock
        self.refresh_token_generator = refresh_token_generator
        self.users = UserRepository(session)
        self.refresh_sessions = RefreshSessionRepository(session)

    def register(self, username: str, password: str) -> User:
        if not validate_username(username):
            raise ServiceError("invalid_username", "Username 格式不正確", 422)
        if not validate_password(password):
            raise ServiceError("invalid_password", "密碼必須為 8 到 128 個字元，並包含英文與數字", 422)
        if self.users.get_by_username(username) is not None:
            raise ServiceError("username_taken", "此 Username 已被使用", 409)
        user = self.users.add(username=username, password_hash=hash_password(password))
        try:
            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            raise ServiceError("username_taken", "此 Username 已被使用", 409) from error
        return user

    def login(self, username: str, password: str) -> TokenPair:
        user = self.users.get_by_username(username)
        if user is None or not user.is_active or not verify_password(user.password_hash, password):
            raise ServiceError("invalid_credentials", "Username 或密碼不正確", 401)
        return self._issue_pair(user)

    def refresh(self, refresh_token: str) -> TokenPair:
        now = self.clock()
        token_hash = hash_refresh_token(refresh_token)
        current = self.refresh_sessions.get_active(token_hash, now)
        if current is None:
            raise ServiceError("invalid_refresh_token", "登入狀態已失效，請重新登入", 401)
        user = self.users.get(current.user_id)
        if user is None or not user.is_active:
            raise ServiceError("invalid_refresh_token", "登入狀態已失效，請重新登入", 401)
        current.revoked_at = now
        return self._issue_pair(user)

    def logout(self, refresh_token: str) -> None:
        self.refresh_sessions.revoke(hash_refresh_token(refresh_token), self.clock())
        self.session.commit()

    def _issue_pair(self, user: User) -> TokenPair:
        now = self.clock()
        refresh_token = self.refresh_token_generator()
        self.refresh_sessions.add(
            user_id=user.id,
            token_hash=hash_refresh_token(refresh_token),
            expires_at=now + timedelta(days=self.settings.refresh_token_days),
        )
        access_token = create_access_token(
            user_id=user.id,
            role=user.role,
            signing_key=self.settings.jwt_signing_key,
            now=now,
            expires_minutes=self.settings.access_token_minutes,
        )
        self.session.commit()
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            access_expires_in=self.settings.access_token_minutes * 60,
            refresh_expires_in=self.settings.refresh_token_days * 86400,
        )
