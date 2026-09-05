"""BAP Desktop App package for local IMU checks and boxing-analysis entry points."""

from __future__ import annotations

from pathlib import Path


APP_NAME = "BAP"
PRODUCT_NAME = "Boxing Analysis Platform"


def resolve_app_version() -> str:
    """Read the one Desktop version file in source and packaged builds."""

    return (Path(__file__).resolve().with_name("VERSION")).read_text(encoding="utf-8").strip()


__version__ = resolve_app_version()

__all__ = ["APP_NAME", "PRODUCT_NAME", "__version__", "resolve_app_version"]
