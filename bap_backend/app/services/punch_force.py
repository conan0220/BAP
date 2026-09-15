"""Deterministic two-IMU punching-bag force estimate.

This production service adopts the equations documented by the repository's
``punch_force`` research reference: two rigidly mounted sensors, center
acceleration ``(top + bottom) / 2``, force ``mass * acceleration``, and impact
offset ``inertia * angular_acceleration / force``.  It deliberately does not
import the research CLI, pandas, plotting side effects, batch folders, or
research datasets.  BAP receives one Common IMU CSV per sensor and aligns the
two streams by the Gateway ``packet_index``.
"""

from __future__ import annotations

import csv
import io
import math
import statistics
from dataclasses import dataclass
from typing import Any

from bap_backend.app.services.analysis_registry import AnalysisInputDescriptor
from bap_common.analysis_contracts import ContractError
from bap_common.imu_csv import CommonImuCsvError, inspect_common_imu_csv_bytes


GRAVITY_MPS2 = 9.80665
ALGORITHM_VERSION = "bag_rigid_body_global_max_v1"
ROLE_NAMES = ("bag_top", "bag_bottom")
MAXIMUM_DISPLAY_POINTS = 300


@dataclass(frozen=True, slots=True)
class PunchForceConfig:
    minimum_sample_rate_hz: float = 100.0
    recommended_sample_rate_hz: float = 300.0
    minimum_calibration_seconds: float = 1.5
    maximum_calibration_orientation_degrees: float = 20.0
    maximum_consecutive_gap: int = 5
    maximum_gap_ratio: float = 0.05
    cutoff_hz: float = 200.0
    filter_order: int = 4


CONFIG = PunchForceConfig()


@dataclass(frozen=True, slots=True)
class ForceImuSample:
    packet_index: int
    elapsed_us: int
    acc_g: tuple[float, float, float]
    gyro_dps: tuple[float, float, float]
    quaternion: tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class AlignedForceFrames:
    packet_index: Any
    elapsed_us: Any
    top_acc_g: Any
    bottom_acc_g: Any
    top_gyro_dps: Any
    bottom_gyro_dps: Any
    top_quaternion: Any
    bottom_quaternion: Any
    sample_rate_hz: float
    interpolated_samples: int


def validate_descriptors(descriptors: dict[str, AnalysisInputDescriptor]) -> None:
    if set(descriptors) != set(ROLE_NAMES):
        raise ContractError("missing_input_role", "出拳力量需要沙袋上方與下方兩顆 IMU")
    top, bottom = (descriptors[name] for name in ROLE_NAMES)
    if top.connection_type != "wireless_receiver" or bottom.connection_type != "wireless_receiver":
        raise ContractError("wireless_sources_required", "出拳力量只能使用同一個無線接收器下的兩顆 IMU")
    if top.port != bottom.port or top.group_id is None or top.group_id != bottom.group_id:
        raise ContractError("different_gateway", "沙袋上、下方 IMU 必須連接同一個無線接收器及 Group")
    if top.csv_id == bottom.csv_id or top.node_id is None or top.node_id == bottom.node_id:
        raise ContractError("duplicate_imu_node", "沙袋上、下方必須選擇兩顆不同的 IMU Node")


def _finite_float(row: dict[str, str], column: str, row_number: int) -> float:
    try:
        value = float(row[column])
    except (KeyError, TypeError, ValueError) as error:
        raise ContractError("missing_sensor_value", f"CSV 第 {row_number} 列的 {column} 缺少或無效") from error
    if not math.isfinite(value):
        raise ContractError("invalid_sensor_value", f"CSV 第 {row_number} 列包含非有限 sensor 數值")
    return value


def read_force_imu_csv(data: bytes) -> tuple[ForceImuSample, ...]:
    try:
        inspect_common_imu_csv_bytes(data)
    except CommonImuCsvError as error:
        raise ContractError(error.code, error.message) from error
    try:
        rows = csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline=""))
    except UnicodeDecodeError as error:
        raise ContractError("invalid_csv_encoding", "CSV 必須使用 UTF-8") from error

    parsed: list[ForceImuSample] = []
    seen: dict[int, ForceImuSample] = {}
    previous_packet = -1
    previous_elapsed = -1
    for row_number, row in enumerate(rows, start=2):
        try:
            if row["packet_index"] == "":
                raise ValueError
            packet = int(row["packet_index"])
            elapsed = int(row["elapsed_us"])
        except (KeyError, TypeError, ValueError) as error:
            raise ContractError("missing_sync_key", f"CSV 第 {row_number} 列缺少 packet_index 或 elapsed_us") from error
        sample = ForceImuSample(
            packet_index=packet,
            elapsed_us=elapsed,
            acc_g=tuple(_finite_float(row, name, row_number) for name in ("acc_x_g", "acc_y_g", "acc_z_g")),
            gyro_dps=tuple(_finite_float(row, name, row_number) for name in ("gyro_x_dps", "gyro_y_dps", "gyro_z_dps")),
            quaternion=tuple(_finite_float(row, name, row_number) for name in ("quat_w", "quat_x", "quat_y", "quat_z")),
        )
        old = seen.get(packet)
        if old is not None:
            if old == sample:
                continue
            raise ContractError("conflicting_duplicate_packet", "相同 packet_index 包含不同 IMU 資料")
        if packet < previous_packet or elapsed < previous_elapsed:
            raise ContractError("time_axis_reversed", "IMU packet 或時間發生倒退")
        parsed.append(sample)
        seen[packet] = sample
        previous_packet = packet
        previous_elapsed = elapsed
    if len(parsed) < 3:
        raise ContractError("insufficient_imu_samples", "IMU 資料不足，請重新測量")
    return tuple(parsed)


def _missing_runs(missing_positions: list[int]) -> int:
    if not missing_positions:
        return 0
    longest = current = 1
    for previous, current_value in zip(missing_positions, missing_positions[1:]):
        current = current + 1 if current_value == previous + 1 else 1
        longest = max(longest, current)
    return longest


def _interpolate_sample(before: ForceImuSample, after: ForceImuSample, packet: int, elapsed_us: int) -> ForceImuSample:
    span = after.packet_index - before.packet_index
    if span <= 0:
        raise ContractError("packet_alignment_failed", "兩顆 IMU 資料無法可靠對齊")
    ratio = (packet - before.packet_index) / span

    def values(first: tuple[float, ...], second: tuple[float, ...]) -> tuple[float, ...]:
        return tuple(a + (b - a) * ratio for a, b in zip(first, second, strict=True))

    return ForceImuSample(
        packet_index=packet,
        elapsed_us=elapsed_us,
        acc_g=values(before.acc_g, after.acc_g),
        gyro_dps=values(before.gyro_dps, after.gyro_dps),
        quaternion=values(before.quaternion, after.quaternion),
    )


def _strict_packet_time_axis(packets: list[int], elapsed_values: list[int]) -> list[int]:
    """Return a strict time axis while tolerating host serial-read batching.

    Windows may return several physical Gateway packets in one serial read.  The
    Desktop records those packets with the same host ``elapsed_us`` even though
    their ``packet_index`` values are distinct and ordered.  Preserve an already
    strict axis; otherwise spread the packets deterministically between the
    observed first and last timestamps.  A reversed or zero-span clock remains
    invalid because no reliable sampling interval can be recovered from it.
    """
    if len(packets) != len(elapsed_values) or len(packets) < 2:
        raise ContractError("invalid_time_axis", "同步 IMU 資料的時間不足")
    if any(second < first for first, second in zip(elapsed_values, elapsed_values[1:])):
        raise ContractError("invalid_time_axis", "同步 IMU 資料的時間發生倒退")
    if all(second > first for first, second in zip(elapsed_values, elapsed_values[1:])):
        return elapsed_values

    packet_span = packets[-1] - packets[0]
    elapsed_span = elapsed_values[-1] - elapsed_values[0]
    if packet_span <= 0 or elapsed_span < packet_span:
        raise ContractError("invalid_time_axis", "同步 IMU 資料沒有足夠的時間跨度")
    rebuilt = [
        elapsed_values[0]
        + round((packet - packets[0]) * elapsed_span / packet_span)
        for packet in packets
    ]
    if any(second <= first for first, second in zip(rebuilt, rebuilt[1:])):
        raise ContractError("invalid_time_axis", "同步 IMU 資料無法建立可靠的時間軸")
    return rebuilt


def align_force_inputs(inputs: dict[str, bytes], *, config: PunchForceConfig = CONFIG) -> AlignedForceFrames:
    import numpy as np

    if set(inputs) != set(ROLE_NAMES):
        raise ContractError("missing_input_role", "出拳力量需要沙袋上方與下方兩份 CSV")
    rows = {role: read_force_imu_csv(inputs[role]) for role in ROLE_NAMES}
    indexed = {role: {item.packet_index: item for item in values} for role, values in rows.items()}
    minima = {role: min(values) for role, values in indexed.items()}
    maxima = {role: max(values) for role, values in indexed.items()}
    if len(set(minima.values())) != 1 or len(set(maxima.values())) != 1:
        raise ContractError("packet_alignment_failed", "兩顆 IMU 開頭或結尾缺少共同 Packet，無法可靠對齊")
    packets = sorted(set(indexed[ROLE_NAMES[0]]) | set(indexed[ROLE_NAMES[1]]))
    missing_by_role = {
        role: [index for index, packet in enumerate(packets) if packet not in indexed[role]]
        for role in ROLE_NAMES
    }
    total_missing = sum(len(items) for items in missing_by_role.values())
    for positions in missing_by_role.values():
        if _missing_runs(positions) > config.maximum_consecutive_gap:
            raise ContractError("packet_alignment_failed", "兩顆 IMU 連續遺漏的 Packet 過多")
    if total_missing / max(len(packets) * len(ROLE_NAMES), 1) > config.maximum_gap_ratio:
        raise ContractError("packet_alignment_failed", "兩顆 IMU 遺漏的 Packet 比例過高")

    aligned: dict[str, list[ForceImuSample]] = {role: [] for role in ROLE_NAMES}
    elapsed_values: list[int] = []
    for position, packet in enumerate(packets):
        existing = [indexed[role].get(packet) for role in ROLE_NAMES]
        observed_elapsed = [item.elapsed_us for item in existing if item is not None]
        if not observed_elapsed:
            continue
        if max(observed_elapsed) - min(observed_elapsed) > 5_000:
            raise ContractError("packet_time_mismatch", "相同 Gateway Packet 的裝置時間不一致")
        elapsed = round(statistics.median(observed_elapsed))
        elapsed_values.append(elapsed)
        for role, item in zip(ROLE_NAMES, existing, strict=True):
            if item is None:
                previous = next((indexed[role][candidate] for candidate in reversed(packets[:position]) if candidate in indexed[role]), None)
                following = next((indexed[role][candidate] for candidate in packets[position + 1:] if candidate in indexed[role]), None)
                if previous is None or following is None:
                    raise ContractError("packet_alignment_failed", "兩顆 IMU 開頭或結尾缺少共同 Packet，無法可靠對齊")
                item = _interpolate_sample(previous, following, packet, elapsed)
            aligned[role].append(item)
    elapsed_values = _strict_packet_time_axis(packets, elapsed_values)
    duration = (elapsed_values[-1] - elapsed_values[0]) / 1_000_000.0
    sample_rate = (len(elapsed_values) - 1) / duration if duration > 0 else 0.0
    if sample_rate < config.minimum_sample_rate_hz:
        raise ContractError("invalid_sample_rate", "出拳力量的實際取樣率不足 100 Hz")

    def matrix(role: str, attribute: str, dtype=float):
        return np.asarray([getattr(item, attribute) for item in aligned[role]], dtype=dtype)

    return AlignedForceFrames(
        packet_index=np.asarray(packets, dtype=np.int64),
        elapsed_us=np.asarray(elapsed_values, dtype=np.int64),
        top_acc_g=matrix("bag_top", "acc_g"),
        bottom_acc_g=matrix("bag_bottom", "acc_g"),
        top_gyro_dps=matrix("bag_top", "gyro_dps"),
        bottom_gyro_dps=matrix("bag_bottom", "gyro_dps"),
        top_quaternion=matrix("bag_top", "quaternion"),
        bottom_quaternion=matrix("bag_bottom", "quaternion"),
        sample_rate_hz=sample_rate,
        interpolated_samples=total_missing,
    )


def _normalize_quaternions(quaternion: Any) -> Any:
    import numpy as np

    values = np.asarray(quaternion, dtype=float)
    norms = np.linalg.norm(values, axis=1)
    if not np.isfinite(values).all() or (norms < 1e-6).any():
        raise ContractError("invalid_quaternion", "IMU 姿態資料無法正規化")
    return values / norms[:, None]


def _quaternion_angle_degrees(first: Any, second: Any) -> float:
    import numpy as np

    dot = abs(float(np.dot(first, second)))
    return math.degrees(2.0 * math.acos(min(1.0, max(-1.0, dot))))


def _rotation_matrices(quaternion: Any) -> Any:
    import numpy as np

    w, x, y, z = _normalize_quaternions(quaternion).T
    return np.stack(
        [
            1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y),
            2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x),
            2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y),
        ],
        axis=1,
    ).reshape((-1, 3, 3))


def _lowpass(values: Any, sample_rate_hz: float, *, config: PunchForceConfig) -> Any:
    import numpy as np
    from scipy.signal import butter, sosfiltfilt

    cutoff = min(config.cutoff_hz, 0.45 * sample_rate_hz)
    sos = butter(config.filter_order, cutoff, btype="low", fs=sample_rate_hz, output="sos")
    try:
        filtered = sosfiltfilt(sos, np.asarray(values, dtype=float), axis=0)
    except ValueError as error:
        raise ContractError("insufficient_imu_samples", "IMU 資料不足以完成低通濾波") from error
    if not np.isfinite(filtered).all():
        raise ContractError("non_finite_force", "力量運算產生無效數值，請重新測量")
    return filtered


def _horizontal_acceleration(acc_g: Any, quaternion: Any, calibration_count: int, sample_rate_hz: float, *, config: PunchForceConfig) -> Any:
    import numpy as np

    filtered = _lowpass(np.asarray(acc_g) * GRAVITY_MPS2, sample_rate_hz, config=config)
    rotations = _rotation_matrices(quaternion)
    forward = np.einsum("nij,nj->ni", rotations, filtered)
    inverse = np.einsum("nji,nj->ni", rotations, filtered)

    def horizontal_calibration_energy(values: Any) -> float:
        return float(np.median(np.linalg.norm(values[:calibration_count, :2], axis=1)))

    earth = forward if horizontal_calibration_energy(forward) <= horizontal_calibration_energy(inverse) else inverse
    baseline = np.median(earth[:calibration_count], axis=0)
    linear = earth - baseline
    return linear[:, :2]


def select_display_indices(length: int, peak_index: int, maximum: int = MAXIMUM_DISPLAY_POINTS) -> tuple[int, ...]:
    if length < 2:
        raise ValueError("force curve needs at least two points")
    if length <= maximum:
        return tuple(range(length))
    selected = [(index * (length - 1)) // (maximum - 1) for index in range(maximum)]
    if peak_index not in selected:
        replacement = min(
            range(1, maximum - 1),
            key=lambda position: abs(selected[position] - peak_index),
        )
        selected[replacement] = peak_index
    return tuple(sorted(selected))


def _validated_parameters(parameters: dict[str, Any]) -> tuple[int, int, float, float, float, float]:
    required = (
        "calibration_end_elapsed_us", "measurement_start_elapsed_us", "bag_mass_kg",
        "bag_length_m", "bag_diameter_m", "sensor_distance_m",
    )
    missing = [name for name in required if name not in parameters]
    if missing:
        raise ContractError("missing_parameter", f"缺少出拳力量參數：{', '.join(missing)}")
    if set(parameters) != set(required):
        raise ContractError("unknown_parameter", "出拳力量包含未知的 Analysis Parameter")
    calibration_end = parameters["calibration_end_elapsed_us"]
    measurement_start = parameters["measurement_start_elapsed_us"]
    if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in (calibration_end, measurement_start)):
        raise ContractError("invalid_parameter", "出拳力量的錄製時間邊界無效")
    if calibration_end > measurement_start:
        raise ContractError("invalid_parameter", "校正結束時間不得晚於正式測量開始時間")
    physical = tuple(float(parameters[name]) for name in required[2:])
    if any(not math.isfinite(value) or value <= 0 for value in physical):
        raise ContractError("invalid_parameter", "沙袋參數必須是大於零的有限數值")
    mass, length, diameter, distance = physical
    if distance > length:
        raise ContractError("invalid_parameter", "上下 IMU 間距不得大於沙袋長度")
    return calibration_end, measurement_start, mass, length, diameter, distance


def analyze_force(
    inputs: dict[str, bytes],
    parameters: dict[str, Any],
    input_descriptors: dict[str, AnalysisInputDescriptor],
    *,
    config: PunchForceConfig = CONFIG,
) -> dict[str, Any]:
    import numpy as np

    validate_descriptors(input_descriptors)
    calibration_end, measurement_start, mass, length, diameter, distance = _validated_parameters(parameters)
    frames = align_force_inputs(inputs, config=config)
    calibration_positions = np.flatnonzero(frames.elapsed_us < calibration_end)
    measurement_positions = np.flatnonzero(frames.elapsed_us >= measurement_start)
    if len(calibration_positions) < 3:
        raise ContractError("insufficient_calibration", "靜止校正資料不足，請重新測量")
    calibration_count = int(calibration_positions[-1]) + 1
    calibration_span = (int(frames.elapsed_us[calibration_count - 1]) - int(frames.elapsed_us[0])) / 1_000_000
    if calibration_span < config.minimum_calibration_seconds:
        raise ContractError("insufficient_calibration", "靜止校正時間不足，請重新測量")
    if len(measurement_positions) < 3:
        raise ContractError("insufficient_imu_samples", "正式測量資料不足，請重新測量")
    measurement_index = int(measurement_positions[0])

    for quaternion in (frames.top_quaternion, frames.bottom_quaternion):
        normalized = _normalize_quaternions(quaternion)
        reference = normalized[0]
        maximum_angle = max(
            _quaternion_angle_degrees(reference, item)
            for item in normalized[:calibration_count]
        )
        if maximum_angle > config.maximum_calibration_orientation_degrees:
            raise ContractError("unstable_calibration", "校正期間姿態變動過大，請讓沙袋保持靜止")

    top_horizontal = _horizontal_acceleration(
        frames.top_acc_g, frames.top_quaternion, calibration_count, frames.sample_rate_hz, config=config
    )
    bottom_horizontal = _horizontal_acceleration(
        frames.bottom_acc_g, frames.bottom_quaternion, calibration_count, frames.sample_rate_hz, config=config
    )
    center = 0.5 * (top_horizontal + bottom_horizontal)
    difference = top_horizontal - bottom_horizontal
    angular = np.column_stack((-difference[:, 1], difference[:, 0])) / distance
    force_n = mass * np.linalg.norm(center, axis=1)
    force_kgf = force_n / GRAVITY_MPS2

    formal_force = force_kgf[measurement_index:]
    # Follow punch_force/README.md: the recording contains one intended hit, so
    # the result is the global maximum of the formal measurement force curve.
    # Bag vibration may create other local maxima; they are not treated as
    # additional punches by this algorithm.
    formal_peak = int(np.argmax(formal_force))
    peak_index = measurement_index + formal_peak
    peak_force_n = float(force_n[peak_index])
    if not math.isfinite(peak_force_n) or peak_force_n <= 1e-12:
        raise ContractError("no_valid_strike", "正式測量區間沒有可用的正力量資料，請重新測量")
    center_magnitude = float(np.linalg.norm(center[peak_index]))
    direction = center[peak_index] / max(center_magnitude, 1e-12)
    normal_axis = np.asarray((-direction[1], direction[0]))
    angular_along_normal = float(np.dot(angular[peak_index], normal_axis))
    radius = diameter / 2.0
    inertia = mass * (3.0 * radius * radius + length * length) / 12.0
    offset = inertia * angular_along_normal / peak_force_n
    height = offset + length / 2.0
    if not all(math.isfinite(value) for value in (peak_force_n, center_magnitude, offset, height)):
        raise ContractError("non_finite_force", "力量運算產生無效數值，請重新測量")

    warnings: list[str] = []
    if frames.interpolated_samples:
        warnings.append(f"兩顆 IMU 有 {frames.interpolated_samples} 筆 Packet 缺口，分析時已進行線性插值。")
    if frames.sample_rate_hz < config.recommended_sample_rate_hz:
        warnings.append(f"實際取樣率為 {frames.sample_rate_hz:.1f} Hz，低於建議的 300 Hz，峰值可能被低估。")
    top_gyro_max = float(np.linalg.norm(frames.top_gyro_dps[measurement_index:], axis=1).max())
    bottom_gyro_max = float(np.linalg.norm(frames.bottom_gyro_dps[measurement_index:], axis=1).max())
    gyro_high, gyro_low = max(top_gyro_max, bottom_gyro_max), min(top_gyro_max, bottom_gyro_max)
    if gyro_high > 50.0 and gyro_low < 0.1 * gyro_high:
        warnings.append("沙袋上、下方 IMU 的旋轉訊號不一致，請檢查 IMU 是否固定牢靠及位置是否選對。")
    if height < 0.0 or height > length:
        warnings.append("估算擊中位置超出沙袋長度，這次位置與力量結果可能不可靠。")

    formal_indices = range(measurement_index, len(frames.elapsed_us))
    formal_peak = peak_index - measurement_index
    display_offsets = select_display_indices(len(formal_force), formal_peak)
    curve_points = []
    for offset_index in display_offsets:
        index = measurement_index + offset_index
        curve_points.append(
            {
                "elapsed_us": int(frames.elapsed_us[index]),
                "top_horizontal_acceleration_mps2": round(float(np.linalg.norm(top_horizontal[index])), 6),
                "bottom_horizontal_acceleration_mps2": round(float(np.linalg.norm(bottom_horizontal[index])), 6),
                "angular_acceleration_x_radps2": round(float(angular[index, 0]), 6),
                "angular_acceleration_y_radps2": round(float(angular[index, 1]), 6),
                "force_kgf": round(float(force_kgf[index]), 6),
            }
        )
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "peak_elapsed_us": int(frames.elapsed_us[peak_index]),
        "peak_force_n": round(peak_force_n, 6),
        "peak_force_kgf": round(peak_force_n / GRAVITY_MPS2, 6),
        "peak_com_acceleration_g": round(center_magnitude / GRAVITY_MPS2, 6),
        "impact_height_from_bottom_m": round(height, 6),
        "impact_offset_from_center_m": round(offset, 6),
        "sample_rate_hz": round(frames.sample_rate_hz, 3),
        "quality_status": "warning" if warnings else "valid",
        "warnings": warnings,
        "curve_points": curve_points,
    }


class PunchForceExecutor:
    def execute(
        self,
        *,
        inputs: dict[str, bytes],
        parameters: dict,
        input_descriptors: dict[str, AnalysisInputDescriptor] | None = None,
    ) -> dict:
        if input_descriptors is None:
            raise ContractError("missing_input_descriptor", "出拳力量缺少 IMU 來源資訊")
        return analyze_force(inputs, parameters, input_descriptors)
