"""Shared IMU motion primitives for punch-speed and punch-trajectory analyses.

The trajectory math intentionally adopts only the documented ideas from the
``kaipo_research`` handoff: 400 Hz-capable input, quaternion sensor-to-world
rotation, gravity/bias removal from a still calibration segment, and
acceleration -> velocity -> position integration.  It does not execute or
package the handoff EXEs, fixed file paths, fixed calibration constants, or
research datasets.  Actual sample intervals are derived from Common IMU CSV.
"""

from __future__ import annotations

import csv
import io
import math
import statistics
from dataclasses import dataclass

from bap_backend.app.services.punch_count import (
    ImuSample,
    RULE_V1 as PUNCH_COUNT_RULE_V1,
    detect_single_wrist_punch_peaks,
    smoothed_motion_scores,
)
from bap_common.imu_csv import CommonImuCsvError, inspect_common_imu_csv_bytes


GRAVITY_MPS2 = 9.80665
MOTION_SENSOR_COLUMNS = (
    "acc_x_g", "acc_y_g", "acc_z_g",
    "gyro_x_dps", "gyro_y_dps", "gyro_z_dps",
    "quat_w", "quat_x", "quat_y", "quat_z",
)


class ImuMotionDataError(ValueError):
    """A stable, user-safe motion-data error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class MotionImuSample:
    sample_index: int
    elapsed_us: int
    time_seconds: float
    acc_g: tuple[float, float, float]
    gyro_dps: tuple[float, float, float]
    quaternion: tuple[float, float, float, float]

    def punch_count_sample(self) -> ImuSample:
        return ImuSample(self.time_seconds, *self.acc_g, *self.gyro_dps)


@dataclass(frozen=True, slots=True)
class PunchWindow:
    start_index: int
    motion_peak_index: int
    end_index: int


@dataclass(frozen=True, slots=True)
class MotionConfig:
    minimum_sample_rate_hz: float = 10.0
    minimum_calibration_samples: int = 10
    minimum_calibration_seconds: float = 0.25
    acceleration_smoothing_samples: int = 3
    maximum_calibration_orientation_degrees: float = 20.0
    # Left and right wrists are naturally mirrored and need not hold identical
    # yaw during a still guard pose. Real hardware validation observed a stable
    # 64.35-degree difference, so the Prototype accepts up to 75 degrees and
    # still rejects clearly inconsistent mounting.
    maximum_heading_difference_degrees: float = 75.0


DEFAULT_MOTION_CONFIG = MotionConfig()


def normalize_quaternion(
    value: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    if any(not math.isfinite(component) for component in value):
        raise ImuMotionDataError("invalid_quaternion", "IMU 姿態資料包含無效數值")
    norm = math.sqrt(sum(component * component for component in value))
    if norm < 1e-6:
        raise ImuMotionDataError("invalid_quaternion", "IMU 姿態資料無法正規化")
    return tuple(component / norm for component in value)  # type: ignore[return-value]


def rotate_vector(
    quaternion: tuple[float, float, float, float],
    vector: tuple[float, float, float],
) -> tuple[float, float, float]:
    """Rotate a sensor-frame vector using an ANROT W, X, Y, Z quaternion."""

    w, x, y, z = normalize_quaternion(quaternion)
    vx, vy, vz = vector
    return (
        (1 - 2 * (y * y + z * z)) * vx
        + 2 * (x * y - z * w) * vy
        + 2 * (x * z + y * w) * vz,
        2 * (x * y + z * w) * vx
        + (1 - 2 * (x * x + z * z)) * vy
        + 2 * (y * z - x * w) * vz,
        2 * (x * z - y * w) * vx
        + 2 * (y * z + x * w) * vy
        + (1 - 2 * (x * x + y * y)) * vz,
    )


def read_motion_imu_csv(
    data: bytes, *, config: MotionConfig = DEFAULT_MOTION_CONFIG
) -> tuple[MotionImuSample, ...]:
    try:
        inspection = inspect_common_imu_csv_bytes(data)
    except CommonImuCsvError as error:
        raise ImuMotionDataError(error.code, error.message) from error
    if inspection.row_count < 3:
        raise ImuMotionDataError("insufficient_imu_samples", "IMU 資料筆數不足，無法分析動作")
    try:
        rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline="")))
    except UnicodeDecodeError as error:
        raise ImuMotionDataError("invalid_csv_encoding", "CSV 必須使用 UTF-8") from error

    elapsed_values: list[int] = []
    sample_indexes: list[int] = []
    device_values: list[int] = []
    device_complete = True
    parsed_values: list[tuple[float, ...]] = []
    for row_number, row in enumerate(rows, start=2):
        values: list[float] = []
        for column in MOTION_SENSOR_COLUMNS:
            raw = row[column]
            if not raw:
                message = "IMU 姿態資料不足，請重新測量" if column.startswith("quat_") else "CSV 缺少必要的 IMU sensor 數值"
                raise ImuMotionDataError(
                    "missing_quaternion" if column.startswith("quat_") else "missing_sensor_value",
                    message,
                )
            try:
                number = float(raw)
            except ValueError as error:
                raise ImuMotionDataError(
                    "invalid_sensor_value", f"CSV 第 {row_number} 列包含無效的 IMU sensor 數值"
                ) from error
            if not math.isfinite(number):
                raise ImuMotionDataError(
                    "invalid_sensor_value", f"CSV 第 {row_number} 列包含非有限 IMU sensor 數值"
                )
            values.append(number)
        normalize_quaternion(tuple(values[6:10]))  # type: ignore[arg-type]
        parsed_values.append(tuple(values))
        try:
            sample_indexes.append(int(row["sample_index"]))
            elapsed_values.append(int(row["elapsed_us"]))
            if row["device_time_ms"]:
                device_values.append(int(row["device_time_ms"]))
            else:
                device_complete = False
        except (TypeError, ValueError) as error:
            raise ImuMotionDataError(
                "invalid_time_axis", f"CSV 第 {row_number} 列的時間欄位無效"
            ) from error

    if sample_indexes != list(range(sample_indexes[0], sample_indexes[0] + len(sample_indexes))):
        raise ImuMotionDataError("invalid_sample_sequence", "CSV 的 sample_index 必須依序連續")

    interval = 0.0
    if device_complete and _is_nondecreasing_with_span(device_values):
        interval = _median_interval(device_values, divisor=1_000.0)
    elif _is_nondecreasing_with_span(elapsed_values):
        interval = _median_interval(elapsed_values, divisor=1_000_000.0)
    if interval <= 0:
        raise ImuMotionDataError("invalid_time_axis", "IMU 資料的時間沒有前進，無法分析動作")
    if 1.0 / interval < config.minimum_sample_rate_hz:
        raise ImuMotionDataError("sample_rate_too_low", "IMU 資料取樣率太低，無法可靠分析動作")

    return tuple(
        MotionImuSample(
            sample_index=index,
            elapsed_us=elapsed_us,
            time_seconds=index * interval,
            acc_g=tuple(values[0:3]),  # type: ignore[arg-type]
            gyro_dps=tuple(values[3:6]),  # type: ignore[arg-type]
            quaternion=normalize_quaternion(tuple(values[6:10])),  # type: ignore[arg-type]
        )
        for index, (elapsed_us, values) in enumerate(zip(elapsed_values, parsed_values, strict=True))
    )


def _is_nondecreasing_with_span(values: list[int]) -> bool:
    return (
        len(values) >= 3
        and values[-1] > values[0]
        and all(current >= previous for previous, current in zip(values, values[1:]))
    )


def _median_interval(values: list[int], *, divisor: float) -> float:
    estimates: list[float] = []
    previous_change = 0
    for index in range(1, len(values)):
        if values[index] > values[previous_change]:
            estimates.append(
                (values[index] - values[previous_change]) / (index - previous_change) / divisor
            )
            previous_change = index
    return statistics.median(estimates) if estimates else 0.0


def measurement_start_index(
    samples: tuple[MotionImuSample, ...],
    boundary_us: int,
    *,
    config: MotionConfig = DEFAULT_MOTION_CONFIG,
) -> int:
    try:
        index = next(i for i, sample in enumerate(samples) if sample.elapsed_us >= boundary_us)
    except StopIteration as error:
        raise ImuMotionDataError("invalid_measurement_boundary", "正式測量開始時間不在 IMU 資料範圍內") from error
    calibration = samples[:index]
    if len(calibration) < config.minimum_calibration_samples:
        raise ImuMotionDataError("insufficient_calibration", "靜止校正資料不足，請重新測量")
    calibration_span = calibration[-1].time_seconds - calibration[0].time_seconds
    if calibration_span < config.minimum_calibration_seconds:
        raise ImuMotionDataError("insufficient_calibration", "靜止校正時間不足，請重新測量")
    if len(samples) - index < 3:
        raise ImuMotionDataError("insufficient_imu_samples", "正式測量資料不足，請重新測量")
    return index


def build_punch_windows(
    samples: tuple[MotionImuSample, ...], measurement_index: int
) -> tuple[PunchWindow, ...]:
    count_samples = tuple(sample.punch_count_sample() for sample in samples)
    peaks = tuple(
        peak for peak in detect_single_wrist_punch_peaks(count_samples) if peak >= measurement_index
    )
    scores = smoothed_motion_scores(count_samples)
    candidates: list[PunchWindow] = []
    for peak in peaks:
        start = peak
        while start > measurement_index and scores[start] > PUNCH_COUNT_RULE_V1.start_threshold:
            start -= 1
        end = peak
        while end < len(scores) - 1 and scores[end] > PUNCH_COUNT_RULE_V1.end_threshold:
            end += 1
        if end >= len(scores) - 1 and scores[end] > PUNCH_COUNT_RULE_V1.end_threshold:
            continue
        if start >= peak or end <= peak:
            continue
        candidates.append(PunchWindow(start, peak, end))

    windows: list[PunchWindow] = []
    for candidate in candidates:
        if windows and candidate.start_index <= windows[-1].end_index:
            previous = windows[-1]
            split = (previous.motion_peak_index + candidate.motion_peak_index) // 2
            windows[-1] = PunchWindow(
                previous.start_index,
                previous.motion_peak_index,
                max(previous.motion_peak_index + 1, split),
            )
            candidate = PunchWindow(
                min(candidate.motion_peak_index - 1, split + 1),
                candidate.motion_peak_index,
                candidate.end_index,
            )
        windows.append(candidate)
    return tuple(windows)


def world_linear_acceleration(
    samples: tuple[MotionImuSample, ...],
    measurement_index: int,
    *,
    config: MotionConfig = DEFAULT_MOTION_CONFIG,
) -> tuple[tuple[float, float, float], ...]:
    world_acceleration = tuple(
        rotate_vector(sample.quaternion, tuple(component * GRAVITY_MPS2 for component in sample.acc_g))
        for sample in samples
    )
    baseline = tuple(
        statistics.median(value[axis] for value in world_acceleration[:measurement_index])
        for axis in range(3)
    )
    linear = tuple(
        tuple(value[axis] - baseline[axis] for axis in range(3))
        for value in world_acceleration
    )
    window = max(1, config.acceleration_smoothing_samples)
    return tuple(
        tuple(
            sum(linear[item][axis] for item in range(max(0, index - window + 1), index + 1))
            / min(index + 1, window)
            for axis in range(3)
        )
        for index in range(len(linear))
    )


def integrate_window_velocity(
    samples: tuple[MotionImuSample, ...],
    linear_acceleration: tuple[tuple[float, float, float], ...],
    window: PunchWindow,
) -> tuple[tuple[float, float, float], ...]:
    velocities: list[tuple[float, float, float]] = [(0.0, 0.0, 0.0)]
    for index in range(window.start_index + 1, window.end_index + 1):
        dt = samples[index].time_seconds - samples[index - 1].time_seconds
        if dt <= 0:
            raise ImuMotionDataError("invalid_time_axis", "IMU 資料的時間沒有前進")
        previous = velocities[-1]
        velocities.append(tuple(
            previous[axis]
            + (linear_acceleration[index - 1][axis] + linear_acceleration[index][axis]) * 0.5 * dt
            for axis in range(3)
        ))
    duration = samples[window.end_index].time_seconds - samples[window.start_index].time_seconds
    if duration <= 0:
        raise ImuMotionDataError("invalid_time_axis", "單拳資料沒有有效的時間範圍")
    terminal = velocities[-1]
    return tuple(
        tuple(
            velocity[axis]
            - terminal[axis]
            * ((samples[window.start_index + offset].time_seconds - samples[window.start_index].time_seconds) / duration)
            for axis in range(3)
        )
        for offset, velocity in enumerate(velocities)
    )


def integrate_window_peak(
    samples: tuple[MotionImuSample, ...],
    linear_acceleration: tuple[tuple[float, float, float], ...],
    window: PunchWindow,
) -> tuple[float, int]:
    velocities = integrate_window_velocity(samples, linear_acceleration, window)
    speeds = [math.sqrt(sum(component * component for component in velocity)) for velocity in velocities]
    relative_peak = max(range(len(speeds)), key=speeds.__getitem__)
    return speeds[relative_peak], window.start_index + relative_peak


def _quaternion_angle_degrees(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    dot = abs(sum(a * b for a, b in zip(first, second, strict=True)))
    return math.degrees(2.0 * math.acos(min(1.0, max(-1.0, dot))))


def calibration_heading(
    samples: tuple[MotionImuSample, ...],
    measurement_index: int,
    *,
    config: MotionConfig = DEFAULT_MOTION_CONFIG,
) -> float:
    """Return world yaw of the sensor's mounted forward (+Y) direction."""

    calibration = samples[:measurement_index]
    reference = calibration[0].quaternion
    if max(_quaternion_angle_degrees(reference, sample.quaternion) for sample in calibration) > config.maximum_calibration_orientation_degrees:
        raise ImuMotionDataError("unstable_calibration", "校正期間姿態變動過大，請保持不動後重新測量")
    forwards = [rotate_vector(sample.quaternion, (0.0, 1.0, 0.0)) for sample in calibration]
    forward_x = statistics.median(vector[0] for vector in forwards)
    forward_y = statistics.median(vector[1] for vector in forwards)
    if math.hypot(forward_x, forward_y) < 1e-6:
        raise ImuMotionDataError("invalid_heading", "無法由校正姿勢判斷出拳方向")
    return math.atan2(forward_x, forward_y)


def validate_paired_headings(
    left_heading: float,
    right_heading: float,
    *,
    config: MotionConfig = DEFAULT_MOTION_CONFIG,
) -> float:
    difference = math.atan2(math.sin(left_heading - right_heading), math.cos(left_heading - right_heading))
    if abs(math.degrees(difference)) > config.maximum_heading_difference_degrees:
        raise ImuMotionDataError("inconsistent_heading", "左右手 IMU 的校正方向不一致，請確認安裝方向")
    x = math.sin(left_heading) + math.sin(right_heading)
    y = math.cos(left_heading) + math.cos(right_heading)
    return math.atan2(x, y)


def rotate_world_to_session(
    vectors: tuple[tuple[float, float, float], ...], heading: float
) -> tuple[tuple[float, float, float], ...]:
    cosine = math.cos(heading)
    sine = math.sin(heading)
    return tuple(
        (cosine * x - sine * y, sine * x + cosine * y, z)
        for x, y, z in vectors
    )
