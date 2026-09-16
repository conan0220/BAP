from __future__ import annotations

import json
from datetime import datetime, timezone

import jwt
from uuid import uuid4

import pytest
from sqlalchemy import select

from bap_backend.app.core.security import create_access_token
from bap_backend.app.models import AnalysisJob, ImuCsvFile
from bap_common.analysis_session import (
    AnalysisInputBinding,
    AnalysisJobRequest,
    CsvDescriptor,
    ImuSourceDescriptor,
    SessionMetadata,
    SessionStopReason,
    SourceConnectionType,
)
from bap_common.imu_csv import inspect_common_imu_csv_bytes
from punch_force_helpers import synthetic_force_pair


def package(*, strikes=(3.0,), sample_rate=400, missing_top=frozenset()):
    raw = synthetic_force_pair(
        strikes=strikes, sample_rate=sample_rate, missing_top=missing_top
    )
    contents = {"bag-top.csv": raw["bag_top"], "bag-bottom.csv": raw["bag_bottom"]}
    descriptors = []
    for node_id, (filename, data) in enumerate(contents.items()):
        inspection = inspect_common_imu_csv_bytes(data)
        descriptors.append(CsvDescriptor(
            csv_id=uuid4(), filename=filename,
            source=ImuSourceDescriptor(
                source_id=f"COM6:group-0:node-{node_id}", port="COM6",
                connection_type=SourceConnectionType.WIRELESS_RECEIVER,
                baud_rate=921600, group_id=0, node_id=node_id,
            ),
            row_count=inspection.row_count, size_bytes=inspection.size_bytes,
            sha256=inspection.sha256,
        ))
    job = AnalysisJobRequest(
        analysis_id=uuid4(), analysis_type="punch_force", spec_version=1,
        input_bindings=(
            AnalysisInputBinding(input_role="bag_top", csv_id=descriptors[0].csv_id),
            AnalysisInputBinding(input_role="bag_bottom", csv_id=descriptors[1].csv_id),
        ),
        parameters={
            "calibration_end_elapsed_us": 2_000_000,
            "measurement_start_elapsed_us": 2_200_000,
            "bag_mass_kg": 36.0, "bag_length_m": 1.24,
            "bag_diameter_m": 0.335, "sensor_distance_m": 1.24,
        },
    )
    now = datetime.now(timezone.utc)
    metadata = SessionMetadata(
        session_id=uuid4(), metadata_schema_version=2, desktop_version="0.1.25",
        started_at=now, ended_at=now, requested_duration_seconds=5,
        actual_duration_seconds=4.2, stop_reason=SessionStopReason.ENDED_BY_USER,
        csv_files=tuple(descriptors), analyses=(job,),
    )
    return metadata, contents


def authenticated(client, settings):
    credentials = {"username": "ForceE2E", "password": "boxing123"}
    assert client.post("/api/v1/auth/register", json=credentials).status_code == 201
    frozen_token = client.post("/api/v1/auth/login", json=credentials).json()["access_token"]
    claims = jwt.decode(frozen_token, options={"verify_signature": False})
    token = create_access_token(
        user_id=claims["sub"], role=claims["role"],
        signing_key=settings.jwt_signing_key, now=datetime.now(timezone.utc),
        expires_minutes=30,
    )
    return {"Authorization": f"Bearer {token}"}


def upload(client, headers, metadata, contents):
    return client.post(
        "/api/v1/measurement-sessions", headers=headers,
        data={"metadata": metadata.canonical_json()},
        files=[("files", (name, data, "text/csv")) for name, data in contents.items()],
    )


@pytest.mark.scenario("punch-force-analysis", "有效資料包含一次打擊")
@pytest.mark.scenario("analysis-specification-contract", "前後端支援相同的 punch_force 規格")
def test_real_punch_force_session_completes_over_http_and_persists(backend_context):
    client, factory, settings, _now = backend_context
    metadata, contents = package()
    originals = {name: inspect_common_imu_csv_bytes(data).sha256 for name, data in contents.items()}
    headers = authenticated(client, settings)
    response = upload(client, headers, metadata, contents)
    assert response.status_code == 202
    endpoint = f"/api/v1/measurement-sessions/{metadata.session_id}/analyses/{metadata.analyses[0].analysis_id}"
    payload = client.get(endpoint, headers=headers).json()
    assert payload["status"] == "completed"
    assert payload["result"]["peak_force_kgf"] > 0
    with factory() as session:
        job = session.get(AnalysisJob, str(metadata.analyses[0].analysis_id))
        assert json.loads(job.parameters_json) == metadata.analyses[0].parameters
        assert json.loads(job.result.result_json) == payload["result"]
        saved = tuple(session.scalars(select(ImuCsvFile)))
        assert {item.filename: inspect_common_imu_csv_bytes(item.csv_blob).sha256 for item in saved} == originals


@pytest.mark.scenario("punch-force-analysis", "正式資料沒有有效打擊")
def test_failed_force_analysis_keeps_csv_and_returns_safe_error(backend_context):
    client, factory, settings, _now = backend_context
    metadata, contents = package(strikes=())
    headers = authenticated(client, settings)
    assert upload(client, headers, metadata, contents).status_code == 202
    endpoint = f"/api/v1/measurement-sessions/{metadata.session_id}/analyses/{metadata.analyses[0].analysis_id}"
    payload = client.get(endpoint, headers=headers).json()
    assert payload["status"] == "failed"
    assert payload["error_code"] == "no_valid_strike"
    assert "Traceback" not in payload["safe_error_message"]
    with factory() as session:
        assert len(tuple(session.scalars(select(ImuCsvFile)))) == 2


@pytest.mark.scenario("punch-force-analysis", "正式資料包含多個局部峰值")
def test_multiple_local_peaks_complete_with_global_maximum_over_http(backend_context):
    client, _factory, settings, _now = backend_context
    metadata, contents = package(strikes=(2.8, 3.4))
    headers = authenticated(client, settings)
    assert upload(client, headers, metadata, contents).status_code == 202
    endpoint = f"/api/v1/measurement-sessions/{metadata.session_id}/analyses/{metadata.analyses[0].analysis_id}"
    payload = client.get(endpoint, headers=headers).json()
    assert payload["status"] == "completed"
    assert payload["result"]["algorithm_version"] == "bag_rigid_body_global_max_v1"
    assert payload["result"]["peak_elapsed_us"] == pytest.approx(2_800_000, abs=5_000)


@pytest.mark.parametrize(
    ("case", "expected_code"),
    (
        ("no_strike", "no_valid_strike"),
        ("low_sample_rate", "invalid_sample_rate"),
        ("packet_gap", "packet_alignment_failed"),
        ("different_group", "different_gateway"),
    ),
)
def test_runtime_force_failures_keep_original_csv_for_diagnosis(backend_context, case, expected_code):
    client, factory, settings, _now = backend_context
    if case == "no_strike":
        metadata, contents = package(strikes=())
    elif case == "low_sample_rate":
        metadata, contents = package(sample_rate=80)
    elif case == "packet_gap":
        metadata, contents = package(missing_top=frozenset(range(1000, 1006)))
    else:
        metadata, contents = package()
        second = metadata.csv_files[1]
        second_source = second.source.model_copy(update={"group_id": 1})
        metadata = metadata.model_copy(
            update={"csv_files": (metadata.csv_files[0], second.model_copy(update={"source": second_source}))}
        )

    expected_hashes = {
        item.filename: inspect_common_imu_csv_bytes(contents[item.filename]).sha256
        for item in metadata.csv_files
    }
    headers = authenticated(client, settings)
    assert upload(client, headers, metadata, contents).status_code == 202
    endpoint = f"/api/v1/measurement-sessions/{metadata.session_id}/analyses/{metadata.analyses[0].analysis_id}"
    payload = client.get(endpoint, headers=headers).json()
    assert payload["status"] == "failed"
    assert payload["error_code"] == expected_code
    assert "Traceback" not in payload["safe_error_message"]
    with factory() as session:
        saved = tuple(session.scalars(select(ImuCsvFile)))
        assert {item.filename: inspect_common_imu_csv_bytes(item.csv_blob).sha256 for item in saved} == expected_hashes


def test_contract_and_corrupt_csv_fail_before_partial_database_write(backend_context):
    client, factory, settings, _now = backend_context
    headers = authenticated(client, settings)

    metadata, contents = package()
    parameters = dict(metadata.analyses[0].parameters)
    parameters.pop("bag_mass_kg")
    invalid_job = metadata.analyses[0].model_copy(update={"parameters": parameters})
    invalid_metadata = metadata.model_copy(update={"analyses": (invalid_job,)})
    response = upload(client, headers, invalid_metadata, contents)
    assert response.status_code == 422

    corrupt_metadata, corrupt_contents = package()
    corrupt_contents["bag-top.csv"] = b"not,a,common,imu,csv\n"
    corrupt = corrupt_metadata.csv_files[0].model_copy(
        update={"row_count": 0, "size_bytes": len(corrupt_contents["bag-top.csv"]), "sha256": "0" * 64}
    )
    corrupt_metadata = corrupt_metadata.model_copy(
        update={"csv_files": (corrupt, corrupt_metadata.csv_files[1])}
    )
    response = upload(client, headers, corrupt_metadata, corrupt_contents)
    assert response.status_code == 422

    with factory() as session:
        assert tuple(session.scalars(select(ImuCsvFile))) == ()
        assert tuple(session.scalars(select(AnalysisJob))) == ()
