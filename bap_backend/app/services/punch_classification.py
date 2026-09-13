"""ONNX-based two-mitt punch segmentation and classification."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bap_common.analysis_contracts import ContractError
from bap_common.imu_csv import CommonImuCsvError, inspect_common_imu_csv_bytes


PUNCH_TYPES = (
    "left_hook",
    "left_jab",
    "left_upper",
    "right_hook",
    "right_jab",
    "right_upper",
)
ROLE_NAMES = ("holder_left_pad", "holder_right_pad")
SENSOR_COLUMNS = (
    "acc_x_g", "acc_y_g", "acc_z_g",
    "gyro_x_dps", "gyro_y_dps", "gyro_z_dps",
    "mag_x_ut", "mag_y_ut", "mag_z_ut",
    "roll_deg", "pitch_deg", "yaw_deg",
    "quat_w", "quat_x", "quat_y", "quat_z",
)


@dataclass(frozen=True, slots=True)
class PunchClassificationInputDescriptor:
    csv_id: str
    source_id: str
    port: str
    connection_type: str
    baud_rate: int
    group_id: int | None
    node_id: int | None


@dataclass(frozen=True, slots=True)
class SynchronizedPunchFrames:
    elapsed_us: Any
    by_role: dict[str, Any]
    pair_ratio: float
    sample_rate_hz: float


class PunchClassificationBundleError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class PunchClassificationModelBundle:
    """Validated model assets and lazy ONNX Runtime sessions."""

    def __init__(self, root: Path) -> None:
        try:
            import numpy as np
            import onnxruntime as ort
        except ImportError as error:
            raise PunchClassificationBundleError(
                "Backend 缺少拳種辨識執行環境"
            ) from error

        self.root = Path(root)
        try:
            self.manifest = json.loads((self.root / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise PunchClassificationBundleError("Model Bundle manifest 無法讀取") from error
        if self.manifest.get("bundle_version") != 1:
            raise PunchClassificationBundleError("Model Bundle version 不支援")
        if tuple(self.manifest.get("classifier", {}).get("labels", ())) != PUNCH_TYPES:
            raise PunchClassificationBundleError("Classifier label 順序不正確")
        if self.manifest.get("role_mapping") != {
            "Node1": "holder_left_pad", "Node2": "holder_right_pad"
        }:
            raise PunchClassificationBundleError("Model Bundle 的 Node role mapping 不正確")
        expected_files = dict(self.manifest.get("files", {}))
        required = {
            "segmentation.onnx", "classifier.onnx", "normalization.npz", "reference_outputs.npz"
        }
        if set(expected_files) != required:
            raise PunchClassificationBundleError("Model Bundle 檔案清單不完整")
        for name, expected in expected_files.items():
            path = self.root / name
            if not path.is_file() or _sha256(path) != expected:
                raise PunchClassificationBundleError(f"Model Bundle 檔案驗證失敗：{name}")

        with np.load(self.root / "normalization.npz", allow_pickle=False) as normalization:
            self.segmentation_mean = np.asarray(normalization["segmentation_mean"], dtype=np.float32)
            self.segmentation_std = np.asarray(normalization["segmentation_std"], dtype=np.float32)
            self.classifier_mean = np.asarray(normalization["classifier_mean"], dtype=np.float32)
            self.classifier_std = np.asarray(normalization["classifier_std"], dtype=np.float32)
        if self.segmentation_mean.shape != (1, 32) or self.segmentation_std.shape != (1, 32):
            raise PunchClassificationBundleError("Segmentation normalization shape 不正確")
        if self.classifier_mean.shape != (1, 12) or self.classifier_std.shape != (1, 12):
            raise PunchClassificationBundleError("Classifier normalization shape 不正確")
        if not np.isfinite(self.segmentation_mean).all() or not np.isfinite(self.classifier_mean).all():
            raise PunchClassificationBundleError("Model Bundle normalization 包含無效數值")
        if (self.segmentation_std < 1e-6).any() or (self.classifier_std < 1e-6).any():
            raise PunchClassificationBundleError("Model Bundle normalization standard deviation 無效")

        self.segmentation_session = ort.InferenceSession(
            str(self.root / "segmentation.onnx"), providers=["CPUExecutionProvider"]
        )
        self.classifier_session = ort.InferenceSession(
            str(self.root / "classifier.onnx"), providers=["CPUExecutionProvider"]
        )

    @property
    def algorithm_version(self) -> str:
        return str(self.manifest["algorithm_version"])


def validate_descriptors(
    descriptors: dict[str, PunchClassificationInputDescriptor],
) -> None:
    if set(descriptors) != set(ROLE_NAMES):
        raise ContractError("missing_input_role", "拳種辨識需要持靶人左手與右手拳靶 IMU")
    left, right = (descriptors[role] for role in ROLE_NAMES)
    if left.connection_type != "wireless_receiver" or right.connection_type != "wireless_receiver":
        raise ContractError("wireless_sources_required", "拳種辨識只能使用同一個無線接收器下的兩顆 IMU")
    if left.port != right.port or left.group_id is None or left.group_id != right.group_id:
        raise ContractError("different_gateway", "兩顆拳靶 IMU 必須連接同一個無線接收器及 Group")
    if left.csv_id == right.csv_id or left.node_id is None or left.node_id == right.node_id:
        raise ContractError("duplicate_imu_node", "左右拳靶必須選擇兩顆不同的 IMU Node")


def _read_rows(data: bytes) -> list[dict[str, Any]]:
    try:
        inspect_common_imu_csv_bytes(data)
    except CommonImuCsvError as error:
        raise ContractError(error.code, error.message) from error
    try:
        rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline="")))
    except UnicodeDecodeError as error:
        raise ContractError("invalid_csv_encoding", "CSV 必須使用 UTF-8") from error
    parsed: list[dict[str, Any]] = []
    seen: dict[tuple[int, int], tuple[float, ...]] = {}
    previous_packet = -1
    previous_device = -1
    previous_elapsed = -1
    for row_number, row in enumerate(rows, start=2):
        try:
            if not row["packet_index"] or not row["device_time_ms"]:
                raise ValueError
            packet = int(row["packet_index"])
            device = int(row["device_time_ms"])
            elapsed = int(row["elapsed_us"])
        except (TypeError, ValueError) as error:
            raise ContractError(
                "missing_sync_key", f"CSV 第 {row_number} 列缺少可用的同步識別"
            ) from error
        values: list[float] = []
        for column in SENSOR_COLUMNS:
            try:
                value = float(row[column])
            except (TypeError, ValueError) as error:
                raise ContractError(
                    "missing_sensor_value", f"CSV 第 {row_number} 列的 {column} 缺少或無效"
                ) from error
            if not math.isfinite(value):
                raise ContractError(
                    "invalid_sensor_value", f"CSV 第 {row_number} 列包含非有限 sensor 數值"
                )
            values.append(value)
        key = (packet, device)
        values_tuple = tuple(values)
        previous_values = seen.get(key)
        if previous_values is not None:
            if previous_values == values_tuple:
                # A wireless receiver can occasionally repeat the same packet.
                # Keep the first observation so Node1/Node2 still have one
                # unambiguous row for this synchronization key.
                continue
            raise ContractError(
                "conflicting_duplicate_sync_key",
                "相同的 Gateway packet 與裝置時間包含不同 IMU 資料，請重新測量",
            )
        if packet < previous_packet or device < previous_device or elapsed < previous_elapsed:
            raise ContractError("time_axis_reversed", "IMU packet 或時間發生倒退")
        parsed.append({"key": key, "elapsed_us": elapsed, "values": values})
        seen[key] = values_tuple
        previous_packet, previous_device, previous_elapsed = packet, device, elapsed
    return parsed


def synchronize_inputs(inputs: dict[str, bytes]) -> SynchronizedPunchFrames:
    import numpy as np

    if set(inputs) != set(ROLE_NAMES):
        raise ContractError("missing_input_role", "拳種辨識需要兩份拳靶 IMU CSV")
    rows = {role: _read_rows(inputs[role]) for role in ROLE_NAMES}
    indexed = {role: {row["key"]: row for row in role_rows} for role, role_rows in rows.items()}
    keys = sorted(set(indexed[ROLE_NAMES[0]]) & set(indexed[ROLE_NAMES[1]]))
    pair_ratio = len(keys) / max(len(rows[ROLE_NAMES[0]]), len(rows[ROLE_NAMES[1]]), 1)
    if pair_ratio < 0.95:
        raise ContractError("insufficient_pair_ratio", "左右拳靶 IMU 的共同資料不足，請重新檢查連線並錄製")
    if len(keys) < 384:
        raise ContractError("insufficient_synchronized_frames", "同步 IMU 資料不足，至少需要 384 筆")
    elapsed: list[int] = []
    matrices: dict[str, list[list[float]]] = {role: [] for role in ROLE_NAMES}
    for key in keys:
        left = indexed[ROLE_NAMES[0]][key]
        right = indexed[ROLE_NAMES[1]][key]
        if left["elapsed_us"] != right["elapsed_us"]:
            raise ContractError("conflicting_device_time", "左右拳靶 IMU 的共同 packet 時間不一致")
        elapsed.append(left["elapsed_us"])
        for role in ROLE_NAMES:
            matrices[role].append(indexed[role][key]["values"])
    duration = (elapsed[-1] - elapsed[0]) / 1_000_000.0
    if duration <= 0:
        raise ContractError("invalid_time_axis", "同步 IMU 資料的時間沒有前進")
    sample_rate = (len(elapsed) - 1) / duration
    if not 360.0 <= sample_rate <= 440.0:
        raise ContractError("invalid_sample_rate", "拳種辨識需要約 400 Hz 的同步 IMU 資料")
    return SynchronizedPunchFrames(
        elapsed_us=np.asarray(elapsed, dtype=np.int64),
        by_role={role: np.asarray(values, dtype=np.float32) for role, values in matrices.items()},
        pair_ratio=pair_ratio,
        sample_rate_hz=sample_rate,
    )


def segmentation_matrix(frames: SynchronizedPunchFrames, manifest: dict) -> Any:
    import numpy as np

    mapping = manifest["role_mapping"]
    # Common IMU SENSOR_COLUMNS already matches the final checkpoint's per-node
    # acc, gyro, magnetometer, Euler and quaternion order.
    matrix = np.concatenate(
        [frames.by_role[mapping["Node1"]], frames.by_role[mapping["Node2"]]], axis=1
    ).astype(np.float32)
    if matrix.shape[1] != 32:
        raise ContractError("invalid_model_input", "拳種辨識模型輸入欄位數不正確")
    return matrix


def _softmax(logits: Any) -> Any:
    import numpy as np

    shifted = logits - np.max(logits, axis=-1, keepdims=True)
    values = np.exp(shifted)
    return values / values.sum(axis=-1, keepdims=True)


def segment_punches(matrix: Any, bundle: PunchClassificationModelBundle) -> list[tuple[int, int]]:
    import numpy as np

    config = bundle.manifest["segmentation"]
    window_size = int(config["window_size"])
    stride = int(config["stride"])
    normalized = ((matrix - bundle.segmentation_mean) / bundle.segmentation_std).astype(np.float32)
    last_start = len(normalized) - window_size
    starts = list(range(0, last_start + 1, stride))
    if starts[-1] != last_start:
        starts.append(last_start)
    windows = np.stack([normalized[start:start + window_size] for start in starts])
    logits = bundle.segmentation_session.run(None, {"frames": windows})[0]
    probabilities = _softmax(logits)
    probability_sum = np.zeros((len(normalized), probabilities.shape[-1]), dtype=np.float64)
    counts = np.zeros((len(normalized), 1), dtype=np.float64)
    for index, start in enumerate(starts):
        probability_sum[start:start + window_size] += probabilities[index]
        counts[start:start + window_size] += 1
    positive = (probability_sum / counts).argmax(axis=1) > 0
    segments: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(positive):
        if value and start is None:
            start = index
        if start is not None and (not value or index == len(positive) - 1):
            end = index if value and index == len(positive) - 1 else index - 1
            if end - start + 1 >= int(config["minimum_segment_frames"]):
                segments.append((start, end))
            start = None
    return segments


def _gravity_sensor(quaternions: Any) -> Any:
    import numpy as np

    q = np.asarray(quaternions, dtype=np.float32)
    norm = np.linalg.norm(q, axis=1, keepdims=True)
    norm = np.where(norm < 1e-8, 1.0, norm)
    qw, qx, qy, qz = (q / norm).T
    return np.stack(
        [2 * (qx * qz - qw * qy), 2 * (qw * qx + qy * qz), qw * qw - qx * qx - qy * qy + qz * qz],
        axis=1,
    )


def _resample(values: Any, target_length: int) -> Any:
    import numpy as np

    if len(values) == target_length:
        return values
    old = np.linspace(0.0, 1.0, len(values))
    new = np.linspace(0.0, 1.0, target_length)
    return np.stack([np.interp(new, old, values[:, column]) for column in range(values.shape[1])], axis=1)


def classify_segments(
    frames: SynchronizedPunchFrames,
    segments: list[tuple[int, int]],
    bundle: PunchClassificationModelBundle,
) -> list[dict[str, Any]]:
    import numpy as np

    if not segments:
        return []
    mapping = bundle.manifest["role_mapping"]
    node_values: list[Any] = []
    for node in ("Node1", "Node2"):
        values = frames.by_role[mapping[node]].copy()
        values[:, 0:3] += _gravity_sensor(values[:, 12:16])
        node_values.append(values[:, 0:6])
    classifier_matrix = np.concatenate(node_values, axis=1).astype(np.float32)
    target_length = int(bundle.manifest["classifier"]["sequence_length"])
    inputs = np.stack(
        [_resample(classifier_matrix[start:end + 1], target_length) for start, end in segments]
    ).astype(np.float32)
    inputs = ((inputs - bundle.classifier_mean) / bundle.classifier_std).astype(np.float32)
    logits = bundle.classifier_session.run(None, {"segments": inputs})[0]
    probabilities = _softmax(logits)
    labels = bundle.manifest["classifier"]["labels"]
    punches: list[dict[str, Any]] = []
    for index, ((start, end), row) in enumerate(zip(segments, probabilities, strict=True), start=1):
        label_index = int(row.argmax())
        punches.append(
            {
                "punch_index": index,
                "punch_type": labels[label_index],
                "start_elapsed_us": int(frames.elapsed_us[start]),
                "end_elapsed_us": int(frames.elapsed_us[end]),
                "confidence": float(row[label_index]),
            }
        )
    return punches


class PunchClassificationExecutor:
    def __init__(self, bundle: PunchClassificationModelBundle) -> None:
        self.bundle = bundle

    def execute(
        self,
        *,
        inputs: dict[str, bytes],
        parameters: dict,
        input_descriptors: dict[str, PunchClassificationInputDescriptor] | None = None,
    ) -> dict:
        if parameters:
            raise ContractError("unknown_parameter", "拳種辨識 version 2 不接受額外參數")
        if input_descriptors is None:
            raise ContractError("missing_input_descriptor", "拳種辨識缺少 IMU 來源資訊")
        validate_descriptors(input_descriptors)
        frames = synchronize_inputs(inputs)
        matrix = segmentation_matrix(frames, self.bundle.manifest)
        segments = segment_punches(matrix, self.bundle)
        punches = classify_segments(frames, segments, self.bundle)
        counts = {punch_type: 0 for punch_type in PUNCH_TYPES}
        for punch in punches:
            counts[punch["punch_type"]] += 1
        return {
            "algorithm_version": self.bundle.algorithm_version,
            "total_punch_count": len(punches),
            "counts_by_type": counts,
            "punches": punches,
        }


def default_model_bundle_path() -> Path:
    return Path(__file__).resolve().parents[1] / "analysis_models" / "punch_classification" / "v1"
