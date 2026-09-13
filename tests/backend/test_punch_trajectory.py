from __future__ import annotations

import csv
import io
import math

import pytest

from bap_backend.app.services.imu_motion import (
    ImuMotionDataError,
    calibration_heading,
    measurement_start_index,
    read_motion_imu_csv,
    validate_paired_headings,
)
from bap_backend.app.services.punch_trajectory import (
    MAXIMUM_DISPLAY_POINTS,
    PunchTrajectoryExecutor,
    select_display_indices,
)
from bap_common.analysis_contracts import ContractError, builtin_analysis_specifications
from bap_common.imu_csv import COMMON_IMU_CSV_HEADER


BOUNDARY_US = 2_000_000
PARAMETERS = {
    "calibration_end_elapsed_us": BOUNDARY_US,
    "measurement_start_elapsed_us": BOUNDARY_US,
}


def trajectory_csv(
    *,
    event_centers: tuple[int, ...] = (275,),
    event: bool = True,
    rows: int = 500,
    quaternion: tuple[object, object, object, object] = (1.0, 0.0, 0.0, 0.0),
    calibration_quaternion: tuple[object, object, object, object] | None = None,
    gap_quaternion: tuple[object, object, object, object] | None = None,
    missing_quaternion: bool = False,
) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(COMMON_IMU_CSV_HEADER)
    for index in range(rows):
        dynamic = 0.0
        gyro = 0.0
        for center in event_centers if event else ():
            start, end = center - 15, center + 15
            if start <= index <= end:
                phase = (index - start) / (end - start)
                dynamic = 6.0 * math.sin(2 * math.pi * phase)
                gyro = 430.0
        current_quaternion = calibration_quaternion if calibration_quaternion is not None and index < 200 else quaternion
        if gap_quaternion is not None and 200 <= index < 240:
            current_quaternion = gap_quaternion
        if missing_quaternion:
            current_quaternion = ("", "", "", "")
        writer.writerow(
            (
                index, index, index * 10_000, index * 10, "0x63",
                dynamic, 0.0, 1.0, gyro, 0.0, 0.0,
                0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                *current_quaternion, "", "",
            )
        )
    return output.getvalue().encode("utf-8")


def trajectory_specification():
    return next(
        item for item in builtin_analysis_specifications()
        if item.analysis_type == "punch_trajectory" and item.spec_version == 2
    )


@pytest.mark.scenario("punch-trajectory-analysis", "一場 Session 包含左右手多拳")
@pytest.mark.scenario("punch-trajectory-analysis", "Backend 回傳一拳的有效軌跡")
@pytest.mark.scenario("punch-trajectory-analysis", "Backend 回傳一拳的有效軌跡")
def test_executor_returns_contract_valid_isolated_trajectories() -> None:
    payload = trajectory_csv(event_centers=(260, 320), rows=450)
    executor = PunchTrajectoryExecutor()
    first = executor.execute(
        inputs={"left_wrist": payload, "right_wrist": payload},
        parameters=PARAMETERS,
    )
    second = executor.execute(
        inputs={"left_wrist": payload, "right_wrist": payload},
        parameters=PARAMETERS,
    )
    assert first == second
    assert first["left_punch_count"] == first["right_punch_count"] == 2
    assert first["total_punch_count"] == len(first["trajectories"]) == 4
    for trajectory in first["trajectories"]:
        assert trajectory["points"][0]["x_m"] == 0
        assert trajectory["points"][0]["y_m"] == 0
        assert trajectory["points"][0]["z_m"] == 0
        assert 2 <= len(trajectory["points"]) <= MAXIMUM_DISPLAY_POINTS
        assert trajectory["path_length_m"] >= trajectory["maximum_displacement_m"] >= 0
    trajectory_specification().validate_result(first)


@pytest.mark.scenario("punch-trajectory-analysis", "正式資料沒有偵測到出拳")
def test_no_punch_is_a_successful_empty_result() -> None:
    payload = trajectory_csv(event=False)
    result = PunchTrajectoryExecutor().execute(
        inputs={"left_wrist": payload, "right_wrist": payload},
        parameters=PARAMETERS,
    )
    assert result["total_punch_count"] == 0
    assert result["trajectories"] == []
    trajectory_specification().validate_result(result)


@pytest.mark.scenario("punch-trajectory-analysis", "軌跡原始點數超過顯示上限")
def test_display_point_selection_is_deterministic_and_preserves_ends() -> None:
    indices = select_display_indices(1_001)
    assert len(indices) == 300
    assert indices[0] == 0
    assert indices[-1] == 1_000
    assert indices == select_display_indices(1_001)
    assert all(current > previous for previous, current in zip(indices, indices[1:]))


@pytest.mark.scenario("punch-trajectory-analysis", "CSV 缺少有效 Quaternion")
def test_missing_quaternion_becomes_safe_contract_error() -> None:
    payload = trajectory_csv(missing_quaternion=True)
    with pytest.raises(ContractError) as captured:
        PunchTrajectoryExecutor().execute(
            inputs={"left_wrist": payload, "right_wrist": payload},
            parameters=PARAMETERS,
        )
    assert captured.value.code == "missing_quaternion"
    assert "D:\\" not in captured.value.message


def test_unstable_calibration_is_rejected() -> None:
    payload = trajectory_csv()
    samples = list(read_motion_imu_csv(payload))
    quarter_turn = (math.sqrt(0.5), 0.0, 0.0, math.sqrt(0.5))
    samples[100] = samples[100].__class__(
        samples[100].sample_index,
        samples[100].elapsed_us,
        samples[100].time_seconds,
        samples[100].acc_g,
        samples[100].gyro_dps,
        quarter_turn,
    )
    start = measurement_start_index(tuple(samples), BOUNDARY_US)
    with pytest.raises(ImuMotionDataError) as captured:
        calibration_heading(tuple(samples), start)
    assert captured.value.code == "unstable_calibration"


def test_paired_heading_must_be_consistent() -> None:
    with pytest.raises(ImuMotionDataError) as captured:
        validate_paired_headings(0.0, math.pi / 2)
    assert captured.value.code == "inconsistent_heading"


def test_stable_mirrored_wrist_headings_are_accepted() -> None:
    heading = validate_paired_headings(
        math.radians(88.50),
        math.radians(152.85),
    )
    assert math.degrees(heading) == pytest.approx(120.675)


def test_movement_between_calibration_and_measurement_is_not_calibration() -> None:
    quarter_turn = (math.sqrt(0.5), 0.0, 0.0, math.sqrt(0.5))
    payload = trajectory_csv(gap_quaternion=quarter_turn)
    result = PunchTrajectoryExecutor().execute(
        inputs={"left_wrist": payload, "right_wrist": payload},
        parameters={
            "calibration_end_elapsed_us": 2_000_000,
            "measurement_start_elapsed_us": 2_400_000,
        },
    )
    assert result["total_punch_count"] == 2


@pytest.mark.scenario("analysis-specification-contract", "前後端使用相同的 version 2")
@pytest.mark.scenario("analysis-specification-contract", "version 2 Result 仍使用 summary placeholder")
@pytest.mark.scenario("analysis-specification-contract", "Result 的拳數與 trajectories 不一致")
def test_contract_rejects_placeholder_and_inconsistent_counts() -> None:
    specification = trajectory_specification()
    with pytest.raises(ContractError):
        specification.validate_result({"summary": {}})
    valid = PunchTrajectoryExecutor().execute(
        inputs={"left_wrist": trajectory_csv(), "right_wrist": trajectory_csv()},
        parameters=PARAMETERS,
    )
    valid["total_punch_count"] += 1
    with pytest.raises(ContractError) as captured:
        specification.validate_result(valid)
    assert captured.value.code == "invalid_result_value"


def test_contract_requires_measurement_boundary() -> None:
    with pytest.raises(ContractError) as captured:
        trajectory_specification().validate_parameters({})
    assert captured.value.code == "missing_parameter"


def test_contract_rejects_reversed_recording_boundaries() -> None:
    with pytest.raises(ContractError) as captured:
        trajectory_specification().validate_parameters(
            {
                "calibration_end_elapsed_us": 3_000_000,
                "measurement_start_elapsed_us": 2_000_000,
            }
        )
    assert captured.value.code == "invalid_parameter"

@pytest.mark.scenario("punch-trajectory-analysis", "校正資料不足")
def test_insufficient_calibration_becomes_safe_contract_error() -> None:
    payload = trajectory_csv()
    with pytest.raises(ContractError) as captured:
        PunchTrajectoryExecutor().execute(
            inputs={"left_wrist": payload, "right_wrist": payload},
            parameters={
                "calibration_end_elapsed_us": 50_000,
                "measurement_start_elapsed_us": 50_000,
            },
        )
    assert captured.value.code == "insufficient_calibration"
    assert "校正" in captured.value.message


def test_non_finite_sensor_value_never_returns_a_fake_trajectory() -> None:
    payload = trajectory_csv(quaternion=(float("nan"), 0.0, 0.0, 0.0))
    with pytest.raises(ContractError) as captured:
        PunchTrajectoryExecutor().execute(
            inputs={"left_wrist": payload, "right_wrist": payload},
            parameters=PARAMETERS,
        )
    assert captured.value.code == "invalid_sensor_value"
    assert "D:\\" not in captured.value.message
