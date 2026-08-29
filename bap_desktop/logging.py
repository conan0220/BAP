"""Desktop logging setup."""

from pathlib import Path

from bap_common.logging import configure_logging


def get_desktop_logger(log_dir: Path):
    return configure_logging(name="bap.desktop", log_file=log_dir / "bap-desktop.log")
