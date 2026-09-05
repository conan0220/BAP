"""Non-blocking Desktop App update decision logic."""

from __future__ import annotations

import hashlib
import hmac
import os
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
import subprocess
from urllib.parse import urlparse

import httpx
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
    sha256: str | None = None


class UpdateInstallError(RuntimeError):
    """An update could not be downloaded, verified, or launched safely."""


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
        if len(release.sha256) != 64 or any(char not in "0123456789abcdefABCDEF" for char in release.sha256):
            return UpdateResult(UpdateStatus.INVALID, self.current_version, release.version)
        return UpdateResult(
            UpdateStatus.AVAILABLE,
            self.current_version,
            release.version,
            release.download_url,
            release.sha256.lower(),
        )


InstallerLauncher = Callable[[Path, list[str]], object]
ProgressCallback = Callable[[int], None]


def _launch_windows_installer(path: Path, arguments: list[str]) -> subprocess.Popen:
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    return subprocess.Popen(
        [str(path), *arguments],
        close_fds=True,
        creationflags=creationflags,
    )


class UpdateInstaller:
    """Download a trusted Installer, verify it, and launch an in-place upgrade."""

    MAX_INSTALLER_BYTES = 512 * 1024 * 1024
    INSTALL_ARGUMENTS = [
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/CLOSEAPPLICATIONS",
        "/RESTARTAPPLICATIONS",
        "/BAPAUTOSTART=1",
    ]

    def __init__(
        self,
        update_dir: Path,
        *,
        client: httpx.Client | None = None,
        launcher: InstallerLauncher = _launch_windows_installer,
    ) -> None:
        self.update_dir = update_dir
        self.client = client or httpx.Client(timeout=120.0, follow_redirects=True)
        self._owns_client = client is None
        self.launcher = launcher

    def download_and_launch(
        self,
        result: UpdateResult,
        *,
        progress: ProgressCallback | None = None,
    ) -> Path:
        if (
            result.status is not UpdateStatus.AVAILABLE
            or not result.latest_version
            or not result.download_url
            or not result.sha256
            or not is_supported_download_url(result.download_url, "windows")
        ):
            raise UpdateInstallError("沒有可安全安裝的 Windows 更新")

        self.update_dir.mkdir(parents=True, exist_ok=True)
        self._remove_old_installers()
        destination = self.update_dir / f"BAP-Setup-{result.latest_version}.exe"
        partial = destination.with_suffix(destination.suffix + ".part")
        digest = hashlib.sha256()
        downloaded = 0
        try:
            with self.client.stream("GET", result.download_url, follow_redirects=True) as response:
                response.raise_for_status()
                content_length = int(response.headers.get("content-length", "0") or 0)
                if content_length > self.MAX_INSTALLER_BYTES:
                    raise UpdateInstallError("更新安裝檔超過允許大小")
                with partial.open("wb") as output:
                    for chunk in response.iter_bytes():
                        if not chunk:
                            continue
                        downloaded += len(chunk)
                        if downloaded > self.MAX_INSTALLER_BYTES:
                            raise UpdateInstallError("更新安裝檔超過允許大小")
                        digest.update(chunk)
                        output.write(chunk)
                        if progress is not None and content_length:
                            progress(min(99, downloaded * 100 // content_length))
            if not hmac.compare_digest(digest.hexdigest(), result.sha256.lower()):
                raise UpdateInstallError("更新安裝檔 SHA-256 驗證失敗")
            partial.replace(destination)
            if progress is not None:
                progress(100)
            self.launcher(destination, list(self.INSTALL_ARGUMENTS))
            return destination
        except UpdateInstallError:
            partial.unlink(missing_ok=True)
            raise
        except (httpx.HTTPError, OSError, ValueError) as error:
            partial.unlink(missing_ok=True)
            raise UpdateInstallError("無法下載或啟動更新安裝程式") from error

    def _remove_old_installers(self) -> None:
        for path in self.update_dir.glob("BAP-Setup-*.exe*"):
            try:
                path.unlink()
            except OSError:
                pass

    def close(self) -> None:
        if self._owns_client:
            self.client.close()
