"""Deterministic rule_v1 Shadow-boxing punch-speed analysis."""

from __future__ import annotations

from dataclasses import dataclass

from bap_backend.app.services import imu_motion as _motion
from bap_backend.app.services.imu_motion import (
    GRAVITY_MPS2,
    ImuMotionDataError,
    MotionConfig,
    MotionImuSample,
    PunchWindow,
)
from bap_common.analysis_contracts import ContractError


PunchSpeedDataError = ImuMotionDataError
SpeedImuSample = MotionImuSample


@dataclass(frozen=True, slots=True)
class PunchSpeedRuleV1Config(MotionConfig):
    algorithm_version: str = "rule_v1"
    minimum_sample_rate_hz: float = 10.0
    minimum_calibration_samples: int = 10
    minimum_calibration_seconds: float = 0.25
    acceleration_smoothing_samples: int = 3


RULE_V1 = PunchSpeedRuleV1Config()


normalize_quaternion = _motion.normalize_quaternion
rotate_vector = _motion.rotate_vector
read_speed_imu_csv = _motion.read_motion_imu_csv
measurement_start_index = _motion.measurement_start_index
calibration_and_measurement_indices = _motion.calibration_and_measurement_indices
build_punch_windows = _motion.build_punch_windows
world_linear_acceleration = _motion.world_linear_acceleration
integrate_window_peak = _motion.integrate_window_peak


def analyze_single_wrist(
    data: bytes,
    *,
    hand: str,
    calibration_end_elapsed_us: int,
    measurement_start_elapsed_us: int,
    config: PunchSpeedRuleV1Config = RULE_V1,
) -> list[dict]:
    samples = read_speed_imu_csv(data, config=config)
    calibration_end_index, start_index = calibration_and_measurement_indices(
        samples,
        calibration_end_elapsed_us,
        measurement_start_elapsed_us,
        config=config,
    )
    linear = world_linear_acceleration(samples, calibration_end_index, config=config)
    punches: list[dict] = []
    for punch_index, window in enumerate(build_punch_windows(samples, start_index), start=1):
        peak_speed, speed_peak_index = integrate_window_peak(samples, linear, window)
        punches.append(
            {
                "hand": hand,
                "punch_index": punch_index,
                "start_elapsed_us": samples[window.start_index].elapsed_us,
                "peak_elapsed_us": samples[speed_peak_index].elapsed_us,
                "end_elapsed_us": samples[window.end_index].elapsed_us,
                "peak_speed_mps": round(peak_speed, 3),
            }
        )
    return punches


def _summary(speeds: list[float]) -> tuple[float, float]:
    if not speeds:
        return 0.0, 0.0
    return round(sum(speeds) / len(speeds), 3), round(max(speeds), 3)


class PunchSpeedExecutor:
    def execute(self, *, inputs: dict[str, bytes], parameters: dict) -> dict:
        if set(inputs) != {"left_wrist", "right_wrist"}:
            raise ContractError("missing_input_role", "拳頭速度需要不同的左手腕與右手腕 CSV")
        calibration_end = parameters.get("calibration_end_elapsed_us")
        measurement_start = parameters.get("measurement_start_elapsed_us")
        if any(
            isinstance(boundary, bool) or not isinstance(boundary, int) or boundary <= 0
            for boundary in (calibration_end, measurement_start)
        ) or calibration_end > measurement_start:
            raise ContractError("invalid_parameter", "拳頭速度的錄製時間邊界無效")
        try:
            left = analyze_single_wrist(
                inputs["left_wrist"],
                hand="left",
                calibration_end_elapsed_us=calibration_end,
                measurement_start_elapsed_us=measurement_start,
            )
            right = analyze_single_wrist(
                inputs["right_wrist"],
                hand="right",
                calibration_end_elapsed_us=calibration_end,
                measurement_start_elapsed_us=measurement_start,
            )
        except PunchSpeedDataError as error:
            raise ContractError(error.code, error.message) from error
        punches = sorted((*left, *right), key=lambda item: item["peak_elapsed_us"])
        left_speeds = [float(item["peak_speed_mps"]) for item in left]
        right_speeds = [float(item["peak_speed_mps"]) for item in right]
        left_average, left_maximum = _summary(left_speeds)
        right_average, right_maximum = _summary(right_speeds)
        return {
            "algorithm_version": RULE_V1.algorithm_version,
            "left_punch_count": len(left),
            "right_punch_count": len(right),
            "total_punch_count": len(punches),
            "left_average_speed_mps": left_average,
            "left_max_speed_mps": left_maximum,
            "right_average_speed_mps": right_average,
            "right_max_speed_mps": right_maximum,
            "punches": punches,
        }
