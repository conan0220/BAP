from __future__ import annotations

import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from anrot_imu_driver.parsers.anrot_serial_parser import AnrotFrame
from bap_common.benchmark_bundle import BenchmarkGroundTruth, BenchmarkInputDescriptor, BenchmarkMetadata, BenchmarkStopReason
from bap_common.analysis_session import ImuSourceDescriptor, SourceConnectionType
from bap_common.imu_csv import inspect_common_imu_csv
from bap_desktop.services.analysis_recording import CommonImuCsvRecorder
from bap_desktop.services.benchmark_recorder import (
    BenchmarkRecorderCoordinator, BenchmarkRecorderError, BenchmarkRecorderState,
    benchmark_bundle_filename, export_benchmark_bundle, load_benchmark_bundle,
)
from bap_desktop.services.imu_capture import CaptureDuration, ImuCaptureError, ImuCaptureResult, LiveImuCapture
from bap_desktop.services.imu_discovery import DiscoveryResult, ImuSource
from bap_desktop.services.imu_scan import ConnectionType
from tests.helpers import build_gateway_frame, build_gateway_node, build_hi91_frame


class Connection:
    def __init__(self, data: bytes = b"", *, error: Exception | None = None):
        self.data = data
        self.error = error
        self.closed = False

    @property
    def in_waiting(self):
        if self.error is not None:
            error, self.error = self.error, None
            raise error
        return len(self.data)

    def read(self, _size=1):
        data, self.data = self.data, b""
        return data

    def close(self):
        self.closed = True


class Adapter:
    def __init__(self, by_port):
        self.by_port = by_port

    def open(self, port, **_kwargs):
        return self.by_port[port]


class Clock:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


def wait_until_connection_is_consumed(connection: Connection) -> None:
    deadline = time.monotonic() + 1.0
    while connection.data and time.monotonic() < deadline:
        time.sleep(0.002)
    assert not connection.data


def test_capture_duration_is_bounded_and_uses_monotonic_values() -> None:
    assert CaptureDuration().requested_seconds == 60
    duration = CaptureDuration(5)
    assert duration.remaining(10, 12) == 3
    assert duration.reached(10, 15)
    for invalid in (4, 3601, 5.5, True):
        with pytest.raises(ValueError):
            CaptureDuration(invalid)


@pytest.mark.scenario("benchmark-data-recorder", "使用同一個無線接收器的兩顆 IMU")
def test_live_capture_writes_one_csv_per_wireless_node(tmp_path: Path) -> None:
    data = build_gateway_frame(gateway_id=7, nodes=(build_gateway_node(1), build_gateway_node(2)))
    capture = LiveImuCapture(
        tmp_path,
        assignments={
            "left_wrist": ImuSource("COM3", ConnectionType.WIRELESS_RECEIVER, 7, 1),
            "right_wrist": ImuSource("COM3", ConnectionType.WIRELESS_RECEIVER, 7, 2),
        },
        adapter=Adapter({"COM3": Connection(data)}),
    )
    capture.start(); time.sleep(0.02)
    result = capture.stop()
    again = capture.stop()
    assert again is result
    assert len(result.descriptors) == 2
    assert {item.source.node_id for item in result.descriptors} == {1, 2}
    assert {item.source.group_id for item in result.descriptors} == {7}
    assert all(inspect_common_imu_csv(result.directory / item.filename).row_count == 1 for item in result.descriptors)


@pytest.mark.scenario("benchmark-data-recorder", "錄製期間無線 Node 中斷")
def test_live_capture_reports_only_the_wireless_node_that_stopped_sending_frames(tmp_path: Path) -> None:
    clock = Clock()
    connection = Connection(build_gateway_frame(gateway_id=7, nodes=(build_gateway_node(1), build_gateway_node(2))))
    left = ImuSource("COM3", ConnectionType.WIRELESS_RECEIVER, 7, 1)
    right = ImuSource("COM3", ConnectionType.WIRELESS_RECEIVER, 7, 2)
    capture = LiveImuCapture(
        tmp_path,
        assignments={"left_wrist": left, "right_wrist": right},
        adapter=Adapter({"COM3": connection}),
        monotonic=clock,
    )
    capture.start()
    wait_until_connection_is_consumed(connection)
    clock.value = 0.6
    connection.data = build_gateway_frame(gateway_id=7, nodes=(build_gateway_node(1),))
    wait_until_connection_is_consumed(connection)

    assert capture.interrupted_sources(now=1.1) == (right,)
    result = capture.stop()
    assert sorted(item.row_count for item in result.descriptors) == [1, 2]


@pytest.mark.scenario("benchmark-data-recorder", "使用兩顆有線 IMU")
def test_live_capture_writes_one_csv_per_wired_port(tmp_path: Path) -> None:
    capture = LiveImuCapture(
        tmp_path,
        assignments={
            "left_wrist": ImuSource("COM1", ConnectionType.WIRED),
            "right_wrist": ImuSource("COM2", ConnectionType.WIRED),
        },
        adapter=Adapter({"COM1": Connection(build_hi91_frame()), "COM2": Connection(build_hi91_frame())}),
    )
    capture.start(); time.sleep(0.02)
    result = capture.stop()
    assert {item.source.port for item in result.descriptors} == {"COM1", "COM2"}
    assert all(item.source.group_id is None and item.source.node_id is None for item in result.descriptors)


@pytest.mark.scenario("benchmark-data-recorder", "錄製期間任一必要來源失敗")
@pytest.mark.scenario("boxing-analysis-session", "中斷來源完全沒有有效資料")
@pytest.mark.parametrize("connection", [Connection(), Connection(error=OSError("disconnected"))])
def test_live_capture_rejects_zero_frames_or_source_failure(tmp_path: Path, connection: Connection) -> None:
    capture = LiveImuCapture(tmp_path, assignments={"left_wrist": ImuSource("COM1", ConnectionType.WIRED)}, adapter=Adapter({"COM1": connection}))
    capture.start(); time.sleep(0.01)
    with pytest.raises((ImuCaptureError, RuntimeError)):
        capture.stop()
    assert capture.state == "failed"
    assert capture.directory.exists()


class FakeCapture:
    def __init__(self, root, *, assignments):
        self.assignments = assignments
        self.session_id = uuid4()
        self.directory = Path(root) / str(self.session_id)
        self.started_monotonic = 10.0
        self.stop_calls = 0
        self.interrupted = ()

    def start(self):
        self.directory.mkdir(parents=True)

    def stop(self):
        self.stop_calls += 1
        descriptors = tuple(make_csv(self.directory, role, source) for role, source in self.assignments.items())
        return ImuCaptureResult(self.session_id, self.directory, datetime.now(timezone.utc), datetime.now(timezone.utc), 5.0, descriptors)

    def interrupted_sources(self, *, now=None):
        return self.interrupted

    def discard(self):
        pass


def frame(value=1.0):
    item = AnrotFrame(); item.frame_type = 0x91; item.system_time_ms = 1
    item.acc = (value, value, value); item.gyr = (1.0, 2.0, 3.0); item.mag = (4.0, 5.0, 6.0)
    item.quat = (1.0, 0.0, 0.0, 0.0); item.roll = item.pitch = item.yaw = 0.0
    return item


def make_csv(directory: Path, role: str, source: ImuSource):
    from bap_desktop.services.analysis_recording import source_descriptor
    csv_id = uuid4(); path = directory / f"imu_{csv_id}.csv"
    recorder = CommonImuCsvRecorder(path); recorder.__enter__(); recorder.append(frame(), elapsed_us=0, packet_index=0); inspection = recorder.finalize()
    from bap_common.analysis_session import CsvDescriptor
    return CsvDescriptor(csv_id=csv_id, filename=path.name, source=source_descriptor(source), row_count=inspection.row_count, size_bytes=inspection.size_bytes, sha256=inspection.sha256)


def ready_coordinator(tmp_path: Path) -> BenchmarkRecorderCoordinator:
    sources = (ImuSource("COM1", ConnectionType.WIRED), ImuSource("COM2", ConnectionType.WIRED))
    coordinator = BenchmarkRecorderCoordinator(tmp_path, desktop_version="0.1.9", capture_factory=FakeCapture, monotonic=lambda: 15.0)
    coordinator.complete_scan(DiscoveryResult(sources=sources, port_reasons=()))
    coordinator.set_assignments({"left_wrist": sources[0], "right_wrist": sources[1]})
    return coordinator


@pytest.mark.scenario("benchmark-data-recorder", "預定時間到達")
def test_coordinator_duration_single_finalization_and_state_machine(tmp_path: Path) -> None:
    coordinator = ready_coordinator(tmp_path)
    coordinator.start(5)
    assert coordinator.state is BenchmarkRecorderState.RECORDING
    assert coordinator.tick(now=15.0)
    assert coordinator.state is BenchmarkRecorderState.LABELING
    assert coordinator.capture.stop_calls == 1
    assert not coordinator.tick(now=20.0)
    truth = coordinator.set_ground_truth("3", "4", notes="人工審查")
    assert truth.total_punch_count == 7
    assert coordinator.state is BenchmarkRecorderState.READY_TO_EXPORT
    assert coordinator.metadata().stop_reason is BenchmarkStopReason.DURATION_REACHED


@pytest.mark.scenario("benchmark-data-recorder", "user 提前結束")
@pytest.mark.scenario("benchmark-data-recorder", "Ground Truth 無效")
def test_early_stop_and_invalid_ground_truth(tmp_path: Path) -> None:
    coordinator = ready_coordinator(tmp_path); coordinator.start(60); coordinator.stop_early()
    assert coordinator.stop_reason is BenchmarkStopReason.ENDED_BY_USER
    for left, right in (("", "1"), ("-1", "2"), ("1.5", "2"), ("x", "2")):
        with pytest.raises(BenchmarkRecorderError):
            coordinator.set_ground_truth(left, right)
    assert coordinator.state is BenchmarkRecorderState.LABELING


@pytest.mark.scenario("benchmark-data-recorder", "錄製期間無線 Node 中斷")
def test_coordinator_stops_and_keeps_partial_data_for_export_after_interruption(tmp_path: Path) -> None:
    coordinator = ready_coordinator(tmp_path)
    coordinator.start(60)
    coordinator.capture.interrupted = (coordinator.assignments["right_wrist"],)

    assert coordinator.tick(now=12.0)
    assert coordinator.state is BenchmarkRecorderState.LABELING
    assert coordinator.stop_reason is BenchmarkStopReason.SOURCE_INTERRUPTED
    assert coordinator.capture.stop_calls == 1
    coordinator.set_ground_truth("0", "0", notes="錄製期間 IMU 中斷")
    assert coordinator.metadata().stop_reason is BenchmarkStopReason.SOURCE_INTERRUPTED


@pytest.mark.scenario("benchmark-data-recorder", "同一來源被重複指定")
def test_duplicate_source_is_rejected(tmp_path: Path) -> None:
    source = ImuSource("COM1", ConnectionType.WIRED)
    coordinator = BenchmarkRecorderCoordinator(tmp_path, desktop_version="0.1.9")
    coordinator.complete_scan(DiscoveryResult(sources=(source,), port_reasons=()))
    with pytest.raises(BenchmarkRecorderError):
        coordinator.set_assignments({"left_wrist": source, "right_wrist": source})


def export_ready(tmp_path: Path):
    coordinator = ready_coordinator(tmp_path / "staging"); coordinator.start(5); coordinator.stop_early(); coordinator.set_ground_truth("8", "9")
    return coordinator, coordinator.metadata()


@pytest.mark.scenario("benchmark-data-recorder", "匯出成功")
def test_atomic_export_and_bundle_loader_contract(tmp_path: Path) -> None:
    coordinator, metadata = export_ready(tmp_path)
    destination = tmp_path / benchmark_bundle_filename(metadata)
    exported = export_benchmark_bundle(metadata, coordinator.capture_result.directory, destination)
    coordinator.mark_exported(exported)
    loaded = load_benchmark_bundle(exported)
    assert set(loaded.csv_by_role) == {"left_wrist", "right_wrist"}
    assert loaded.metadata.ground_truth.total_punch_count == 17
    assert not destination.with_name(destination.name + ".partial").exists()
    assert coordinator.state is BenchmarkRecorderState.EXPORTED


@pytest.mark.scenario("benchmark-data-recorder", "匯出寫入失敗")
def test_export_failure_keeps_staging_and_removes_partial(tmp_path: Path, monkeypatch) -> None:
    coordinator, metadata = export_ready(tmp_path)
    destination = tmp_path / "result.zip"
    original = zipfile.ZipFile
    def fail_zip(*args, **kwargs):
        if Path(args[0]).name.endswith(".partial"):
            raise OSError("disk full")
        return original(*args, **kwargs)
    monkeypatch.setattr(zipfile, "ZipFile", fail_zip)
    with pytest.raises(BenchmarkRecorderError):
        export_benchmark_bundle(metadata, coordinator.capture_result.directory, destination)
    assert coordinator.has_unsaved_recording
    assert coordinator.capture_result.directory.exists()
    assert not destination.exists()
    assert not destination.with_name("result.zip.partial").exists()


def test_loader_rejects_checksum_corruption(tmp_path: Path) -> None:
    coordinator, metadata = export_ready(tmp_path)
    destination = export_benchmark_bundle(metadata, coordinator.capture_result.directory, tmp_path / "result.zip")
    first = metadata.inputs[0]
    with zipfile.ZipFile(destination, "r") as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    entries[first.filename] = b"corrupted"
    with zipfile.ZipFile(destination, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    with pytest.raises(BenchmarkRecorderError):
        load_benchmark_bundle(destination)
