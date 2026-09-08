"""Versioned contract for locally exported punch-count benchmark bundles."""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePath
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .analysis_session import ImuSourceDescriptor, SHA256_PATTERN
from .imu_csv import inspect_common_imu_csv_bytes


BENCHMARK_SCHEMA_VERSION = 1
BENCHMARK_ANALYSIS_TYPE = "punch_count"
BENCHMARK_ACTIVITY_TYPE = "shadow_boxing"
BENCHMARK_INPUT_ROLES = frozenset({"left_wrist", "right_wrist"})


class BenchmarkBundleError(RuntimeError):
    """A stable validation error for a self-contained Benchmark ZIP."""


class BenchmarkStopReason(StrEnum):
    DURATION_REACHED = "duration_reached"
    ENDED_BY_USER = "ended_by_user"
    SOURCE_INTERRUPTED = "source_interrupted"


class BenchmarkGroundTruth(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    left_punch_count: int = Field(ge=0, strict=True)
    right_punch_count: int = Field(ge=0, strict=True)
    total_punch_count: int = Field(ge=0, strict=True)

    @model_validator(mode="after")
    def validate_total(self) -> "BenchmarkGroundTruth":
        if self.total_punch_count != self.left_punch_count + self.right_punch_count:
            raise ValueError("總拳數必須等於左手與右手拳數相加")
        return self

    @classmethod
    def from_counts(cls, left: int, right: int) -> "BenchmarkGroundTruth":
        if (
            not isinstance(left, int)
            or isinstance(left, bool)
            or not isinstance(right, int)
            or isinstance(right, bool)
        ):
            raise ValueError("拳數必須是整數")
        return cls(
            left_punch_count=left,
            right_punch_count=right,
            total_punch_count=left + right,
        )


class BenchmarkInputDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    input_role: Literal["left_wrist", "right_wrist"]
    csv_id: UUID
    filename: str = Field(min_length=1, max_length=255)
    source: ImuSourceDescriptor
    row_count: int = Field(ge=1)
    size_bytes: int = Field(ge=1)
    sha256: str

    @model_validator(mode="after")
    def validate_file(self) -> "BenchmarkInputDescriptor":
        path = PurePath(self.filename)
        if (
            path.name != self.filename
            or not self.filename.lower().endswith(".csv")
            or path.is_absolute()
        ):
            raise ValueError("Benchmark CSV filename 必須是單純的相對檔名")
        if not SHA256_PATTERN.fullmatch(self.sha256):
            raise ValueError("Benchmark CSV SHA-256 格式不正確")
        return self


class BenchmarkMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    benchmark_schema_version: Literal[1] = BENCHMARK_SCHEMA_VERSION
    imu_csv_schema_version: Literal[1] = 1
    session_id: UUID
    analysis_type: Literal["punch_count"] = BENCHMARK_ANALYSIS_TYPE
    activity_type: Literal["shadow_boxing"] = BENCHMARK_ACTIVITY_TYPE
    requested_duration_seconds: int = Field(ge=5, le=3600, strict=True)
    actual_duration_seconds: float = Field(gt=0)
    stop_reason: BenchmarkStopReason
    desktop_version: str = Field(min_length=1, max_length=32)
    inputs: tuple[BenchmarkInputDescriptor, ...]
    ground_truth: BenchmarkGroundTruth
    notes: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def validate_bundle_references(self) -> "BenchmarkMetadata":
        roles = [item.input_role for item in self.inputs]
        if len(self.inputs) != 2 or set(roles) != BENCHMARK_INPUT_ROLES:
            raise ValueError("Benchmark 必須各包含一份 left_wrist 與 right_wrist CSV")
        filenames = [item.filename.casefold() for item in self.inputs]
        csv_ids = [item.csv_id for item in self.inputs]
        source_ids = [item.source.source_id.casefold() for item in self.inputs]
        if len(filenames) != len(set(filenames)):
            raise ValueError("Benchmark CSV filename 不得重複")
        if len(csv_ids) != len(set(csv_ids)):
            raise ValueError("Benchmark CSV ID 不得重複")
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("同一顆 IMU 不得分配給兩個 Input Roles")
        return self

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


@dataclass(frozen=True, slots=True)
class LoadedBenchmarkBundle:
    metadata: BenchmarkMetadata
    csv_by_role: dict[str, bytes]


def load_benchmark_bundle(path: Path) -> LoadedBenchmarkBundle:
    """Load and strictly verify one self-contained Benchmark ZIP."""

    try:
        with zipfile.ZipFile(path, "r") as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or "metadata.json" not in names:
                raise BenchmarkBundleError("Benchmark ZIP entry 不完整或重複")
            if any(Path(name).name != name or name.startswith(("/", "\\")) for name in names):
                raise BenchmarkBundleError("Benchmark ZIP 不得包含資料夾或絕對路徑")
            metadata = BenchmarkMetadata.model_validate_json(archive.read("metadata.json"))
            expected = {"metadata.json", *(item.filename for item in metadata.inputs)}
            if set(names) != expected:
                raise BenchmarkBundleError("Benchmark ZIP 內容與 Metadata 不一致")
            csv_by_role: dict[str, bytes] = {}
            for item in metadata.inputs:
                data = archive.read(item.filename)
                inspection = inspect_common_imu_csv_bytes(data)
                if (
                    inspection.row_count != item.row_count
                    or inspection.size_bytes != item.size_bytes
                    or inspection.sha256 != item.sha256
                ):
                    raise BenchmarkBundleError(f"{item.filename} checksum 或內容不正確")
                csv_by_role[item.input_role] = data
            return LoadedBenchmarkBundle(metadata=metadata, csv_by_role=csv_by_role)
    except BenchmarkBundleError:
        raise
    except (OSError, zipfile.BadZipFile, KeyError, ValueError) as error:
        raise BenchmarkBundleError("Benchmark ZIP 無法通過驗證") from error
