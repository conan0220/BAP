"""Five-second IMU diagnostics, local CSV storage, and report calculation."""

from __future__ import annotations

import csv
import re
import shutil
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Callable

from anrot_imu_driver.commands.record_data import split_gateway_packets
from anrot_imu_driver.parsers.anrot_serial_parser import AnrotFrame
from bap_desktop.services.imu_scan import (
    DEFAULT_BAUD_RATE,
    ConnectionType,
    PortAdapter,
    PortScanResult,
    PySerialPortAdapter,
    ScanStatus,
    scan_all_ports,
)


MAX_NODES = 16
WIRELESS_NODE_FIELDS = (
    "ID",
    "AccX[G]",
    "AccY[G]",
    "AccZ[G]",
    "GyrX[deg/s]",
    "GyrY[deg/s]",
    "GyrZ[deg/s]",
    "MagX[uT]",
    "MagY[uT]",
    "MagZ[uT]",
    "Roll[deg]",
    "Pitch[deg]",
    "Yaw[deg]",
    "Qw",
    "Qx",
    "Qy",
    "Qz",
)
WIRELESS_CSV_HEADER = (
    "ts_ms(ms)",
    "UnixTimeStamp(sec)",
    *(f"Node{node}_{field}" for node in range(1, MAX_NODES + 1) for field in WIRELESS_NODE_FIELDS),
)
WIRED_CSV_HEADER = (
    "UnixTimeStamp(sec)",
    "Time(ms)",
    "Pressure(Pa)",
    "Temperature(°C)",
    "AccX[G]",
    "AccY[G]",
    "AccZ[G]",
    "GyrX[deg/s]",
    "GyrY[deg/s]",
    "GyrZ[deg/s]",
    "MagX[uT]",
    "MagY[uT]",
    "MagZ[uT]",
    "Roll[deg]",
    "Pitch[deg]",
    "Yaw[deg]",
    "Qw",
    "Qx",
    "Qy",
    "Qz",
)


def _wireless_packets(frames: list[AnrotFrame]) -> list[list[AnrotFrame]]:
    return split_gateway_packets([frame for frame in frames if frame.frame_type == 0x63])


REPORT_COLUMNS = (
    "Port",
    "Manufacturer",
    "連線方式",
    "Baud rate",
    "Group ID／Node IDs",
    "取樣率",
    "連線狀態",
    "說明",
)


@dataclass(frozen=True, slots=True)
class DiagnosticReportRow:
    port: str
    manufacturer: str
    connection_type: str
    baud_rate: int
    group_nodes: str
    sample_rate_hz: float
    status: str
    reason: str

    def as_display_values(self) -> tuple[str, ...]:
        return (
            self.port,
            self.manufacturer,
            self.connection_type,
            str(self.baud_rate),
            self.group_nodes,
            f"{self.sample_rate_hz:.1f} Hz",
            self.status,
            self.reason,
        )


@dataclass(frozen=True, slots=True)
class DiagnosticReport:
    rows: tuple[DiagnosticReportRow, ...]
    csv_files: tuple["DiagnosticCsvFile", ...]

    @property
    def csv_path(self) -> Path | None:
        """Keep the former single-file API for a one-Port report."""

        return self.csv_files[0].path if len(self.csv_files) == 1 else None


@dataclass(frozen=True, slots=True)
class DiagnosticCsvFile:
    port: str
    connection_type: ConnectionType
    path: Path
    data_row_count: int


class ImuDiagnosticsService:
    """Run one bounded scan and keep its CSV only in App-managed local storage."""

    def __init__(
        self,
        *,
        adapter: PortAdapter | None = None,
        duration_seconds: float = 5.0,
        temp_dir: Path | None = None,
        scan: Callable[..., list[PortScanResult]] = scan_all_ports,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self.adapter = adapter or PySerialPortAdapter()
        self.duration_seconds = duration_seconds
        self.temp_dir = temp_dir or Path(tempfile.gettempdir()) / "BAP" / "imu-diagnostics"
        self.scan = scan
        self.wall_clock = wall_clock
        self._managed_files: set[Path] = set()
        self._latest: DiagnosticReport | None = None
        self._run_sequence = 0

    @property
    def latest_report(self) -> DiagnosticReport | None:
        return self._latest

    def run(
        self,
        *,
        cancel_event: Event | None = None,
        phase_callback: Callable[[str], None] | None = None,
    ) -> DiagnosticReport:
        self._delete_latest_csv()
        if phase_callback is not None:
            phase_callback("collecting")
        results = self.scan(
            self.adapter,
            duration_seconds=self.duration_seconds,
            baud_rate=DEFAULT_BAUD_RATE,
            cancel_event=cancel_event,
        )
        if phase_callback is not None:
            phase_callback("analyzing")
        run_timestamp = self.wall_clock()
        self._run_sequence += 1
        csv_files = self._write_csv_files(
            results,
            run_timestamp=run_timestamp,
            run_sequence=self._run_sequence,
        )
        rows = tuple(self._to_report_row(result) for result in results)
        self._latest = DiagnosticReport(rows=rows, csv_files=csv_files)
        return self._latest

    def export_csv(self, destination: Path) -> Path:
        if self._latest is None or len(self._latest.csv_files) != 1:
            raise FileNotFoundError("目前沒有可匯出的 IMU 測試 CSV")
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self._latest.csv_files[0].path, destination)
        return destination

    def export_csv_files(self, destination_directory: Path) -> tuple[Path, ...]:
        if self._latest is None or not self._latest.csv_files:
            raise FileNotFoundError("目前沒有可匯出的 IMU 測試 CSV")
        destination_directory = Path(destination_directory)
        destination_directory.mkdir(parents=True, exist_ok=True)
        exported: list[Path] = []
        for csv_file in self._latest.csv_files:
            destination = self._unique_path(destination_directory / csv_file.path.name)
            shutil.copy2(csv_file.path, destination)
            exported.append(destination)
        return tuple(exported)

    def cleanup(self) -> None:
        for path in tuple(self._managed_files):
            path.unlink(missing_ok=True)
            self._managed_files.discard(path)
        self._latest = None

    def _delete_latest_csv(self) -> None:
        if self._latest is not None:
            for csv_file in self._latest.csv_files:
                csv_file.path.unlink(missing_ok=True)
                self._managed_files.discard(csv_file.path)

    def _write_csv_files(
        self,
        results: list[PortScanResult],
        *,
        run_timestamp: float,
        run_sequence: int,
    ) -> tuple[DiagnosticCsvFile, ...]:
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.fromtimestamp(run_timestamp).strftime("%Y%m%d_%H%M%S")
        run_id = f"{stamp}_{run_sequence:02d}"
        files: list[DiagnosticCsvFile] = []
        for result in results:
            if result.status is not ScanStatus.CONNECTED or not result.frames:
                continue
            kind = "wireless" if result.connection_type is ConnectionType.WIRELESS_RECEIVER else "wired"
            safe_port = re.sub(r"[^A-Za-z0-9._-]+", "-", result.port).strip("-") or "port"
            path = self._unique_path(self.temp_dir / f"imu_{run_id}_{safe_port}_{kind}.csv")
            if result.connection_type is ConnectionType.WIRELESS_RECEIVER:
                row_count = self._write_wireless_csv(path, result, run_timestamp)
            else:
                row_count = self._write_wired_csv(path, result, run_timestamp)
            self._managed_files.add(path)
            files.append(DiagnosticCsvFile(result.port, result.connection_type, path, row_count))
        return tuple(files)

    def _write_wireless_csv(
        self,
        path: Path,
        result: PortScanResult,
        fallback_timestamp: float,
    ) -> int:
        packets = _wireless_packets(result.frames)
        timestamp_by_frame = self._timestamp_by_frame(result)
        with path.open("w", encoding="utf-8-sig", newline="") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(WIRELESS_CSV_HEADER)
            for packet in packets:
                unix_timestamp = timestamp_by_frame.get(id(packet[0]), fallback_timestamp)
                writer.writerow(self._wireless_row(packet, unix_timestamp))
        return len(packets)

    def _write_wired_csv(
        self,
        path: Path,
        result: PortScanResult,
        fallback_timestamp: float,
    ) -> int:
        timestamp_by_frame = self._timestamp_by_frame(result)
        with path.open("w", encoding="utf-8-sig", newline="") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(WIRED_CSV_HEADER)
            for frame in result.frames:
                unix_timestamp = timestamp_by_frame.get(id(frame), fallback_timestamp)
                writer.writerow(self._wired_row(frame, unix_timestamp))
        return len(result.frames)

    @staticmethod
    def _timestamp_by_frame(result: PortScanResult) -> dict[int, float]:
        return {
            id(frame): timestamp
            for frame, timestamp in zip(result.frames, result.frame_timestamps)
        }

    @staticmethod
    def _unique_path(path: Path) -> Path:
        candidate = path
        counter = 2
        while candidate.exists():
            candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
            counter += 1
        return candidate

    @classmethod
    def _wireless_row(cls, packet: list[AnrotFrame], unix_timestamp: float) -> list[object]:
        first = packet[0]
        frames_by_index = {
            frame.node_index: frame
            for frame in packet
            if frame.node_index is not None and 0 <= frame.node_index < MAX_NODES
        }
        row: list[object] = [
            first.gw_ts_ms if first.gw_ts_ms is not None else "",
            int(unix_timestamp),
        ]
        for node_index in range(MAX_NODES):
            frame = frames_by_index.get(node_index)
            row.extend([""] * len(WIRELESS_NODE_FIELDS) if frame is None else cls._wireless_node_fields(frame))
        return row

    @classmethod
    def _wireless_node_fields(cls, frame: AnrotFrame) -> list[object]:
        return [
            frame.node_id if frame.node_id is not None else "",
            *cls._vector(frame.acc, 3),
            *cls._vector(frame.gyr, 2),
            *cls._vector(frame.mag, 2),
            cls._number(frame.roll, 2),
            cls._number(frame.pitch, 2),
            cls._number(frame.yaw, 2),
            *cls._vector(frame.quat, 3, count=4),
        ]

    @classmethod
    def _wired_row(cls, frame: AnrotFrame, unix_timestamp: float) -> list[object]:
        return [
            int(unix_timestamp),
            frame.system_time_ms if frame.system_time_ms is not None else "",
            cls._number(frame.pressure, 0),
            cls._number(frame.temperature, 0),
            *cls._vector(frame.acc, 3),
            *cls._vector(frame.gyr, 3),
            *cls._vector(frame.mag, 2),
            cls._number(frame.roll, 2),
            cls._number(frame.pitch, 2),
            cls._number(frame.yaw, 2),
            *cls._vector(frame.quat, 3, count=4),
        ]

    @staticmethod
    def _number(value, precision: int) -> str:
        return "" if value is None else f"{value:.{precision}f}"

    @classmethod
    def _vector(cls, value, precision: int, *, count: int = 3) -> list[str]:
        if value is None:
            return [""] * count
        return [cls._number(component, precision) for component in value]

    @staticmethod
    def _to_report_row(result: PortScanResult) -> DiagnosticReportRow:
        if result.connection_type is ConnectionType.WIRELESS_RECEIVER:
            nodes = ", ".join(str(node) for node in result.node_ids) or "—"
            group_nodes = f"Group {result.group_id if result.group_id is not None else '—'} / Nodes {nodes}"
        else:
            group_nodes = "—"
        duration = result.duration_seconds
        data_rows = (
            len(_wireless_packets(result.frames))
            if result.connection_type is ConnectionType.WIRELESS_RECEIVER
            else len(result.frames)
        )
        sample_rate = data_rows / duration if duration > 0 else 0.0
        if result.status is not ScanStatus.CONNECTED:
            sample_rate = 0.0
        return DiagnosticReportRow(
            port=result.port,
            manufacturer=result.manufacturer or "—",
            connection_type=result.connection_type.value,
            baud_rate=result.baud_rate,
            group_nodes=group_nodes,
            sample_rate_hz=round(sample_rate, 1),
            status=result.status.value,
            reason=result.reason,
        )
