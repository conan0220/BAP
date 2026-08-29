"""Backend logging setup."""

from pathlib import Path

from bap_common.logging import configure_logging


def get_backend_logger(log_dir: Path):
    return configure_logging(name="bap.backend", log_file=log_dir / "bap-backend.log")
