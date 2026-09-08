from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from bap_backend.app.services.punch_count import (
    PunchCountDataError,
    PunchCountExecutor,
    count_single_wrist_punches,
    read_common_imu_csv,
)
from bap_common.analysis_contracts import ContractError
from bap_common.analysis_contracts import builtin_analysis_specifications
from bap_common.benchmark_bundle import load_benchmark_bundle
from bap_common.imu_csv import COMMON_IMU_CSV_HEADER


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "punch_count"


def imu_csv(
    *,
    peaks: tuple[int, ...] = (),
    rows: int = 300,
    repeated_elapsed: bool = False,
    fixed_time: bool = False,
) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(COMMON_IMU_CSV_HEADER)
    for index in range(rows):
        distance = min((abs(index - peak) for peak in peaks), default=999)
        amplitude = {0: 7.0, 1: 4.0, 2: 1.0}.get(distance, 0.0)
        elapsed = 0 if fixed_time else (index // 4 if repeated_elapsed else index) * 10_000
        device = 0 if fixed_time else index * 10
        writer.writerow(
            (
                index,
                index,
                elapsed,
                device,
                "0x63",
                amplitude,
                0,
                1,
                amplitude * 100,
                0,
                0,
                *("" for _ in range(12)),
            )
        )
    return output.getvalue().encode("utf-8")


@pytest.mark.scenario("punch-count-analysis", "一隻手完成一次 Shadow boxing 出拳")
def test_single_motion_episode_counts_once() -> None:
    samples = read_common_imu_csv(imu_csv(peaks=(100, 108)))
    assert count_single_wrist_punches(samples) == 1


@pytest.mark.scenario("punch-count-analysis", "同一隻手快速連續出拳")
def test_two_separated_motion_episodes_count_twice() -> None:
    samples = read_common_imu_csv(imu_csv(peaks=(80, 130)))
    assert count_single_wrist_punches(samples) == 2


@pytest.mark.scenario("punch-count-analysis", "只有一般手腕晃動")
def test_low_intensity_wrist_movement_counts_zero() -> None:
    assert count_single_wrist_punches(read_common_imu_csv(imu_csv())) == 0


@pytest.mark.scenario("punch-count-analysis", "elapsed_us 有重複但仍有有效順序")
def test_device_time_keeps_batched_elapsed_samples_in_order() -> None:
    samples = read_common_imu_csv(imu_csv(peaks=(80,), repeated_elapsed=True))
    assert len(samples) == 300
    assert count_single_wrist_punches(samples) == 1


@pytest.mark.scenario("punch-count-analysis", "CSV 沒有足夠有效資料")
@pytest.mark.parametrize(
    "payload",
    (
        imu_csv(rows=2),
        imu_csv(fixed_time=True),
    ),
)
def test_reader_rejects_insufficient_or_stationary_time_axis(payload: bytes) -> None:
    with pytest.raises(PunchCountDataError):
        read_common_imu_csv(payload)


def test_reader_rejects_missing_required_sensor_value() -> None:
    rows = list(csv.reader(io.StringIO(imu_csv().decode("utf-8"))))
    rows[1][5] = ""
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\n").writerows(rows)
    payload = output.getvalue().encode("utf-8")
    with pytest.raises(PunchCountDataError):
        read_common_imu_csv(payload)


@pytest.mark.scenario("punch-count-analysis", "左右手幾乎同時出拳")
@pytest.mark.scenario("punch-count-analysis", "成功完成分析")
@pytest.mark.scenario("punch-count-analysis", "相同資料重複分析")
def test_executor_analyzes_hands_independently_and_is_deterministic() -> None:
    executor = PunchCountExecutor()
    inputs = {
        "left_wrist": imu_csv(peaks=(80,)),
        "right_wrist": imu_csv(peaks=(82,)),
    }
    expected = {"left_punch_count": 1, "right_punch_count": 1, "total_punch_count": 2}
    assert executor.execute(inputs=inputs, parameters={}) == expected
    assert executor.execute(inputs=inputs, parameters={}) == expected


@pytest.mark.scenario("punch-count-analysis", "左右手輸入缺少或重複")
def test_executor_requires_both_input_roles() -> None:
    with pytest.raises(ContractError) as captured:
        PunchCountExecutor().execute(inputs={"left_wrist": imu_csv()}, parameters={})
    assert captured.value.code == "missing_input_role"


def test_punch_count_result_contract_rejects_negative_or_wrong_total() -> None:
    specification = builtin_analysis_specifications()[0]
    with pytest.raises(ContractError) as negative:
        specification.validate_result(
            {"left_punch_count": -1, "right_punch_count": 1, "total_punch_count": 0}
        )
    assert negative.value.code == "invalid_result_value"
    with pytest.raises(ContractError) as wrong_total:
        specification.validate_result(
            {"left_punch_count": 1, "right_punch_count": 1, "total_punch_count": 3}
        )
    assert wrong_total.value.code == "invalid_result_value"


@pytest.mark.scenario("pull-request-ci", "所有 Benchmark cases 計算正確")
@pytest.mark.scenario("pull-request-ci", "CI 載入既有 Benchmark ZIP")
@pytest.mark.parametrize("path", sorted(FIXTURES.glob("*.zip")), ids=lambda path: path.stem)
def test_production_executor_matches_approved_benchmark(path: Path) -> None:
    bundle = load_benchmark_bundle(path)
    actual = PunchCountExecutor().execute(inputs=bundle.csv_by_role, parameters={})
    expected = bundle.metadata.ground_truth.model_dump()
    assert actual == expected, f"{path.name}: expected={expected}, actual={actual}"
