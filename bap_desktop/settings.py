"""Typed settings for the BAP Desktop App."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DesktopSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BAP_", extra="ignore")

    api_base_url: AnyHttpUrl = "https://imuapp.lab2312.cs.nthu.edu.tw/api/"
    data_dir: Path = Field(
        default_factory=lambda: Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "BAP"
    )

    @property
    def temp_imu_dir(self) -> Path:
        return self.data_dir / "temp" / "imu-diagnostics"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def update_dir(self) -> Path:
        return self.data_dir / "updates"

    @property
    def settings_file(self) -> Path:
        return self.data_dir / "settings.json"

    def prepare_local_directories(self) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.temp_imu_dir.mkdir(parents=True, exist_ok=True)
        self.update_dir.mkdir(parents=True, exist_ok=True)
