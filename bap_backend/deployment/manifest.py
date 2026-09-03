"""Strict schemas for immutable BAP deployment artifacts."""

from __future__ import annotations

import re
from datetime import datetime

from packaging.version import InvalidVersion, Version
from pydantic import BaseModel, ConfigDict, Field, field_validator


FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ALEMBIC_REVISION = re.compile(r"^[A-Za-z0-9_]+$")


def _full_sha(value: str, field: str) -> str:
    value = value.lower()
    if not FULL_SHA.fullmatch(value):
        raise ValueError(f"{field} must be a full 40-character hexadecimal SHA")
    return value


class DeploymentManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: str = Field(pattern=r"^BAP$")
    component: str = Field(pattern=r"^backend$")
    commit_sha: str
    source_tree_sha: str
    version: str
    created_at: datetime
    python_requires: str
    application_entry_point: str
    alembic_revision: str
    files: list[str] = Field(default_factory=list)

    @field_validator("commit_sha")
    @classmethod
    def validate_commit_sha(cls, value: str) -> str:
        return _full_sha(value, "commit_sha")

    @field_validator("source_tree_sha")
    @classmethod
    def validate_source_tree_sha(cls, value: str) -> str:
        return _full_sha(value, "source_tree_sha")

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        try:
            parsed = Version(value)
        except InvalidVersion as error:
            raise ValueError("version must use semantic version syntax") from error
        if str(parsed) != value:
            raise ValueError("version must use normalized semantic version syntax")
        return value

    @field_validator("alembic_revision")
    @classmethod
    def validate_alembic_revision(cls, value: str) -> str:
        if value != "none" and not ALEMBIC_REVISION.fullmatch(value):
            raise ValueError("invalid Alembic revision")
        return value


class ArtifactReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str
    sha256: str

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        if not value or value != value.replace("\\", "/").split("/")[-1]:
            raise ValueError("filename must be a basename")
        return value

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        value = value.lower()
        if not SHA256.fullmatch(value):
            raise ValueError("sha256 must contain 64 hexadecimal characters")
        return value


class DeliveryManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1, le=1)
    project: str = Field(pattern=r"^BAP$")
    pr_number: int = Field(gt=0)
    pr_head_sha: str
    pr_base_sha: str
    ci_test_commit_sha: str
    source_tree_sha: str
    ci_workflow_run_id: int = Field(gt=0)
    ci_workflow_url: str
    created_at: datetime
    docs_only: bool
    backend_changed: bool
    desktop_changed: bool
    backend: ArtifactReference | None
    desktop: ArtifactReference | None
    tests: dict[str, str]

    @field_validator("pr_head_sha", "pr_base_sha", "ci_test_commit_sha", "source_tree_sha")
    @classmethod
    def validate_git_sha(cls, value: str, info) -> str:
        return _full_sha(value, info.field_name)


class PromotionRecord(BaseModel):
    """Identity and result metadata copied to a promoted Backend release."""

    model_config = ConfigDict(extra="forbid")

    project: str = Field(pattern=r"^BAP$")
    master_commit_sha: str
    pr_number: int = Field(gt=0)
    ci_workflow_run_id: int = Field(gt=0)
    source_tree_sha: str
    backend_sha256: str
    desktop_sha256: str
    backend_changed: bool
    desktop_changed: bool
    database_revision: str
    promoted_at: datetime
    backend_result: str = Field(pattern=r"^(pending|succeeded|failed|not_selected)$")
    desktop_result: str = Field(pattern=r"^(pending|succeeded|failed|not_selected)$")

    @field_validator("master_commit_sha", "source_tree_sha")
    @classmethod
    def validate_record_git_sha(cls, value: str, info) -> str:
        return _full_sha(value, info.field_name)

    @field_validator("backend_sha256", "desktop_sha256")
    @classmethod
    def validate_record_checksum(cls, value: str) -> str:
        value = value.lower()
        if not SHA256.fullmatch(value):
            raise ValueError("promotion checksum must contain 64 hexadecimal characters")
        return value

    @field_validator("database_revision")
    @classmethod
    def validate_database_revision(cls, value: str) -> str:
        if not ALEMBIC_REVISION.fullmatch(value):
            raise ValueError("invalid database revision")
        return value
