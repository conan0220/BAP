"""Validate and atomically accept measurement Session packages."""

from __future__ import annotations

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from bap_common.analysis_contracts import ContractError
from bap_common.analysis_session import SessionMetadata
from bap_common.imu_csv import CommonImuCsvError, inspect_common_imu_csv_bytes
from bap_backend.app.models import MeasurementSession
from bap_backend.app.repositories import AnalysisSessionRepository
from bap_backend.app.services.analysis_registry import AnalysisRegistry
from bap_backend.app.services.errors import ServiceError


def _bad_request(code: str, message: str) -> ServiceError:
    return ServiceError(code, message, 422)


class AnalysisSessionService:
    def __init__(self, session: Session, registry: AnalysisRegistry) -> None:
        self.session = session
        self.registry = registry
        self.repository = AnalysisSessionRepository(session)

    def accept(self, *, user_id: str, metadata_json: str, csv_contents: dict[str, bytes]):
        try:
            metadata = SessionMetadata.model_validate_json(metadata_json)
        except ValidationError as error:
            raise _bad_request("invalid_session_metadata", "Session Metadata 格式不正確") from error
        if metadata.metadata_schema_version != 1:
            raise _bad_request("unsupported_metadata_schema", "不支援的 Metadata schema version")
        if metadata.imu_csv_schema_version != 1:
            raise _bad_request("unsupported_csv_schema", "不支援的 Common IMU CSV schema version")
        expected = {item.filename for item in metadata.csv_files}
        if set(csv_contents) != expected:
            raise _bad_request("csv_file_mismatch", "上傳的 CSV 檔案與 Metadata 不一致")

        available_csv_ids = {str(item.csv_id) for item in metadata.csv_files}
        for descriptor in metadata.csv_files:
            try:
                inspection = inspect_common_imu_csv_bytes(
                    csv_contents[descriptor.filename],
                    schema_version=metadata.imu_csv_schema_version,
                )
            except CommonImuCsvError as error:
                raise _bad_request(error.code, error.message) from error
            if (
                inspection.row_count != descriptor.row_count
                or inspection.size_bytes != descriptor.size_bytes
                or inspection.sha256 != descriptor.sha256
            ):
                raise _bad_request("csv_integrity_mismatch", f"{descriptor.filename} 的完整性資料不一致")

        try:
            for job in metadata.analyses:
                specification = self.registry.specification(job.analysis_type, job.spec_version)
                specification.validate_inputs(job.input_bindings, available_csv_ids)
                specification.validate_parameters(job.parameters)
        except ContractError as error:
            raise _bad_request(error.code, error.message) from error

        fingerprint = metadata.package_fingerprint()
        existing = self.repository.find_idempotent(user_id, fingerprint)
        if existing is not None:
            return existing, True
        conflicting = self.session.get(MeasurementSession, str(metadata.session_id))
        if conflicting is not None:
            raise ServiceError("session_id_conflict", "Session ID 已被使用", 409)
        try:
            item = self.repository.create_package(
                user_id=user_id, metadata=metadata, csv_contents=csv_contents
            )
            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            existing = self.repository.find_idempotent(user_id, fingerprint)
            if existing is not None:
                return existing, True
            raise ServiceError("session_conflict", "Session 無法重複建立", 409) from error
        except BaseException:
            self.session.rollback()
            raise
        return item, False

    def get_owned(self, *, session_id: str, user_id: str):
        item = self.repository.get_owned(session_id, user_id)
        if item is None:
            raise ServiceError("session_not_found", "找不到這個 Session", 404)
        return item

    def get_analysis(self, *, session_id: str, analysis_id: str, user_id: str):
        item = self.get_owned(session_id=session_id, user_id=user_id)
        for job in item.analysis_jobs:
            if job.id == analysis_id:
                return job
        raise ServiceError("analysis_not_found", "找不到這個 Analysis Job", 404)

    def retry(self, *, session_id: str, analysis_id: str, user_id: str):
        job = self.get_analysis(session_id=session_id, analysis_id=analysis_id, user_id=user_id)
        if job.status != "failed":
            raise ServiceError("analysis_not_retryable", "只有失敗的 Analysis Job 可以重試", 409)
        job.status = "pending"
        job.error_code = None
        job.safe_error_message = None
        job.started_at = None
        job.completed_at = None
        self.session.commit()
        return job
