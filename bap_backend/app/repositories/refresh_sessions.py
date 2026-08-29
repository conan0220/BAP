"""Refresh-session persistence operations."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from bap_backend.app.models import RefreshSession


class RefreshSessionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, *, user_id: str, token_hash: str, expires_at: datetime) -> RefreshSession:
        item = RefreshSession(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self.session.add(item)
        self.session.flush()
        return item

    def get_active(self, token_hash: str, now: datetime) -> RefreshSession | None:
        return self.session.scalar(
            select(RefreshSession).where(
                RefreshSession.token_hash == token_hash,
                RefreshSession.revoked_at.is_(None),
                RefreshSession.expires_at > now,
            )
        )

    def revoke(self, token_hash: str, now: datetime) -> bool:
        item = self.session.scalar(
            select(RefreshSession).where(
                RefreshSession.token_hash == token_hash,
                RefreshSession.revoked_at.is_(None),
            )
        )
        if item is None:
            return False
        item.revoked_at = now
        return True
