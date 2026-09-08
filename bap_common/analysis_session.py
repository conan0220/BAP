"""Shared Session metadata and upload contract models."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class SourceConnectionType(StrEnum):
    WIRED = "wired"
    WIRELESS_RECEIVER = "wireless_receiver"


class SessionStopReason(StrEnum):
    DURATION_REACHED = "duration_reached"
    ENDED_BY_USER = "ended_by_user"
    SOURCE_INTERRUPTED = "source_interrupted"


class ImuSourceDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1, max_length=255)
    port: str = Field(min_length=1, max_length=255)
    connection_type: SourceConnectionType
    baud_rate: int = Field(gt=0)
    group_id: int | None = Field(default=None, ge=0)
    node_id: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_identity(self) -> "ImuSourceDescriptor":
        if self.connection_type is SourceConnectionType.WIRELESS_RECEIVER:
            if self.group_id is None or self.node_id is None:
                raise ValueError("無線 IMU 必須提供 Group ID 與 Node ID")
        elif self.group_id is not None or self.node_id is not None:
            raise ValueError("有線 IMU 的 Group ID 與 Node ID 必須留空")
        return self


class CsvDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    csv_id: UUID
    filename: str = Field(min_length=1, max_length=255)
    source: ImuSourceDescriptor
    row_count: int = Field(ge=1)
    size_bytes: int = Field(ge=1)
    sha256: str

    @model_validator(mode="after")
    def validate_descriptor(self) -> "CsvDescriptor":
        if not self.filename.lower().endswith(".csv") or "/" in self.filename or "\\" in self.filename:
            raise ValueError("CSV filename 格式不正確")
        if not SHA256_PATTERN.fullmatch(self.sha256):
            raise ValueError("CSV SHA-256 格式不正確")
        return self


class AnalysisInputBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    input_role: str
    csv_id: UUID


class AnalysisJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    analysis_id: UUID
    analysis_type: str
    spec_version: int = Field(ge=1)
    input_bindings: tuple[AnalysisInputBinding, ...]
    parameters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_bindings(self) -> "AnalysisJobRequest":
        roles = [binding.input_role for binding in self.input_bindings]
        if len(roles) != len(set(roles)):
            raise ValueError("同一 Analysis Job 的 Input Role 不得重複")
        return self


class SessionMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: UUID
    metadata_schema_version: int = Field(default=1, ge=1)
    imu_csv_schema_version: int = Field(default=1, ge=1)
    desktop_version: str = Field(min_length=1, max_length=32)
    started_at: datetime
    ended_at: datetime
    requested_duration_seconds: int | None = Field(default=None, ge=5, le=3600, strict=True)
    actual_duration_seconds: float | None = Field(default=None, gt=0)
    stop_reason: SessionStopReason | None = None
    csv_files: tuple[CsvDescriptor, ...]
    analyses: tuple[AnalysisJobRequest, ...]

    @model_validator(mode="after")
    def validate_package_references(self) -> "SessionMetadata":
        duration_values = (
            self.requested_duration_seconds,
            self.actual_duration_seconds,
            self.stop_reason,
        )
        if self.metadata_schema_version == 1 and any(value is not None for value in duration_values):
            raise ValueError("Metadata version 1 不得包含錄製時間或結束原因")
        if self.metadata_schema_version == 2 and any(value is None for value in duration_values):
            raise ValueError("Metadata version 2 必須包含預定時間、實際時間與結束原因")
        if self.ended_at < self.started_at:
            raise ValueError("Session 結束時間不得早於開始時間")
        if not self.csv_files:
            raise ValueError("Session 至少需要一份 CSV")
        if not self.analyses:
            raise ValueError("Session 至少需要一個 Analysis Job")
        csv_ids = [str(item.csv_id) for item in self.csv_files]
        filenames = [item.filename.casefold() for item in self.csv_files]
        analysis_ids = [str(item.analysis_id) for item in self.analyses]
        if len(csv_ids) != len(set(csv_ids)):
            raise ValueError("CSV ID 不得重複")
        if len(filenames) != len(set(filenames)):
            raise ValueError("CSV filename 不得重複")
        if len(analysis_ids) != len(set(analysis_ids)):
            raise ValueError("Analysis ID 不得重複")
        available = set(csv_ids)
        for analysis in self.analyses:
            for binding in analysis.input_bindings:
                if str(binding.csv_id) not in available:
                    raise ValueError("Input Binding 引用了 Metadata 中不存在的 CSV")
        return self

    def canonical_json(self) -> str:
        payload = self.model_dump(mode="json")
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def package_fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()
