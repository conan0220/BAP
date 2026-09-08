"""Reusable live multi-source IMU capture with one Common IMU CSV per source."""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Callable
from uuid import UUID, uuid4

from anrot_imu_driver.parsers.anrot_serial_parser import AnrotSerialParser
from bap_common.analysis_session import CsvDescriptor
from bap_desktop.services.imu_discovery import ImuSource
from bap_desktop.services.imu_scan import DEFAULT_BAUD_RATE, ConnectionType, PortAdapter, PySerialPortAdapter


class ImuCaptureError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CaptureDuration:
    requested_seconds: int = 60

    def __post_init__(self) -> None:
        if isinstance(self.requested_seconds, bool) or not isinstance(self.requested_seconds, int):
            raise ValueError("錄製時間必須是整數秒")
        if not 5 <= self.requested_seconds <= 3600:
            raise ValueError("錄製時間必須介於 5 到 3600 秒")

    def elapsed(self, started: float, now: float) -> float:
        return max(0.0, now - started)

    def remaining(self, started: float, now: float) -> float:
        return max(0.0, self.requested_seconds - self.elapsed(started, now))

    def reached(self, started: float, now: float) -> bool:
        return self.elapsed(started, now) >= self.requested_seconds


@dataclass(frozen=True, slots=True)
class ImuCaptureResult:
    session_id: UUID
    directory: Path
    started_at: datetime
    ended_at: datetime
    actual_duration_seconds: float
    descriptors: tuple[CsvDescriptor, ...]


class LiveImuCapture:
    """Capture assigned IMUs. The caller decides what metadata or upload follows."""

    def __init__(
        self,
        root: Path,
        *,
        assignments: dict[str, ImuSource],
        adapter: PortAdapter | None = None,
        monotonic: Callable[[], float] = time.perf_counter,
        wall_clock: Callable[[], float] = time.time,
        recorder_factory=None,
        session_id: UUID | None = None,
    ) -> None:
        if not assignments:
            raise ImuCaptureError("至少要分配一顆 IMU")
        if len(set(assignments.values())) != len(assignments):
            raise ImuCaptureError("同一顆 IMU 不得分配給多個 Input Roles")
        if recorder_factory is None:
            from bap_desktop.services.analysis_recording import CommonImuCsvRecorder
            recorder_factory = CommonImuCsvRecorder
        self.assignments = dict(assignments)
        self.sources = tuple(dict.fromkeys(assignments.values()))
        self.adapter = adapter or PySerialPortAdapter()
        self.monotonic = monotonic
        self.wall_clock = wall_clock
        self.recorder_factory = recorder_factory
        self.session_id = session_id or uuid4()
        self.directory = Path(root) / str(self.session_id)
        self.csv_ids = {self._source_id(source): uuid4() for source in self.sources}
        self._recorders = {}
        self._connections = {}
        self._threads: list[Thread] = []
        self._stop = Event()
        self._errors: list[BaseException] = []
        self._lock = Lock()
        self._state = "created"
        self._result: ImuCaptureResult | None = None
        self._started_monotonic = 0.0
        self._started_epoch = 0.0

    @staticmethod
    def _source_id(source: ImuSource) -> str:
        from bap_desktop.services.analysis_recording import source_id
        return source_id(source)

    @staticmethod
    def _source_descriptor(source: ImuSource):
        from bap_desktop.services.analysis_recording import source_descriptor
        return source_descriptor(source)

    @property
    def state(self) -> str:
        return self._state

    @property
    def started_monotonic(self) -> float:
        return self._started_monotonic

    def start(self) -> None:
        with self._lock:
            if self._state != "created":
                raise ImuCaptureError("IMU capture 只能開始一次")
            self.directory.mkdir(parents=True, exist_ok=False)
            self._state = "recording"
        self._started_monotonic = self.monotonic()
        self._started_epoch = self.wall_clock()
        try:
            for source in self.sources:
                csv_id = self.csv_ids[self._source_id(source)]
                recorder = self.recorder_factory(self.directory / f"imu_{csv_id}.csv")
                recorder.__enter__()
                self._recorders[self._source_id(source)] = recorder
            for port in sorted({source.port for source in self.sources}):
                connection = self.adapter.open(port, baud_rate=DEFAULT_BAUD_RATE, timeout=0.05)
                self._connections[port] = connection
                thread = Thread(target=self._read_port, args=(port, connection), daemon=True)
                self._threads.append(thread)
                thread.start()
        except BaseException:
            self.fail()
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
                        self._recorders[self._source_id(source)].append(
                            frame, elapsed_us=elapsed_us, packet_index=packet_index
                        )
        except BaseException as error:
            if not self._stop.is_set():
                self._errors.append(error)
            self._stop.set()

    def stop(self) -> ImuCaptureResult:
        with self._lock:
            if self._state == "finalized" and self._result is not None:
                return self._result
            if self._state != "recording":
                raise ImuCaptureError("IMU capture 目前不在錄製中")
            self._state = "finalizing"
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=2.0)
        for connection in self._connections.values():
            try:
                connection.close()
            except Exception:
                pass
        if any(thread.is_alive() for thread in self._threads):
            self.fail()
            raise ImuCaptureError("IMU reader 無法在期限內停止")
        if self._errors:
            error = self._errors[0]
            self.fail()
            raise ImuCaptureError("錄製 IMU 資料時發生錯誤") from error
        try:
            descriptors = []
            for source in self.sources:
                identity = self._source_id(source)
                csv_id = self.csv_ids[identity]
                recorder = self._recorders[identity]
                inspection = recorder.finalize()
                descriptors.append(CsvDescriptor(
                    csv_id=csv_id,
                    filename=recorder.final_path.name,
                    source=self._source_descriptor(source),
                    row_count=inspection.row_count,
                    size_bytes=inspection.size_bytes,
                    sha256=inspection.sha256,
                ))
            ended_epoch = self.wall_clock()
            result = ImuCaptureResult(
                session_id=self.session_id,
                directory=self.directory,
                started_at=datetime.fromtimestamp(self._started_epoch, tz=timezone.utc),
                ended_at=datetime.fromtimestamp(ended_epoch, tz=timezone.utc),
                actual_duration_seconds=max(0.000001, self.monotonic() - self._started_monotonic),
                descriptors=tuple(descriptors),
            )
            with self._lock:
                self._result = result
                self._state = "finalized"
            return result
        except BaseException:
            self.fail()
            raise

    def fail(self) -> None:
        self._stop.set()
        for connection in self._connections.values():
            try:
                connection.close()
            except Exception:
                pass
        for recorder in self._recorders.values():
            try:
                recorder.abort()
            except Exception:
                pass
        with self._lock:
            self._state = "failed"

    def discard(self) -> None:
        if self._state in {"recording", "finalizing"}:
            self.fail()
        resolved = self.directory.resolve()
        if resolved.exists() and resolved.is_dir():
            shutil.rmtree(resolved)
        with self._lock:
            self._state = "discarded"