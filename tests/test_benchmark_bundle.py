from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from bap_common.analysis_session import ImuSourceDescriptor, SourceConnectionType
from bap_common.benchmark_bundle import BenchmarkGroundTruth, BenchmarkInputDescriptor, BenchmarkMetadata, BenchmarkStopReason


def source(source_id: str, *, port: str, node: int | None = None) -> ImuSourceDescriptor:
    return ImuSourceDescriptor(source_id=source_id, port=port, connection_type=(SourceConnectionType.WIRELESS_RECEIVER if node is not None else SourceConnectionType.WIRED), baud_rate=921600, group_id=7 if node is not None else None, node_id=node)


def descriptor(role: str, item_source: ImuSourceDescriptor) -> BenchmarkInputDescriptor:
    csv_id = uuid4()
    return BenchmarkInputDescriptor(input_role=role, csv_id=csv_id, filename=f"imu_{csv_id}.csv", source=item_source, row_count=10, size_bytes=123, sha256="a" * 64)


def valid_payload() -> dict:
    return {
        "session_id": uuid4(), "requested_duration_seconds": 60,
        "actual_duration_seconds": 42.5, "stop_reason": BenchmarkStopReason.ENDED_BY_USER,
        "desktop_version": "0.1.9",
        "inputs": (
            descriptor("left_wrist", source("COM3:group-7:node-1", port="COM3", node=1)),
            descriptor("right_wrist", source("COM3:group-7:node-2", port="COM3", node=2)),
        ),
        "ground_truth": BenchmarkGroundTruth.from_counts(4, 5),
        "notes": "人工確認為 Shadow boxing",
    }


@pytest.mark.scenario("benchmark-data-recorder", "Ground Truth 有效")
def test_metadata_accepts_fixed_contract_and_computes_total() -> None:
    metadata = BenchmarkMetadata(**valid_payload())
    assert metadata.analysis_type == "punch_count"
    assert metadata.activity_type == "shadow_boxing"
    assert metadata.ground_truth.total_punch_count == 9
    assert {item.input_role for item in metadata.inputs} == {"left_wrist", "right_wrist"}


def test_metadata_accepts_source_interrupted_stop_reason() -> None:
    payload = valid_payload()
    payload["stop_reason"] = BenchmarkStopReason.SOURCE_INTERRUPTED
    metadata = BenchmarkMetadata(**payload)
    assert metadata.stop_reason is BenchmarkStopReason.SOURCE_INTERRUPTED


@pytest.mark.parametrize("left,right", [(-1, 0), (0, -1), (1.5, 0), ("x", 0)])
def test_ground_truth_rejects_invalid_counts(left, right) -> None:
    with pytest.raises((ValidationError, ValueError)):
        BenchmarkGroundTruth.from_counts(left, right)


def test_ground_truth_rejects_wrong_total_and_unknown_field() -> None:
    with pytest.raises(ValidationError):
        BenchmarkGroundTruth(left_punch_count=1, right_punch_count=2, total_punch_count=4)
    with pytest.raises(ValidationError):
        BenchmarkGroundTruth(left_punch_count=1, right_punch_count=2, total_punch_count=3, password="secret")


@pytest.mark.parametrize("field,value", [("analysis_type", "punch_speed"), ("activity_type", "heavy_bag"), ("benchmark_schema_version", 2), ("imu_csv_schema_version", 2)])
def test_metadata_rejects_non_v1_fixed_values(field: str, value) -> None:
    payload = valid_payload(); payload[field] = value
    with pytest.raises(ValidationError):
        BenchmarkMetadata(**payload)


def test_metadata_rejects_missing_roles_and_duplicate_sources() -> None:
    payload = valid_payload(); payload["inputs"] = payload["inputs"][:1]
    with pytest.raises(ValidationError):
        BenchmarkMetadata(**payload)
    payload = valid_payload()
    payload["inputs"] = (descriptor("left_wrist", source("COM1:wired", port="COM1")), descriptor("right_wrist", source("COM1:wired", port="COM1")))
    with pytest.raises(ValidationError):
        BenchmarkMetadata(**payload)


def test_metadata_forbids_private_identity_fields_and_absolute_paths() -> None:
    for private_field in ("username", "password", "access_token", "refresh_token", "computer_name"):
        payload = valid_payload(); payload[private_field] = "must-not-be-stored"
        with pytest.raises(ValidationError):
            BenchmarkMetadata(**payload)
    with pytest.raises(ValidationError):
        BenchmarkInputDescriptor(input_role="left_wrist", csv_id=uuid4(), filename=r"C:\Users\person\imu.csv", source=source("COM1:wired", port="COM1"), row_count=1, size_bytes=1, sha256="a" * 64)
