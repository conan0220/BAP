from __future__ import annotations

from dataclasses import replace

import pytest

from anrot_imu_driver.parsers.anrot_serial_parser import AnrotSerialParser
from bap_desktop.services.imu_discovery import ImuDiscoveryService
from bap_desktop.services.imu_scan import (
    ConnectionType,
    PortScanResult,
    ReasonCode,
    ScanStatus,
)
from bap_desktop.ui.punch_items import PunchItemPage


def make_result(port: str, raw: bytes, connection_type: ConnectionType) -> PortScanResult:
    frames = AnrotSerialParser().parse(raw)
    return PortScanResult(
        port=port,
        manufacturer="ANROT",
        baud_rate=921600,
        started_at=1,
        ended_at=4,
        byte_count=len(raw),
        frames=frames,
        connection_type=connection_type,
        group_id=frames[0].gw_id if connection_type is ConnectionType.WIRELESS_RECEIVER else None,
        node_ids=tuple(sorted({frame.node_id for frame in frames if frame.node_id is not None})),
        status=ScanStatus.CONNECTED,
        reason_code=ReasonCode.NONE,
    )


@pytest.mark.scenario("imu-source-discovery", "先前已查看 IMU 連線狀態")
@pytest.mark.scenario("imu-source-discovery", "先前沒有執行 IMU 測試")
@pytest.mark.scenario("imu-source-discovery", "正在探索多個 Port")
@pytest.mark.scenario("imu-source-discovery", "發現有線 IMU")
@pytest.mark.scenario("imu-source-discovery", "發現無線接收器與多個 Node")
@pytest.mark.scenario("imu-source-discovery", "相同 ID 出現在不同 Port")
def test_discovery_runs_fresh_scan_and_preserves_port_identity(hi91_frame, gateway_frame) -> None:
    calls = []
    wireless = make_result("COM2", gateway_frame, ConnectionType.WIRELESS_RECEIVER)
    results = [
        make_result("COM1", hi91_frame, ConnectionType.WIRED),
        wireless,
        replace(wireless, port="COM3"),
    ]

    def scan(*args, **kwargs):
        calls.append(kwargs)
        return results

    service = ImuDiscoveryService(adapter=object(), scan=scan)
    first = service.discover()
    second = service.discover()
    assert len(calls) == 2
    assert all(call["duration_seconds"] == 3.0 for call in calls)
    assert [source.port for source in first.sources] == ["COM1", "COM2", "COM3"]
    assert first == second


def test_only_successfully_parsed_sources_are_offered(hi91_frame) -> None:
    connected = make_result("COM1", hi91_frame, ConnectionType.WIRED)
    failed = replace(
        connected,
        port="COM9",
        frames=[],
        status=ScanStatus.NOT_CONNECTED,
        reason_code=ReasonCode.NO_BYTES,
        connection_type=ConnectionType.UNKNOWN,
    )
    result = ImuDiscoveryService(
        adapter=object(), scan=lambda *args, **kwargs: [connected, failed]
    ).discover()
    assert [source.port for source in result.sources] == ["COM1"]
    assert result.port_reasons == (("COM9", failed.reason),)


@pytest.mark.scenario("desktop-app-shell", "完成 IMU 來源選擇")
@pytest.mark.scenario("imu-source-discovery", "改選有線 Port")
@pytest.mark.scenario("imu-source-discovery", "選好來源並繼續")
def test_page_enforces_single_selection_and_shows_pending(qtbot, hi91_frame) -> None:
    service = ImuDiscoveryService(
        adapter=object(),
        duration_seconds=0.01,
        scan=lambda *args, **kwargs: [
            make_result("COM1", hi91_frame, ConnectionType.WIRED),
            make_result("COM2", hi91_frame, ConnectionType.WIRED),
        ],
    )
    page = PunchItemPage("出拳速度", service)
    qtbot.addWidget(page)
    page.show()
    qtbot.waitUntil(lambda: len(page._source_buttons) == 2, timeout=1000)
    buttons = list(page._source_buttons)
    buttons[0].click()
    assert page.selected_source.port == "COM1"
    buttons[1].click()
    assert page.selected_source.port == "COM2"
    assert not buttons[0].isChecked()
    page.continue_button.click()
    assert page.status.text() == "出拳速度：待開發"
    assert service.latest_result is None


@pytest.mark.scenario("imu-source-discovery", "user 按下再次確認")
@pytest.mark.scenario("imu-source-discovery", "所有 Port 都沒有可解析資料")
def test_page_shows_reasons_and_can_retry(qtbot) -> None:
    failed = PortScanResult(
        port="COM8",
        manufacturer=None,
        baud_rate=921600,
        started_at=0,
        ended_at=3,
        reason_code=ReasonCode.NO_BYTES,
    )
    calls = []

    def scan(*args, **kwargs):
        calls.append(1)
        return [failed]

    service = ImuDiscoveryService(adapter=object(), duration_seconds=0.01, scan=scan)
    page = PunchItemPage("出拳力量", service)
    qtbot.addWidget(page)
    page.show()
    qtbot.waitUntil(lambda: page.retry_button.isVisible(), timeout=1000)
    assert page.status.text() == "找不到可用的 IMU"
    assert "COM8" in page.sources_layout.itemAt(0).widget().text()
    page.retry_button.click()
    qtbot.waitUntil(lambda: len(calls) == 2, timeout=1000)


@pytest.mark.scenario("imu-source-discovery", "選擇無線 Node")
def test_page_selects_one_wireless_node(qtbot, gateway_frame) -> None:
    service = ImuDiscoveryService(
        adapter=object(),
        duration_seconds=0.01,
        scan=lambda *args, **kwargs: [
            make_result("COM7", gateway_frame, ConnectionType.WIRELESS_RECEIVER)
        ],
    )
    page = PunchItemPage("拳型辨識", service)
    qtbot.addWidget(page)
    page.show()
    qtbot.waitUntil(lambda: len(page._source_buttons) >= 1, timeout=1000)
    button = list(page._source_buttons)[0]
    button.click()

    assert page.selected_source is not None
    assert page.selected_source.port == "COM7"
    assert page.selected_source.group_id is not None
    assert page.selected_source.node_id is not None
