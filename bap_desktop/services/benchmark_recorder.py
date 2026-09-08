"""Local benchmark recording state machine, bundle validation, and atomic ZIP export."""

from __future__ import annotations

import json
import os
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Callable
from uuid import UUID

from pydantic import ValidationError

from bap_common.benchmark_bundle import (
    BenchmarkGroundTruth,
    BenchmarkInputDescriptor,
    BenchmarkMetadata,
    BenchmarkStopReason,
)
from bap_common.imu_csv import inspect_common_imu_csv, inspect_common_imu_csv_bytes
from bap_desktop.services.imu_capture import CaptureDuration, ImuCaptureResult, LiveImuCapture
from bap_desktop.services.imu_discovery import DiscoveryResult, ImuSource


class BenchmarkRecorderError(RuntimeError):
    pass


class BenchmarkRecorderState(StrEnum):
    SCANNING = "scanning"
    READY = "ready"
    RECORDING = "recording"
    LABELING = "labeling"
    READY_TO_EXPORT = "ready_to_export"
    EXPORTED = "exported"
    FAILED = "failed"
    DISCARDED = "discarded"


@dataclass(frozen=True, slots=True)
class LoadedBenchmarkBundle:
    metadata: BenchmarkMetadata
    csv_by_role: dict[str, bytes]


class BenchmarkRecorderCoordinator:
    def __init__(
        self,
        root: Path,
        *,
        desktop_version: str,
        capture_factory=LiveImuCapture,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        import time
        self.root = Path(root)
        self.desktop_version = desktop_version
        self.capture_factory = capture_factory
        self.monotonic = monotonic or time.perf_counter
        self.state = BenchmarkRecorderState.SCANNING
        self.sources: tuple[ImuSource, ...] = ()
        self.assignments: dict[str, ImuSource] = {}
        self.duration = CaptureDuration()
        self.capture = None
        self.capture_result: ImuCaptureResult | None = None
        self.stop_reason: BenchmarkStopReason | None = None
        self.ground_truth: BenchmarkGroundTruth | None = None
        self.notes = ""
        self.exported_path: Path | None = None
        self.error_message = ""

    @property
    def has_unsaved_recording(self) -> bool:
        return self.capture_result is not None and self.state in {
            BenchmarkRecorderState.LABELING,
            BenchmarkRecorderState.READY_TO_EXPORT,
        }

    def begin_scan(self) -> None:
        if self.has_unsaved_recording:
            raise BenchmarkRecorderError("目前有尚未匯出的錄製資料")
        self.state = BenchmarkRecorderState.SCANNING
        self.sources = ()
        self.assignments.clear()

    def complete_scan(self, result: DiscoveryResult) -> None:
        if self.state is not BenchmarkRecorderState.SCANNING:
            raise BenchmarkRecorderError("目前不能接受掃描結果")
        self.sources = result.sources
        self.state = BenchmarkRecorderState.READY

    def set_assignments(self, assignments: dict[str, ImuSource]) -> None:
        if self.state is not BenchmarkRecorderState.READY:
            raise BenchmarkRecorderError("目前不能指定 IMU")
        if set(assignments) != {"left_wrist", "right_wrist"}:
            raise BenchmarkRecorderError("左手腕與右手腕都必須指定 IMU")
        if len(set(assignments.values())) != 2:
            raise BenchmarkRecorderError("左右手腕不得使用同一顆 IMU")
        if any(source not in self.sources for source in assignments.values()):
            raise BenchmarkRecorderError("只能使用本次掃描找到的 IMU")
        self.assignments = dict(assignments)

    def start(self, requested_duration_seconds: int = 60) -> None:
        if self.state is not BenchmarkRecorderState.READY or len(self.assignments) != 2:
            raise BenchmarkRecorderError("請先為左右手腕指定不同的 IMU")
        self.duration = CaptureDuration(requested_duration_seconds)
        self.capture = self.capture_factory(self.root, assignments=self.assignments)
        try:
            self.capture.start()
        except Exception as error:
            self.state = BenchmarkRecorderState.FAILED
            self.error_message = "無法開始錄製 IMU 資料"
            raise BenchmarkRecorderError(self.error_message) from error
        self.state = BenchmarkRecorderState.RECORDING

    def elapsed_seconds(self, now: float | None = None) -> float:
        if self.capture is None:
            return 0.0
        return self.duration.elapsed(self.capture.started_monotonic, self.monotonic() if now is None else now)

    def remaining_seconds(self, now: float | None = None) -> float:
        if self.capture is None:
            return float(self.duration.requested_seconds)
        return self.duration.remaining(self.capture.started_monotonic, self.monotonic() if now is None else now)

    def tick(self, now: float | None = None) -> bool:
        if self.state is not BenchmarkRecorderState.RECORDING or self.capture is None:
            return False
        current = self.monotonic() if now is None else now
        interrupted_sources = getattr(self.capture, "interrupted_sources", None)
        if callable(interrupted_sources) and interrupted_sources(now=current):
            self._finish(BenchmarkStopReason.SOURCE_INTERRUPTED)
            return True
        if self.duration.reached(self.capture.started_monotonic, current):
            self._finish(BenchmarkStopReason.DURATION_REACHED)
            return True
        return False

    def stop_early(self) -> None:
        self._finish(BenchmarkStopReason.ENDED_BY_USER)

    def _finish(self, reason: BenchmarkStopReason) -> None:
        if self.state is not BenchmarkRecorderState.RECORDING or self.capture is None:
            raise BenchmarkRecorderError("目前沒有正在錄製的 Benchmark")
        try:
            self.capture_result = self.capture.stop()
        except Exception as error:
            self.state = BenchmarkRecorderState.FAILED
            self.error_message = "錄製失敗，必要 IMU 來源沒有產生可用資料"
            raise BenchmarkRecorderError(self.error_message) from error
        self.stop_reason = reason
        self.state = BenchmarkRecorderState.LABELING

    @staticmethod
    def parse_ground_truth(left: str, right: str) -> BenchmarkGroundTruth:
        values = []
        for value in (left.strip(), right.strip()):
            if not value or not value.isdecimal():
                raise BenchmarkRecorderError("左右手拳數都必須是大於或等於零的整數")
            values.append(int(value))
        return BenchmarkGroundTruth.from_counts(values[0], values[1])

    def set_ground_truth(self, left: str, right: str, *, notes: str = "") -> BenchmarkGroundTruth:
        if self.state not in {BenchmarkRecorderState.LABELING, BenchmarkRecorderState.READY_TO_EXPORT}:
            raise BenchmarkRecorderError("錄製完成後才能輸入 Ground Truth")
        try:
            truth = self.parse_ground_truth(left, right)
            if len(notes) > 2000:
                raise BenchmarkRecorderError("備註不可超過 2000 個字元")
        except (ValueError, ValidationError) as error:
            raise BenchmarkRecorderError("左右手拳數都必須是大於或等於零的整數") from error
        self.ground_truth = truth
        self.notes = notes
        self.state = BenchmarkRecorderState.READY_TO_EXPORT
        return truth

    def metadata(self) -> BenchmarkMetadata:
        if (
            self.state not in {BenchmarkRecorderState.READY_TO_EXPORT, BenchmarkRecorderState.EXPORTED}
            or self.capture_result is None
            or self.ground_truth is None
            or self.stop_reason is None
        ):
            raise BenchmarkRecorderError("Benchmark 尚未準備好匯出")
        roles_by_source = {
            source_id(source): role for role, source in self.assignments.items()
        }
        inputs = tuple(
            BenchmarkInputDescriptor(
                input_role=roles_by_source[descriptor.source.source_id],
                csv_id=descriptor.csv_id,
                filename=descriptor.filename,
                source=descriptor.source,
                row_count=descriptor.row_count,
                size_bytes=descriptor.size_bytes,
                sha256=descriptor.sha256,
            )
            for descriptor in self.capture_result.descriptors
        )
        return BenchmarkMetadata(
            session_id=self.capture_result.session_id,
            requested_duration_seconds=self.duration.requested_seconds,
            actual_duration_seconds=self.capture_result.actual_duration_seconds,
            stop_reason=self.stop_reason,
            desktop_version=self.desktop_version,
            inputs=inputs,
            ground_truth=self.ground_truth,
            notes=self.notes,
        )

    def mark_exported(self, path: Path) -> None:
        if self.state is not BenchmarkRecorderState.READY_TO_EXPORT:
            raise BenchmarkRecorderError("Benchmark 尚未準備好匯出")
        self.exported_path = Path(path)
        if self.capture is not None:
            self.capture.discard()
        self.state = BenchmarkRecorderState.EXPORTED

    def discard(self) -> None:
        if self.capture is not None:
            self.capture.discard()
        self.capture_result = None
        self.state = BenchmarkRecorderState.DISCARDED


def source_id(source: ImuSource) -> str:
    from bap_desktop.services.analysis_recording import source_id as build_source_id
    return build_source_id(source)


def benchmark_bundle_filename(metadata: BenchmarkMetadata) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"bap-punch-count-benchmark-{timestamp}-{str(metadata.session_id)[:8]}.zip"


def validate_benchmark_staging(metadata: BenchmarkMetadata, directory: Path) -> None:
    directory = Path(directory)
    expected = {"metadata.json", *(item.filename for item in metadata.inputs)}
    actual = {item.name for item in directory.iterdir() if item.is_file() and not item.name.endswith(".part")}
    if actual - expected:
        raise BenchmarkRecorderError("Benchmark staging 包含規格以外的檔案")
    for item in metadata.inputs:
        path = directory / item.filename
        if not path.is_file():
            raise BenchmarkRecorderError(f"缺少 {item.filename}")
        inspection = inspect_common_imu_csv(path)
        if (
            inspection.row_count != item.row_count
            or inspection.size_bytes != item.size_bytes
            or inspection.sha256 != item.sha256
        ):
            raise BenchmarkRecorderError(f"{item.filename} 與 Metadata 不一致")


def load_benchmark_bundle(path: Path) -> LoadedBenchmarkBundle:
    try:
        with zipfile.ZipFile(path, "r") as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or "metadata.json" not in names:
                raise BenchmarkRecorderError("Benchmark ZIP entry 不完整或重複")
            if any(Path(name).name != name or name.startswith(("/", "\\")) for name in names):
                raise BenchmarkRecorderError("Benchmark ZIP 不得包含資料夾或絕對路徑")
            metadata = BenchmarkMetadata.model_validate_json(archive.read("metadata.json"))
            expected = {"metadata.json", *(item.filename for item in metadata.inputs)}
            if set(names) != expected:
                raise BenchmarkRecorderError("Benchmark ZIP 內容與 Metadata 不一致")
            csv_by_role = {}
            for item in metadata.inputs:
                data = archive.read(item.filename)
                inspection = inspect_common_imu_csv_bytes(data)
                if (
                    inspection.row_count != item.row_count
                    or inspection.size_bytes != item.size_bytes
                    or inspection.sha256 != item.sha256
                ):
                    raise BenchmarkRecorderError(f"{item.filename} checksum 或內容不正確")
                csv_by_role[item.input_role] = data
            return LoadedBenchmarkBundle(metadata=metadata, csv_by_role=csv_by_role)
    except (OSError, zipfile.BadZipFile, KeyError, ValueError) as error:
        raise BenchmarkRecorderError("Benchmark ZIP 無法通過驗證") from error


def export_benchmark_bundle(metadata: BenchmarkMetadata, staging_directory: Path, destination: Path) -> Path:
    destination = Path(destination)
    if destination.suffix.lower() != ".zip":
        destination = destination.with_suffix(".zip")
    partial = destination.with_name(destination.name + ".partial")
    validate_benchmark_staging(metadata, staging_directory)
    metadata_path = Path(staging_directory) / "metadata.json"
    metadata_path.write_text(metadata.canonical_json(), encoding="utf-8")
    try:
        partial.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("metadata.json", metadata.canonical_json().encode("utf-8"))
            for item in metadata.inputs:
                archive.write(Path(staging_directory) / item.filename, arcname=item.filename)
        load_benchmark_bundle(partial)
        os.replace(partial, destination)
        return destination
    except BaseException as error:
        try:
            partial.unlink(missing_ok=True)
        except OSError:
            pass
        if isinstance(error, BenchmarkRecorderError):
            raise
        raise BenchmarkRecorderError("Benchmark ZIP 寫入失敗，錄製資料仍保留在本機") from error
