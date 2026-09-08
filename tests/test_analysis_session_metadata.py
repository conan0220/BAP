from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from bap_common.analysis_session import (
    AnalysisInputBinding,
    AnalysisJobRequest,
    CsvDescriptor,
    ImuSourceDescriptor,
    SessionMetadata,
    SessionStopReason,
    SourceConnectionType,
)


def valid_metadata_payload(*, version: int = 1) -> dict:
    csv_id = uuid4()
    now = datetime.now(timezone.utc)
    payload = {
        "session_id": uuid4(),
        "metadata_schema_version": version,
        "desktop_version": "0.1.10",
        "started_at": now,
        "ended_at": now,
        "csv_files": (
            CsvDescriptor(
                csv_id=csv_id,
                filename="left.csv",
                source=ImuSourceDescriptor(
                    source_id="COM1:wired",
                    port="COM1",
                    connection_type=SourceConnectionType.WIRED,
                    baud_rate=921600,
                ),
                row_count=1,
                size_bytes=10,
                sha256="a" * 64,
            ),
        ),
        "analyses": (
            AnalysisJobRequest(
                analysis_id=uuid4(),
                analysis_type="punch_count",
                spec_version=1,
                input_bindings=(
                    AnalysisInputBinding(input_role="left_wrist", csv_id=csv_id),
                ),
            ),
        ),
    }
    if version == 2:
        payload.update(
            requested_duration_seconds=60,
            actual_duration_seconds=42.5,
            stop_reason=SessionStopReason.ENDED_BY_USER,
        )
    return payload


@pytest.mark.scenario("analysis-session-ingestion", "Desktop 上傳 Metadata version 2")
@pytest.mark.parametrize("reason", tuple(SessionStopReason))
def test_metadata_v2_accepts_all_supported_stop_reasons(reason: SessionStopReason) -> None:
    payload = valid_metadata_payload(version=2)
    payload["stop_reason"] = reason
    metadata = SessionMetadata(**payload)
    assert metadata.stop_reason is reason
    assert metadata.requested_duration_seconds == 60


@pytest.mark.scenario("analysis-session-ingestion", "duration 欄位不符合格式")
@pytest.mark.parametrize(
    "update",
    (
        {"requested_duration_seconds": None},
        {"requested_duration_seconds": 4},
        {"requested_duration_seconds": 3601},
        {"requested_duration_seconds": 5.5},
        {"actual_duration_seconds": 0},
        {"stop_reason": None},
        {"stop_reason": "unknown"},
    ),
)
def test_metadata_v2_rejects_missing_or_invalid_duration_values(update: dict) -> None:
    payload = valid_metadata_payload(version=2)
    payload.update(update)
    with pytest.raises(ValidationError):
        SessionMetadata(**payload)


@pytest.mark.scenario("analysis-session-ingestion", "既有 Metadata version 1 Session")
def test_metadata_v1_remains_readable_without_invented_duration() -> None:
    metadata = SessionMetadata(**valid_metadata_payload(version=1))
    assert metadata.requested_duration_seconds is None
    assert metadata.actual_duration_seconds is None
    assert metadata.stop_reason is None


def test_metadata_v1_rejects_v2_only_fields() -> None:
    payload = valid_metadata_payload(version=1)
    payload.update(
        requested_duration_seconds=60,
        actual_duration_seconds=30.0,
        stop_reason="ended_by_user",
    )
    with pytest.raises(ValidationError):
        SessionMetadata(**payload)
