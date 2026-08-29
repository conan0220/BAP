"""Five-second IMU diagnostics, local CSV storage, and report calculation."""

from __future__ import annotations

import csv
import json
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable

from bap_desktop.services.imu_scan import (
    DEFAULT_BAUD_RATE,
    ConnectionType,
    PortAdapter,
    PortScanResult,
    PySerialPortAdapter,
    ScanStatus,
    scan_all_ports,
)


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
    csv_path: Path | None


class ImuDiagnosticsService:
    """Run one bounded scan and keep its CSV only in App-managed local storage."""

    def __init__(
        self,
        *,
        adapter: PortAdapter | None = None,
        duration_seconds: float = 5.0,
        temp_dir: Path | None = None,
        scan: Callable[..., list[PortScanResult]] = scan_all_ports,
    ) -> None:
        self.adapter = adapter or PySerialPortAdapter()
        self.duration_seconds = duration_seconds
        self.temp_dir = temp_dir or Path(tempfile.gettempdir()) / "BAP" / "imu-diagnostics"
        self.scan = scan
        self._managed_files: set[Path] = set()
        self._latest: DiagnosticReport | None = None

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
        csv_path = self._write_csv(results) if any(result.frames for result in results) else None
        rows = tuple(self._to_report_row(result) for result in results)
        self._latest = DiagnosticReport(rows=rows, csv_path=csv_path)
        return self._latest

    def export_csv(self, destination: Path) -> Path:
        if self._latest is None or self._latest.csv_path is None:
            raise FileNotFoundError("目前沒有可匯出的 IMU 測試 CSV")
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self._latest.csv_path, destination)
        return destination

    def cleanup(self) -> None:
        for path in tuple(self._managed_files):
            path.unlink(missing_ok=True)
            self._managed_files.discard(path)
        self._latest = None

    def _delete_latest_csv(self) -> None:
        if self._latest is not None and self._latest.csv_path is not None:
            self._latest.csv_path.unlink(missing_ok=True)
            self._managed_files.discard(self._latest.csv_path)

    def _write_csv(self, results: list[PortScanResult]) -> Path:
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        path = self.temp_dir / f"{uuid.uuid4()}.csv"
        frame_keys = sorted(
            {
                key
                for result in results
                for frame in result.frames
                for key in frame.to_dict()
            }
        )
        fieldnames = [
            "port",
            "manufacturer",
            "connection_type",
            "group_id",
            "node_id",
            *frame_keys,
        ]
        with path.open("w", encoding="utf-8-sig", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for result in results:
                for frame in result.frames:
                    row = {
                        "port": result.port,
                        "manufacturer": result.manufacturer or "",
                        "connection_type": result.connection_type.value,
                        "group_id": getattr(frame, "gw_id", None),
                        "node_id": getattr(frame, "node_id", None),
                    }
                    row.update(
                        {
                            key: json.dumps(value, ensure_ascii=False)
                            if isinstance(value, (list, tuple, dict))
                            else value
                            for key, value in frame.to_dict().items()
                        }
                    )
                    writer.writerow(row)
        self._managed_files.add(path)
        return path

    @staticmethod
    def _to_report_row(result: PortScanResult) -> DiagnosticReportRow:
        if result.connection_type is ConnectionType.WIRELESS_RECEIVER:
            nodes = ", ".join(str(node) for node in result.node_ids) or "—"
            group_nodes = f"Group {result.group_id if result.group_id is not None else '—'} / Nodes {nodes}"
        else:
            group_nodes = "—"
        duration = result.duration_seconds
        sample_rate = len(result.frames) / duration if duration > 0 else 0.0
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
