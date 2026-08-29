"""Fresh three-second IMU source discovery for one boxing item."""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class ImuSource:
    port: str
    connection_type: ConnectionType
    group_id: int | None = None
    node_id: int | None = None

    @property
    def label(self) -> str:
        if self.connection_type is ConnectionType.WIRED:
            return f"{self.port}｜有線連接"
        return f"{self.port}｜無線接收器連接｜Group {self.group_id}｜Node {self.node_id}"


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    sources: tuple[ImuSource, ...]
    port_reasons: tuple[tuple[str, str], ...]


class ImuDiscoveryService:
    def __init__(
        self,
        *,
        adapter: PortAdapter | None = None,
        duration_seconds: float = 3.0,
        scan: Callable[..., list[PortScanResult]] = scan_all_ports,
    ) -> None:
        self.adapter = adapter or PySerialPortAdapter()
        self.duration_seconds = duration_seconds
        self.scan = scan
        self._latest: DiscoveryResult | None = None

    @property
    def latest_result(self) -> DiscoveryResult | None:
        return self._latest

    def discover(self, *, cancel_event: Event | None = None) -> DiscoveryResult:
        # This intentionally performs a new scan on every invocation and has no
        # dependency on the five-second diagnostics service or its CSV cache.
        results = self.scan(
            self.adapter,
            duration_seconds=self.duration_seconds,
            baud_rate=DEFAULT_BAUD_RATE,
            cancel_event=cancel_event,
        )
        sources: list[ImuSource] = []
        reasons: list[tuple[str, str]] = []
        for result in results:
            if result.status is not ScanStatus.CONNECTED:
                reasons.append((result.port, result.reason))
                continue
            if result.connection_type is ConnectionType.WIRED:
                sources.append(ImuSource(result.port, ConnectionType.WIRED))
            elif result.connection_type is ConnectionType.WIRELESS_RECEIVER:
                sources.extend(
                    ImuSource(
                        result.port,
                        ConnectionType.WIRELESS_RECEIVER,
                        group_id=result.group_id,
                        node_id=node_id,
                    )
                    for node_id in result.node_ids
                )
        self._latest = DiscoveryResult(tuple(sources), tuple(reasons))
        return self._latest

    def clear(self) -> None:
        self._latest = None
