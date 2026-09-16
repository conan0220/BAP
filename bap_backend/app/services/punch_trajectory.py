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
COORDINATE_SYSTEM = "session_local_x_right_y_forward_z_up"
MAXIMUM_DISPLAY_POINTS = 300
UNSTABLE_CALIBRATION_WARNING = (
    "校正期間偵測到明顯動作，本次軌跡仍已產生，但方向或位置漂移可能較大。"
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
            raise ContractError("missing_input_role", "出拳軌跡需要不同的左手腕與右手腕 CSV")
        calibration_end = parameters.get("calibration_end_elapsed_us")
        measurement_start = parameters.get("measurement_start_elapsed_us")
        if any(
            isinstance(boundary, bool) or not isinstance(boundary, int) or boundary <= 0
            for boundary in (calibration_end, measurement_start)
        ) or calibration_end > measurement_start:
            raise ContractError("invalid_parameter", "出拳軌跡的錄製時間邊界無效")
        try:
            left_samples = read_motion_imu_csv(inputs["left_wrist"])
            right_samples = read_motion_imu_csv(inputs["right_wrist"])
            left_calibration_end, left_start = calibration_and_measurement_indices(
                left_samples, calibration_end, measurement_start
            )
            right_calibration_end, right_start = calibration_and_measurement_indices(
                right_samples, calibration_end, measurement_start
            )
            left_heading, left_unstable = _calibration_heading_with_warning(
                left_samples, left_calibration_end
            )
            right_heading, right_unstable = _calibration_heading_with_warning(
                right_samples, right_calibration_end
            )
            warnings: list[str] = []
            if left_unstable or right_unstable:
                warnings.append(UNSTABLE_CALIBRATION_WARNING)
            try:
                heading = validate_paired_headings(left_heading, right_heading)
            except ImuMotionDataError as error:
                if error.code != "inconsistent_heading" or not warnings:
                    raise
                # An unstable calibration can also make the two fallback
                # headings disagree.  Keep a deterministic left-wrist frame
                # and surface the lower confidence instead of stopping.
                heading = left_heading
                warnings.append(
                    "校正不穩定且左右手方向不一致，本次使用左手腕方向作為參考。"
                )
            left = analyze_single_wrist_trajectories(
                left_samples,
                left_start,
                heading,
                hand="left",
                calibration_end_index=left_calibration_end,
            )
            right = analyze_single_wrist_trajectories(
                right_samples,
                right_start,
                heading,
                hand="right",
                calibration_end_index=right_calibration_end,
            )
        except ImuMotionDataError as error:
            raise ContractError(error.code, error.message) from error
        trajectories = sorted((*left, *right), key=lambda item: (item["start_elapsed_us"], item["hand"]))
        return {
            "algorithm_version": ALGORITHM_VERSION,
            "coordinate_system": COORDINATE_SYSTEM,
            "distance_unit": "m",
            "left_punch_count": len(left),
            "right_punch_count": len(right),
            "total_punch_count": len(trajectories),
            "quality_status": "warning" if warnings else "valid",
            "warnings": warnings,
            "trajectories": trajectories,
        }
