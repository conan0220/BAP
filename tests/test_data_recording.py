from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest
import serial

from commands import record_data as record_module
from helpers import FakeSerial, SequenceClock, build_gateway_frame, build_hi91_frame
from parsers.anrot_serial_parser import AnrotFrame, AnrotSerialParser


def configure_finite_recording(monkeypatch, *, monotonic_values=(0.0, 0.0, 1000.0)) -> None:
    monkeypatch.setattr(record_module.time, "monotonic", SequenceClock(monotonic_values))
    monkeypatch.setattr(record_module.time, "time", lambda: 1000.25)
    monkeypatch.setattr(record_module.time, "sleep", lambda _seconds: None)


@pytest.mark.scenario("imu-data-recording", "Start with valid recording inputs")
def test_record_command_opens_valid_ports_with_requested_options(cli_runner, monkeypatch, tmp_path) -> None:
    opened = {}

    def serial_factory(port, baudrate, **kwargs):
        opened[port] = (baudrate, kwargs, FakeSerial())
        return opened[port][2]

    monkeypatch.setattr(record_module.serial, "Serial", serial_factory)
    configure_finite_recording(monkeypatch)

    result = cli_runner.invoke(
        record_module.cmd_record,
        [
            "--ports",
            "COM3, COM4",
            "--baudrate",
            "230400",
            "--output",
            str(tmp_path / "capture.csv"),
            "--duration",
            "0.1",
        ],
    )

    assert result.exit_code == 0
    assert set(opened) == {"COM3", "COM4"}
    assert all(baudrate == 230400 and kwargs == {"timeout": 0} for baudrate, kwargs, _ in opened.values())
    assert all(fake.closed for _, _, fake in opened.values())


@pytest.mark.scenario("imu-data-recording", "Start with valid recording inputs")
def test_record_command_exposes_current_defaults() -> None:
    parameters = {parameter.name: parameter for parameter in record_module.cmd_record.params}

    assert parameters["baudrate"].default == "115200"
    assert parameters["output"].default == "recorded_data.csv"
    assert parameters["duration"].default == 10


@pytest.mark.scenario("imu-data-recording", "Reject an empty port list")
@pytest.mark.parametrize("ports", ["", ",", " ,  , "])
def test_record_command_rejects_empty_port_list(cli_runner, monkeypatch, ports: str) -> None:
    opened = False

    def serial_factory(*args, **kwargs):
        nonlocal opened
        opened = True
        return FakeSerial()

    monkeypatch.setattr(record_module.serial, "Serial", serial_factory)

    result = cli_runner.invoke(record_module.cmd_record, ["--ports", ports])

    assert result.exit_code != 0
    assert "At least one serial port is required" in result.output
    assert not opened


@pytest.mark.scenario("imu-data-recording", "Reject an invalid baud rate or duration")
@pytest.mark.parametrize(
    "arguments",
    [
        pytest.param(["--baudrate", "0"], id="zero-baud"),
        pytest.param(["--baudrate", "-1"], id="negative-baud"),
        pytest.param(["--baudrate", "abc"], id="non-numeric-baud"),
        pytest.param(["--duration", "0"], id="zero-duration"),
        pytest.param(["--duration", "-1"], id="negative-duration"),
        pytest.param(["--duration", "abc"], id="non-numeric-duration"),
    ],
)
def test_record_command_rejects_invalid_baud_or_duration(cli_runner, monkeypatch, arguments) -> None:
    opened = False

    def serial_factory(*args, **kwargs):
        nonlocal opened
        opened = True
        return FakeSerial()

    monkeypatch.setattr(record_module.serial, "Serial", serial_factory)

    result = cli_runner.invoke(record_module.cmd_record, ["--ports", "COM3", *arguments])

    assert result.exit_code != 0
    assert not opened


@pytest.mark.scenario("imu-data-recording", "Frames are interleaved across two ports")
def test_interleaved_ports_keep_independent_parser_state(cli_runner, monkeypatch, tmp_path) -> None:
    first = build_gateway_frame(gateway_id=1)
    second = build_gateway_frame(gateway_id=2)
    serials = {
        "COM3": FakeSerial([first[:12], first[12:]]),
        "COM4": FakeSerial([second[:19], second[19:]]),
    }
    monkeypatch.setattr(
        record_module.serial, "Serial", lambda port, baudrate, **kwargs: serials[port]
    )
    configure_finite_recording(monkeypatch, monotonic_values=(0.0, 0.0, 0.1, 1.0))
    output = tmp_path / "capture.csv"

    result = cli_runner.invoke(
        record_module.cmd_record,
        ["--ports", "COM3,COM4", "--output", str(output), "--duration", "0.5"],
    )

    assert result.exit_code == 0
    for gateway_id in (1, 2):
        rows = list(csv.reader((tmp_path / f"capture_{gateway_id}.csv").open(newline="")))
        assert len(rows) == 2
        assert rows[1][2] == "11"


@pytest.mark.scenario("imu-data-recording", "Record two gateway IDs")
def test_packets_are_routed_to_separate_gateway_files(cli_runner, monkeypatch, tmp_path) -> None:
    fake_serial = FakeSerial(
        [build_gateway_frame(gateway_id=4) + build_gateway_frame(gateway_id=9)]
    )
    monkeypatch.setattr(record_module.serial, "Serial", lambda *args, **kwargs: fake_serial)
    configure_finite_recording(monkeypatch)
    output = tmp_path / "session.data"

    result = cli_runner.invoke(
        record_module.cmd_record,
        ["--ports", "COM3", "--output", str(output), "--duration", "0.1"],
    )

    assert result.exit_code == 0
    assert (tmp_path / "session_4.data").exists()
    assert (tmp_path / "session_9.data").exists()


@pytest.mark.scenario("imu-data-recording", "Record two gateway IDs")
def test_output_without_suffix_uses_csv_and_missing_gateway_uses_unknown(
    cli_runner, monkeypatch, tmp_path
) -> None:
    fake_serial = FakeSerial([build_hi91_frame()])
    monkeypatch.setattr(record_module.serial, "Serial", lambda *args, **kwargs: fake_serial)
    configure_finite_recording(monkeypatch)

    result = cli_runner.invoke(
        record_module.cmd_record,
        ["--ports", "COM3", "--output", str(tmp_path / "capture"), "--duration", "0.1"],
    )

    assert result.exit_code == 0
    assert (tmp_path / "capture_unknown.csv").exists()


@pytest.mark.scenario("imu-data-recording", "No packet is decoded for a gateway")
def test_no_decoded_packet_creates_no_output_file(cli_runner, monkeypatch, tmp_path) -> None:
    fake_serial = FakeSerial([b"not an ANROT frame"])
    monkeypatch.setattr(record_module.serial, "Serial", lambda *args, **kwargs: fake_serial)
    configure_finite_recording(monkeypatch)

    result = cli_runner.invoke(
        record_module.cmd_record,
        ["--ports", "COM3", "--output", str(tmp_path / "capture.csv"), "--duration", "0.1"],
    )

    assert result.exit_code == 0
    assert list(tmp_path.iterdir()) == []


@pytest.mark.scenario("imu-data-recording", "Write a gateway packet row")
def test_gateway_csv_header_and_row_use_fixed_packet_positions(monkeypatch) -> None:
    frame = AnrotSerialParser().parse(build_gateway_frame(gateway_id=3, timestamp_ms=654321))[0]
    monkeypatch.setattr(record_module.time, "time", lambda: 1234.99)

    header = record_module.build_csv_header()
    row = record_module.build_csv_row([frame])

    assert len(header) == 2 + 16 * record_module.NODE_FIELD_COUNT
    assert header[:3] == ["UnixTimeStamp(sec)", "SystemTime(ms)", "Node1_ID"]
    assert header[-1] == "Node16_Qz"
    assert row[:3] == [1234, 654321, 11]
    assert len(row) == len(header)


@pytest.mark.scenario("imu-data-recording", "A node slot is absent")
def test_absent_node_slot_contains_seventeen_empty_fields(monkeypatch) -> None:
    frame = AnrotSerialParser().parse(build_gateway_frame())[0]
    frame.node_index = 1
    monkeypatch.setattr(record_module.time, "time", lambda: 1.0)

    row = record_module.build_csv_row([frame])

    assert row[2 : 2 + record_module.NODE_FIELD_COUNT] == [""] * record_module.NODE_FIELD_COUNT
    assert row[2 + record_module.NODE_FIELD_COUNT] == 11


@pytest.mark.scenario("imu-data-recording", "Write available and unavailable measurements")
def test_csv_formats_available_values_and_blanks_unavailable_values(monkeypatch) -> None:
    frame = AnrotFrame()
    frame.node_index = 0
    frame.node_id = 5
    frame.system_time_ms = 99
    frame.acc = (1.23456, -2.0, 0.0)
    frame.gyr = (12.345, None, -6.789)
    frame.mag = None
    frame.roll = 1.236
    frame.pitch = None
    frame.yaw = -7.891
    frame.quat = (1.0, 0.12345, None, -0.5)
    monkeypatch.setattr(record_module.time, "time", lambda: 12.9)

    row = record_module.build_csv_row([frame])
    fields = row[2 : 2 + record_module.NODE_FIELD_COUNT]

    assert fields == [
        5,
        "1.235",
        "-2.000",
        "0.000",
        "12.35",
        "",
        "-6.79",
        "",
        "",
        "",
        "1.24",
        "",
        "-7.89",
        "1.000",
        "0.123",
        "",
        "-0.500",
    ]


@pytest.mark.scenario("imu-data-recording", "Configured duration elapses")
def test_configured_duration_closes_serial_and_files(cli_runner, monkeypatch, tmp_path) -> None:
    fake_serial = FakeSerial([build_gateway_frame()])
    monkeypatch.setattr(record_module.serial, "Serial", lambda *args, **kwargs: fake_serial)
    configure_finite_recording(monkeypatch, monotonic_values=(10.0, 10.0, 10.2))

    result = cli_runner.invoke(
        record_module.cmd_record,
        ["--ports", "COM3", "--output", str(tmp_path / "capture.csv"), "--duration", "0.1"],
    )

    assert result.exit_code == 0
    assert fake_serial.closed
    output = tmp_path / "capture_3.csv"
    assert output.exists()
    assert output.open("a").close() is None


@pytest.mark.scenario("imu-data-recording", "Operator interrupts recording")
def test_keyboard_interrupt_closes_resources_and_preserves_rows(cli_runner, monkeypatch, tmp_path) -> None:
    fake_serial = FakeSerial([build_gateway_frame()], interrupt_when_empty=True)
    monkeypatch.setattr(record_module.serial, "Serial", lambda *args, **kwargs: fake_serial)
    monkeypatch.setattr(record_module.time, "monotonic", SequenceClock([0.0, 0.0, 0.1]))
    monkeypatch.setattr(record_module.time, "time", lambda: 1000.0)
    monkeypatch.setattr(record_module.time, "sleep", lambda _seconds: None)

    result = cli_runner.invoke(
        record_module.cmd_record,
        ["--ports", "COM3", "--output", str(tmp_path / "capture.csv")],
    )

    assert result.exit_code == 0
    assert fake_serial.closed
    rows = list(csv.reader((tmp_path / "capture_3.csv").open(newline="")))
    assert len(rows) == 2


@pytest.mark.scenario("imu-data-recording", "A selected serial port cannot be accessed")
@pytest.mark.parametrize("failure_stage", ["open", "read"])
def test_serial_access_failure_closes_open_resources(
    cli_runner, monkeypatch, tmp_path, failure_stage: str
) -> None:
    first_serial = FakeSerial(
        waiting_error=serial.SerialException("read failed") if failure_stage == "read" else None
    )

    def serial_factory(port, baudrate, **kwargs):
        if failure_stage == "open" and port == "COM4":
            raise PermissionError("access denied")
        return first_serial

    monkeypatch.setattr(record_module.serial, "Serial", serial_factory)
    configure_finite_recording(monkeypatch)
    ports = "COM3,COM4" if failure_stage == "open" else "COM3"

    result = cli_runner.invoke(
        record_module.cmd_record,
        ["--ports", ports, "--output", str(tmp_path / "capture.csv"), "--duration", "0.1"],
    )

    assert result.exit_code == 1
    assert first_serial.closed


@pytest.mark.scenario("imu-data-recording", "Configured duration elapses")
def test_open_gateway_file_is_flushed_at_least_once_per_second(
    cli_runner, monkeypatch, tmp_path
) -> None:
    class TrackingFile(io.StringIO):
        def __init__(self) -> None:
            super().__init__()
            self.periodic_flushes = 0
            self.closing = False

        def flush(self) -> None:
            if not self.closing:
                self.periodic_flushes += 1
            super().flush()

        def close(self) -> None:
            self.closing = True
            super().close()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            self.close()

    tracking_file = TrackingFile()
    fake_serial = FakeSerial([build_gateway_frame()])
    monkeypatch.setattr(record_module.serial, "Serial", lambda *args, **kwargs: fake_serial)
    monkeypatch.setattr(record_module, "open", lambda *args, **kwargs: tracking_file, raising=False)
    monkeypatch.setattr(record_module.time, "monotonic", SequenceClock([0.0, 0.0, 2.0]))
    monkeypatch.setattr(record_module.time, "time", SequenceClock([0.0, 1.1]))
    monkeypatch.setattr(record_module.time, "sleep", lambda _seconds: None)

    result = cli_runner.invoke(
        record_module.cmd_record,
        ["--ports", "COM3", "--output", str(tmp_path / "capture.csv"), "--duration", "2"],
    )

    assert result.exit_code == 0
    assert tracking_file.periodic_flushes >= 1
    assert tracking_file.closed
