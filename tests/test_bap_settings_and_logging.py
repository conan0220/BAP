import io
import logging

import pytest
from pydantic import ValidationError

from bap_backend.app.core.config import BackendSettings
from bap_common.logging import SensitiveDataFilter, safe_log_event
from bap_desktop.settings import DesktopSettings


def test_desktop_settings_use_public_https_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BAP_API_BASE_URL", raising=False)
    settings = DesktopSettings(_env_file=None)
    assert str(settings.api_base_url) == "https://imuapp.lab2312.cs.nthu.edu.tw/api/"


def test_settings_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BAP_BIND_PORT", "54321")
    assert BackendSettings(_env_file=None).bind_port == 54321


def test_production_rejects_default_jwt_key() -> None:
    with pytest.raises(ValidationError):
        BackendSettings(env="production", _env_file=None)


def test_logging_redacts_sensitive_values() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(SensitiveDataFilter())
    logger = logging.getLogger("bap.test.redaction")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    logger.info("password=hunter2 access_token=abc imu_payload=raw-frame")
    safe_log_event(logger, "login_failed", username="boxer1", refresh_token="secret-token")

    output = stream.getvalue()
    assert "hunter2" not in output
    assert "abc" not in output
    assert "raw-frame" not in output
    assert "secret-token" not in output
    assert "username=boxer1" in output
