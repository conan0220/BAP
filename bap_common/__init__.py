"""Shared BAP infrastructure that has no Qt or FastAPI dependency."""

from .logging import configure_logging, safe_log_event

__all__ = ["configure_logging", "safe_log_event"]
