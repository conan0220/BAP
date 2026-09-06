"""Atomic persistence operations for measurement Sessions."""

from __future__ import annotations

import json

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from bap_common.analysis_session import SessionMetadata
from bap_backend.app.models import (
    AnalysisInputBindingEntity,
    AnalysisJob,
    AnalysisResult,
    ImuCsvFile,
    MeasurementSession,
)


class AnalysisSessionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_idempotent(self, user_id: str, fingerprint: str) -> MeasurementSession | None:
        return self.session.scalar(
            select(MeasurementSession).where(
                MeasurementSession.user_id == user_id,
                MeasurementSession.package_fingerprint == fingerprint,
            )
        )

    def get_owned(self, session_id: str, user_id: str) -> MeasurementSession | None:
        return self.session.scalar(
            select(MeasurementSession)
            .options(
                selectinload(MeasurementSession.csv_files),
                selectinload(MeasurementSession.analysis_jobs).selectinload(AnalysisJob.input_bindings),
                selectinload(MeasurementSession.analysis_jobs).selectinload(AnalysisJob.result),
            )
            .where(MeasurementSession.id == session_id, MeasurementSession.user_id == user_id)
        )

    def create_package(
        self,
        *,
        user_id: str,
        metadata: SessionMetadata,
        csv_contents: dict[str, bytes],
    ) -> MeasurementSession:
        item = MeasurementSession(
            id=str(metadata.session_id),
            user_id=user_id,
            package_fingerprint=metadata.package_fingerprint(),
            status="accepted",
            metadata_schema_version=metadata.metadata_schema_version,
            imu_csv_schema_version=metadata.imu_csv_schema_version,
            desktop_version=metadata.desktop_version,
            started_at=metadata.started_at.replace(tzinfo=None),
            ended_at=metadata.ended_at.replace(tzinfo=None),
        )
        item.csv_files = [
            ImuCsvFile(
                id=str(csv.csv_id), filename=csv.filename, source_id=csv.source.source_id,
                port=csv.source.port, connection_type=csv.source.connection_type.value,
                baud_rate=csv.source.baud_rate, group_id=csv.source.group_id,
                node_id=csv.source.node_id, row_count=csv.row_count,
                size_bytes=csv.size_bytes, sha256=csv.sha256,
                csv_blob=csv_contents[csv.filename],
            )
            for csv in metadata.csv_files
        ]
        item.analysis_jobs = []
        for job in metadata.analyses:
            entity = AnalysisJob(
                id=str(job.analysis_id), analysis_type=job.analysis_type,
                spec_version=job.spec_version,
                parameters_json=json.dumps(job.parameters, ensure_ascii=False, sort_keys=True),
                status="pending",
            )
            entity.input_bindings = [
                AnalysisInputBindingEntity(
                    session_id=str(metadata.session_id), input_role=binding.input_role,
                    csv_id=str(binding.csv_id),
                )
                for binding in job.input_bindings
            ]
            item.analysis_jobs.append(entity)
        self.session.add(item)
        self.session.flush()
        return item

    def pending_jobs(self) -> list[AnalysisJob]:
        return list(self.session.scalars(
            select(AnalysisJob)
            .options(selectinload(AnalysisJob.input_bindings).selectinload(AnalysisInputBindingEntity.csv_file))
            .where(AnalysisJob.status == "pending")
        ))

    def claim(self, job: AnalysisJob, started_at) -> bool:
        result = self.session.execute(
            update(AnalysisJob)
            .where(AnalysisJob.id == job.id, AnalysisJob.status == "pending")
            .values(status="processing", started_at=started_at)
        )
        self.session.commit()
        if result.rowcount != 1:
            return False
        job.status = "processing"
        job.started_at = started_at
        return True

    def recover_processing(self) -> int:
        jobs = list(self.session.scalars(select(AnalysisJob).where(AnalysisJob.status == "processing")))
        for job in jobs:
            job.status = "pending"
            job.started_at = None
        return len(jobs)

    def save_result(self, job: AnalysisJob, result: dict, now) -> None:
        job.result = AnalysisResult(
            analysis_id=job.id,
            result_json=json.dumps(result, ensure_ascii=False, sort_keys=True),
            created_at=now,
        )
        job.status = "completed"
        job.completed_at = now
        job.error_code = None
        job.safe_error_message = None
