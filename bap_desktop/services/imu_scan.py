"""Qt-independent, bounded serial-port scanning for supported ANROT IMUs."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import StrEnum
from threading import Event
from typing import Callable, Protocol, Sequence

import serial
from serial.tools import list_ports

from anrot_imu_driver.parsers.anrot_serial_parser import AnrotFrame, AnrotSerialParser


DEFAULT_BAUD_RATE = 921600


@dataclass(frozen=True, slots=True)
class PortInfo:
    device: str
    manufacturer: str | None = None


class SerialConnection(Protocol):
    @property
    def in_waiting(self) -> int: ...

    def read(self, size: int = 1) -> bytes: ...

    def close(self) -> None: ...


class PortAdapter(Protocol):
    def list_ports(self) -> Sequence[PortInfo]: ...

    def open(self, port: str, *, baud_rate: int, timeout: float) -> SerialConnection: ...


class PySerialPortAdapter:
    """Production adapter around pyserial and the operating-system port list."""

    def list_ports(self) -> list[PortInfo]:
        return [
            PortInfo(device=port.device, manufacturer=port.manufacturer or None)
            for port in list_ports.comports()
        ]

    def open(self, port: str, *, baud_rate: int, timeout: float) -> SerialConnection:
        return serial.Serial(
            port=port,
            baudrate=baud_rate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout,
        )


class ConnectionType(StrEnum):
    WIRED = "有線連接"
    WIRELESS_RECEIVER = "無線接收器連接"
    UNKNOWN = "—"


class ScanStatus(StrEnum):
    CONNECTED = "已連線"
    NOT_CONNECTED = "未連線"
    CANCELLED = "已取消"


class ReasonCode(StrEnum):
    NONE = "none"
    PORT_IN_USE = "port_in_use"
    PERMISSION_DENIED = "permission_denied"
    DISCONNECTED = "disconnected"
    NO_BYTES = "no_bytes"
    UNSUPPORTED_DATA = "unsupported_data"
    SERIAL_ERROR = "serial_error"
    CANCELLED = "cancelled"


REASON_MESSAGES: dict[ReasonCode, str] = {
    ReasonCode.NONE: "資料解析正常",
    ReasonCode.PORT_IN_USE: "Port 正在使用中",
    ReasonCode.PERMISSION_DENIED: "沒有權限開啟此 Port",
    ReasonCode.DISCONNECTED: "測試期間裝置已中斷",
    ReasonCode.NO_BYTES: "可能不是 IMU、裝置未開啟，或波特率不是 921600",
    ReasonCode.UNSUPPORTED_DATA: "收到不支援的資料，可能不是 IMU 或波特率設定不正確",
    ReasonCode.SERIAL_ERROR: "無法讀取此 Port",
    ReasonCode.CANCELLED: "測試已取消",
}


@dataclass(slots=True)
class PortScanResult:
    port: str
    manufacturer: str | None
    baud_rate: int
    started_at: float
    ended_at: float
    byte_count: int = 0
    frames: list[AnrotFrame] = field(default_factory=list)
    connection_type: ConnectionType = ConnectionType.UNKNOWN
    group_id: int | None = None
    node_ids: tuple[int, ...] = ()
    status: ScanStatus = ScanStatus.NOT_CONNECTED
    reason_code: ReasonCode = ReasonCode.NO_BYTES

    @property
    def duration_seconds(self) -> float:
        return max(0.0, self.ended_at - self.started_at)

    @property
    def reason(self) -> str:
        return REASON_MESSAGES[self.reason_code]


def _classify_exception(error: BaseException, *, opened: bool) -> ReasonCode:
    text = str(error).lower()
    if isinstance(error, PermissionError) or "permission" in text or "access is denied" in text:
        return ReasonCode.PERMISSION_DENIED
    if "busy" in text or "in use" in text or "being used" in text:
        return ReasonCode.PORT_IN_USE
    if opened and ("disconnected" in text or "device" in text or "does not exist" in text):
        return ReasonCode.DISCONNECTED
    return ReasonCode.SERIAL_ERROR


def _finalize_classification(result: PortScanResult) -> None:
    if not result.frames:
        result.status = ScanStatus.NOT_CONNECTED
        result.reason_code = (
            ReasonCode.NO_BYTES if result.byte_count == 0 else ReasonCode.UNSUPPORTED_DATA
        )
        return

    wireless_frames = [frame for frame in result.frames if frame.frame_type == 0x63]
    if wireless_frames:
        result.connection_type = ConnectionType.WIRELESS_RECEIVER
        group_ids = sorted({frame.gw_id for frame in wireless_frames if frame.gw_id is not None})
        result.group_id = group_ids[0] if group_ids else None
        result.node_ids = tuple(
            sorted({frame.node_id for frame in wireless_frames if frame.node_id is not None})
        )
    else:
        result.connection_type = ConnectionType.WIRED
    result.status = ScanStatus.CONNECTED
    result.reason_code = ReasonCode.NONE


def scan_port(
    port_info: PortInfo,
    adapter: PortAdapter,
    *,
    duration_seconds: float,
    baud_rate: int = DEFAULT_BAUD_RATE,
    cancel_event: Event | None = None,
    parser_factory: Callable[[], AnrotSerialParser] = AnrotSerialParser,
    clock: Callable[[], float] = time.perf_counter,
    sleep: Callable[[float], None] = time.sleep,
) -> PortScanResult:
    """Read one port until a fixed deadline without ever writing to the device."""

    started = clock()
    result = PortScanResult(
        port=port_info.device,
        manufacturer=port_info.manufacturer,
        baud_rate=baud_rate,
        started_at=started,
        ended_at=started,
    )
    connection: SerialConnection | None = None
    opened = False
    try:
        connection = adapter.open(
            port_info.device,
            baud_rate=baud_rate,
            timeout=min(0.05, max(duration_seconds, 0.001)),
        )
        opened = True
        parser = parser_factory()
        # Opening a real serial port (and scheduling this worker) is setup time,
        # not part of the requested recording window.  Starting the deadline
        # here also keeps every concurrently scanned port from losing its whole
        # sample window when another worker is slow to start.
        recording_started = clock()
        result.started_at = recording_started
        deadline = recording_started + max(duration_seconds, 0.0)
        while clock() < deadline:
            if cancel_event is not None and cancel_event.is_set():
                result.status = ScanStatus.CANCELLED
                result.reason_code = ReasonCode.CANCELLED
                return result
            available = max(0, int(connection.in_waiting))
            if available == 0:
                sleep(min(0.005, max(0.0, deadline - clock())))
                continue
            data = connection.read(available)
            result.byte_count += len(data)
            result.frames.extend(parser.parse(data))
        _finalize_classification(result)
    except (OSError, serial.SerialException) as error:
        result.status = ScanStatus.NOT_CONNECTED
        result.reason_code = _classify_exception(error, opened=opened)
    finally:
        result.ended_at = clock()
        if connection is not None:
            try:
                connection.close()
            except (OSError, serial.SerialException):
                if result.reason_code is ReasonCode.NONE:
                    result.status = ScanStatus.NOT_CONNECTED
                    result.reason_code = ReasonCode.DISCONNECTED
    return result


def scan_all_ports(
    adapter: PortAdapter,
    *,
    duration_seconds: float,
    baud_rate: int = DEFAULT_BAUD_RATE,
    cancel_event: Event | None = None,
    max_workers: int | None = None,
) -> list[PortScanResult]:
    """Scan a snapshot of all candidate ports concurrently and isolate failures."""

    ports = list(adapter.list_ports())
    if not ports:
        return []
    workers = max_workers or len(ports)
    results: dict[str, PortScanResult] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="bap-imu") as executor:
        futures = {
            executor.submit(
                scan_port,
                port,
                adapter,
                duration_seconds=duration_seconds,
                baud_rate=baud_rate,
                cancel_event=cancel_event,
            ): port
            for port in ports
        }
        for future in as_completed(futures):
            port = futures[future]
            try:
                results[port.device] = future.result()
            except BaseException:
                now = time.perf_counter()
                results[port.device] = PortScanResult(
                    port=port.device,
                    manufacturer=port.manufacturer,
                    baud_rate=baud_rate,
                    started_at=now,
                    ended_at=now,
                    reason_code=ReasonCode.SERIAL_ERROR,
                )
    return [results[port.device] for port in ports]
