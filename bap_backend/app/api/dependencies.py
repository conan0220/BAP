"""FastAPI-only dependency adapters."""

from collections.abc import Generator

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from bap_backend.app.core.security import decode_access_token
from bap_backend.app.models import User
from bap_backend.app.services.errors import ServiceError


bearer = HTTPBearer(auto_error=False)


def get_session(request: Request) -> Generator[Session, None, None]:
    with request.app.state.session_factory() as session:
        yield session


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise ServiceError("authentication_required", "請先登入", 401)
    try:
        payload = decode_access_token(
            credentials.credentials,
            signing_key=request.app.state.settings.jwt_signing_key,
        )
    except jwt.PyJWTError as error:
        raise ServiceError("invalid_access_token", "登入狀態已失效，請重新登入", 401) from error
    user = session.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise ServiceError("invalid_access_token", "登入狀態已失效，請重新登入", 401)
    return user
