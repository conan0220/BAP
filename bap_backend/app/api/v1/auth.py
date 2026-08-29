"""Account and session HTTP routes."""

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from bap_backend.app.api.dependencies import get_session
from bap_backend.app.schemas import Credentials, MessageResponse, RefreshRequest, TokenPair, UserResponse
from bap_backend.app.services import AuthService


router = APIRouter(prefix="/auth", tags=["auth"])


def _service(request: Request, session: Session) -> AuthService:
    return AuthService(
        session,
        request.app.state.settings,
        clock=request.app.state.clock,
        refresh_token_generator=request.app.state.refresh_token_generator,
    )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(payload: Credentials, request: Request, session: Session = Depends(get_session)):
    return _service(request, session).register(payload.username, payload.password)


@router.post("/login", response_model=TokenPair)
def login(payload: Credentials, request: Request, session: Session = Depends(get_session)):
    return _service(request, session).login(payload.username, payload.password)


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, request: Request, session: Session = Depends(get_session)):
    return _service(request, session).refresh(payload.refresh_token)


@router.post("/logout", response_model=MessageResponse)
def logout(payload: RefreshRequest, request: Request, session: Session = Depends(get_session)):
    _service(request, session).logout(payload.refresh_token)
    return MessageResponse(message="已登出")
