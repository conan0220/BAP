from __future__ import annotations

import csv
import io
from pathlib import Path

import numpy as np
import pytest

from bap_backend.app.main import create_default_analysis_registry
from bap_backend.app.services.punch_classification import (
    PUNCH_TYPES,
    PunchClassificationBundleError,
    PunchClassificationInputDescriptor,
    PunchClassificationModelBundle,
    default_model_bundle_path,
    classify_segments,
    segment_punches,
    segmentation_matrix,
    synchronize_inputs,
    validate_descriptors,
    SynchronizedPunchFrames,
    _gravity_sensor,
    _resample,
)
from bap_common.analysis_contracts import ContractError, builtin_analysis_specifications
from bap_common.imu_csv import COMMON_IMU_CSV_HEADER


def _csv_bytes(
    count: int = 400,
    *,
    start_packet: int = 0,
    drop: set[int] | None = None,
    bad_column: str | None = None,
    sample_period_us: int = 2500,
    duplicate_key_at: int | None = None,
) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=COMMON_IMU_CSV_HEADER, lineterminator="\n")
    writer.writeheader()
    sample_index = 0
    for index in range(count):
        if drop and index in drop:
            continue
        row = {name: "" for name in COMMON_IMU_CSV_HEADER}
        key_index = index - 1 if duplicate_key_at == index else index
        row.update(
            sample_index=sample_index,
            packet_index=start_packet + key_index,
            elapsed_us=index * sample_period_us,
            device_time_ms=10_000 + key_index,
            frame_type="0x91",
            acc_x_g="0.01",
            acc_y_g="0.02",
            acc_z_g="1.0",
            gyro_x_dps="0.1",
            gyro_y_dps="0.2",
            gyro_z_dps="0.3",
            mag_x_ut="1",
            mag_y_ut="2",
            mag_z_ut="3",
            roll_deg="0",
            pitch_deg="0",
            yaw_deg="0",
            quat_w="1",
            quat_x="0",
            quat_y="0",
            quat_z="0",
        )
        if bad_column:
            row[bad_column] = ""
        writer.writerow(row)
        sample_index += 1
    return output.getvalue().encode("utf-8")


def _descriptors(**overrides):
    common = dict(
        source_id="COM6:group-1:node-0",
        port="COM6",
        connection_type="wireless_receiver",
        baud_rate=921600,
        group_id=1,
    )
    left_values = common | {"csv_id": "left-csv", "node_id": 0} | overrides.get("left", {})
    right_values = common | {
        "csv_id": "right-csv", "node_id": 1, "source_id": "COM6:group-1:node-1"
    } | overrides.get("right", {})
    left = PunchClassificationInputDescriptor(**left_values)
    right = PunchClassificationInputDescriptor(**right_values)
    return {"holder_left_pad": left, "holder_right_pad": right}


@pytest.mark.scenario("punch-classification-analysis", "user 分配同一個 Gateway 下的兩顆 IMU")
def test_descriptor_validator_accepts_same_gateway_distinct_nodes():
    validate_descriptors(_descriptors())


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"right": {"port": "COM7"}}, "different_gateway"),
        ({"right": {"group_id": 2}}, "different_gateway"),
        ({"right": {"connection_type": "wired", "group_id": None}}, "wireless_sources_required"),
        ({"right": {"node_id": 0}}, "duplicate_imu_node"),
        ({"right": {"csv_id": "left-csv"}}, "duplicate_imu_node"),
    ],
)
@pytest.mark.scenario("punch-classification-analysis", "user 對左右拳靶選擇同一個 Node")
def test_descriptor_validator_rejects_invalid_pairs(overrides, code):
    with pytest.raises(ContractError) as error:
        validate_descriptors(_descriptors(**overrides))
    assert error.value.code == code


@pytest.mark.scenario("punch-classification-analysis", "左右 CSV 含有足夠同步 Frames")
def test_sync_uses_packet_and_device_time_and_preserves_elapsed_time():
    frames = synchronize_inputs(
        {"holder_left_pad": _csv_bytes(), "holder_right_pad": _csv_bytes()}
    )
    assert len(frames.elapsed_us) == 400
    assert frames.elapsed_us[1] == 2500
    assert frames.pair_ratio == 1.0
    assert frames.sample_rate_hz == pytest.approx(400.0)


def test_sync_rejects_pair_ratio_below_95_percent():
    with pytest.raises(ContractError) as error:
        synchronize_inputs(
            {
                "holder_left_pad": _csv_bytes(),
                "holder_right_pad": _csv_bytes(drop=set(range(30))),
            }
        )
    assert error.value.code == "insufficient_pair_ratio"


def test_sync_accepts_small_packet_loss_and_different_csv_start():
    frames = synchronize_inputs(
        {
            "holder_left_pad": _csv_bytes(410),
            "holder_right_pad": _csv_bytes(410, drop=set(range(10))),
        }
    )
    assert len(frames.elapsed_us) == 400
    assert frames.pair_ratio > 0.95


def test_sync_rejects_less_than_one_model_window():
    with pytest.raises(ContractError) as error:
        synchronize_inputs(
            {"holder_left_pad": _csv_bytes(383), "holder_right_pad": _csv_bytes(383)}
        )
    assert error.value.code == "insufficient_synchronized_frames"


@pytest.mark.scenario("punch-classification-analysis", "必要 sensor 欄位缺少或不是有效數值")
def test_sync_rejects_missing_model_sensor_value():
    with pytest.raises(ContractError) as error:
        synchronize_inputs(
            {
                "holder_left_pad": _csv_bytes(bad_column="quat_w"),
                "holder_right_pad": _csv_bytes(),
            }
        )
    assert error.value.code == "missing_sensor_value"


def test_sync_rejects_low_sample_rate():
    with pytest.raises(ContractError) as error:
        synchronize_inputs(
            {
                "holder_left_pad": _csv_bytes(sample_period_us=5000),
                "holder_right_pad": _csv_bytes(sample_period_us=5000),
            }
        )
    assert error.value.code == "invalid_sample_rate"


def test_sync_rejects_duplicate_gateway_packet_key():
    with pytest.raises(ContractError) as error:
        synchronize_inputs({
            "holder_left_pad": _csv_bytes(duplicate_key_at=100),
            "holder_right_pad": _csv_bytes(),
        })
    assert error.value.code == "duplicate_sync_key"


@pytest.mark.scenario("punch-classification-analysis", "部署轉換後的模型")
def test_onnx_outputs_match_saved_pytorch_reference():
    bundle = PunchClassificationModelBundle(default_model_bundle_path())
    with np.load(bundle.root / "reference_outputs.npz", allow_pickle=False) as reference:
        segmentation = bundle.segmentation_session.run(
            None, {"frames": reference["segmentation_input"]}
        )[0]
        classifier = bundle.classifier_session.run(
            None, {"segments": reference["classifier_input"]}
        )[0]
        np.testing.assert_allclose(segmentation, reference["segmentation_logits"], rtol=1e-4, atol=1e-5)
        np.testing.assert_allclose(classifier, reference["classifier_logits"], rtol=1e-4, atol=1e-5)
        assert np.array_equal(segmentation.argmax(axis=-1), reference["segmentation_labels"])
        assert np.array_equal(classifier.argmax(axis=-1), reference["classifier_labels"])


def test_bundle_loader_rejects_modified_model(tmp_path: Path):
    source = default_model_bundle_path()
    for item in source.iterdir():
        (tmp_path / item.name).write_bytes(item.read_bytes())
    with (tmp_path / "classifier.onnx").open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(PunchClassificationBundleError):
        PunchClassificationModelBundle(tmp_path)


@pytest.mark.scenario("analysis-specification-contract", "Backend 回傳完整拳種辨識 Result")
@pytest.mark.scenario("analysis-specification-contract", "摘要與每拳明細一致")
def test_classification_v2_result_contract_accepts_six_type_summary():
    specification = next(
        item for item in builtin_analysis_specifications()
        if (item.analysis_type, item.spec_version) == ("punch_classification", 2)
    )


@pytest.mark.parametrize(
    "mutation",
    (
        lambda result: result.pop("algorithm_version"),
        lambda result: result.update(summary={}),
        lambda result: result["counts_by_type"].update(unknown=1),
        lambda result: result["punches"][0].update(confidence=1.1),
        lambda result: result["punches"][0].update(punch_index=2),
        lambda result: result["punches"][0].update(end_elapsed_us=50),
        lambda result: result.update(total_punch_count=2),
    ),
)
@pytest.mark.scenario("analysis-specification-contract", "Result 仍使用舊的 summary placeholder")
@pytest.mark.scenario("analysis-specification-contract", "摘要與每拳明細不一致")
@pytest.mark.scenario("analysis-specification-contract", "明細使用未知拳種")
def test_classification_v2_result_contract_rejects_invalid_results(mutation):
    specification = next(
        item for item in builtin_analysis_specifications()
        if (item.analysis_type, item.spec_version) == ("punch_classification", 2)
    )
    result = {
        "algorithm_version": "mitt_tcn_bilstm_lstm_v1",
        "total_punch_count": 1,
        "counts_by_type": {name: int(name == "left_jab") for name in PUNCH_TYPES},
        "punches": [{
            "punch_index": 1,
            "punch_type": "left_jab",
            "start_elapsed_us": 100,
            "end_elapsed_us": 200,
            "confidence": 0.75,
        }],
    }
    mutation(result)
    with pytest.raises(ContractError):
        specification.validate_result(result)
    counts = {name: 0 for name in PUNCH_TYPES}
    counts["left_jab"] = 1
    specification.validate_result(
        {
            "algorithm_version": "mitt_tcn_bilstm_lstm_v1",
            "total_punch_count": 1,
            "counts_by_type": counts,
            "punches": [
                {
                    "punch_index": 1,
                    "punch_type": "left_jab",
                    "start_elapsed_us": 100,
                    "end_elapsed_us": 200,
                    "confidence": 0.75,
                }
            ],
        }
    )


@pytest.mark.scenario("analysis-specification-contract", "舊 Desktop App 只要求 version 1")
def test_default_registry_exposes_executable_version_two_only():
    capabilities = {
        (item["analysis_type"], item["spec_version"]): item
        for item in create_default_analysis_registry().capabilities()
    }
    assert capabilities[("punch_classification", 1)]["executable"] is False
    assert capabilities[("punch_classification", 2)]["executable"] is True


@pytest.mark.scenario("punch-classification-analysis", "相同模型版本重複分析相同輸入")
def test_segmentation_is_deterministic_for_same_input():
    bundle = PunchClassificationModelBundle(default_model_bundle_path())
    matrix = np.tile(np.arange(32, dtype=np.float32), (384, 1)) / 32.0
    assert segment_punches(matrix, bundle) == segment_punches(matrix, bundle)


def test_role_adapter_places_holder_left_in_node1_and_right_in_node2():
    left = np.ones((384, 16), dtype=np.float32)
    right = np.full((384, 16), 2.0, dtype=np.float32)
    frames = SynchronizedPunchFrames(
        elapsed_us=np.arange(384, dtype=np.int64) * 2500,
        by_role={"holder_left_pad": left, "holder_right_pad": right},
        pair_ratio=1.0,
        sample_rate_hz=400.0,
    )
    matrix = segmentation_matrix(
        frames, {"role_mapping": {"Node1": "holder_left_pad", "Node2": "holder_right_pad"}}
    )
    assert np.all(matrix[:, :16] == 1.0)
    assert np.all(matrix[:, 16:] == 2.0)


@pytest.mark.scenario("punch-classification-analysis", "Session 包含多種有效出拳")
def test_classifier_preserves_multiple_segment_order_and_types():
    class Session:
        def run(self, _outputs, inputs):
            count = len(inputs["segments"])
            logits = np.full((count, 6), -5.0, dtype=np.float32)
            logits[0, 1] = 4.0  # left_jab
            logits[1, :] = 0.0
            logits[1, 3] = 0.1  # right_hook, intentionally low confidence
            return [logits]

    class Bundle:
        manifest = {
            "role_mapping": {"Node1": "holder_left_pad", "Node2": "holder_right_pad"},
            "classifier": {"sequence_length": 96, "labels": list(PUNCH_TYPES)},
        }
        classifier_mean = np.zeros((1, 12), dtype=np.float32)
        classifier_std = np.ones((1, 12), dtype=np.float32)
        classifier_session = Session()

    values = np.zeros((384, 16), dtype=np.float32)
    values[:, 12] = 1.0
    frames = SynchronizedPunchFrames(
        elapsed_us=np.arange(384, dtype=np.int64) * 2500,
        by_role={"holder_left_pad": values.copy(), "holder_right_pad": values.copy()},
        pair_ratio=1.0,
        sample_rate_hz=400.0,
    )
    result = classify_segments(frames, [(10, 40), (100, 140)], Bundle())
    assert [item["punch_type"] for item in result] == ["left_jab", "right_hook"]
    assert [item["punch_index"] for item in result] == [1, 2]
    assert result[0]["start_elapsed_us"] == 25_000
    assert result[1]["confidence"] < 0.25


def test_segmentation_drops_short_regions_and_does_not_merge_gaps():
    class Session:
        def run(self, _outputs, inputs):
            batch = len(inputs["frames"])
            logits = np.zeros((batch, 384, 2), dtype=np.float32)
            logits[:, :, 0] = 2.0
            logits[:, 10:29, 1] = 5.0  # 19 frames: drop
            logits[:, 50:70, 1] = 5.0  # 20 frames: keep
            logits[:, 100:110, 1] = 5.0
            logits[:, 111:121, 1] = 5.0  # no legacy gap merge
            return [logits]

    class Bundle:
        manifest = {"segmentation": {
            "window_size": 384, "stride": 128, "minimum_segment_frames": 20
        }}
        segmentation_mean = np.zeros((1, 32), dtype=np.float32)
        segmentation_std = np.ones((1, 32), dtype=np.float32)
        segmentation_session = Session()

    assert segment_punches(np.zeros((384, 32), dtype=np.float32), Bundle()) == [(50, 69)]


def test_classifier_gravity_and_resample_match_handover_rules():
    gravity = _gravity_sensor(np.asarray([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32))
    np.testing.assert_allclose(gravity, [[0.0, 0.0, 1.0]])
    values = np.asarray([[0.0, 0.0], [1.0, 2.0]], dtype=np.float32)
    np.testing.assert_allclose(_resample(values, 3), [[0.0, 0.0], [0.5, 1.0], [1.0, 2.0]])
