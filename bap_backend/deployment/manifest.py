"""Strict schema for immutable BAP deployment artifacts."""

from __future__ import annotations

import re
from datetime import datetime

from packaging.version import InvalidVersion, Version
from pydantic import BaseModel, ConfigDict, Field, field_validator


FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
ALEMBIC_REVISION = re.compile(r"^[A-Za-z0-9_]+$")


class DeploymentManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: str = Field(pattern=r"^BAP$")
    component: str = Field(pattern=r"^(backend|deployment-scripts)$")
    commit_sha: str
    version: str
    created_at: datetime
    python_requires: str
    application_entry_point: str
    alembic_revision: str
    files: list[str] = Field(default_factory=list)

    @field_validator("commit_sha")
    @classmethod
    def validate_commit_sha(cls, value: str) -> str:
        value = value.lower()
        if not FULL_SHA.fullmatch(value):
            raise ValueError("commit_sha must be a full 40-character hexadecimal SHA")
        return value

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

