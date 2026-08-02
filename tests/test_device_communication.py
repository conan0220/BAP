from __future__ import annotations

from types import SimpleNamespace

import pytest
import serial

import utils
from commands import cmd_list as list_module
from commands import cmd_send as send_module
from commands import read_data as read_module
from helpers import FakeSerial, SequenceClock, build_hi91_frame, build_nmea_sentence


@pytest.mark.scenario("imu-device-communication", "Serial ports are available")
def test_list_command_displays_available_ports(cli_runner, monkeypatch) -> None:
    ports = [
        SimpleNamespace(device="COM3", manufacturer="ANROT"),
        SimpleNamespace(device="COM4", manufacturer=None),
    ]
    monkeypatch.setattr(list_module.list_ports, "comports", lambda: ports)

    result = cli_runner.invoke(list_module.cmd_list)

    assert result.exit_code == 0
    assert "Found 2 available serial port(s)" in result.output
    assert "COM3" in result.output and "ANROT" in result.output
    assert "COM4" in result.output and "Unknown" in result.output
    assert "Permissions:" in result.output


@pytest.mark.scenario("imu-device-communication", "No serial ports are available")
def test_list_command_reports_empty_inventory(cli_runner, monkeypatch) -> None:
    monkeypatch.setattr(list_module.list_ports, "comports", lambda: [])

    result = cli_runner.invoke(list_module.cmd_list)

    assert result.exit_code == 0
    assert "No available serial ports found." in result.output


@pytest.mark.scenario("imu-device-communication", "Monitor valid mixed device output")
def test_read_command_displays_mixed_frames_and_rate(cli_runner, monkeypatch) -> None:
    nmea = build_nmea_sentence(
        "GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,"
    ).encode("ascii")
    fake_serial = FakeSerial([build_hi91_frame() + nmea], interrupt_when_empty=True)
    monkeypatch.setattr(read_module.serial, "Serial", lambda *args, **kwargs: fake_serial)
    monkeypatch.setattr(read_module.time, "time", SequenceClock([0.0, 0.0, 1.1]))
    monkeypatch.setattr(read_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(read_module, "clear_screen", lambda: None)

    result = cli_runner.invoke(
        read_module.cmd_read, ["--port", "COM3", "--baudrate", "115200"]
    )

    assert result.exit_code == 0
    assert "Frame Type" in result.output and "HI91" in result.output
    assert "=== GGA ===" in result.output
    assert "Frame rate: 2 Hz" in result.output
    assert "Program interrupted by user" in result.output
    assert fake_serial.closed


@pytest.mark.scenario("imu-device-communication", "Reject an invalid monitoring baud rate")
@pytest.mark.parametrize("baudrate", ["0", "-1", "abc"])
def test_read_command_rejects_invalid_baudrate(cli_runner, monkeypatch, baudrate: str) -> None:
    opened = False

    def serial_factory(*args, **kwargs):
        nonlocal opened
        opened = True
        return FakeSerial()

    monkeypatch.setattr(read_module.serial, "Serial", serial_factory)

    result = cli_runner.invoke(
        read_module.cmd_read, ["--port", "COM3", "--baudrate", baudrate]
    )

    assert result.exit_code != 0
    assert "Invalid baudrate" in result.output
    assert not opened


@pytest.mark.scenario("imu-device-communication", "Serial monitoring cannot access the port")
@pytest.mark.parametrize(
    "error",
    [serial.SerialException("port busy"), PermissionError("access denied")],
    ids=["serial-error", "permission-error"],
)
def test_read_command_reports_serial_access_failure(cli_runner, monkeypatch, error) -> None:
    def serial_factory(*args, **kwargs):
        raise error

    monkeypatch.setattr(read_module.serial, "Serial", serial_factory)

    result = cli_runner.invoke(
        read_module.cmd_read, ["--port", "COM3", "--baudrate", "115200"]
    )

    assert result.exit_code == 1
    assert f"Error: {error}" in result.output


@pytest.mark.scenario("imu-device-communication", "Send and save a command successfully")
def test_configure_serial_uses_8n1(monkeypatch) -> None:
    captured = {}
    fake_serial = FakeSerial()

    def serial_factory(**kwargs):
        captured.update(kwargs)
        return fake_serial

    monkeypatch.setattr(utils.serial, "Serial", serial_factory)

    configured = utils.configure_serial("COM3", "115200")

    assert configured is fake_serial
    assert captured == {
        "port": "COM3",
        "baudrate": 115200,
        "bytesize": serial.EIGHTBITS,
        "parity": serial.PARITY_NONE,
        "stopbits": serial.STOPBITS_ONE,
    }


@pytest.mark.scenario("imu-device-communication", "Send and save a command successfully")
def test_send_command_completes_saved_sequence(cli_runner, monkeypatch) -> None:
    fake_serial = FakeSerial(
        responses=[b"OK\r\n", b"AT+ODR=100\r\nOK\r\n", b"OK\r\n", b"OK\r\n"]
    )
    monkeypatch.setattr(send_module, "configure_serial", lambda port, baudrate: fake_serial)
    monkeypatch.setattr(send_module.time, "sleep", lambda _seconds: None)

    result = cli_runner.invoke(
        send_module.cmd_send,
        ["--port", "COM3", "--baudrate", "115200", "AT+ODR=100"],
    )

    assert result.exit_code == 0
    assert fake_serial.writes == [
        b"AT+EOUT=0\r\n",
        b"AT+ODR=100\r\n",
        b"SAVECONFIG\r\n",
        b"AT+EOUT=1\r\n",
    ]
    assert "AT+ODR=100" in result.output and "OK" in result.output


@pytest.mark.scenario("imu-device-communication", "Device output does not stop initially")
def test_send_command_stops_after_three_output_stop_attempts(cli_runner, monkeypatch) -> None:
    fake_serial = FakeSerial(responses=[b"ERROR\r\n"] * 3)
    monkeypatch.setattr(send_module, "configure_serial", lambda port, baudrate: fake_serial)
    monkeypatch.setattr(send_module.time, "sleep", lambda _seconds: None)

    result = cli_runner.invoke(send_module.cmd_send, ["--port", "COM3", "AT+ODR=100"])

    assert result.exit_code == 0
    assert fake_serial.writes == [b"AT+EOUT=0\r\n"] * 3
    assert "after multiple attempts" in result.output


@pytest.mark.scenario("imu-device-communication", "A later command is not acknowledged")
@pytest.mark.parametrize(
    ("responses", "expected_writes", "failed_step"),
    [
        pytest.param([b"OK", b"ERROR"], 2, "AT+ODR=100", id="operator-command"),
        pytest.param([b"OK", b"OK", b"ERROR"], 3, "SAVECONFIG", id="save-command"),
        pytest.param([b"OK", b"OK", b"OK", b"ERROR"], 4, "AT+EOUT=1", id="restart-output"),
    ],
)
def test_send_command_stops_on_later_unacknowledged_step(
    cli_runner, monkeypatch, responses, expected_writes: int, failed_step: str
) -> None:
    fake_serial = FakeSerial(responses=responses)
    monkeypatch.setattr(send_module, "configure_serial", lambda port, baudrate: fake_serial)
    monkeypatch.setattr(send_module.time, "sleep", lambda _seconds: None)

    result = cli_runner.invoke(send_module.cmd_send, ["--port", "COM3", "AT+ODR=100"])

    assert result.exit_code == 0
    assert len(fake_serial.writes) == expected_writes
    assert f"Failed to send command '{failed_step}'" in result.output


@pytest.mark.scenario("imu-device-communication", "Reject an invalid command baud rate")
@pytest.mark.parametrize("baudrate", ["0", "-1", "abc"])
def test_send_command_rejects_invalid_baudrate(cli_runner, monkeypatch, baudrate: str) -> None:
    configured = False

    def configure_serial(*args, **kwargs):
        nonlocal configured
        configured = True
        return FakeSerial()

    monkeypatch.setattr(send_module, "configure_serial", configure_serial)

    result = cli_runner.invoke(
        send_module.cmd_send,
        ["--port", "COM3", "--baudrate", baudrate, "AT+ODR=100"],
    )

    assert result.exit_code != 0
    assert "Invalid baudrate" in result.output
    assert not configured
