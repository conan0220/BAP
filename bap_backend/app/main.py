"""FastAPI application factory and executable Backend entry point."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from bap_backend.app.api.v1.auth import router as auth_router
from bap_backend.app.api.v1.releases import router as releases_router
from bap_backend.app.core.config import BackendSettings
from bap_backend.app.core.security import default_refresh_token_generator
from bap_backend.app.db.session import create_database_engine, create_session_factory
from bap_backend.app.services.auth import utcnow
from bap_backend.app.services.errors import ServiceError


def _error(code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message}})


def create_app(
    *,
    settings: BackendSettings | None = None,
    session_factory=None,
    clock: Callable = utcnow,
    refresh_token_generator: Callable[[], str] = default_refresh_token_generator,
) -> FastAPI:
    settings = settings or BackendSettings()
    if session_factory is None:
        session_factory = create_session_factory(create_database_engine(settings.database_url))

    application = FastAPI(title="BAP Backend", version="0.1.0")
    application.state.settings = settings
    application.state.session_factory = session_factory
    application.state.clock = clock
    application.state.refresh_token_generator = refresh_token_generator

    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(auth_router)
    api_v1.include_router(releases_router)
    application.include_router(api_v1)

    @application.get("/health")
    def health(request: Request):
        try:
            with request.app.state.session_factory() as session:
                session.execute(text("SELECT 1"))
        except SQLAlchemyError:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "not_ready",
                    "service": "bap-backend",
                    "commit_sha": settings.commit_sha,
                },
            )
        return {
            "status": "ok",
            "service": "bap-backend",
            "commit_sha": settings.commit_sha,
        }

    @application.exception_handler(ServiceError)
    async def service_error_handler(_request: Request, error: ServiceError):
        return _error(error.code, error.message, error.status_code)

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, _error_value: RequestValidationError):
        return _error("invalid_request", "輸入資料格式不正確", 422)

    @application.exception_handler(Exception)
    async def unexpected_error_handler(_request: Request, _error_value: Exception):
        return _error("internal_error", "伺服器暫時無法完成要求", 500)

    return application


app = create_app()


def main() -> None:
    import uvicorn

    settings = app.state.settings
    uvicorn.run(app, host=settings.bind_host, port=settings.bind_port)


if __name__ == "__main__":
    main()
