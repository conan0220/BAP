"""Canonical Common IMU CSV version 1 writer and validator."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, TextIO


COMMON_IMU_CSV_VERSION = 1
COMMON_IMU_CSV_HEADER = (
    "sample_index",
    "packet_index",
    "elapsed_us",
    "device_time_ms",
    "frame_type",
    "acc_x_g",
    "acc_y_g",
    "acc_z_g",
    "gyro_x_dps",
    "gyro_y_dps",
    "gyro_z_dps",
    "mag_x_ut",
    "mag_y_ut",
    "mag_z_ut",
    "roll_deg",
    "pitch_deg",
    "yaw_deg",
    "quat_w",
    "quat_x",
    "quat_y",
    "quat_z",
    "temperature_c",
    "pressure_pa",
)
FRAME_TYPE_PATTERN = re.compile(r"^0x[0-9A-Fa-f]{2}$")
INTEGER_COLUMNS = {"sample_index", "packet_index", "elapsed_us", "device_time_ms"}
REQUIRED_INTEGER_COLUMNS = {"sample_index", "elapsed_us"}
FLOAT_COLUMNS = set(COMMON_IMU_CSV_HEADER) - INTEGER_COLUMNS - {"frame_type"}


class CommonImuCsvError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class CommonImuCsvInspection:
    row_count: int
    size_bytes: int
    sha256: str


def format_optional_number(value: Any) -> str:
    if value is None:
        return ""
    return format(float(value), ".9g")


def frame_csv_row(
    frame: Any,
    *,
    sample_index: int,
    packet_index: int | None,
    elapsed_us: int,
) -> list[str | int]:
    def vector(value: Any, index: int) -> str:
        return "" if value is None else format_optional_number(value[index])

    frame_type = getattr(frame, "frame_type", None)
    return [
        sample_index,
        "" if packet_index is None else packet_index,
        elapsed_us,
        "" if getattr(frame, "system_time_ms", None) is None else int(frame.system_time_ms),
        "" if frame_type is None else f"0x{int(frame_type):02X}",
        vector(getattr(frame, "acc", None), 0),
        vector(getattr(frame, "acc", None), 1),
        vector(getattr(frame, "acc", None), 2),
        vector(getattr(frame, "gyr", None), 0),
        vector(getattr(frame, "gyr", None), 1),
        vector(getattr(frame, "gyr", None), 2),
        vector(getattr(frame, "mag", None), 0),
        vector(getattr(frame, "mag", None), 1),
        vector(getattr(frame, "mag", None), 2),
        format_optional_number(getattr(frame, "roll", None)),
        format_optional_number(getattr(frame, "pitch", None)),
        format_optional_number(getattr(frame, "yaw", None)),
        vector(getattr(frame, "quat", None), 0),
        vector(getattr(frame, "quat", None), 1),
        vector(getattr(frame, "quat", None), 2),
        vector(getattr(frame, "quat", None), 3),
        format_optional_number(getattr(frame, "temperature", None)),
        format_optional_number(getattr(frame, "pressure", None)),
    ]


def write_header(file: TextIO) -> csv.writer:
    writer = csv.writer(file, lineterminator="\n")
    writer.writerow(COMMON_IMU_CSV_HEADER)
    return writer


def inspect_common_imu_csv(path: Path, *, schema_version: int = COMMON_IMU_CSV_VERSION) -> CommonImuCsvInspection:
    with Path(path).open("rb") as binary:
        return inspect_common_imu_csv_stream(binary, schema_version=schema_version)


def inspect_common_imu_csv_bytes(data: bytes, *, schema_version: int = COMMON_IMU_CSV_VERSION) -> CommonImuCsvInspection:
    return inspect_common_imu_csv_stream(io.BytesIO(data), schema_version=schema_version)


def inspect_common_imu_csv_stream(
    binary: BinaryIO,
    *,
    schema_version: int = COMMON_IMU_CSV_VERSION,
) -> CommonImuCsvInspection:
    if schema_version != COMMON_IMU_CSV_VERSION:
        raise CommonImuCsvError("unsupported_csv_schema", "不支援的 Common IMU CSV schema version")
    digest = hashlib.sha256()
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = binary.read(1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
        chunks.append(chunk)
        size += len(chunk)
    try:
        text = b"".join(chunks).decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise CommonImuCsvError("invalid_csv_encoding", "CSV 必須使用 UTF-8") from error
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = tuple(next(reader))
    except StopIteration as error:
        raise CommonImuCsvError("empty_csv", "CSV 沒有 header") from error
    if header != COMMON_IMU_CSV_HEADER:
        raise CommonImuCsvError("invalid_csv_header", "CSV header 與 Common IMU CSV schema 不符")

    count = 0
    previous_elapsed = -1
    for row_number, row in enumerate(reader, start=2):
        if len(row) != len(COMMON_IMU_CSV_HEADER):
            raise CommonImuCsvError("invalid_csv_row", f"CSV 第 {row_number} 列欄位數不正確")
        values = dict(zip(COMMON_IMU_CSV_HEADER, row))
        sample_index = _parse_integer(values["sample_index"], "sample_index", required=True)
        if sample_index != count:
            raise CommonImuCsvError("invalid_sample_index", "sample_index 必須從 0 逐列增加")
        elapsed = _parse_integer(values["elapsed_us"], "elapsed_us", required=True)
        if elapsed < previous_elapsed:
            raise CommonImuCsvError("elapsed_time_reversed", "elapsed_us 不得倒退")
        previous_elapsed = elapsed
        for column in INTEGER_COLUMNS - REQUIRED_INTEGER_COLUMNS:
            _parse_integer(values[column], column, required=False)
        if values["frame_type"] and not FRAME_TYPE_PATTERN.fullmatch(values["frame_type"]):
            raise CommonImuCsvError("invalid_frame_type", "frame_type 格式不正確")
        for column in FLOAT_COLUMNS:
            if values[column]:
                try:
                    float(values[column])
                except ValueError as error:
                    raise CommonImuCsvError("invalid_csv_number", f"{column} 必須是數值或空白") from error
        count += 1
    if count == 0:
        raise CommonImuCsvError("empty_csv", "CSV 至少需要一筆資料")
    return CommonImuCsvInspection(row_count=count, size_bytes=size, sha256=digest.hexdigest())


def _parse_integer(value: str, column: str, *, required: bool) -> int | None:
    if not value:
        if required:
            raise CommonImuCsvError("missing_csv_value", f"{column} 不得留白")
        return None
    try:
        number = int(value)
    except ValueError as error:
        raise CommonImuCsvError("invalid_csv_integer", f"{column} 必須是整數") from error
    if number < 0:
        raise CommonImuCsvError("invalid_csv_integer", f"{column} 不得小於 0")
    return number
