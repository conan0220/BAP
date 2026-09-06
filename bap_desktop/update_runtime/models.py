"""Validated on-disk contracts used by the versioned Desktop updater."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePath
from typing import Any


_VERSION = re.compile(r"^\d+\.\d+\.\d+(?:[+-][0-9A-Za-z.-]+)?$")
_TREE_SHA = re.compile(r"^[0-9a-f]{40}$")
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_OPERATION_STATUSES = {
    "accepted",
    "waiting_for_app",
    "installing",
    "health_check",
    "switching",
    "waiting_for_ready",
    "succeeded",
    "install_failed",
    "health_failed",
    "ready_timeout",
    "rolled_back",
    "rollback_failed",
}


class UpdateContractError(ValueError):
    """A persisted update contract is invalid or unsafe."""


def utc_now_text() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def validate_version(value: str) -> str:
    normalized = value.strip()
    if not _VERSION.fullmatch(normalized):
        raise UpdateContractError("Desktop version is invalid")
    return normalized


def validate_tree_sha(value: str) -> str:
    normalized = value.strip().lower()
    if not _TREE_SHA.fullmatch(normalized):
        raise UpdateContractError("Source Tree SHA is invalid")
    return normalized


def validate_token(value: str, *, label: str) -> str:
    if not _SAFE_TOKEN.fullmatch(value):
        raise UpdateContractError(f"{label} is invalid")
    return value


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Durably replace one JSON document without exposing a partial file."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise UpdateContractError(f"Unable to read update state: {path}") from error
    if not isinstance(value, dict):
        raise UpdateContractError(f"Update state must be an object: {path}")
    return value


def _safe_entry_point(value: str) -> str:
    entry = PurePath(value.replace("\\", "/"))
    if entry.is_absolute() or not entry.parts or ".." in entry.parts:
        raise UpdateContractError("Release entry point is unsafe")
    return entry.as_posix()


@dataclass(frozen=True, slots=True)
class UpdatePaths:
    program_root: Path
    user_data_root: Path

    @classmethod
    def from_environment(
        cls,
        *,
        program_root: str | Path | None = None,
        user_data_root: str | Path | None = None,
    ) -> "UpdatePaths":
        local = Path(
            os.environ.get(
                "LOCALAPPDATA",
                Path.home() / "AppData" / "Local",
            )
        )
        program = Path(program_root) if program_root is not None else local / "Programs" / "BAP"
        configured_data = os.environ.get("BAP_DATA_DIR")
        data = (
            Path(user_data_root)
            if user_data_root is not None
            else Path(configured_data)
            if configured_data
            else local / "BAP"
        )
        program = program.expanduser().resolve()
        data = data.expanduser().resolve()
        if program == data or program in data.parents or data in program.parents:
            raise UpdateContractError("Program Root and User Data Root must be separate")
        return cls(program_root=program, user_data_root=data)

    @property
    def releases_dir(self) -> Path:
        return self.program_root / "releases"

    @property
    def staging_dir(self) -> Path:
        return self.program_root / "staging"

    @property
    def state_file(self) -> Path:
        return self.program_root / "active-release.json"

    @property
    def launcher_exe(self) -> Path:
        return self.program_root / "BAPLauncher.exe"

    @property
    def updater_exe(self) -> Path:
        return self.program_root / "BAPUpdater.exe"

    @property
    def update_root(self) -> Path:
        return self.user_data_root / "updates"

    @property
    def log_dir(self) -> Path:
        return self.user_data_root / "logs"

    @property
    def lock_file(self) -> Path:
        return self.update_root / "update.lock.json"

    def release_dir(self, version: str) -> Path:
        return self.releases_dir / validate_version(version)

    def operation_dir(self, operation_id: str) -> Path:
        return self.update_root / validate_token(operation_id, label="Operation ID")

    def prepare(self) -> None:
        for path in (
            self.program_root,
            self.releases_dir,
            self.staging_dir,
            self.update_root,
            self.log_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True, slots=True)
class ReleaseManifest:
    version: str
    source_tree_sha: str
    entry_point: str = "BAP.exe"
    created_at: str = field(default_factory=utc_now_text)
    schema_version: int = 1
    legacy: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise UpdateContractError("Unsupported Release Manifest schema")
        object.__setattr__(self, "version", validate_version(self.version))
        object.__setattr__(self, "source_tree_sha", validate_tree_sha(self.source_tree_sha))
        object.__setattr__(self, "entry_point", _safe_entry_point(self.entry_point))
        if not isinstance(self.created_at, str) or not self.created_at:
            raise UpdateContractError("Release created_at is invalid")
        if not isinstance(self.legacy, bool):
            raise UpdateContractError("Release legacy flag is invalid")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ReleaseManifest":
        expected = {
            "schema_version",
            "version",
            "source_tree_sha",
            "entry_point",
            "created_at",
            "legacy",
        }
        if set(value) != expected:
            raise UpdateContractError("Release Manifest schema is invalid")
        return cls(**value)

    @classmethod
    def load(cls, release_dir: Path, *, require_entry: bool = True) -> "ReleaseManifest":
        release_dir = Path(release_dir).resolve()
        manifest = cls.from_dict(read_json(release_dir / "release-manifest.json"))
        entry = (release_dir / manifest.entry_point).resolve()
        try:
            entry.relative_to(release_dir)
        except ValueError as error:
            raise UpdateContractError("Release entry point escapes its version directory") from error
        if require_entry and not entry.is_file():
            raise UpdateContractError("Release entry point does not exist")
        return manifest

    def save(self, release_dir: Path) -> Path:
        release_dir = Path(release_dir)
        path = release_dir / "release-manifest.json"
        atomic_write_json(path, asdict(self))
        return path

    def entry_path(self, release_dir: Path) -> Path:
        return Path(release_dir) / self.entry_point


@dataclass(frozen=True, slots=True)
class ActiveReleaseState:
    active_version: str
    previous_version: str | None = None
    operation_id: str | None = None
    updated_at: str = field(default_factory=utc_now_text)
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise UpdateContractError("Unsupported Active State schema")
        object.__setattr__(self, "active_version", validate_version(self.active_version))
        if self.previous_version is not None:
            object.__setattr__(self, "previous_version", validate_version(self.previous_version))
            if self.previous_version == self.active_version:
                raise UpdateContractError("Active and previous versions must differ")
        if self.operation_id is not None:
            object.__setattr__(
                self,
                "operation_id",
                validate_token(self.operation_id, label="Operation ID"),
            )
        if not isinstance(self.updated_at, str) or not self.updated_at:
            raise UpdateContractError("Active State updated_at is invalid")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ActiveReleaseState":
        expected = {
            "schema_version",
            "active_version",
            "previous_version",
            "operation_id",
            "updated_at",
        }
        if set(value) != expected:
            raise UpdateContractError("Active State schema is invalid")
        return cls(**value)

    @classmethod
    def load(cls, path: Path) -> "ActiveReleaseState":
        return cls.from_dict(read_json(path))

    def save(self, path: Path) -> None:
        atomic_write_json(path, asdict(self))


@dataclass(slots=True)
class OperationJournal:
    path: Path
    operation_id: str
    target_version: str
    status: str = "accepted"
    previous_version: str | None = None
    error_code: str | None = None
    message: str | None = None
    events: list[dict[str, str]] = field(default_factory=list)

    @classmethod
    def create(cls, paths: UpdatePaths, operation_id: str, target_version: str) -> "OperationJournal":
        validate_token(operation_id, label="Operation ID")
        validate_version(target_version)
        journal = cls(
            path=paths.operation_dir(operation_id) / "operation.json",
            operation_id=operation_id,
            target_version=target_version,
        )
        journal.transition("accepted", "Updater accepted the operation")
        return journal

    def transition(
        self,
        status: str,
        message: str,
        *,
        error_code: str | None = None,
        previous_version: str | None = None,
    ) -> None:
        if status not in _OPERATION_STATUSES:
            raise UpdateContractError("Unknown update operation status")
        if error_code is not None:
            validate_token(error_code, label="Error code")
        if previous_version is not None:
            previous_version = validate_version(previous_version)
        self.status = status
        self.message = message
        self.error_code = error_code
        if previous_version is not None:
            self.previous_version = previous_version
        self.events.append({"at": utc_now_text(), "status": status, "message": message})
        atomic_write_json(
            self.path,
            {
                "schema_version": 1,
                "operation_id": self.operation_id,
                "target_version": self.target_version,
                "previous_version": self.previous_version,
                "status": self.status,
                "error_code": self.error_code,
                "message": self.message,
                "events": self.events,
            },
        )

    def append_cleanup_warning(self, message: str) -> None:
        self.events.append({"at": utc_now_text(), "status": "cleanup_warning", "message": message})
        atomic_write_json(
            self.path,
            {
                "schema_version": 1,
                "operation_id": self.operation_id,
                "target_version": self.target_version,
                "previous_version": self.previous_version,
                "status": self.status,
                "error_code": self.error_code,
                "message": self.message,
                "events": self.events,
            },
        )
