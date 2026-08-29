from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from bap_backend.app.core.config import BackendSettings
from bap_backend.app.db.base import Base
from bap_backend.app.db.session import create_database_engine, create_session_factory
from bap_backend.app.main import create_app


@pytest.fixture
def backend_context(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    settings = BackendSettings(
        database_url=database_url,
        jwt_signing_key="test-signing-key-that-is-long-enough",
        _env_file=None,
    )
    engine = create_database_engine(database_url)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    tokens = iter(f"refresh-token-{index}-" + "x" * 32 for index in range(20))
    now = datetime(2026, 8, 29, 12, 0, 0)
    app = create_app(
        settings=settings,
        session_factory=factory,
        clock=lambda: now,
        refresh_token_generator=lambda: next(tokens),
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, factory, settings, now
    engine.dispose()
