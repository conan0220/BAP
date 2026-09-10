from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from bap_common.analysis_contracts import (
    AnalysisSpecification,
    ContractError,
    InputRoleSpecification,
    ResultFieldSpecification,
    ResultValueType,
    builtin_analysis_specifications,
)
from bap_common.analysis_session import (
    AnalysisInputBinding,
    AnalysisJobRequest,
    CsvDescriptor,
    ImuSourceDescriptor,
    SessionMetadata,
    SourceConnectionType,
)
from bap_common.imu_csv import (
    COMMON_IMU_CSV_HEADER,
    CommonImuCsvError,
    inspect_common_imu_csv_bytes,
)


def reference_specification() -> AnalysisSpecification:
    return AnalysisSpecification(
        analysis_type="reference_roundtrip",
        spec_version=1,
        display_name="測試分析",
        input_roles=(
            InputRoleSpecification(name="left_wrist", display_name="左手腕"),
            InputRoleSpecification(name="right_wrist", display_name="右手腕"),
        ),
        result_fields=(
            ResultFieldSpecification(name="total_rows", value_type=ResultValueType.INTEGER),
        ),
    )


def csv_bytes(rows: list[list[object]] | None = None) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(COMMON_IMU_CSV_HEADER)
    for row in rows or [[0, "", 0, "", "0x91", *([""] * 18)]]:
        writer.writerow(row)
    return output.getvalue().encode("utf-8")


def descriptor(csv_id: UUID, *, filename: str, data: bytes) -> CsvDescriptor:
    inspection = inspect_common_imu_csv_bytes(data)
    return CsvDescriptor(
        csv_id=csv_id,
        filename=filename,
        source=ImuSourceDescriptor(
            source_id=f"wired:{filename}",
            port=filename,
            connection_type=SourceConnectionType.WIRED,
            baud_rate=921600,
        ),
        row_count=inspection.row_count,
        size_bytes=inspection.size_bytes,
        sha256=inspection.sha256,
    )


def metadata() -> SessionMetadata:
    first_id, second_id = uuid4(), uuid4()
    data = csv_bytes()
    started = datetime.now(UTC)
    return SessionMetadata(
        session_id=uuid4(),
        desktop_version="0.1.4",
        started_at=started,
        ended_at=started + timedelta(seconds=1),
        csv_files=(
            descriptor(first_id, filename="left.csv", data=data),
            descriptor(second_id, filename="right.csv", data=data),
        ),
        analyses=(
            AnalysisJobRequest(
                analysis_id=uuid4(),
                analysis_type="reference_roundtrip",
                spec_version=1,
                input_bindings=(
                    AnalysisInputBinding(input_role="left_wrist", csv_id=first_id),
                    AnalysisInputBinding(input_role="right_wrist", csv_id=second_id),
                ),
            ),
        ),
    )


@pytest.mark.scenario("analysis-specification-contract", "前後端支援相同規格")
@pytest.mark.scenario("analysis-specification-contract", "出拳次數輸入規格")
@pytest.mark.scenario("analysis-specification-contract", "Session 建立實際輸入對應")
def test_analysis_specification_validates_bindings_and_result() -> None:
    specification = reference_specification()
    left, right = uuid4(), uuid4()
    bindings = (
        AnalysisInputBinding(input_role="left_wrist", csv_id=left),
        AnalysisInputBinding(input_role="right_wrist", csv_id=right),
    )
    specification.validate_inputs(bindings, {str(left), str(right)})
    specification.validate_result({"total_rows": 20})


@pytest.mark.parametrize(
    ("bindings", "code"),
    [
        (lambda left, right: (AnalysisInputBinding(input_role="left_wrist", csv_id=left),), "missing_input_role"),
        (
            lambda left, right: (
                AnalysisInputBinding(input_role="left_wrist", csv_id=left),
                AnalysisInputBinding(input_role="right_wrist", csv_id=left),
            ),
            "duplicate_csv_binding",
        ),
        (
            lambda left, right: (
                AnalysisInputBinding(input_role="left_wrist", csv_id=left),
                AnalysisInputBinding(input_role="right_wrist", csv_id=right),
            ),
            "unknown_csv",
        ),
    ],
)
@pytest.mark.scenario("analysis-specification-contract", "必要 Role 缺少 Binding")
@pytest.mark.scenario("analysis-specification-contract", "Binding 引用其他 Session 的 CSV")
@pytest.mark.scenario("analysis-specification-contract", "左右手綁定同一份 CSV")
def test_analysis_specification_rejects_invalid_bindings(bindings, code: str) -> None:
    left, right = uuid4(), uuid4()
    available = {str(left), str(right)} if code != "unknown_csv" else {str(left)}
    with pytest.raises(ContractError) as captured:
        reference_specification().validate_inputs(bindings(left, right), available)
    assert captured.value.code == code


@pytest.mark.scenario("analysis-specification-contract", "Executor 回傳錯誤格式")
def test_result_contract_rejects_missing_unknown_and_wrong_type() -> None:
    specification = reference_specification()
    for payload, code in [
        ({}, "missing_result_field"),
        ({"total_rows": 2, "extra": True}, "unknown_result_field"),
        ({"total_rows": "2"}, "invalid_result_type"),
    ]:
        with pytest.raises(ContractError) as captured:
            specification.validate_result(payload)
        assert captured.value.code == code


@pytest.mark.scenario("analysis-specification-contract", "同一對左右手 CSV 供兩種分析使用")
def test_session_metadata_is_canonical_and_allows_shared_csv_between_jobs() -> None:
    original = metadata()
    second = original.analyses[0].model_copy(
        update={"analysis_id": uuid4(), "analysis_type": "another_analysis"}
    )
    combined = original.model_copy(update={"analyses": (*original.analyses, second)})
    reparsed = SessionMetadata.model_validate_json(combined.canonical_json())
    assert reparsed == combined
    assert reparsed.package_fingerprint() == combined.package_fingerprint()
    assert reparsed.analyses[0].input_bindings[0].csv_id == reparsed.analyses[1].input_bindings[0].csv_id


def test_session_metadata_rejects_missing_csv_reference_and_bad_source() -> None:
    original = metadata()
    invalid_job = original.analyses[0].model_copy(
        update={"input_bindings": (AnalysisInputBinding(input_role="left_wrist", csv_id=uuid4()),)}
    )
    with pytest.raises(ValidationError):
        SessionMetadata.model_validate({**original.model_dump(), "analyses": [invalid_job]})
    with pytest.raises(ValidationError):
        ImuSourceDescriptor(
            source_id="wireless:3:8",
            port="COM5",
            connection_type=SourceConnectionType.WIRELESS_RECEIVER,
            baud_rate=921600,
        )


@pytest.mark.scenario("common-imu-csv", "產生 version 1 CSV")
@pytest.mark.scenario("common-imu-csv", "裝置沒有提供溫度與氣壓")
@pytest.mark.scenario("common-imu-csv", "Backend 讀取 Desktop App 產生的 CSV")
def test_common_csv_accepts_utf8_and_optional_blank_values() -> None:
    inspection = inspect_common_imu_csv_bytes(csv_bytes())
    assert inspection.row_count == 1
    assert inspection.size_bytes > 0
    assert len(inspection.sha256) == 64


@pytest.mark.scenario("common-imu-csv", "Backend 收到不支援的 schema version")
def test_common_csv_rejects_unknown_schema_header_index_and_reversed_time() -> None:
    valid = csv_bytes()
    with pytest.raises(CommonImuCsvError, match="不支援"):
        inspect_common_imu_csv_bytes(valid, schema_version=2)
    with pytest.raises(CommonImuCsvError, match="header"):
        inspect_common_imu_csv_bytes(valid.replace(b"sample_index", b"sample"))
    rows = [
        [0, "", 10, "", "0x91", *([""] * 18)],
        [1, "", 9, "", "0x91", *([""] * 18)],
    ]
    with pytest.raises(CommonImuCsvError, match="不得倒退"):
        inspect_common_imu_csv_bytes(csv_bytes(rows))
    rows[1][0] = 3
    rows[1][2] = 11
    with pytest.raises(CommonImuCsvError, match="sample_index"):
        inspect_common_imu_csv_bytes(csv_bytes(rows))


def punch_speed_specification(version: int = 2) -> AnalysisSpecification:
    return next(
        item
        for item in builtin_analysis_specifications()
        if item.analysis_type == "punch_speed" and item.spec_version == version
    )


def valid_punch_speed_result() -> dict:
    return {
        "algorithm_version": "rule_v1",
        "left_punch_count": 1,
        "right_punch_count": 1,
        "total_punch_count": 2,
        "left_average_speed_mps": 4.5,
        "left_max_speed_mps": 4.5,
        "right_average_speed_mps": 5.25,
        "right_max_speed_mps": 5.25,
        "punches": [
            {
                "hand": "left",
                "punch_index": 1,
                "start_elapsed_us": 2_100_000,
                "peak_elapsed_us": 2_250_000,
                "end_elapsed_us": 2_500_000,
                "peak_speed_mps": 4.5,
            },
            {
                "hand": "right",
                "punch_index": 1,
                "start_elapsed_us": 2_600_000,
                "peak_elapsed_us": 2_750_000,
                "end_elapsed_us": 3_000_000,
                "peak_speed_mps": 5.25,
            },
        ],
    }


@pytest.mark.scenario("analysis-specification-contract", "Backend 回傳完整拳頭速度 Result")
def test_punch_speed_v2_contract_accepts_complete_result_and_parameter() -> None:
    specification = punch_speed_specification()
    assert specification.display_name == "拳頭速度"
    specification.validate_parameters({"measurement_start_elapsed_us": 2_000_000})
    specification.validate_result(valid_punch_speed_result())


@pytest.mark.scenario("analysis-specification-contract", "Result 仍使用舊的 summary placeholder")
@pytest.mark.parametrize(
    "payload",
    (
        {"summary": {}},
        {**valid_punch_speed_result(), "left_punch_count": 2},
        {
            **valid_punch_speed_result(),
            "punches": [
                {**valid_punch_speed_result()["punches"][0], "hand": "unknown"},
                valid_punch_speed_result()["punches"][1],
            ],
        },
        {
            **valid_punch_speed_result(),
            "punches": [
                {**valid_punch_speed_result()["punches"][0], "peak_speed_mps": float("nan")},
                valid_punch_speed_result()["punches"][1],
            ],
        },
    ),
)
def test_punch_speed_v2_contract_rejects_placeholder_and_invalid_semantics(payload) -> None:
    with pytest.raises(ContractError):
        punch_speed_specification().validate_result(payload)


@pytest.mark.scenario("analysis-specification-contract", "Result 內的摘要與明細不一致")
def test_punch_speed_v2_contract_rejects_inconsistent_summary() -> None:
    payload = valid_punch_speed_result()
    payload["left_average_speed_mps"] = 99.0
    with pytest.raises(ContractError, match="摘要"):
        punch_speed_specification().validate_result(payload)


def test_punch_speed_v2_contract_requires_valid_measurement_boundary() -> None:
    specification = punch_speed_specification()
    for parameters in ({}, {"measurement_start_elapsed_us": 0}, {"measurement_start_elapsed_us": True}):
        with pytest.raises(ContractError):
            specification.validate_parameters(parameters)
