from __future__ import annotations

import csv
import io
import math

import pytest

from bap_backend.app.services.punch_speed import (
    PunchSpeedDataError,
    PunchSpeedExecutor,
    PunchWindow,
    analyze_single_wrist,
    build_punch_windows,
    integrate_window_peak,
    measurement_start_index,
    normalize_quaternion,
    read_speed_imu_csv,
    rotate_vector,
    world_linear_acceleration,
)
from bap_common.analysis_contracts import ContractError, builtin_analysis_specifications
from bap_common.imu_csv import COMMON_IMU_CSV_HEADER


BOUNDARY_US = 2_000_000


def speed_csv(
    *,
    amplitude_g: float = 6.0,
    event: bool = True,
    event_centers: tuple[int, ...] = (275,),
    rows: int = 500,
    repeated_elapsed: bool = False,
    fixed_time: bool = False,
    quaternion: tuple[object, object, object, object] = (1.0, 0.0, 0.0, 0.0),
    sample_interval_us: int = 10_000,
) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(COMMON_IMU_CSV_HEADER)
    for index in range(rows):
        dynamic_acceleration = 0.0
        gyro = 0.0
        for center in event_centers if event else ():
            start = center - 15
            end = center + 15
            if start <= index <= end:
                phase = (index - start) / (end - start)
                dynamic_acceleration = amplitude_g * math.sin(2 * math.pi * phase)
                gyro = 420.0 + 20.0 * math.sin(math.pi * phase)
        elapsed = 0 if fixed_time else (index // 4 if repeated_elapsed else index) * sample_interval_us
        device = 0 if fixed_time else round(index * sample_interval_us / 1_000)
        writer.writerow(
            (
                index,
                index,
                elapsed,
                device,
                "0x63",
                dynamic_acceleration,
                0.0,
                1.0,
                gyro,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                *quaternion,
                "",
                "",
            )
        )
    return output.getvalue().encode("utf-8")


@pytest.mark.scenario("punch-speed-analysis", "執行自動測試")
def test_quaternion_normalization_and_known_rotation() -> None:
    assert normalize_quaternion((2.0, 0.0, 0.0, 0.0)) == (1.0, 0.0, 0.0, 0.0)
    quarter_turn = (math.sqrt(0.5), 0.0, 0.0, math.sqrt(0.5))
    assert rotate_vector(quarter_turn, (1.0, 0.0, 0.0)) == pytest.approx((0.0, 1.0, 0.0))


@pytest.mark.scenario("punch-speed-analysis", "合成資料驗證單位換算與積分")
def test_known_acceleration_integrates_to_known_speed() -> None:
    from bap_backend.app.services.punch_speed import SpeedImuSample, GRAVITY_MPS2

    samples = tuple(
        SpeedImuSample(
            sample_index=index,
            elapsed_us=index * 1_000_000,
            time_seconds=float(index),
            acc_g=(0.0, 0.0, 1.0),
            gyro_dps=(0.0, 0.0, 0.0),
            quaternion=(1.0, 0.0, 0.0, 0.0),
        )
        for index in range(3)
    )
    peak, peak_index = integrate_window_peak(
        samples,
        ((1.0, 0.0, 0.0), (0.0, 0.0, 0.0), (-1.0, 0.0, 0.0)),
        PunchWindow(0, 1, 2),
    )
    assert peak == pytest.approx(0.5, abs=1e-9)
    assert peak_index == 1
    assert GRAVITY_MPS2 == pytest.approx(9.80665)


@pytest.mark.scenario("punch-speed-analysis", "靜止 baseline 會移除重力與固定偏差")
def test_world_acceleration_removes_calibration_baseline() -> None:
    from bap_backend.app.services.punch_speed import SpeedImuSample, GRAVITY_MPS2

    samples = tuple(
        SpeedImuSample(
            sample_index=index,
            elapsed_us=index * 10_000,
            time_seconds=index * 0.01,
            acc_g=(0.0 if index < 12 else 1.0, 0.0, 1.0),
            gyro_dps=(0.0, 0.0, 0.0),
            quaternion=(1.0, 0.0, 0.0, 0.0),
        )
        for index in range(15)
    )
    linear = world_linear_acceleration(samples, 12)
    assert linear[11] == pytest.approx((0.0, 0.0, 0.0))
    assert linear[14][0] == pytest.approx(GRAVITY_MPS2)


@pytest.mark.scenario("punch-speed-analysis", "一隻手完成一次有效出拳")
def test_one_motion_builds_one_complete_window_and_positive_peak_speed() -> None:
    samples = read_speed_imu_csv(speed_csv())
    start = measurement_start_index(samples, BOUNDARY_US)
    windows = build_punch_windows(samples, start)
    assert len(windows) == 1
    assert windows[0].start_index < windows[0].motion_peak_index < windows[0].end_index
    linear = world_linear_acceleration(samples, start)
    peak, peak_index = integrate_window_peak(samples, linear, windows[0])
    assert peak > 0
    assert windows[0].start_index <= peak_index <= windows[0].end_index


def test_incomplete_motion_at_end_is_not_reported_as_a_punch() -> None:
    samples = read_speed_imu_csv(speed_csv(rows=275))
    start = measurement_start_index(samples, BOUNDARY_US)
    assert build_punch_windows(samples, start) == ()


@pytest.mark.scenario("punch-speed-analysis", "相同輸入重複分析")
@pytest.mark.scenario("punch-speed-analysis", "左右手都有有效出拳")
@pytest.mark.scenario("punch-speed-analysis", "左右手輸入完整")
def test_executor_is_deterministic_and_faster_pulse_has_higher_speed() -> None:
    inputs = {"left_wrist": speed_csv(amplitude_g=7.0), "right_wrist": speed_csv(amplitude_g=4.0)}
    parameters = {"measurement_start_elapsed_us": BOUNDARY_US}
    executor = PunchSpeedExecutor()
    first = executor.execute(inputs=inputs, parameters=parameters)
    second = executor.execute(inputs=inputs, parameters=parameters)
    assert first == second
    assert first["left_punch_count"] == first["right_punch_count"] == 1
    assert first["total_punch_count"] == len(first["punches"]) == 2
    assert first["left_max_speed_mps"] > first["right_max_speed_mps"] > 0
    specification = next(
        item for item in builtin_analysis_specifications()
        if item.analysis_type == "punch_speed" and item.spec_version == 2
    )
    specification.validate_result(first)


def test_rapid_successive_and_simultaneous_left_right_punches_remain_separate() -> None:
    payload = speed_csv(event_centers=(250, 300), rows=400)
    result = PunchSpeedExecutor().execute(
        inputs={"left_wrist": payload, "right_wrist": payload},
        parameters={"measurement_start_elapsed_us": BOUNDARY_US},
    )
    assert result["left_punch_count"] == 2
    assert result["right_punch_count"] == 2
    assert result["total_punch_count"] == 4
    assert [item["punch_index"] for item in result["punches"] if item["hand"] == "left"] == [1, 2]
    assert [item["punch_index"] for item in result["punches"] if item["hand"] == "right"] == [1, 2]


@pytest.mark.scenario("punch-speed-analysis", "其中一隻手沒有出拳")
def test_zero_punch_hand_has_zero_summary() -> None:
    result = PunchSpeedExecutor().execute(
        inputs={"left_wrist": speed_csv(event=False), "right_wrist": speed_csv()},
        parameters={"measurement_start_elapsed_us": BOUNDARY_US},
    )
    assert result["left_punch_count"] == 0
    assert result["left_average_speed_mps"] == result["left_max_speed_mps"] == 0.0
    assert result["right_punch_count"] == 1


def test_motion_before_measurement_boundary_is_not_counted() -> None:
    result = PunchSpeedExecutor().execute(
        inputs={"left_wrist": speed_csv(), "right_wrist": speed_csv()},
        parameters={"measurement_start_elapsed_us": 3_000_000},
    )
    assert result["total_punch_count"] == 0


@pytest.mark.scenario("punch-speed-analysis", "無法建立有效時間軸")
def test_repeated_elapsed_keeps_distinct_samples_when_device_time_is_valid() -> None:
    samples = read_speed_imu_csv(speed_csv(repeated_elapsed=True))
    assert len(samples) == 500
    assert all(current.time_seconds > previous.time_seconds for previous, current in zip(samples, samples[1:]))


def test_reader_rejects_non_contiguous_sample_indexes() -> None:
    payload = speed_csv().replace(b"\n1,", b"\n9,", 1)
    with pytest.raises(PunchSpeedDataError) as captured:
        read_speed_imu_csv(payload)
    assert captured.value.code in {"invalid_sample_index", "invalid_sample_sequence"}


@pytest.mark.scenario("punch-speed-analysis", "Quaternion 缺少或無效")
@pytest.mark.parametrize(
    "quaternion",
    (("", "", "", ""), (0.0, 0.0, 0.0, 0.0), (float("nan"), 0.0, 0.0, 0.0)),
)
def test_reader_rejects_missing_or_invalid_quaternion(quaternion) -> None:
    with pytest.raises(PunchSpeedDataError) as captured:
        read_speed_imu_csv(speed_csv(quaternion=quaternion))
    assert captured.value.code in {"missing_quaternion", "invalid_quaternion", "invalid_sensor_value"}


@pytest.mark.scenario("punch-speed-analysis", "無法建立有效時間軸")
@pytest.mark.parametrize(
    "payload,boundary",
    (
        (speed_csv(fixed_time=True), BOUNDARY_US),
        (speed_csv(rows=20, sample_interval_us=1_000_000), 10_000_000),
        (speed_csv(), 9_000_000),
        (speed_csv(), 20_000),
    ),
    ids=("fixed-time", "low-rate", "boundary-after-data", "insufficient-calibration"),
)
def test_invalid_time_rate_boundary_or_calibration_is_rejected(payload: bytes, boundary: int) -> None:
    with pytest.raises(PunchSpeedDataError):
        samples = read_speed_imu_csv(payload)
        measurement_start_index(samples, boundary)


@pytest.mark.scenario("punch-speed-analysis", "左右手輸入缺少或重複")
def test_executor_requires_two_roles_and_valid_parameter() -> None:
    executor = PunchSpeedExecutor()
    with pytest.raises(ContractError) as missing_role:
        executor.execute(
            inputs={"left_wrist": speed_csv()},
            parameters={"measurement_start_elapsed_us": BOUNDARY_US},
        )
    assert missing_role.value.code == "missing_input_role"
    with pytest.raises(ContractError) as missing_parameter:
        executor.execute(
            inputs={"left_wrist": speed_csv(), "right_wrist": speed_csv()},
            parameters={},
        )
    assert missing_parameter.value.code == "invalid_parameter"

def test_analyze_single_wrist_returns_traceable_elapsed_times() -> None:
    punches = analyze_single_wrist(
        speed_csv(), hand="left", measurement_start_elapsed_us=BOUNDARY_US
    )
    assert len(punches) == 1
    assert punches[0]["hand"] == "left"
    assert punches[0]["punch_index"] == 1
    assert BOUNDARY_US <= punches[0]["start_elapsed_us"] <= punches[0]["peak_elapsed_us"]
    assert punches[0]["peak_elapsed_us"] <= punches[0]["end_elapsed_us"]
