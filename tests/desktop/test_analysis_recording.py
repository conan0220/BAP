from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from anrot_imu_driver.parsers.anrot_serial_parser import AnrotFrame
from bap_common.analysis_session import AnalysisInputBinding, AnalysisJobRequest
from bap_common.imu_csv import inspect_common_imu_csv
from bap_desktop.services.analysis_recording import (
    AnalysisSessionRecorder,
    CommonImuCsvRecorder,
    LiveAnalysisRecording,
    RecordingError,
    RecordingState,
)
from helpers import build_hi91_frame
from bap_desktop.services.imu_discovery import ImuSource
from bap_desktop.services.imu_scan import (
    ConnectionType,
    PortInfo,
    PortScanResult,
    ScanStatus,
)


class FakeAdapter:
    def list_ports(self):
        return [PortInfo("COM1"), PortInfo("COM2"), PortInfo("COM9")]

    def open(self, *_args, **_kwargs):
        raise AssertionError("fake scan should be injected")


def frame(*, node_id=None, gw_id=None, timestamp=1, value=1.0):
    item = AnrotFrame()
    item.frame_type = 0x63 if node_id is not None else 0x91
    item.node_id = node_id
    item.gw_id = gw_id
    item.gw_ts_ms = timestamp if node_id is not None else None
    item.system_time_ms = timestamp
    item.acc = (value, value + 1, value + 2)
    item.gyr = (3.0, 4.0, 5.0)
    item.mag = (6.0, 7.0, 8.0)
    item.quat = (1.0, 0.0, 0.0, 0.0)
    item.roll = item.pitch = item.yaw = 0.0
    return item


@pytest.mark.scenario("common-imu-csv", "Desktop App 完成一份 CSV")
def test_csv_recorder_uses_part_then_atomic_final_name(tmp_path: Path):
    path = tmp_path / "imu.csv"
    recorder = CommonImuCsvRecorder(path)
    with recorder:
        assert recorder.part_path.exists()
        assert not path.exists()
        recorder.append(frame(), elapsed_us=0, packet_index=0)
        inspected = recorder.finalize()
    assert path.exists()
    assert not recorder.part_path.exists()
    assert inspected.row_count == 1


@pytest.mark.scenario("common-imu-csv", "Session 使用兩顆無線 IMU")
@pytest.mark.scenario("common-imu-csv", "一個 Gateway packet 包含左右手 Nodes")
def test_one_csv_per_wireless_node_and_metadata(tmp_path: Path):
    sources = (
        ImuSource("COM1", ConnectionType.WIRELESS_RECEIVER, 7, 1),
        ImuSource("COM1", ConnectionType.WIRELESS_RECEIVER, 7, 2),
    )

    def fake_scan(adapter, **_kwargs):
        assert [item.device for item in adapter.list_ports()] == ["COM1"]
        frames = [frame(node_id=1, gw_id=7, timestamp=10), frame(node_id=2, gw_id=7, timestamp=10)]
        return [
            PortScanResult(
                port="COM1",
                manufacturer="ANROT",
                baud_rate=921600,
                started_at=0,
                ended_at=1,
                frames=frames,
                frame_timestamps=[100.0, 100.0],
                status=ScanStatus.CONNECTED,
                connection_type=ConnectionType.WIRELESS_RECEIVER,
                group_id=7,
                node_ids=(1, 2),
            )
        ]

    csv_ids = (uuid4(), uuid4())
    analysis = AnalysisJobRequest(
        analysis_id=uuid4(),
        analysis_type="punch_count",
        spec_version=1,
        input_bindings=(
            AnalysisInputBinding(input_role="left_wrist", csv_id=csv_ids[0]),
            AnalysisInputBinding(input_role="right_wrist", csv_id=csv_ids[1]),
        ),
    )
    recorder = AnalysisSessionRecorder(tmp_path, adapter=FakeAdapter(), scan=fake_scan, clock=lambda: 100.0)
    draft = recorder.record(
        sources=sources,
        analyses=(analysis,),
        desktop_version="0.1.3",
        duration_seconds=1,
        csv_ids_by_source={
            "COM1:group-7:node-1": csv_ids[0],
            "COM1:group-7:node-2": csv_ids[1],
        },
    )
    assert draft.state is RecordingState.FINALIZED
    assert draft.metadata is not None
    assert len(draft.metadata.csv_files) == 2
    assert {item.row_count for item in draft.metadata.csv_files} == {1}
    assert all(inspect_common_imu_csv(draft.directory / item.filename).row_count == 1 for item in draft.metadata.csv_files)
    assert (draft.directory / "metadata.json").exists()


def test_recording_failure_removes_incomplete_session(tmp_path: Path):
    source = ImuSource("COM2", ConnectionType.WIRED)

    def failed_scan(_adapter, **_kwargs):
        return []

    recorder = AnalysisSessionRecorder(tmp_path, adapter=FakeAdapter(), scan=failed_scan)
    with pytest.raises(RecordingError):
        recorder.record(sources=(source,), analyses=(), desktop_version="0.1.3", duration_seconds=1)
    assert list(tmp_path.iterdir()) == []


def test_common_csv_rejects_no_rows(tmp_path: Path):
    path = tmp_path / "empty.csv"
    recorder = CommonImuCsvRecorder(path)
    with pytest.raises(RecordingError):
        with recorder:
            recorder.finalize()
    assert not path.exists()


@pytest.mark.scenario("common-imu-csv", "一顆 IMU 連續寫入 Frames")
@pytest.mark.scenario("boxing-analysis-session", "user 結束測量")
@pytest.mark.scenario("boxing-analysis-session", "user 再次開始相同項目")
def test_live_recording_starts_and_stops_with_new_session_ids(tmp_path: Path):
    class Connection:
        def __init__(self):
            self.data = build_hi91_frame() + build_hi91_frame()
            self.closed = False

        @property
        def in_waiting(self):
            return len(self.data)

        def read(self, _size=1):
            data, self.data = self.data, b""
            return data

        def close(self):
            self.closed = True

    class Adapter:
        def __init__(self):
            self.connections = []

        def open(self, *_args, **_kwargs):
            connection = Connection()
            self.connections.append(connection)
            return connection

    adapter = Adapter()
    kwargs = dict(
        assignments={"left_wrist": ImuSource("COM1", ConnectionType.WIRED)},
        analysis_type="punch_count", spec_version=1, desktop_version="0.1.3",
        adapter=adapter,
    )
    first = LiveAnalysisRecording(tmp_path, **kwargs)
    first.start()
    import time
    time.sleep(0.02)
    first_draft = first.stop()
    second = LiveAnalysisRecording(tmp_path, **kwargs)

    assert first_draft.state is RecordingState.FINALIZED
    assert first_draft.metadata.csv_files[0].row_count == 2
    assert len(first_draft.metadata.analyses) == 1
    assert first_draft.metadata.analyses[0].analysis_type == "punch_count"
    assert first_draft.session_id != second.draft.session_id
    assert all(item.closed for item in adapter.connections)


@pytest.mark.scenario("common-imu-csv", "Session 使用不同 Port 的兩顆有線 IMU")
@pytest.mark.scenario("common-imu-csv", "兩個有線 Port 的接收時間不同")
@pytest.mark.scenario("common-imu-csv", "有線 IMU 沒有 Group ID 與 Node ID")
def test_mixed_wireless_nodes_and_wired_ports_use_one_csv_each_and_common_clock(tmp_path: Path):
    sources = (
        ImuSource("COM1", ConnectionType.WIRELESS_RECEIVER, 7, 1),
        ImuSource("COM1", ConnectionType.WIRELESS_RECEIVER, 7, 2),
        ImuSource("COM2", ConnectionType.WIRED),
        ImuSource("COM3", ConnectionType.WIRED),
    )

    def fake_scan(_adapter, **_kwargs):
        wireless = [frame(node_id=1, gw_id=7, timestamp=10), frame(node_id=2, gw_id=7, timestamp=10)]
        return [
            PortScanResult(
                port="COM1", manufacturer=None, baud_rate=921600, started_at=0, ended_at=1,
                frames=wireless, frame_timestamps=[100.25, 100.25], status=ScanStatus.CONNECTED,
                connection_type=ConnectionType.WIRELESS_RECEIVER, group_id=7, node_ids=(1, 2),
            ),
            PortScanResult(
                port="COM2", manufacturer=None, baud_rate=921600, started_at=0, ended_at=1,
                frames=[frame(timestamp=20)], frame_timestamps=[100.5], status=ScanStatus.CONNECTED,
                connection_type=ConnectionType.WIRED,
            ),
            PortScanResult(
                port="COM3", manufacturer=None, baud_rate=921600, started_at=0, ended_at=1,
                frames=[frame(timestamp=30)], frame_timestamps=[100.75], status=ScanStatus.CONNECTED,
                connection_type=ConnectionType.WIRED,
            ),
        ]

    csv_ids = {source_id: uuid4() for source_id in (
        "COM1:group-7:node-1", "COM1:group-7:node-2", "COM2:wired", "COM3:wired"
    )}
    job = AnalysisJobRequest(
        analysis_id=uuid4(), analysis_type="mixed_test", spec_version=1,
        input_bindings=tuple(
            AnalysisInputBinding(input_role=f"source_{index}", csv_id=csv_ids[key])
            for index, key in enumerate(csv_ids)
        ),
    )
    recorder = AnalysisSessionRecorder(tmp_path, adapter=FakeAdapter(), scan=fake_scan, clock=lambda: 100.0)
    draft = recorder.record(
        sources=sources, analyses=(job,), desktop_version="0.1.3", duration_seconds=1,
        csv_ids_by_source=csv_ids,
    )
    assert len(draft.metadata.csv_files) == 4
    import csv
    elapsed = {}
    packets = {}
    for descriptor in draft.metadata.csv_files:
        with (draft.directory / descriptor.filename).open(encoding="utf-8", newline="") as stream:
            row = next(csv.DictReader(stream))
        elapsed[descriptor.source.source_id] = int(row["elapsed_us"])
        packets[descriptor.source.source_id] = int(row["packet_index"])
    assert elapsed["COM1:group-7:node-1"] == elapsed["COM1:group-7:node-2"] == 250_000
    assert packets["COM1:group-7:node-1"] == packets["COM1:group-7:node-2"] == 0
    assert elapsed["COM2:wired"] == 500_000
    assert elapsed["COM3:wired"] == 750_000
