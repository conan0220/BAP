from __future__ import annotations

import httpx
import pytest
import io
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from bap_common.analysis_contracts import ContractError, builtin_analysis_specifications
from bap_desktop.api_client import (
    AnalysisApiClient,
    ApiRejectedError,
    AuthenticatedAnalysisClient,
)
from bap_desktop.services.analysis_flow import AnalysisFlowService
from bap_desktop.services.analysis_flow import LocalSessionDataError
from bap_common.analysis_session import (
    AnalysisInputBinding, AnalysisJobRequest, CsvDescriptor, ImuSourceDescriptor,
    SessionMetadata, SourceConnectionType,
)
from bap_common.imu_csv import COMMON_IMU_CSV_HEADER, inspect_common_imu_csv_bytes
import csv


class SessionStub:
    def __init__(self):
        self.token = "old"
        self.refreshes = 0

    def ensure_access_token(self):
        return self.token

    def refresh_access_token(self):
        self.refreshes += 1
        self.token = "new"
        return True


def test_authenticated_analysis_client_refreshes_once_after_401():
    calls = []

    def handler(request: httpx.Request):
        calls.append(request.headers["authorization"])
        if request.headers["authorization"] == "Bearer old":
            return httpx.Response(401, json={"error": {"message": "expired"}})
        spec = builtin_analysis_specifications()[0].model_dump(mode="json")
        return httpx.Response(200, json={"capabilities": [{**spec, "executable": True}], "upload_limits": {}})

    session = SessionStub()
    api = AnalysisApiClient(
        "http://test/api/", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    result = AuthenticatedAnalysisClient(api, session).call("capabilities")
    assert result[0].executable is True
    assert session.refreshes == 1
    assert calls == ["Bearer old", "Bearer new"]


def test_result_presenter_rejects_invalid_completed_payload():
    spec = builtin_analysis_specifications()[0]

    class AuthClient:
        def call(self, operation, *args):
            assert operation == "capabilities"
            from bap_desktop.api_client.analysis import AnalysisCapability
            return (AnalysisCapability(spec, True),)

    flow = AnalysisFlowService(AuthClient())
    flow.refresh_capabilities()
    with pytest.raises(ContractError, match="left_punch_count"):
        flow.validate_completed({
            "session_id": "s1", "analysis_id": "a1", "analysis_type": "punch_count",
            "spec_version": 1, "status": "completed", "result": {"total_punch_count": 1},
        })


def test_result_presenter_accepts_contract_result():
    spec = builtin_analysis_specifications()[0]

    class AuthClient:
        def call(self, operation, *args):
            from bap_desktop.api_client.analysis import AnalysisCapability
            return (AnalysisCapability(spec, True),)

    flow = AnalysisFlowService(AuthClient())
    flow.refresh_capabilities()
    result = flow.validate_completed({
        "session_id": "s1", "analysis_id": "a1", "analysis_type": "punch_count",
        "spec_version": 1, "status": "completed",
        "result": {"left_punch_count": 2, "right_punch_count": 3, "total_punch_count": 5},
    })
    assert result.result["total_punch_count"] == 5


@pytest.mark.scenario("analysis-specification-contract", "前後端規格版本不一致")
def test_desktop_rejects_backend_contract_that_differs_from_local_spec():
    from bap_desktop.api_client.analysis import AnalysisCapability
    local = builtin_analysis_specifications()[0]
    changed = local.model_copy(update={"display_name": "different contract"})

    class AuthClient:
        def call(self, operation, *args):
            return (AnalysisCapability(changed, True),)

    flow = AnalysisFlowService(AuthClient())
    assert flow.refresh_capabilities() == ()
    assert flow.capability("punch_count", 1) is None


@pytest.mark.scenario("desktop-ui-design", "本機 CSV 已損壞")
def test_upload_validates_local_csv_before_network(tmp_path: Path):
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(COMMON_IMU_CSV_HEADER)
    writer.writerow([0, "", 0, "", "0x91", *([""] * 18)])
    data = output.getvalue().encode()
    inspection = inspect_common_imu_csv_bytes(data)
    csv_id = uuid4()
    descriptor = CsvDescriptor(
        csv_id=csv_id, filename="imu.csv",
        source=ImuSourceDescriptor(
            source_id="COM1:wired", port="COM1",
            connection_type=SourceConnectionType.WIRED, baud_rate=921600,
        ),
        row_count=inspection.row_count, size_bytes=inspection.size_bytes, sha256=inspection.sha256,
    )
    job = AnalysisJobRequest(
        analysis_id=uuid4(), analysis_type="punch_count", spec_version=1,
        input_bindings=(AnalysisInputBinding(input_role="left_wrist", csv_id=csv_id),),
    )
    now = datetime.now(timezone.utc)
    metadata = SessionMetadata(
        session_id=uuid4(), desktop_version="0.1.3", started_at=now, ended_at=now,
        csv_files=(descriptor,), analyses=(job,),
    )
    (tmp_path / "imu.csv").write_bytes(data + b"tampered")

    class NeverNetwork:
        def call(self, *_args):
            raise AssertionError("corrupt local data must not be uploaded")

    flow = AnalysisFlowService(NeverNetwork())
    with pytest.raises(LocalSessionDataError):
        flow.upload(SimpleNamespace(metadata=metadata, directory=tmp_path))
