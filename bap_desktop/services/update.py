"""Non-blocking Desktop App update decision logic."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlparse

from packaging.version import InvalidVersion, Version

from bap_desktop.api_client import ApiRejectedError, ApiUnavailableError, ReleaseApiClient


class UpdateStatus(StrEnum):
    LATEST = "latest"
    AVAILABLE = "available"
    OFFLINE = "offline"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class UpdateResult:
    status: UpdateStatus
    current_version: str
    latest_version: str | None = None
    download_url: str | None = None


def is_supported_download_url(url: str, platform: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "github.com":
        return False
    if "/releases/download/" not in parsed.path:
        return False
    if platform == "windows" and not parsed.path.lower().endswith(".exe"):
        return False
    return True


class UpdateService:
    def __init__(self, client: ReleaseApiClient, *, current_version: str, platform: str) -> None:
        self.client = client
        self.current_version = current_version
        self.platform = platform.lower()

    def check(self) -> UpdateResult:
        try:
            release = self.client.latest(self.platform)
        except ApiUnavailableError:
            return UpdateResult(UpdateStatus.OFFLINE, self.current_version)
        except ApiRejectedError:
            return UpdateResult(UpdateStatus.INVALID, self.current_version)

        try:
            current = Version(self.current_version)
            latest = Version(release.version)
        except InvalidVersion:
            return UpdateResult(UpdateStatus.INVALID, self.current_version)
        if release.platform.lower() != self.platform:
            return UpdateResult(UpdateStatus.INVALID, self.current_version, release.version)
        if latest <= current:
            return UpdateResult(UpdateStatus.LATEST, self.current_version, release.version)
        if not is_supported_download_url(release.download_url, self.platform):
            return UpdateResult(UpdateStatus.INVALID, self.current_version, release.version)
        return UpdateResult(
            UpdateStatus.AVAILABLE,
            self.current_version,
            release.version,
            release.download_url,
        )

