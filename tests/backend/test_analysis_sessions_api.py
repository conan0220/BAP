from __future__ import annotations

import io
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from bap_backend.app.core.config import BackendSettings
from bap_backend.app.db.base import Base
from bap_backend.app.db.session import create_database_engine, create_session_factory
from bap_backend.app.main import create_app
from bap_backend.app.models import AnalysisJob, ImuCsvFile, MeasurementSession, User
from bap_backend.app.services.analysis_dispatcher import AnalysisDispatcher
from bap_backend.app.services.analysis_sessions import AnalysisSessionService
from bap_backend.app.services.analysis_registry import AnalysisRegistry
from bap_common.analysis_contracts import builtin_analysis_specifications
from bap_common.analysis_session import (
    AnalysisInputBinding,
    AnalysisJobRequest,
    CsvDescriptor,
    ImuSourceDescriptor,
    SessionMetadata,
    SourceConnectionType,
)
from bap_common.imu_csv import frame_csv_row, inspect_common_imu_csv_bytes, write_header
from anrot_imu_driver.parsers.anrot_serial_parser import AnrotFrame
from sqlalchemy import event, func, select


class ReferencePunchCountExecutor:
    def execute(self, *, inputs: dict[str, bytes], parameters: dict) -> dict:
        assert parameters == {}
        assert set(inputs) == {"left_wrist", "right_wrist"}
        return {"left_punch_count": 2, "right_punch_count": 3, "total_punch_count": 5}


def csv_payload(value: float) -> bytes:
    stream = io.StringIO(newline="")
    writer = write_header(stream)
    frame = AnrotFrame()
    frame.frame_type = 0x91
    frame.system_time_ms = 10
    frame.acc = (value, 2.0, 3.0)
    frame.gyr = (4.0, 5.0, 6.0)
    frame.mag = (7.0, 8.0, 9.0)
    frame.quat = (1.0, 0.0, 0.0, 0.0)
    frame.roll = frame.pitch = frame.yaw = 0.0
    writer.writerow(frame_csv_row(frame, sample_index=0, packet_index=0, elapsed_us=0))
    return stream.getvalue().encode("utf-8")


def build_package() -> tuple[SessionMetadata, dict[str, bytes]]:
    contents = {"left.csv": csv_payload(1.0), "right.csv": csv_payload(2.0)}
    descriptors = []
    for name, data in contents.items():
        inspection = inspect_common_imu_csv_bytes(data)
        descriptors.append(CsvDescriptor(
            csv_id=uuid4(), filename=name,
            source=ImuSourceDescriptor(
                source_id=f"COM1:{name}", port="COM1",
                connection_type=SourceConnectionType.WIRED, baud_rate=921600,
            ),
            row_count=inspection.row_count, size_bytes=inspection.size_bytes,
            sha256=inspection.sha256,
        ))
    job = AnalysisJobRequest(
        analysis_id=uuid4(), analysis_type="punch_count", spec_version=1,
        input_bindings=(
            AnalysisInputBinding(input_role="left_wrist", csv_id=descriptors[0].csv_id),
            AnalysisInputBinding(input_role="right_wrist", csv_id=descriptors[1].csv_id),
        ),
    )
    now = datetime.now(timezone.utc)
    return SessionMetadata(
        session_id=uuid4(), desktop_version="0.1.3", started_at=now, ended_at=now,
        csv_files=tuple(descriptors), analyses=(job,),
    ), contents


def make_context(tmp_path, *, with_executor: bool = True):
    url = f"sqlite:///{(tmp_path / 'analysis.db').as_posix()}"
    settings = BackendSettings(database_url=url, jwt_signing_key="x" * 40, _env_file=None)
    engine = create_database_engine(url)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    registry = AnalysisRegistry(builtin_analysis_specifications())
    if with_executor:
        registry.register_executor("punch_count", 1, ReferencePunchCountExecutor())
    app = create_app(settings=settings, session_factory=factory, analysis_registry=registry)
    return TestClient(app, raise_server_exceptions=False), factory, engine


def authenticated(client: TestClient, username: str = "Boxer01") -> dict[str, str]:
    credentials = {"username": username, "password": "boxing123"}
    assert client.post("/api/v1/auth/register", json=credentials).status_code == 201
    token = client.post("/api/v1/auth/login", json=credentials).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def upload(client, headers, metadata, contents):
    return client.post(
        "/api/v1/measurement-sessions", headers=headers,
        data={"metadata": metadata.canonical_json()},
        files=[("files", (name, data, "text/csv")) for name, data in contents.items()],
    )


import pytest


@pytest.mark.scenario("analysis-session-ingestion", "已登入 user 上傳 Session")
@pytest.mark.scenario("analysis-session-ingestion", "完整提交兩顆 IMU 資料")
@pytest.mark.scenario("analysis-session-ingestion", "CSV 完整性資料相符")
@pytest.mark.scenario("analysis-session-ingestion", "完整保存成功")
@pytest.mark.scenario("analysis-session-ingestion", "Analysis 完成")
@pytest.mark.scenario("analysis-specification-contract", "Executor 回傳有效 Result")
@pytest.mark.scenario("boxing-analysis-session", "Backend 確認完整接收")
def test_full_http_upload_dispatch_and_result(tmp_path):
    client, factory, engine = make_context(tmp_path)
    with client:
        headers = authenticated(client)
        metadata, contents = build_package()
        response = upload(client, headers, metadata, contents)
        assert response.status_code == 202
        result = client.get(
            f"/api/v1/measurement-sessions/{metadata.session_id}/analyses/{metadata.analyses[0].analysis_id}",
            headers=headers,
        )
        assert result.status_code == 200
        assert result.json()["status"] == "completed"
        assert result.json()["result"]["total_punch_count"] == 5
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(ImuCsvFile)) == 2
            assert all(item.csv_blob for item in session.scalars(select(ImuCsvFile)))
    engine.dispose()


@pytest.mark.scenario("analysis-session-ingestion", "網路中斷後重送相同 Session")
@pytest.mark.scenario("analysis-session-ingestion", "user 查詢別人的 Session")
def test_upload_is_idempotent_and_owner_scoped(tmp_path):
    client, _factory, engine = make_context(tmp_path)
    with client:
        first_headers = authenticated(client, "Boxer01")
        second_headers = authenticated(client, "Boxer02")
        metadata, contents = build_package()
        first = upload(client, first_headers, metadata, contents)
        repeated = upload(client, first_headers, metadata, contents)
        assert first.status_code == repeated.status_code == 202
        assert repeated.json()["idempotent"] is True
        assert client.get(f"/api/v1/measurement-sessions/{metadata.session_id}", headers=second_headers).status_code == 404
    engine.dispose()


@pytest.mark.scenario("analysis-session-ingestion", "CSV SHA-256 不符")
def test_invalid_csv_rolls_back_entire_package(tmp_path):
    client, factory, engine = make_context(tmp_path)
    with client:
        headers = authenticated(client)
        metadata, contents = build_package()
        contents["left.csv"] += b"tampered"
        response = upload(client, headers, metadata, contents)
        assert response.status_code == 422
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(MeasurementSession)) == 0
            assert session.scalar(select(func.count()).select_from(ImuCsvFile)) == 0
    engine.dispose()


@pytest.mark.scenario("analysis-specification-contract", "Analysis Type 沒有 Executor")
@pytest.mark.scenario("boxing-analysis-session", "Analysis Executor 尚未提供")
@pytest.mark.scenario("analysis-session-ingestion", "Analysis 失敗")
@pytest.mark.scenario("boxing-analysis-session", "Backend 回報分析失敗")
def test_production_registry_has_no_fake_executor(tmp_path):
    client, _factory, engine = make_context(tmp_path, with_executor=False)
    with client:
        headers = authenticated(client)
        capabilities = client.get("/api/v1/analysis-capabilities", headers=headers).json()
        punch = next(item for item in capabilities["capabilities"] if item["analysis_type"] == "punch_count")
        assert punch["executable"] is False
        metadata, contents = build_package()
        response = upload(client, headers, metadata, contents)
        assert response.status_code == 202
        job = client.get(
            f"/api/v1/measurement-sessions/{metadata.session_id}/analyses/{metadata.analyses[0].analysis_id}",
            headers=headers,
        ).json()
        assert job["status"] == "failed"
        assert job["error_code"] == "executor_unavailable"
        assert job["result"] is None
    engine.dispose()


@pytest.mark.scenario("boxing-analysis-session", "分析失敗但資料已保存")
def test_failed_analysis_can_retry_without_uploading_csv_again(tmp_path):
    client, factory, engine = make_context(tmp_path, with_executor=False)
    with client:
        headers = authenticated(client)
        metadata, contents = build_package()
        upload(client, headers, metadata, contents)
        analysis_id = str(metadata.analyses[0].analysis_id)
        client.app.state.analysis_registry.register_executor(
            "punch_count", 1, ReferencePunchCountExecutor()
        )
        retried = client.post(
            f"/api/v1/measurement-sessions/{metadata.session_id}/analyses/{analysis_id}/retry",
            headers=headers,
        )
        assert retried.status_code == 202
        completed = client.get(
            f"/api/v1/measurement-sessions/{metadata.session_id}/analyses/{analysis_id}",
            headers=headers,
        ).json()
        assert completed["status"] == "completed"
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(ImuCsvFile)) == 2
    engine.dispose()


@pytest.mark.scenario("analysis-session-ingestion", "Analysis 正在執行")
def test_dispatcher_recovers_processing_jobs(tmp_path):
    client, factory, engine = make_context(tmp_path, with_executor=False)
    with client:
        headers = authenticated(client)
        metadata, contents = build_package()
        upload(client, headers, metadata, contents)
        with factory() as session:
            job = session.get(AnalysisJob, str(metadata.analyses[0].analysis_id))
            job.status = "processing"
            session.commit()
        assert AnalysisDispatcher(factory, client.app.state.analysis_registry).recover() == 1
        with factory() as session:
            assert session.get(AnalysisJob, str(metadata.analyses[0].analysis_id)).status == "pending"
    engine.dispose()


@pytest.mark.scenario("analysis-specification-contract", "Executor 回傳錯誤格式")
def test_invalid_executor_result_is_failed_without_fake_result(tmp_path):
    class InvalidExecutor:
        def execute(self, **_kwargs):
            return {"total_punch_count": "not-an-integer"}

    client, factory, engine = make_context(tmp_path, with_executor=False)
    client.app.state.analysis_registry.register_executor("punch_count", 1, InvalidExecutor())
    with client:
        headers = authenticated(client)
        metadata, contents = build_package()
        upload(client, headers, metadata, contents)
        with factory() as session:
            job = session.get(AnalysisJob, str(metadata.analyses[0].analysis_id))
            assert job.status == "failed"
            assert job.result is None
            assert job.error_code in {"missing_result_field", "invalid_result_type"}
    engine.dispose()


@pytest.mark.scenario("analysis-session-ingestion", "保存其中一份 CSV 時失敗")
def test_repository_failure_rolls_back_session_and_all_csv(tmp_path):
    client, factory, engine = make_context(tmp_path)
    with client:
        headers = authenticated(client)
        metadata, contents = build_package()
        inserted = 0

        def fail_second(_mapper, _connection, _target):
            nonlocal inserted
            inserted += 1
            if inserted == 2:
                raise RuntimeError("injected database failure")

        event.listen(ImuCsvFile, "before_insert", fail_second)
        try:
            response = upload(client, headers, metadata, contents)
        finally:
            event.remove(ImuCsvFile, "before_insert", fail_second)
        assert response.status_code == 500
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(MeasurementSession)) == 0
            assert session.scalar(select(func.count()).select_from(ImuCsvFile)) == 0
    engine.dispose()


def test_deleting_owner_cascades_session_csv_jobs_and_results(tmp_path):
    client, factory, engine = make_context(tmp_path)
    with client:
        headers = authenticated(client)
        metadata, contents = build_package()
        upload(client, headers, metadata, contents)
        with factory() as session:
            user = session.scalar(select(User).where(User.username == "Boxer01"))
            session.delete(user)
            session.commit()
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(MeasurementSession)) == 0
            assert session.scalar(select(func.count()).select_from(ImuCsvFile)) == 0
            assert session.scalar(select(func.count()).select_from(AnalysisJob)) == 0
    engine.dispose()


@pytest.mark.scenario("analysis-session-ingestion", "未登入 Client 上傳 Session")
def test_upload_requires_access_token(tmp_path):
    client, _factory, engine = make_context(tmp_path)
    metadata, contents = build_package()
    with client:
        response = upload(client, {}, metadata, contents)
        assert response.status_code == 401
    engine.dispose()


@pytest.mark.scenario("analysis-session-ingestion", "Metadata 引用缺少的 CSV")
@pytest.mark.scenario("analysis-session-ingestion", "Request 包含未宣告 CSV")
def test_uploaded_files_must_exactly_match_metadata(tmp_path):
    client, factory, engine = make_context(tmp_path)
    with client:
        headers = authenticated(client)
        metadata, contents = build_package()
        missing = dict(contents)
        missing.pop("right.csv")
        assert upload(client, headers, metadata, missing).status_code == 422
        extra = {**contents, "extra.csv": csv_payload(3.0)}
        assert upload(client, headers, metadata, extra).status_code == 422
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(MeasurementSession)) == 0
    engine.dispose()


@pytest.mark.scenario("analysis-session-ingestion", "相同 Session ID 的內容不同")
def test_same_session_id_with_different_content_is_rejected(tmp_path):
    client, _factory, engine = make_context(tmp_path)
    with client:
        headers = authenticated(client)
        metadata, contents = build_package()
        assert upload(client, headers, metadata, contents).status_code == 202
        changed = metadata.model_copy(update={"desktop_version": "9.9.9"})
        response = upload(client, headers, changed, contents)
        assert response.status_code == 409
    engine.dispose()


@pytest.mark.scenario("analysis-session-ingestion", "上傳超過設定限制")
def test_file_upload_limit_is_enforced_before_database_write(tmp_path, monkeypatch):
    import bap_backend.app.api.v1.analysis_sessions as routes

    client, factory, engine = make_context(tmp_path)
    with client:
        headers = authenticated(client)
        metadata, contents = build_package()
        monkeypatch.setattr(routes, "MAX_FILE_BYTES", 8)
        response = upload(client, headers, metadata, contents)
        assert response.status_code == 413
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(MeasurementSession)) == 0
    engine.dispose()


@pytest.mark.scenario("boxing-analysis-session", "Backend 接收包含多個 Analyses 的有效 Session")
def test_one_session_tracks_multiple_jobs_that_share_csv(tmp_path):
    client, factory, engine = make_context(tmp_path)
    with client:
        headers = authenticated(client)
        metadata, contents = build_package()
        second = metadata.analyses[0].model_copy(update={"analysis_id": uuid4()})
        metadata = metadata.model_copy(update={"analyses": (*metadata.analyses, second)})
        response = upload(client, headers, metadata, contents)
        assert response.status_code == 202
        assert len(response.json()["analysis_ids"]) == 2
        with factory() as session:
            jobs = list(session.scalars(select(AnalysisJob)))
            assert len(jobs) == 2
            assert {job.status for job in jobs} == {"completed"}
            assert session.scalar(select(func.count()).select_from(ImuCsvFile)) == 2
    engine.dispose()


@pytest.mark.scenario("analysis-session-ingestion", "Session 已保存但尚未分析")
@pytest.mark.scenario("boxing-analysis-session", "Backend 尚未完成分析")
def test_session_status_exposes_pending_without_result(tmp_path):
    client, factory, engine = make_context(tmp_path, with_executor=False)
    with client:
        headers = authenticated(client)
        metadata, contents = build_package()
        # Persist directly so the test can inspect the pre-dispatch state.
        with factory() as session:
            AnalysisSessionService(session, client.app.state.analysis_registry).accept(
                user_id=session.scalar(select(User.id).where(User.username == "Boxer01")),
                metadata_json=metadata.canonical_json(), csv_contents=contents,
            )
        response = client.get(f"/api/v1/measurement-sessions/{metadata.session_id}", headers=headers)
        assert response.json()["status"] == "pending"
        assert response.json()["analyses"][0]["result"] is None
    engine.dispose()
