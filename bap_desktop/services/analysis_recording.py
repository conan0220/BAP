"""Record one Common IMU CSV per selected IMU and build a Session package."""

from __future__ import annotations

import csv
import json
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from threading import Event
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
    SourceConnectionType,
)
from bap_common.imu_csv import frame_csv_row, inspect_common_imu_csv, write_header
from bap_desktop.services.imu_discovery import ImuSource
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
    """User-controlled recording: start now and stop only when requested."""

    def __init__(
        self,
        root: Path,
        *,
        assignments: dict[str, ImuSource],
        analysis_type: str,
        spec_version: int,
        desktop_version: str,
        adapter: PortAdapter | None = None,
        monotonic: Callable[[], float] = time.perf_counter,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        if not assignments:
            raise RecordingError("至少要分配一顆 IMU")
        if len(set(assignments.values())) != len(assignments):
            raise RecordingError("同一顆 IMU 不得分配給多個 Input Roles")
        self.adapter = adapter or PySerialPortAdapter()
        self.monotonic = monotonic
        self.wall_clock = wall_clock
        self.desktop_version = desktop_version
        self.assignments = dict(assignments)
        self.sources = tuple(dict.fromkeys(assignments.values()))
        self.csv_ids = {source_id(source): uuid4() for source in self.sources}
        self.job = build_analysis_request(
            analysis_type=analysis_type,
            spec_version=spec_version,
            role_sources={role: self.csv_ids[source_id(source)] for role, source in assignments.items()},
        )
        session_id = uuid4()
        self.draft = SessionDraft(session_id, Path(root) / str(session_id))
        self._recorders: dict[str, CommonImuCsvRecorder] = {}
        self._connections = {}
        self._threads: list[Thread] = []
        self._stop = Event()
        self._errors: list[BaseException] = []
        self._started_monotonic = 0.0
        self._started_epoch = 0.0

    def start(self) -> None:
        self.draft.directory.mkdir(parents=True, exist_ok=False)
        self.draft.begin()
        self._started_monotonic = self.monotonic()
        self._started_epoch = self.wall_clock()
        try:
            for source in self.sources:
                csv_id = self.csv_ids[source_id(source)]
                recorder = CommonImuCsvRecorder(self.draft.directory / f"imu_{csv_id}.csv")
                recorder.__enter__()
                self._recorders[source_id(source)] = recorder
            for port in sorted({source.port for source in self.sources}):
                connection = self.adapter.open(port, baud_rate=DEFAULT_BAUD_RATE, timeout=0.05)
                self._connections[port] = connection
                thread = Thread(target=self._read_port, args=(port, connection), daemon=True)
                self._threads.append(thread)
                thread.start()
        except BaseException:
            self.abort()
            raise

    def _read_port(self, port: str, connection) -> None:
        parser = AnrotSerialParser()
        packet_numbers: dict[int, int] = {}
        wired_packet_index = 0
        try:
            while not self._stop.is_set():
                available = max(0, int(connection.in_waiting))
                if available == 0:
                    time.sleep(0.002)
                    continue
                frames = parser.parse(connection.read(available))
                elapsed_us = round(max(0.0, self.monotonic() - self._started_monotonic) * 1_000_000)
                for frame in frames:
                    for source in self.sources:
                        if source.port != port:
                            continue
                        if source.connection_type is ConnectionType.WIRED:
                            if frame.frame_type == 0x63:
                                continue
                            packet_index = wired_packet_index
                            wired_packet_index += 1
                        else:
                            if frame.gw_id != source.group_id or frame.node_id != source.node_id:
                                continue
                            key = int(frame.gw_ts_ms or elapsed_us)
                            if key not in packet_numbers:
                                packet_numbers[key] = len(packet_numbers)
                            packet_index = packet_numbers[key]
                        self._recorders[source_id(source)].append(
                            frame, elapsed_us=elapsed_us, packet_index=packet_index
                        )
        except BaseException as error:
            self._errors.append(error)
            self._stop.set()

    def stop(self) -> SessionDraft:
        if self.draft.state is not RecordingState.RECORDING:
            raise RecordingError("Session 目前不在錄製中")
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=2.0)
        if any(thread.is_alive() for thread in self._threads):
            self.abort()
            raise RecordingError("IMU reader 無法在期限內停止")
        for connection in self._connections.values():
            connection.close()
        if self._errors:
            self.abort()
            raise RecordingError("錄製 IMU 資料時發生錯誤") from self._errors[0]
        try:
            descriptors = []
            for source in self.sources:
                csv_id = self.csv_ids[source_id(source)]
                recorder = self._recorders[source_id(source)]
                inspection = recorder.finalize()
                descriptors.append(CsvDescriptor(
                    csv_id=csv_id,
                    filename=recorder.final_path.name,
                    source=source_descriptor(source),
                    row_count=inspection.row_count,
                    size_bytes=inspection.size_bytes,
                    sha256=inspection.sha256,
                ))
            metadata = SessionMetadata(
                session_id=self.draft.session_id,
                desktop_version=self.desktop_version,
                started_at=datetime.fromtimestamp(self._started_epoch, tz=timezone.utc),
                ended_at=datetime.fromtimestamp(self.wall_clock(), tz=timezone.utc),
                csv_files=tuple(descriptors),
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
        self._stop.set()
        for connection in self._connections.values():
            try:
                connection.close()
            except Exception:
                pass
        for recorder in self._recorders.values():
            recorder.abort()
        self.draft.fail()
        if self.draft.directory.exists():
            shutil.rmtree(self.draft.directory)
        self.draft.close()
