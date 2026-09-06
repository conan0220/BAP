"""Non-blocking Desktop App update decision logic."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
import subprocess
from urllib.parse import urlparse

import httpx
from packaging.version import InvalidVersion, Version

from bap_desktop.api_client import ApiRejectedError, ApiUnavailableError, ReleaseApiClient
from bap_desktop.update_runtime.models import UpdatePaths


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


@dataclass(frozen=True, slots=True)
class UpdateOutcome:
    status: str
    message: str


def consume_latest_update_outcome(update_dir: Path) -> UpdateOutcome | None:
    """Return one terminal update outcome once so the restarted App can explain it."""

    candidates: list[Path] = []
    if not update_dir.is_dir():
        return None
    for operation in update_dir.iterdir():
        journal = operation / "operation.json"
        if journal.is_file() and not (operation / "outcome-shown").exists():
            candidates.append(journal)
    for journal in sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            value = json.loads(journal.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        status = value.get("status")
        if status not in {"health_failed", "install_failed", "rolled_back", "rollback_failed"}:
            continue
        message = value.get("message")
        if not isinstance(message, str) or not message.strip():
            message = "更新未完成，原本版本仍可繼續使用。"
        try:
            journal.with_name("outcome-shown").write_text("shown\n", encoding="utf-8")
        except OSError:
            pass
        return UpdateOutcome(status=status, message=message)
    return None


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


UpdaterLauncher = Callable[[Path, list[str]], object]
ProgressCallback = Callable[[int], None]


def _launch_windows_updater(path: Path, arguments: list[str]) -> subprocess.Popen:
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    return subprocess.Popen(
        [str(path), *arguments],
        close_fds=True,
        creationflags=creationflags,
    )


class UpdateInstaller:
    """Download a trusted Installer, verify it, and hand it to the stable Updater."""

    MAX_INSTALLER_BYTES = 512 * 1024 * 1024
    HANDOFF_TIMEOUT_SECONDS = 5.0

    def __init__(
        self,
        update_dir: Path,
        *,
        client: httpx.Client | None = None,
        launcher: UpdaterLauncher = _launch_windows_updater,
        program_root: Path | None = None,
        current_pid: int | None = None,
        handoff_timeout: float = HANDOFF_TIMEOUT_SECONDS,
    ) -> None:
        self.update_dir = update_dir
        self.paths = UpdatePaths.from_environment(
            program_root=program_root,
            user_data_root=update_dir.parent,
        )
        self.client = client or httpx.Client(timeout=120.0, follow_redirects=True)
        self._owns_client = client is None
        self.launcher = launcher
        self.current_pid = current_pid if current_pid is not None else os.getpid()
        self.handoff_timeout = handoff_timeout

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
            operation_id = uuid.uuid4().hex
            accepted = self.paths.operation_dir(operation_id) / "accepted.json"
            arguments = [
                "handoff",
                "--installer",
                str(destination),
                "--version",
                result.latest_version,
                "--sha256",
                result.sha256,
                "--old-pid",
                str(self.current_pid),
                "--operation-id",
                operation_id,
                "--program-root",
                str(self.paths.program_root),
                "--user-data-root",
                str(self.paths.user_data_root),
            ]
            process = self.launcher(self.paths.updater_exe, arguments)
            deadline = time.monotonic() + self.handoff_timeout
            while not accepted.is_file():
                poll = getattr(process, "poll", None)
                if callable(poll) and poll() is not None:
                    raise UpdateInstallError("Updater 未成功接手，BAP 將保持開啟")
                if time.monotonic() >= deadline:
                    raise UpdateInstallError("Updater 未在時間內確認接手，BAP 將保持開啟")
                time.sleep(0.05)
            return destination
        except UpdateInstallError:
            partial.unlink(missing_ok=True)
            raise
        except (httpx.HTTPError, OSError, ValueError) as error:
            partial.unlink(missing_ok=True)
            raise UpdateInstallError("無法下載更新或啟動 Updater") from error

    def _remove_old_installers(self) -> None:
        for path in self.update_dir.glob("BAP-Setup-*.exe*"):
            try:
                path.unlink()
            except OSError:
                pass

    def close(self) -> None:
        if self._owns_client:
            self.client.close()
