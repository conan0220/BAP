from __future__ import annotations

import csv
import io
import math

import pytest

from bap_backend.app.services.analysis_registry import AnalysisInputDescriptor
from bap_backend.app.services.punch_force import (
    PunchForceExecutor,
    align_force_inputs,
)
from bap_common.analysis_contracts import ContractError, builtin_analysis_specifications
from bap_common.imu_csv import COMMON_IMU_CSV_HEADER


def descriptor(role: str, *, port: str = "COM6", group: int = 0, node: int | None = None, connection: str = "wireless_receiver"):
    return AnalysisInputDescriptor(
        csv_id=f"csv-{role}", source_id=f"COM6:group-{group}:node-{node}",
        port=port, connection_type=connection, baud_rate=921600,
        group_id=group if connection == "wireless_receiver" else None,
        node_id=(0 if role == "bag_top" else 1) if node is None and connection == "wireless_receiver" else node,
    )


def parameters(*, mass: float = 36.0):
    return {
        "calibration_end_elapsed_us": 2_000_000,
        "measurement_start_elapsed_us": 2_200_000,
        "bag_mass_kg": mass,
        "bag_length_m": 1.24,
        "bag_diameter_m": 0.335,
        "sensor_distance_m": 1.24,
    }


def synthetic_pair(
    *,
    sample_rate: int = 400,
    duration: float = 4.2,
    strikes: tuple[float, ...] = (3.0,),
    force_kgf: float = 50.0,
    impact_offset_m: float = 0.2,
    missing_top: set[int] | None = None,
    missing_bottom: set[int] | None = None,
    gyro_mismatch: bool = False,
) -> dict[str, bytes]:
    count = int(sample_rate * duration) + 1
    mass = 36.0
    length = 1.24
    radius = 0.335 / 2
    inertia = mass * (3 * radius * radius + length * length) / 12
    outputs = {}
    for role in ("bag_top", "bag_bottom"):
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=COMMON_IMU_CSV_HEADER, lineterminator="\n")
        writer.writeheader()
        row_index = 0
        missing = missing_top if role == "bag_top" else missing_bottom
        for packet in range(count):
            if missing and packet in missing:
                continue
            time_seconds = packet / sample_rate
            pulse = 0.0
            for strike in strikes:
                distance = abs(time_seconds - strike)
                if distance <= 0.04:
                    pulse = max(pulse, math.cos(distance / 0.04 * math.pi / 2))
            center_acc = force_kgf / mass * 9.80665 * pulse
            angular_y = impact_offset_m * (force_kgf * 9.80665) / inertia * pulse
            difference_x = angular_y * length
            x_mps2 = center_acc + (difference_x / 2 if role == "bag_top" else -difference_x / 2)
            gyro = 90.0 * pulse
            if gyro_mismatch and role == "bag_bottom":
                gyro = 0.0
            values = {name: "" for name in COMMON_IMU_CSV_HEADER}
            values.update(
                sample_index=row_index,
                packet_index=packet,
                elapsed_us=round(time_seconds * 1_000_000),
                device_time_ms=round(time_seconds * 1000),
                frame_type="0x63",
                acc_x_g=x_mps2 / 9.80665,
                acc_y_g=0.0,
                acc_z_g=1.0,
                gyro_x_dps=0.0,
                gyro_y_dps=gyro,
                gyro_z_dps=0.0,
                quat_w=1.0,
                quat_x=0.0,
                quat_y=0.0,
                quat_z=0.0,
            )
            writer.writerow(values)
            row_index += 1
        outputs[role] = output.getvalue().encode("utf-8")
    return outputs


def execute(inputs=None, *, params=None, descriptors=None):
    return PunchForceExecutor().execute(
        inputs=inputs or synthetic_pair(),
        parameters=params or parameters(),
        input_descriptors=descriptors or {role: descriptor(role) for role in ("bag_top", "bag_bottom")},
    )


@pytest.mark.scenario("punch-force-analysis", "有效資料包含一次打擊")
@pytest.mark.scenario("punch-force-analysis", "Backend 回傳有效 Result")
@pytest.mark.scenario("analysis-specification-contract", "前後端支援相同的 punch_force 規格")
def test_single_strike_is_deterministic_and_contract_valid() -> None:
    first = execute()
    second = execute()
    assert first == second
    assert first["peak_force_n"] > 0
    assert first["peak_force_kgf"] == pytest.approx(first["peak_force_n"] / 9.80665, abs=1e-3)
    assert first["impact_height_from_bottom_m"] == pytest.approx(0.82, abs=0.05)
    assert len(first["curve_points"]) <= 300
    assert first["peak_elapsed_us"] in {point["elapsed_us"] for point in first["curve_points"]}
    spec = next(item for item in builtin_analysis_specifications() if item.analysis_type == "punch_force")
    spec.validate_parameters(parameters())
    spec.validate_result(first)


@pytest.mark.scenario("punch-force-analysis", "user 改變沙袋質量")
def test_mass_parameter_changes_force_without_hidden_default() -> None:
    normal = execute()
    heavier = execute(params=parameters(mass=72.0))
    assert heavier["peak_force_n"] == pytest.approx(normal["peak_force_n"] * 2, rel=1e-5)


@pytest.mark.scenario("punch-force-analysis", "正式資料沒有有效打擊")
def test_no_strike_is_rejected_without_fake_force() -> None:
    with pytest.raises(ContractError) as captured:
        execute(synthetic_pair(strikes=()))
    assert captured.value.code == "no_valid_strike"


@pytest.mark.scenario("punch-force-analysis", "正式資料包含多次打擊")
def test_multiple_strikes_are_rejected() -> None:
    with pytest.raises(ContractError) as captured:
        execute(synthetic_pair(strikes=(2.8, 3.4)))
    assert captured.value.code == "multiple_strikes"


@pytest.mark.scenario("punch-force-analysis", "上下方 CSV 具有共同 Packet")
@pytest.mark.scenario("punch-force-analysis", "原始運算點超過顯示上限")
def test_packet_alignment_and_display_limit_preserve_source_bytes() -> None:
    inputs = synthetic_pair()
    before = dict(inputs)
    frames = align_force_inputs(inputs)
    result = execute(inputs)
    assert len(frames.elapsed_us) > 300
    assert len(result["curve_points"]) == 300
    assert inputs == before


@pytest.mark.scenario("punch-force-analysis", "Serial 批次接收使相鄰 Packet 共用 elapsed_us")
def test_serial_batch_duplicate_elapsed_is_reconstructed_from_packet_index() -> None:
    inputs = synthetic_pair()

    def batch_timestamp(_index: int, row: dict[str, str]) -> None:
        elapsed = int(row["elapsed_us"])
        row["elapsed_us"] = str((elapsed // 5_000) * 5_000)

    inputs = {role: rewrite_csv(data, batch_timestamp) for role, data in inputs.items()}
    frames = align_force_inputs(inputs)
    assert all(second > first for first, second in zip(frames.elapsed_us, frames.elapsed_us[1:]))
    assert frames.sample_rate_hz == pytest.approx(400.0)
    assert execute(inputs)["peak_force_kgf"] > 0


def test_elapsed_without_any_time_span_is_rejected() -> None:
    inputs = synthetic_pair()
    inputs = {
        role: rewrite_csv(data, lambda _index, row: row.update(elapsed_us="1"))
        for role, data in inputs.items()
    }
    with pytest.raises(ContractError) as captured:
        align_force_inputs(inputs)
    assert captured.value.code == "invalid_time_axis"


@pytest.mark.scenario("punch-force-analysis", "少量無線 Packet 遺漏")
def test_small_internal_packet_gap_is_interpolated_and_warned() -> None:
    inputs = synthetic_pair(missing_top={1000, 1001})
    result = execute(inputs)
    assert result["quality_status"] == "warning"
    assert any("插值" in warning for warning in result["warnings"])


@pytest.mark.scenario("punch-force-analysis", "Packet 遺漏過多")
def test_large_or_endpoint_gap_is_rejected() -> None:
    for missing in ({0}, set(range(1000, 1006)), set(range(100, 190))):
        with pytest.raises(ContractError) as captured:
            execute(synthetic_pair(missing_top=missing))
        assert captured.value.code == "packet_alignment_failed"


@pytest.mark.scenario("punch-force-analysis", "取樣率低於可靠分析範圍")
def test_sample_rate_below_one_hundred_hz_is_rejected() -> None:
    with pytest.raises(ContractError) as captured:
        execute(synthetic_pair(sample_rate=80))
    assert captured.value.code == "invalid_sample_rate"


def test_sample_rate_below_recommendation_adds_warning() -> None:
    result = execute(synthetic_pair(sample_rate=125))
    assert any("低於建議" in warning for warning in result["warnings"])


@pytest.mark.scenario("punch-force-analysis", "上下 IMU 的旋轉行為不一致")
def test_gyro_mismatch_is_a_visible_warning() -> None:
    result = execute(synthetic_pair(gyro_mismatch=True))
    assert result["quality_status"] == "warning"
    assert any("旋轉訊號不一致" in warning for warning in result["warnings"])


@pytest.mark.scenario("punch-force-analysis", "打擊位置超出沙袋範圍")
def test_out_of_bag_impact_is_a_visible_warning() -> None:
    result = execute(synthetic_pair(impact_offset_m=1.0))
    assert any("超出沙袋長度" in warning for warning in result["warnings"])


@pytest.mark.scenario("punch-force-analysis", "兩顆 IMU 沒有共同 Packet 時間基準")
def test_invalid_source_descriptors_are_rejected() -> None:
    cases = (
        {"bag_top": descriptor("bag_top", connection="wired", node=None), "bag_bottom": descriptor("bag_bottom")},
        {"bag_top": descriptor("bag_top"), "bag_bottom": descriptor("bag_bottom", port="COM7")},
        {"bag_top": descriptor("bag_top", group=0), "bag_bottom": descriptor("bag_bottom", group=1)},
        {"bag_top": descriptor("bag_top", node=0), "bag_bottom": descriptor("bag_bottom", node=0)},
    )
    for descriptors in cases:
        with pytest.raises(ContractError):
            execute(descriptors=descriptors)


def rewrite_csv(data: bytes, transform) -> bytes:
    source = io.StringIO(data.decode("utf-8"), newline="")
    rows = list(csv.DictReader(source))
    for index, row in enumerate(rows):
        transform(index, row)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=COMMON_IMU_CSV_HEADER, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def test_insufficient_or_unstable_calibration_is_rejected() -> None:
    short = parameters()
    short["calibration_end_elapsed_us"] = 500_000
    with pytest.raises(ContractError) as captured:
        execute(params=short)
    assert captured.value.code == "insufficient_calibration"

    inputs = synthetic_pair()
    inputs["bag_top"] = rewrite_csv(
        inputs["bag_top"],
        lambda index, row: row.update(
            quat_w=0.70710678, quat_x=0.0, quat_y=0.0, quat_z=0.70710678
        ) if 100 <= index < 200 else None,
    )
    with pytest.raises(ContractError) as captured:
        execute(inputs)
    assert captured.value.code == "unstable_calibration"


def test_invalid_quaternion_and_non_finite_sensor_value_are_rejected() -> None:
    invalid_quaternion = synthetic_pair()
    invalid_quaternion["bag_bottom"] = rewrite_csv(
        invalid_quaternion["bag_bottom"],
        lambda index, row: row.update(quat_w=0.0, quat_x=0.0, quat_y=0.0, quat_z=0.0)
        if index == 10 else None,
    )
    with pytest.raises(ContractError) as captured:
        execute(invalid_quaternion)
    assert captured.value.code == "invalid_quaternion"

    non_finite = synthetic_pair()
    non_finite["bag_top"] = rewrite_csv(
        non_finite["bag_top"],
        lambda index, row: row.update(acc_x_g="nan") if index == 10 else None,
    )
    with pytest.raises(ContractError) as captured:
        execute(non_finite)
    assert captured.value.code in {"invalid_sensor_value", "invalid_csv_value"}


def test_packet_streams_without_the_same_boundaries_are_rejected() -> None:
    inputs = synthetic_pair()
    inputs["bag_bottom"] = rewrite_csv(
        inputs["bag_bottom"],
        lambda _index, row: row.update(packet_index=int(row["packet_index"]) + 10_000),
    )
    with pytest.raises(ContractError) as captured:
        execute(inputs)
    assert captured.value.code == "packet_alignment_failed"
