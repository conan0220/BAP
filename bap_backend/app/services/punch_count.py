"""Deterministic rule_v1 Shadow-boxing punch-count analysis."""

from __future__ import annotations

import csv
import io
import math
import statistics
from dataclasses import dataclass

from bap_common.analysis_contracts import ContractError
from bap_common.imu_csv import CommonImuCsvError, inspect_common_imu_csv_bytes


SENSOR_COLUMNS = (
    "acc_x_g",
    "acc_y_g",
    "acc_z_g",
    "gyro_x_dps",
    "gyro_y_dps",
    "gyro_z_dps",
)


class PunchCountDataError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class ImuSample:
    time_seconds: float
    acc_x_g: float
    acc_y_g: float
    acc_z_g: float
    gyro_x_dps: float
    gyro_y_dps: float
    gyro_z_dps: float


@dataclass(frozen=True, slots=True)
class RuleV1Config:
    """Versioned constants calibrated against the five prototype cases."""

    baseline_seconds: float = 0.5
    smoothing_seconds: float = 0.0075
    minimum_smoothing_samples: int = 3
    gyro_scale_dps: float = 200.0
    start_threshold: float = 2.0
    confirm_threshold: float = 5.0
    end_threshold: float = 1.5
    refractory_seconds: float = 0.35
    minimum_sample_rate_hz: float = 10.0


RULE_V1 = RuleV1Config()


def read_common_imu_csv(data: bytes) -> tuple[ImuSample, ...]:
    """Read one strict Common IMU CSV and select its best valid time axis."""

    try:
        inspection = inspect_common_imu_csv_bytes(data)
    except CommonImuCsvError as error:
        raise PunchCountDataError(error.code, error.message) from error
    if inspection.row_count < 3:
        raise PunchCountDataError(
            "insufficient_imu_samples", "IMU 資料筆數不足，無法計算出拳次數"
        )
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise PunchCountDataError("invalid_csv_encoding", "CSV 必須使用 UTF-8") from error
    rows = list(csv.DictReader(io.StringIO(text, newline="")))

    sensor_values: list[tuple[float, ...]] = []
    elapsed_values: list[int] = []
    device_values: list[int] = []
    device_complete = True
    for row_number, row in enumerate(rows, start=2):
        values: list[float] = []
        for column in SENSOR_COLUMNS:
            raw = row[column]
            if not raw:
                raise PunchCountDataError(
                    "missing_sensor_value", f"CSV 第 {row_number} 列缺少必要的 IMU sensor 數值"
                )
            try:
                value = float(raw)
            except ValueError as error:
                raise PunchCountDataError(
                    "invalid_sensor_value", f"CSV 第 {row_number} 列包含無效的 IMU sensor 數值"
                ) from error
            if not math.isfinite(value):
                raise PunchCountDataError(
                    "invalid_sensor_value", f"CSV 第 {row_number} 列包含非有限 IMU sensor 數值"
                )
            values.append(value)
        sensor_values.append(tuple(values))
        elapsed_values.append(int(row["elapsed_us"]))
        raw_device_time = row["device_time_ms"]
        if raw_device_time:
            device_values.append(int(raw_device_time))
        else:
            device_complete = False

    raw_times: list[int]
    scale: float
    if device_complete and _is_forward_time_axis(device_values):
        raw_times = device_values
        scale = 1000.0
    elif _is_forward_time_axis(elapsed_values):
        raw_times = elapsed_values
        scale = 1_000_000.0
    else:
        raise PunchCountDataError(
            "invalid_time_axis", "IMU 資料的時間沒有前進，無法計算出拳次數"
        )

    start = raw_times[0]
    times = [(value - start) / scale for value in raw_times]
    duration = times[-1]
    sample_rate = (len(times) - 1) / duration
    if sample_rate < RULE_V1.minimum_sample_rate_hz:
        raise PunchCountDataError(
            "sample_rate_too_low", "IMU 資料取樣率太低，無法可靠計算出拳次數"
        )
    return tuple(
        ImuSample(time_value, *values)
        for time_value, values in zip(times, sensor_values, strict=True)
    )


def _is_forward_time_axis(values: list[int]) -> bool:
    return (
        len(values) >= 3
        and values[-1] > values[0]
        and all(current >= previous for previous, current in zip(values, values[1:]))
    )


def count_single_wrist_punches(
    samples: tuple[ImuSample, ...], *, config: RuleV1Config = RULE_V1
) -> int:
    if len(samples) < 3:
        raise PunchCountDataError(
            "insufficient_imu_samples", "IMU 資料筆數不足，無法計算出拳次數"
        )
    duration = samples[-1].time_seconds - samples[0].time_seconds
    if duration <= 0:
        raise PunchCountDataError("invalid_time_axis", "IMU 資料的時間沒有前進")
    sample_rate = (len(samples) - 1) / duration

    baseline_limit = samples[0].time_seconds + config.baseline_seconds
    baseline_magnitudes = [
        _acc_magnitude(sample)
        for sample in samples
        if sample.time_seconds <= baseline_limit
    ]
    if len(baseline_magnitudes) < 3:
        baseline_magnitudes = [_acc_magnitude(sample) for sample in samples[:3]]
    baseline_gravity = statistics.median(baseline_magnitudes)

    scores = [
        abs(_acc_magnitude(sample) - baseline_gravity)
        + _gyro_magnitude(sample) / config.gyro_scale_dps
        for sample in samples
    ]
    window = max(
        config.minimum_smoothing_samples,
        round(sample_rate * config.smoothing_seconds),
    )
    smoothed = _moving_average(scores, window)

    # A local maximum above the confirmation threshold is one candidate punch.
    # Peaks closer than the refractory period belong to the same motion episode;
    # only the strongest peak in that episode is retained.
    episode_peaks: list[int] = []
    for index in range(1, len(smoothed) - 1):
        value = smoothed[index]
        if (
            value < config.confirm_threshold
            or value < smoothed[index - 1]
            or value <= smoothed[index + 1]
        ):
            continue
        if not episode_peaks:
            episode_peaks.append(index)
            continue
        previous = episode_peaks[-1]
        if samples[index].time_seconds - samples[previous].time_seconds >= config.refractory_seconds:
            episode_peaks.append(index)
        elif value > smoothed[previous]:
            episode_peaks[-1] = index
    return len(episode_peaks)


def _moving_average(values: list[float], window: int) -> list[float]:
    result: list[float] = []
    total = 0.0
    for index, value in enumerate(values):
        total += value
        if index >= window:
            total -= values[index - window]
        result.append(total / min(index + 1, window))
    return result


def _acc_magnitude(sample: ImuSample) -> float:
    return math.sqrt(sample.acc_x_g**2 + sample.acc_y_g**2 + sample.acc_z_g**2)


def _gyro_magnitude(sample: ImuSample) -> float:
    return math.sqrt(
        sample.gyro_x_dps**2 + sample.gyro_y_dps**2 + sample.gyro_z_dps**2
    )


class PunchCountExecutor:
    def execute(self, *, inputs: dict[str, bytes], parameters: dict) -> dict:
        if parameters:
            raise ContractError("unknown_parameter", "出拳次數 version 1 不接受額外參數")
        if set(inputs) != {"left_wrist", "right_wrist"}:
            raise ContractError(
                "missing_input_role", "出拳次數需要不同的左手腕與右手腕 CSV"
            )
        try:
            left = count_single_wrist_punches(read_common_imu_csv(inputs["left_wrist"]))
            right = count_single_wrist_punches(read_common_imu_csv(inputs["right_wrist"]))
        except PunchCountDataError as error:
            raise ContractError(error.code, error.message) from error
        return {
            "left_punch_count": left,
            "right_punch_count": right,
            "total_punch_count": left + right,
        }
