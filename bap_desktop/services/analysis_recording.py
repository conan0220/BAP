"""Record one Common IMU CSV per selected IMU and build a Session package."""

from __future__ import annotations

import csv
import json
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from threading import Event, Lock
from threading import Thread
from typing import Callable, Iterable
from uuid import UUID, uuid4

from anrot_imu_driver.parsers.anrot_serial_parser import AnrotFrame
from anrot_imu_driver.parsers.anrot_serial_parser import AnrotSerialParser
from bap_common.analysis_session import (
    AnalysisInputBinding,
    AnalysisJobRequest,
    CsvDescriptor,
    ImuSourceDescriptor,
    SessionMetadata,
    SessionStopReason,
    SourceConnectionType,
)
from bap_common.imu_csv import frame_csv_row, inspect_common_imu_csv, write_header
from bap_desktop.services.imu_discovery import ImuSource
from bap_desktop.services.imu_capture import CaptureDuration, ImuCaptureError, LiveImuCapture
from bap_desktop.services.imu_scan import (
    DEFAULT_BAUD_RATE,
    ConnectionType,
    PortAdapter,
    PortInfo,
    PortScanResult,
    PySerialPortAdapter,
    ScanStatus,
    scan_all_ports,
)


class RecordingState(StrEnum):
    CREATED = "created"
    RECORDING = "recording"
    FINALIZED = "finalized"
    UPLOADED = "uploaded"
    FAILED = "failed"
    CLOSED = "closed"


class RecordingError(RuntimeError):
    pass


@dataclass(slots=True)
class SessionDraft:
    session_id: UUID
    directory: Path
    state: RecordingState = RecordingState.CREATED
    metadata: SessionMetadata | None = None

    def begin(self) -> None:
        if self.state is not RecordingState.CREATED:
            raise RecordingError("Session 只能開始錄製一次")
        self.state = RecordingState.RECORDING

    def finalize(self, metadata: SessionMetadata) -> None:
        if self.state is not RecordingState.RECORDING:
            raise RecordingError("只有錄製中的 Session 可以完成")
        self.metadata = metadata
        self.state = RecordingState.FINALIZED

    def mark_uploaded(self) -> None:
        if self.state is not RecordingState.FINALIZED:
            raise RecordingError("Session 尚未完成，不能標記為已上傳")
        self.state = RecordingState.UPLOADED

    def fail(self) -> None:
        self.state = RecordingState.FAILED

    def close(self) -> None:
        self.state = RecordingState.CLOSED


class CommonImuCsvRecorder:
    """Crash-safe writer for exactly one IMU source."""

    def __init__(self, final_path: Path) -> None:
        self.final_path = Path(final_path)
        self.part_path = self.final_path.with_suffix(self.final_path.suffix + ".part")
        self._file = None
        self._writer: csv.writer | None = None
        self._sample_index = 0

    def __enter__(self) -> "CommonImuCsvRecorder":
        self.final_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.part_path.open("w", encoding="utf-8", newline="")
        self._writer = write_header(self._file)
        return self

    def append(self, frame: AnrotFrame, *, elapsed_us: int, packet_index: int | None) -> None:
        if self._writer is None:
            raise RecordingError("CSV recorder 尚未開啟")
        self._writer.writerow(
            frame_csv_row(
                frame,
                sample_index=self._sample_index,
                packet_index=packet_index,
                elapsed_us=max(0, elapsed_us),
            )
        )
        self._sample_index += 1

    def finalize(self):
        if self._file is None:
            raise RecordingError("CSV recorder 尚未開啟")
        self._file.flush()
        self._file.close()
        self._file = None
        if self._sample_index == 0:
            self.part_path.unlink(missing_ok=True)
            raise RecordingError("IMU 沒有產生任何可保存的資料")
        self.part_path.replace(self.final_path)
        return inspect_common_imu_csv(self.final_path)

    def abort(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None
        self.part_path.unlink(missing_ok=True)

    def __exit__(self, exc_type, _exc, _tb) -> None:
        if exc_type is not None:
            self.abort()


class _SelectedPortAdapter:
    def __init__(self, inner: PortAdapter, ports: set[str]) -> None:
        self.inner = inner
        self.ports = ports

    def list_ports(self) -> list[PortInfo]:
        return [port for port in self.inner.list_ports() if port.device in self.ports]

    def open(self, port: str, *, baud_rate: int, timeout: float):
        return self.inner.open(port, baud_rate=baud_rate, timeout=timeout)


def source_id(source: ImuSource) -> str:
    if source.connection_type is ConnectionType.WIRED:
        return f"{source.port}:wired"
    return f"{source.port}:group-{source.group_id}:node-{source.node_id}"


def source_descriptor(source: ImuSource) -> ImuSourceDescriptor:
    connection_type = (
        SourceConnectionType.WIRED
        if source.connection_type is ConnectionType.WIRED
        else SourceConnectionType.WIRELESS_RECEIVER
    )
    return ImuSourceDescriptor(
        source_id=source_id(source),
        port=source.port,
        connection_type=connection_type,
        baud_rate=DEFAULT_BAUD_RATE,
        group_id=source.group_id,
        node_id=source.node_id,
    )


class AnalysisSessionRecorder:
    def __init__(
        self,
        root: Path,
        *,
        adapter: PortAdapter | None = None,
        scan: Callable[..., list[PortScanResult]] = scan_all_ports,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.root = Path(root)
        self.adapter = adapter or PySerialPortAdapter()
        self.scan = scan
        self.clock = clock

    def record(
        self,
        *,
        sources: Iterable[ImuSource],
        analyses: tuple[AnalysisJobRequest, ...],
        desktop_version: str,
        duration_seconds: float,
        cancel_event: Event | None = None,
        session_id: UUID | None = None,
        csv_ids_by_source: dict[str, UUID] | None = None,
    ) -> SessionDraft:
        selected = tuple(sources)
        if not selected:
            raise RecordingError("至少要選擇一顆 IMU")
        if len({source_id(item) for item in selected}) != len(selected):
            raise RecordingError("同一顆 IMU 不得重複錄製")

        session_id = session_id or uuid4()
        directory = self.root / str(session_id)
        directory.mkdir(parents=True, exist_ok=False)
        draft = SessionDraft(session_id, directory)
        draft.begin()
        started_epoch = self.clock()
        try:
            results = self.scan(
                _SelectedPortAdapter(self.adapter, {item.port for item in selected}),
                duration_seconds=duration_seconds,
                baud_rate=DEFAULT_BAUD_RATE,
                cancel_event=cancel_event,
            )
            descriptors = self._write_results(
                directory,
                selected,
                results,
                csv_ids_by_source=csv_ids_by_source or {},
                session_started_epoch=started_epoch,
            )
            ended_epoch = self.clock()
            metadata = SessionMetadata(
                session_id=session_id,
                desktop_version=desktop_version,
                started_at=datetime.fromtimestamp(started_epoch, tz=timezone.utc),
                ended_at=datetime.fromtimestamp(ended_epoch, tz=timezone.utc),
                csv_files=tuple(descriptors),
                analyses=analyses,
            )
            (directory / "metadata.json").write_text(
                metadata.canonical_json(), encoding="utf-8"
            )
            draft.finalize(metadata)
            return draft
        except BaseException:
            draft.fail()
            self.cleanup(draft)
            raise

    def _write_results(
        self,
        directory: Path,
        sources: tuple[ImuSource, ...],
        results: list[PortScanResult],
        *,
        csv_ids_by_source: dict[str, UUID],
        session_started_epoch: float,
    ) -> list[CsvDescriptor]:
        by_port = {result.port: result for result in results}
        descriptors: list[CsvDescriptor] = []
        for source in sources:
            result = by_port.get(source.port)
            if result is None or result.status is not ScanStatus.CONNECTED:
                raise RecordingError(f"{source.port} 在錄製期間沒有有效的 IMU 資料")
            csv_id = csv_ids_by_source.get(source_id(source), uuid4())
            filename = f"imu_{csv_id}.csv"
            recorder = CommonImuCsvRecorder(directory / filename)
            with recorder:
                packet_numbers: dict[int, int] = {}
                for index, frame in enumerate(result.frames):
                    if source.connection_type is ConnectionType.WIRELESS_RECEIVER:
                        if frame.gw_id != source.group_id or frame.node_id != source.node_id:
                            continue
                        packet_key = int(frame.gw_ts_ms or index)
                        if packet_key not in packet_numbers:
                            packet_numbers[packet_key] = len(packet_numbers)
                        packet_index = packet_numbers[packet_key]
                    else:
                        if frame.frame_type == 0x63:
                            continue
                        packet_index = index
                    timestamp = (
                        result.frame_timestamps[index]
                        if index < len(result.frame_timestamps)
                        else session_started_epoch
                    )
                    recorder.append(
                        frame,
                        elapsed_us=round(max(0.0, timestamp - session_started_epoch) * 1_000_000),
                        packet_index=packet_index,
                    )
                inspection = recorder.finalize()
            descriptors.append(
                CsvDescriptor(
                    csv_id=csv_id,
                    filename=filename,
                    source=source_descriptor(source),
                    row_count=inspection.row_count,
                    size_bytes=inspection.size_bytes,
                    sha256=inspection.sha256,
                )
            )
        return descriptors

    @staticmethod
    def cleanup(draft: SessionDraft) -> None:
        resolved = draft.directory.resolve()
        if resolved.exists() and resolved.is_dir():
            shutil.rmtree(resolved)
        draft.close()


def build_analysis_request(
    *,
    analysis_type: str,
    spec_version: int,
    role_sources: dict[str, UUID],
    parameters: dict | None = None,
) -> AnalysisJobRequest:
    return AnalysisJobRequest(
        analysis_id=uuid4(),
        analysis_type=analysis_type,
        spec_version=spec_version,
        input_bindings=tuple(
            AnalysisInputBinding(input_role=role, csv_id=csv_id)
            for role, csv_id in role_sources.items()
        ),
        parameters=parameters or {},
    )


class LiveAnalysisRecording:
    """Formal Session wrapper around the reusable live IMU capture primitive."""

    def __init__(
        self,
        root: Path,
        *,
        assignments: dict[str, ImuSource],
        analysis_type: str,
        spec_version: int,
        desktop_version: str,
        requested_duration_seconds: int = 60,
        adapter: PortAdapter | None = None,
        monotonic: Callable[[], float] = time.perf_counter,
        wall_clock: Callable[[], float] = time.time,
        capture_factory=LiveImuCapture,
    ) -> None:
        try:
            self.capture = capture_factory(
                root,
                assignments=assignments,
                adapter=adapter,
                monotonic=monotonic,
                wall_clock=wall_clock,
            )
        except ImuCaptureError as error:
            raise RecordingError(str(error)) from error
        self.desktop_version = desktop_version
        self.analysis_type = analysis_type
        self.spec_version = spec_version
        self.calibration_seconds = 2.0 if analysis_type == "punch_speed" and spec_version == 2 else 0.0
        self.duration = CaptureDuration(requested_duration_seconds)
        self.monotonic = monotonic
        self.assignments = dict(assignments)
        self.sources = self.capture.sources
        self.csv_ids = self.capture.csv_ids
        self.job = build_analysis_request(
            analysis_type=analysis_type,
            spec_version=spec_version,
            role_sources={
                role: self.csv_ids[source_id(source)]
                for role, source in assignments.items()
            },
        )
        self.draft = SessionDraft(self.capture.session_id, self.capture.directory)
        self._finalization_lock = Lock()
        self._measurement_started_monotonic: float | None = None
        self._measurement_start_elapsed_us: int | None = None

    def start(self) -> None:
        self.draft.begin()
        try:
            self.capture.start()
            if self.calibration_seconds == 0:
                self.begin_measurement()
        except BaseException:
            self.draft.fail()
            self.capture.discard()
            self.draft.close()
            raise

    @property
    def is_calibrating(self) -> bool:
        return self._measurement_started_monotonic is None and self.calibration_seconds > 0

    def calibration_remaining_seconds(self, *, now: float | None = None) -> float:
        if not self.is_calibrating:
            return 0.0
        current = self.monotonic() if now is None else now
        return max(0.0, self.calibration_seconds - (current - self.capture.started_monotonic))

    def calibration_due(self, *, now: float | None = None) -> bool:
        return self.is_calibrating and self.calibration_remaining_seconds(now=now) <= 0

    def begin_measurement(self, *, now: float | None = None) -> int:
        if self._measurement_started_monotonic is not None:
            return self._measurement_start_elapsed_us or 0
        current = self.monotonic() if now is None else now
        self._measurement_started_monotonic = current
        self._measurement_start_elapsed_us = max(
            1, round((current - self.capture.started_monotonic) * 1_000_000)
        )
        parameters = (
            {"measurement_start_elapsed_us": self._measurement_start_elapsed_us}
            if self.analysis_type == "punch_speed" and self.spec_version == 2
            else {}
        )
        self.job = build_analysis_request(
            analysis_type=self.analysis_type,
            spec_version=self.spec_version,
            role_sources={
                role: self.csv_ids[source_id(source)]
                for role, source in self.assignments.items()
            },
            parameters=parameters,
        )
        return self._measurement_start_elapsed_us

    def set_requested_duration(self, requested_duration_seconds: int) -> None:
        if self._measurement_started_monotonic is not None:
            raise RecordingError("正式測量開始後不能修改錄製時間")
        self.duration = CaptureDuration(requested_duration_seconds)

    def elapsed_seconds(self, *, now: float | None = None) -> float:
        if self._measurement_started_monotonic is None:
            return 0.0
        current = self.monotonic() if now is None else now
        return self.duration.elapsed(self._measurement_started_monotonic, current)

    def remaining_seconds(self, *, now: float | None = None) -> float:
        if self._measurement_started_monotonic is None:
            return self.duration.requested_seconds
        current = self.monotonic() if now is None else now
        return self.duration.remaining(self._measurement_started_monotonic, current)

    def due_stop_reason(self, *, now: float | None = None) -> SessionStopReason | None:
        current = self.monotonic() if now is None else now
        if self.capture.interrupted_sources(now=current):
            return SessionStopReason.SOURCE_INTERRUPTED
        if (
            self._measurement_started_monotonic is not None
            and self.duration.reached(self._measurement_started_monotonic, current)
        ):
            return SessionStopReason.DURATION_REACHED
        return None

    def stop(
        self,
        reason: SessionStopReason = SessionStopReason.ENDED_BY_USER,
    ) -> SessionDraft:
        with self._finalization_lock:
            if self.draft.state is RecordingState.FINALIZED:
                return self.draft
            if self.draft.state is not RecordingState.RECORDING:
                raise RecordingError("Session 目前不在錄製中")
            if self._measurement_started_monotonic is None:
                raise RecordingError("校正尚未完成，不能建立分析 Session")
            try:
                actual_duration_seconds = max(0.000001, self.elapsed_seconds())
                result = self.capture.stop()
                started_at = result.ended_at - timedelta(seconds=actual_duration_seconds)
                metadata = SessionMetadata(
                    session_id=self.draft.session_id,
                    metadata_schema_version=2,
                    desktop_version=self.desktop_version,
                    started_at=started_at,
                    ended_at=result.ended_at,
                    requested_duration_seconds=self.duration.requested_seconds,
                    actual_duration_seconds=actual_duration_seconds,
                    stop_reason=reason,
                    csv_files=result.descriptors,
                    analyses=(self.job,),
                )
                (self.draft.directory / "metadata.json").write_text(
                    metadata.canonical_json(), encoding="utf-8"
                )
                self.draft.finalize(metadata)
                return self.draft
            except BaseException:
                self.abort()
                raise

    def abort(self) -> None:
        self.capture.discard()
        self.draft.fail()
        self.draft.close()
