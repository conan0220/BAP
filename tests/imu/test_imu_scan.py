from __future__ import annotations

from dataclasses import dataclass
from threading import Barrier, Event

import pytest

from bap_desktop.services.imu_scan import (
    DEFAULT_BAUD_RATE,
    ConnectionType,
    PortInfo,
    ReasonCode,
    ScanStatus,
    scan_all_ports,
)
from tests.helpers import build_gateway_frame, build_gateway_node


@dataclass
class FakeConnection:
    chunks: list[bytes]
    error: BaseException | None = None
    closed: bool = False
    write_called: bool = False

    @property
    def in_waiting(self) -> int:
        if self.error is not None:
            error, self.error = self.error, None
            raise error
        return len(self.chunks[0]) if self.chunks else 0

    def read(self, size: int = 1) -> bytes:
        return self.chunks.pop(0) if self.chunks else b""

    def close(self) -> None:
        self.closed = True


class FakeAdapter:
    def __init__(self, connections: dict[str, FakeConnection | BaseException]):
        self.connections = connections
        self.open_calls: list[tuple[str, int]] = []

    def list_ports(self):
        return [PortInfo(port, None if port == "COM2" else "ANROT") for port in self.connections]

    def open(self, port: str, *, baud_rate: int, timeout: float):
        self.open_calls.append((port, baud_rate))
        value = self.connections[port]
        if isinstance(value, BaseException):
            raise value
        return value


class CoordinatedAdapter(FakeAdapter):
    """Requires every fake port worker to reach open() before any may continue."""

    def __init__(self, connections: dict[str, FakeConnection | BaseException]):
        super().__init__(connections)
        self.open_barrier = Barrier(len(connections))

    def open(self, port: str, *, baud_rate: int, timeout: float):
        connection = super().open(port, baud_rate=baud_rate, timeout=timeout)
        self.open_barrier.wait(timeout=1)
        return connection


@pytest.mark.scenario("imu-connection-diagnostics", "電腦有多個 Port")
@pytest.mark.scenario("imu-connection-diagnostics", "成功解析有線 IMU")
@pytest.mark.scenario("imu-connection-diagnostics", "成功解析無線接收器資料")
@pytest.mark.scenario("imu-connection-diagnostics", "Manufacturer 可以取得")
@pytest.mark.scenario("imu-connection-diagnostics", "Manufacturer 無法取得")
def test_scans_ports_concurrently_with_fixed_baud_and_manufacturer(hi91_frame) -> None:
    adapter = CoordinatedAdapter(
        {
            "COM1": FakeConnection([hi91_frame]),
            "COM2": FakeConnection([build_gateway_frame()]),
        }
    )
    results = scan_all_ports(adapter, duration_seconds=0.03)

    assert set(adapter.open_calls) == {
        ("COM1", DEFAULT_BAUD_RATE),
        ("COM2", DEFAULT_BAUD_RATE),
    }
    assert results[0].manufacturer == "ANROT"
    assert results[1].manufacturer is None
    assert all(result.status is ScanStatus.CONNECTED for result in results)
    assert results[0].connection_type is ConnectionType.WIRED
    assert results[1].connection_type is ConnectionType.WIRELESS_RECEIVER


@pytest.mark.scenario("imu-connection-diagnostics", "無線接收器有多個 Node")
def test_wireless_result_has_group_and_sorted_unique_nodes() -> None:
    raw = build_gateway_frame(
        nodes=(build_gateway_node(12), build_gateway_node(11), build_gateway_node(12)),
        gateway_id=7,
    )
    result = scan_all_ports(
        FakeAdapter({"COM7": FakeConnection([raw])}), duration_seconds=0.01
    )[0]
    assert result.group_id == 7
    assert result.node_ids == (11, 12)


@pytest.mark.parametrize(
    ("connection", "expected"),
    [
        (FakeConnection([]), ReasonCode.NO_BYTES),
        (FakeConnection([b"not-an-imu-frame"]), ReasonCode.UNSUPPORTED_DATA),
        (PermissionError("Access is denied"), ReasonCode.PERMISSION_DENIED),
        (OSError("port is busy and in use"), ReasonCode.PORT_IN_USE),
        (FakeConnection([], OSError("device disconnected")), ReasonCode.DISCONNECTED),
        (OSError("unknown serial failure"), ReasonCode.SERIAL_ERROR),
    ],
)
@pytest.mark.scenario("imu-connection-diagnostics", "沒有成功解析資料")
@pytest.mark.scenario("imu-connection-diagnostics", "Port 正被使用")
@pytest.mark.scenario("imu-connection-diagnostics", "沒有 Port 權限")
@pytest.mark.scenario("imu-connection-diagnostics", "測試期間 Port 消失")
@pytest.mark.scenario("imu-connection-diagnostics", "五秒內沒有收到 bytes")
@pytest.mark.scenario("imu-connection-diagnostics", "收到 bytes 但無法解析")
def test_reason_code_isolated_per_port(connection, expected) -> None:
    adapter = FakeAdapter({"COM9": connection, "COM10": FakeConnection([])})
    results = scan_all_ports(adapter, duration_seconds=0.005)
    assert results[0].reason_code is expected
    assert len(results) == 2


def test_cancel_marks_result_without_writing() -> None:
    connection = FakeConnection([])
    cancel = Event()
    cancel.set()
    result = scan_all_ports(
        FakeAdapter({"COM3": connection}),
        duration_seconds=1,
        cancel_event=cancel,
    )[0]
    assert result.status is ScanStatus.CANCELLED
    assert result.reason_code is ReasonCode.CANCELLED
    assert connection.closed
    assert not connection.write_called


@pytest.mark.scenario("imu-connection-diagnostics", "電腦沒有 Port")
def test_no_ports_returns_empty_result() -> None:
    assert scan_all_ports(FakeAdapter({}), duration_seconds=1) == []
