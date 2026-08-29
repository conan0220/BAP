"""User persistence operations with no FastAPI dependency."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from bap_backend.app.models import User


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_username(self, username: str) -> User | None:
        return self.session.scalar(select(User).where(User.username == username))

    def get(self, user_id: str) -> User | None:
        return self.session.get(User, user_id)

    def add(self, *, username: str, password_hash: str) -> User:
        user = User(username=username, password_hash=password_hash, role="user")
        self.session.add(user)
        self.session.flush()
        return user
