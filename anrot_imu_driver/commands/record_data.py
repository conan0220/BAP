import csv
import sys
import time
from contextlib import ExitStack
from pathlib import Path
from typing import Any, List, TextIO, Tuple, Union

import click
import serial

try:
    from ..parsers.anrot_serial_parser import AnrotSerialParser, AnrotFrame
except ImportError:  # Preserve legacy direct execution.
    from parsers.anrot_serial_parser import AnrotSerialParser, AnrotFrame


MAX_NODES = 16
NODE_FIELD_COUNT = 17


def build_csv_header() -> List[str]:
    header = ["UnixTimeStamp(sec)", "SystemTime(ms)"]
    for node_num in range(1, MAX_NODES + 1):
        header.extend([
            f"Node{node_num}_ID",
            f"Node{node_num}_AccX[G]",
            f"Node{node_num}_AccY[G]",
            f"Node{node_num}_AccZ[G]",
            f"Node{node_num}_GyrX[deg/s]",
            f"Node{node_num}_GyrY[deg/s]",
            f"Node{node_num}_GyrZ[deg/s]",
            f"Node{node_num}_MagX[uT]",
            f"Node{node_num}_MagY[uT]",
            f"Node{node_num}_MagZ[uT]",
            f"Node{node_num}_Roll[deg]",
            f"Node{node_num}_Pitch[deg]",
            f"Node{node_num}_Yaw[deg]",
            f"Node{node_num}_Qw",
            f"Node{node_num}_Qx",
            f"Node{node_num}_Qy",
            f"Node{node_num}_Qz",
        ])
    return header


def build_group_output_path(output, group_id) -> Path:
    output_path = Path(output)
    suffix = output_path.suffix or ".csv"
    stem = output_path.stem if output_path.suffix else output_path.name
    return output_path.with_name(f"{stem}_{group_id}{suffix}")


def format_number(value, precision) -> str:
    if value is None:
        return ""
    return f"{value:.{precision}f}"


def append_node_fields(row, frame) -> None:
    row.extend([
        frame.node_id if frame.node_id is not None else "",
        format_number(frame.acc[0], 3) if frame.acc is not None else "",
        format_number(frame.acc[1], 3) if frame.acc is not None else "",
        format_number(frame.acc[2], 3) if frame.acc is not None else "",
        format_number(frame.gyr[0], 2) if frame.gyr is not None else "",
        format_number(frame.gyr[1], 2) if frame.gyr is not None else "",
        format_number(frame.gyr[2], 2) if frame.gyr is not None else "",
        format_number(frame.mag[0], 2) if frame.mag is not None else "",
        format_number(frame.mag[1], 2) if frame.mag is not None else "",
        format_number(frame.mag[2], 2) if frame.mag is not None else "",
        format_number(frame.roll, 2),
        format_number(frame.pitch, 2),
        format_number(frame.yaw, 2),
        format_number(frame.quat[0], 3) if frame.quat is not None else "",
        format_number(frame.quat[1], 3) if frame.quat is not None else "",
        format_number(frame.quat[2], 3) if frame.quat is not None else "",
        format_number(frame.quat[3], 3) if frame.quat is not None else "",
    ])


def build_csv_row(frames) -> List[object]:
    first_frame = frames[0]
    frames_by_index = {
        frame.node_index: frame
        for frame in frames
        if frame.node_index is not None and 0 <= frame.node_index < MAX_NODES
    }

    system_time_ms = first_frame.system_time_ms if first_frame.system_time_ms is not None else ""
    row = [int(time.time()), system_time_ms]
    for node_index in range(MAX_NODES):
        frame = frames_by_index.get(node_index)
        if frame is None:
            row.extend([""] * NODE_FIELD_COUNT)
        else:
            append_node_fields(row, frame)
    return row


def split_gateway_packets(frames) -> List[List[AnrotFrame]]:
    packets = []
    current_packet = []

    for frame in frames:
        if frame.frame_type != 0x63 or frame.node_count is None:
            packets.append([frame])
            continue

        if frame.node_index == 0 and current_packet:
            packets.append(current_packet)
            current_packet = []

        current_packet.append(frame)

        if len(current_packet) >= frame.node_count:
            packets.append(current_packet)
            current_packet = []

    if current_packet:
        packets.append(current_packet)

    return packets


def open_group_writer(group_writers, stack, output, group_id) -> Tuple[Any, TextIO, Path]:
    if group_id in group_writers:
        return group_writers[group_id]

    output_path = build_group_output_path(output, group_id)
    output_file = stack.enter_context(open(output_path, "w", newline=""))
    writer = csv.writer(output_file)
    writer.writerow(build_csv_header())
    group_writers[group_id] = (writer, output_file, output_path)
    return group_writers[group_id]


def get_packet_group_id(packet_frames) -> Union[int, str]:
    group_id = packet_frames[0].gw_id
    if group_id is None:
        return "unknown"
    return group_id


@click.command(name="record", short_help="Record ANROT data from the specified serial ports")
@click.option("--ports", "-p", required=True, help="Serial ports separated by commas, such as COM3,COM4.")
@click.option("--baudrate", "-b", default="115200", help="The baud rate for the serial connection (default: 115200).")
@click.option("--output", "-o", default="recorded_data.csv", help="The output CSV file prefix (default: recorded_data.csv). Files are written as <output>_<group id>.csv.")
@click.option("--duration", "-d", type=click.FloatRange(min=0, min_open=True), default=10, help="Recording duration in seconds (default: 10).")
def cmd_record(ports, baudrate, output, duration) -> None:
    if not baudrate.isdigit() or int(baudrate) <= 0:
        raise click.BadParameter("Invalid baudrate. Baudrate must be a positive integer.")

    port_list = [port.strip() for port in ports.split(",") if port.strip()]
    if not port_list:
        raise click.BadParameter("At least one serial port is required.")

    serial_parsers = {port: AnrotSerialParser() for port in port_list}

    last_flush_time = time.time()
    group_writers = {}

    try:
        with ExitStack() as stack:
            serial_ports = {
                port: stack.enter_context(serial.Serial(port, int(baudrate), timeout=0))
                for port in port_list
            }

            recording_deadline = (
                time.monotonic() + duration
                if duration is not None
                else None
            )

            while recording_deadline is None or time.monotonic() < recording_deadline:
                for port, ser in serial_ports.items():
                    if not ser.in_waiting:
                        continue

                    data = ser.read(ser.in_waiting)

                    try:
                        anrot_frames = serial_parsers[port].parse(data)

                        if anrot_frames:
                            for packet_frames in split_gateway_packets(anrot_frames):
                                group_id = get_packet_group_id(packet_frames)
                                writer, _, _ = open_group_writer(group_writers, stack, output, group_id)
                                writer.writerow(build_csv_row(packet_frames))

                    except Exception:
                        pass

                current_time = time.time()
                if current_time - last_flush_time >= 1.0:
                    for _, output_file, _ in group_writers.values():
                        output_file.flush()
                    last_flush_time = current_time

                time.sleep(0.001)

    except KeyboardInterrupt:
        pass
    except (serial.SerialException, PermissionError):
        sys.exit(1)


if __name__ == "__main__":
    cmd_record()
