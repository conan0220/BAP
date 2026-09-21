"""Deterministic per-punch 3D trajectory reconstruction for Shadow boxing."""

from __future__ import annotations

import math

from bap_backend.app.services.imu_motion import (
    ImuMotionDataError,
    MotionImuSample,
    PunchWindow,
    build_punch_windows,
    calibration_and_measurement_indices,
    calibration_heading,
    integrate_window_velocity,
    read_motion_imu_csv,
    rotate_world_to_session,
    validate_paired_headings,
    world_linear_acceleration,
)
from bap_common.analysis_contracts import ContractError


ALGORITHM_VERSION = "trajectory_rule_v2"
DIRECT_ALGORITHM_VERSION = "trajectory_direct_v1"
COORDINATE_SYSTEM = "session_local_x_right_y_forward_z_up"
MAXIMUM_DISPLAY_POINTS = 300
UNSTABLE_CALIBRATION_WARNING = (
    "校正期間偵測到明顯動作，本次軌跡仍已產生，但方向或位置漂移可能較大。"
)
INCONSISTENT_INITIAL_ORIENTATION_WARNING = (
    "左右手 IMU 的初始方向不同，系統已使用左手腕方向作為顯示基準；軌跡方向可能較不準確。"
)


def _calibration_heading_with_warning(
    samples: tuple[MotionImuSample, ...], calibration_end_index: int
) -> tuple[float, bool]:
    """Return a usable heading while reporting unstable calibration as quality."""

    try:
        return calibration_heading(samples, calibration_end_index), False
    except ImuMotionDataError as error:
        if error.code != "unstable_calibration":
            raise
        # CSV parsing already proved that this sample has a finite, normalizable
        # Quaternion.  It is a deterministic best-effort fallback, not a claim
        # that the calibration was stable.
        return calibration_heading(samples[:1], 1), True


def direct_measurement_index(
    samples: tuple[MotionImuSample, ...], measurement_start_elapsed_us: int
) -> int:
    """Resolve a direct-recording boundary without requiring calibration data."""

    try:
        index = next(
            item
            for item, sample in enumerate(samples)
            if sample.elapsed_us >= measurement_start_elapsed_us
        )
    except StopIteration as error:
        raise ImuMotionDataError(
            "invalid_measurement_boundary", "正式測量開始時間不在 IMU 資料範圍內"
        ) from error
    # Keep one initial sample as the deterministic acceleration and heading
    # reference. This is an internal calculation baseline, not a user-facing
    # calibration stage.
    index = max(1, index)
    if len(samples) - index < 3:
        raise ImuMotionDataError("insufficient_imu_samples", "正式測量資料不足，請重新測量")
    return index


def integrate_window_positions(
    samples: tuple[MotionImuSample, ...],
    linear_acceleration: tuple[tuple[float, float, float], ...],
    window: PunchWindow,
) -> tuple[tuple[float, float, float], ...]:
    """Drift-correct velocity, then integrate one isolated punch from origin."""

    velocities = integrate_window_velocity(samples, linear_acceleration, window)
    positions: list[tuple[float, float, float]] = [(0.0, 0.0, 0.0)]
    for offset in range(1, len(velocities)):
        index = window.start_index + offset
        dt = samples[index].time_seconds - samples[index - 1].time_seconds
        previous = positions[-1]
        position = tuple(
            previous[axis] + (velocities[offset - 1][axis] + velocities[offset][axis]) * 0.5 * dt
            for axis in range(3)
        )
        if any(not math.isfinite(component) for component in position):
            raise ImuMotionDataError("non_finite_trajectory", "軌跡運算產生無效數值，請重新測量")
        positions.append(position)
    return tuple(positions)


def select_display_indices(length: int, maximum: int = MAXIMUM_DISPLAY_POINTS) -> tuple[int, ...]:
    """Select deterministic, ordered points while always preserving both ends."""

    if length < 2:
        raise ValueError("trajectory needs at least two points")
    if maximum < 2:
        raise ValueError("maximum display points must be at least two")
    if length <= maximum:
        return tuple(range(length))
    return tuple((index * (length - 1)) // (maximum - 1) for index in range(maximum))


def _trajectory_summary(
    samples: tuple[MotionImuSample, ...],
    window: PunchWindow,
    positions: tuple[tuple[float, float, float], ...],
    *,
    hand: str,
    punch_index: int,
) -> dict:
    path_length = sum(
        math.dist(previous, current)
        for previous, current in zip(positions, positions[1:])
    )
    maximum_displacement = max(math.dist((0.0, 0.0, 0.0), position) for position in positions)
    if any(not math.isfinite(value) or value < 0 for value in (path_length, maximum_displacement)):
        raise ImuMotionDataError("non_finite_trajectory", "軌跡運算產生無效數值，請重新測量")
    indices = select_display_indices(len(positions))
    points = [
        {
            "elapsed_us": samples[window.start_index + offset].elapsed_us,
            "x_m": round(positions[offset][0], 6),
            "y_m": round(positions[offset][1], 6),
            "z_m": round(positions[offset][2], 6),
        }
        for offset in indices
    ]
    start = samples[window.start_index].elapsed_us
    end = samples[window.end_index].elapsed_us
    return {
        "hand": hand,
        "punch_index": punch_index,
        "start_elapsed_us": start,
        "end_elapsed_us": end,
        "duration_seconds": round((end - start) / 1_000_000, 6),
        "path_length_m": round(path_length, 6),
        "maximum_displacement_m": round(maximum_displacement, 6),
        "points": points,
    }


def analyze_single_wrist_trajectories(
    samples: tuple[MotionImuSample, ...],
    measurement_index: int,
    session_heading: float,
    *,
    hand: str,
    calibration_end_index: int,
) -> list[dict]:
    world = world_linear_acceleration(samples, calibration_end_index)
    session_acceleration = rotate_world_to_session(world, session_heading)
    trajectories: list[dict] = []
    for punch_index, window in enumerate(build_punch_windows(samples, measurement_index), start=1):
        positions = integrate_window_positions(samples, session_acceleration, window)
        trajectories.append(
            _trajectory_summary(
                samples, window, positions, hand=hand, punch_index=punch_index
            )
        )
    return trajectories


class PunchTrajectoryExecutor:
    def execute(self, *, inputs: dict[str, bytes], parameters: dict) -> dict:
        if set(inputs) != {"left_wrist", "right_wrist"}:
            raise ContractError("missing_input_role", "出拳軌跡需要左、右手腕兩份 CSV")
        calibration_end = parameters.get("calibration_end_elapsed_us")
        measurement_start = parameters.get("measurement_start_elapsed_us")
        if (
            isinstance(measurement_start, bool)
            or not isinstance(measurement_start, int)
            or measurement_start <= 0
        ):
            raise ContractError("invalid_parameter", "出拳軌跡的錄製時間邊界無效")
        direct_recording = calibration_end is None
        if not direct_recording and (
            isinstance(calibration_end, bool)
            or not isinstance(calibration_end, int)
            or calibration_end <= 0
            or calibration_end > measurement_start
        ):
            raise ContractError("invalid_parameter", "出拳軌跡的錄製時間邊界無效")
        try:
            left_samples = read_motion_imu_csv(inputs["left_wrist"])
            right_samples = read_motion_imu_csv(inputs["right_wrist"])
            warnings: list[str] = []
            if direct_recording:
                left_start = direct_measurement_index(left_samples, measurement_start)
                right_start = direct_measurement_index(right_samples, measurement_start)
                left_reference = left_start
                right_reference = right_start
                left_heading = calibration_heading(left_samples[:1], 1)
                right_heading = calibration_heading(right_samples[:1], 1)
            else:
                left_reference, left_start = calibration_and_measurement_indices(
                    left_samples, calibration_end, measurement_start
                )
                right_reference, right_start = calibration_and_measurement_indices(
                    right_samples, calibration_end, measurement_start
                )
                left_heading, left_unstable = _calibration_heading_with_warning(
                    left_samples, left_reference
                )
                right_heading, right_unstable = _calibration_heading_with_warning(
                    right_samples, right_reference
                )
                if left_unstable or right_unstable:
                    warnings.append(UNSTABLE_CALIBRATION_WARNING)
            try:
                heading = validate_paired_headings(left_heading, right_heading)
            except ImuMotionDataError as error:
                if error.code != "inconsistent_heading":
                    raise
                heading = left_heading
                warnings.append(INCONSISTENT_INITIAL_ORIENTATION_WARNING)
            left = analyze_single_wrist_trajectories(
                left_samples,
                left_start,
                heading,
                hand="left",
                calibration_end_index=left_reference,
            )
            right = analyze_single_wrist_trajectories(
                right_samples,
                right_start,
                heading,
                hand="right",
                calibration_end_index=right_reference,
            )
        except ImuMotionDataError as error:
            raise ContractError(error.code, error.message) from error
        trajectories = sorted(
            (*left, *right), key=lambda item: (item["start_elapsed_us"], item["hand"])
        )
        return {
            "algorithm_version": DIRECT_ALGORITHM_VERSION if direct_recording else ALGORITHM_VERSION,
            "coordinate_system": COORDINATE_SYSTEM,
            "distance_unit": "m",
            "left_punch_count": len(left),
            "right_punch_count": len(right),
            "total_punch_count": len(trajectories),
            "quality_status": "warning" if warnings else "valid",
            "warnings": warnings,
            "trajectories": trajectories,
        }
