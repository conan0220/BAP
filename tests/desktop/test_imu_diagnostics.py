from __future__ import annotations

import csv
import time
from pathlib import Path

import pytest

from anrot_imu_driver.parsers.anrot_serial_parser import AnrotSerialParser
from bap_desktop.services.imu_diagnostics import (
    ImuDiagnosticsService,
    REPORT_COLUMNS,
    WIRED_CSV_HEADER,
    WIRELESS_CSV_HEADER,
)
from bap_desktop.services.imu_scan import (
    ConnectionType,
    PortScanResult,
    ReasonCode,
    ScanStatus,
)
from bap_desktop.ui.imu_diagnostics import ImuDiagnosticsPage
from tests.helpers import build_gateway_frame, build_gateway_node


def result_with_frames(port: str, raw: bytes, *, duration: float = 5.0) -> PortScanResult:
    frames = AnrotSerialParser().parse(raw)
    return PortScanResult(
        port=port,
        manufacturer="ANROT",
        baud_rate=921600,
        started_at=10.0,
        ended_at=10.0 + duration,
        byte_count=len(raw),
        frames=frames,
        connection_type=ConnectionType.WIRELESS_RECEIVER
        if frames and frames[0].frame_type == 0x63
        else ConnectionType.WIRED,
        group_id=frames[0].gw_id if frames else None,
        node_ids=tuple(sorted({frame.node_id for frame in frames if frame.node_id is not None})),
        status=ScanStatus.CONNECTED if frames else ScanStatus.NOT_CONNECTED,
        reason_code=ReasonCode.NONE if frames else ReasonCode.NO_BYTES,
    )


@pytest.mark.scenario("imu-connection-diagnostics", "正在產生 Report")
def test_report_and_csv_use_rows_over_actual_duration(tmp_path: Path, hi91_frame) -> None:
    results = [result_with_frames("COM3", hi91_frame * 2, duration=0.5)]
    service = ImuDiagnosticsService(
        adapter=object(),
        duration_seconds=5,
        temp_dir=tmp_path,
        scan=lambda *args, **kwargs: results,
    )
    report = service.run()
    assert report.rows[0].sample_rate_hz == 4.0
    assert report.rows[0].as_display_values()[0:4] == ("COM3", "ANROT", "有線連接", "921600")
    assert report.csv_path is not None
    with report.csv_path.open(encoding="utf-8-sig", newline="") as csv_file:
        rows = list(csv.reader(csv_file))
    assert tuple(rows[0]) == WIRED_CSV_HEADER
    assert len(rows) == 3
    assert report.csv_path.name.startswith("imu_")
    assert report.csv_path.name.endswith("_COM3_wired.csv")


@pytest.mark.scenario("imu-connection-diagnostics", "按下重新測試")
@pytest.mark.scenario("imu-connection-diagnostics", "匯出 CSV")
@pytest.mark.scenario("imu-connection-diagnostics", "App 關閉時存在未匯出的暫存 CSV")
def test_retest_replaces_old_csv_and_export_survives_cleanup(tmp_path: Path, hi91_frame) -> None:
    service = ImuDiagnosticsService(
        adapter=object(),
        temp_dir=tmp_path / "managed",
        scan=lambda *args, **kwargs: [result_with_frames("COM1", hi91_frame)],
    )
    first = service.run().csv_path
    second = service.run().csv_path
    assert first is not None and not first.exists()
    assert second is not None and second.exists()
    exported = service.export_csv(tmp_path / "user" / "report.csv")
    service.cleanup()
    assert not second.exists()
    assert exported.exists()


def test_no_ports_produces_empty_report_without_csv(tmp_path: Path) -> None:
    service = ImuDiagnosticsService(
        adapter=object(), temp_dir=tmp_path, scan=lambda *args, **kwargs: []
    )
    report = service.run()
    assert report.rows == ()
    assert report.csv_files == ()
    assert report.csv_path is None


@pytest.mark.scenario("imu-connection-diagnostics", "正在收集資料")
@pytest.mark.scenario("imu-connection-diagnostics", "完成 IMU 連線測試")
def test_report_ui_has_required_columns_and_stays_responsive(qtbot, tmp_path: Path, hi91_frame) -> None:
    class SlowService(ImuDiagnosticsService):
        def run(self, *, cancel_event=None, phase_callback=None):
            time.sleep(0.03)
            return super().run(cancel_event=cancel_event, phase_callback=phase_callback)

    service = SlowService(
        adapter=object(),
        duration_seconds=0.03,
        temp_dir=tmp_path,
        scan=lambda *args, **kwargs: [result_with_frames("COM5", hi91_frame, duration=0.03)],
    )
    page = ImuDiagnosticsPage(service)
    qtbot.addWidget(page)
    page.show()
    assert page.status_label.text() in {"準備測試所有 Port", "IMU 測試中，請稍後。正在收集資料…"}
    qtbot.waitUntil(lambda: page.table.rowCount() == 1, timeout=1000)
    assert tuple(page.table.horizontalHeaderItem(index).text() for index in range(page.table.columnCount())) == REPORT_COLUMNS
    assert page.retest_button.isEnabled()
    assert page.export_button.isEnabled()
    page.shutdown()


def test_diagnostics_module_has_no_remote_api_dependency() -> None:
    source = Path(ImuDiagnosticsService.__module__.replace(".", "/") + ".py")
    actual = Path(__file__).resolve().parents[2] / source
    text = actual.read_text(encoding="utf-8")
    assert "api_client" not in text
    assert "httpx" not in text


@pytest.mark.scenario("imu-connection-diagnostics", "五秒內寫入 2000 筆資料")
@pytest.mark.scenario("imu-connection-diagnostics", "資料內容重複")
def test_sample_rate_uses_all_raw_rows_even_when_values_repeat(tmp_path: Path, hi91_frame) -> None:
    service = ImuDiagnosticsService(
        adapter=object(),
        duration_seconds=5,
        temp_dir=tmp_path,
        scan=lambda *args, **kwargs: [result_with_frames("COM4", hi91_frame * 2000, duration=5.0)],
    )
    report = service.run()

    assert report.rows[0].sample_rate_hz == 400.0
    assert report.csv_path is not None
    with report.csv_path.open(encoding="utf-8-sig", newline="") as csv_file:
        assert sum(1 for _ in csv.DictReader(csv_file)) == 2000


@pytest.mark.scenario("imu-connection-diagnostics", "同一個無線封包包含多個 Node")
@pytest.mark.scenario("imu-connection-diagnostics", "產生無線接收器 CSV")
def test_wireless_csv_matches_reference_schema_and_counts_packets_not_nodes(tmp_path: Path) -> None:
    raw_packet = build_gateway_frame(
        gateway_id=3,
        timestamp_ms=142970,
        nodes=(build_gateway_node(0), build_gateway_node(1)),
    )
    service = ImuDiagnosticsService(
        adapter=object(),
        duration_seconds=2,
        temp_dir=tmp_path,
        wall_clock=lambda: 1_788_528_607,
        scan=lambda *args, **kwargs: [
            result_with_frames("COM7", raw_packet * 10, duration=2.0)
        ],
    )

    report = service.run()

    assert report.rows[0].sample_rate_hz == 5.0
    assert report.csv_path is not None
    assert report.csv_path.name.endswith("_COM7_wireless.csv")
    with report.csv_path.open(encoding="utf-8-sig", newline="") as csv_file:
        rows = list(csv.reader(csv_file))
    assert tuple(rows[0]) == WIRELESS_CSV_HEADER
    assert len(rows) == 11
    assert rows[1][:3] == ["142970", "1788528607", "0"]
    assert rows[1][2 + 17] == "1"


@pytest.mark.scenario("imu-connection-diagnostics", "產生有線 IMU CSV")
@pytest.mark.scenario("imu-connection-diagnostics", "同時測試多個已連線 Port")
def test_each_connected_port_gets_its_own_schema_file(tmp_path: Path, hi91_frame) -> None:
    wireless = build_gateway_frame(nodes=(build_gateway_node(2), build_gateway_node(3)))
    service = ImuDiagnosticsService(
        adapter=object(),
        temp_dir=tmp_path / "managed",
        scan=lambda *args, **kwargs: [
            result_with_frames("COM1", hi91_frame),
            result_with_frames("COM7", wireless),
        ],
    )

    report = service.run()
    exported = service.export_csv_files(tmp_path / "exported")

    assert len(report.csv_files) == 2
    assert report.csv_path is None
    assert {item.connection_type for item in report.csv_files} == {
        ConnectionType.WIRED,
        ConnectionType.WIRELESS_RECEIVER,
    }
    assert len(exported) == 2
    assert all(path.exists() for path in exported)
