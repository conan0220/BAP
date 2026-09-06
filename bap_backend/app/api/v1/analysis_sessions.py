"""Analysis capability, Session upload, status, and retry APIs."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile, status
from sqlalchemy.orm import Session

from bap_backend.app.api.dependencies import get_current_user, get_session
from bap_backend.app.models import User
from bap_backend.app.services.analysis_sessions import AnalysisSessionService
from bap_backend.app.services.errors import ServiceError


MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_PACKAGE_BYTES = 64 * 1024 * 1024
router = APIRouter(tags=["analysis-sessions"])


def _service(request: Request, session: Session) -> AnalysisSessionService:
    return AnalysisSessionService(session, request.app.state.analysis_registry)


def _job_response(job) -> dict:
    return {
        "session_id": job.session_id,
        "analysis_id": job.id,
        "analysis_type": job.analysis_type,
        "spec_version": job.spec_version,
        "status": job.status,
        "error_code": job.error_code,
        "safe_error_message": job.safe_error_message,
        "result": json.loads(job.result.result_json) if job.result is not None else None,
    }


def _session_state(jobs) -> str:
    states = {job.status for job in jobs}
    if states and states == {"completed"}:
        return "completed"
    if "processing" in states:
        return "processing"
    if "pending" in states:
        return "pending"
    if "failed" in states:
        return "failed"
    return "accepted"


@router.get("/analysis-capabilities")
def capabilities(request: Request, _user: User = Depends(get_current_user)):
    return {
        "capabilities": request.app.state.analysis_registry.capabilities(),
        "upload_limits": {
            "max_file_bytes": MAX_FILE_BYTES,
            "max_package_bytes": MAX_PACKAGE_BYTES,
        },
    }


@router.post("/measurement-sessions", status_code=status.HTTP_202_ACCEPTED)
async def upload_session(
    request: Request,
    background_tasks: BackgroundTasks,
    metadata: str = Form(...),
    files: list[UploadFile] = File(...),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    contents: dict[str, bytes] = {}
    total = 0
    staging = Path(tempfile.mkdtemp(prefix="bap-session-upload-"))
    try:
        for upload in files:
            if not upload.filename or Path(upload.filename).name != upload.filename:
                raise ServiceError("invalid_filename", "CSV 檔名格式不正確", 422)
            if upload.filename in contents:
                raise ServiceError("duplicate_filename", "CSV 檔名不得重複", 422)
            target = staging / upload.filename
            size = 0
            with target.open("wb") as output:
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    total += len(chunk)
                    if size > MAX_FILE_BYTES or total > MAX_PACKAGE_BYTES:
                        raise ServiceError("upload_too_large", "Session 上傳內容超過大小限制", 413)
                    output.write(chunk)
            contents[upload.filename] = target.read_bytes()
        item, idempotent = _service(request, session).accept(
            user_id=user.id, metadata_json=metadata, csv_contents=contents
        )
    finally:
        for child in staging.glob("*"):
            child.unlink(missing_ok=True)
        staging.rmdir()
    background_tasks.add_task(request.app.state.analysis_dispatcher.dispatch_pending)
    return {
        "session_id": item.id,
        "status": _session_state(item.analysis_jobs),
        "analysis_ids": [job.id for job in item.analysis_jobs],
        "idempotent": idempotent,
    }


@router.get("/measurement-sessions/{session_id}")
def session_status(
    session_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    item = _service(request, session).get_owned(session_id=session_id, user_id=user.id)
    return {
        "session_id": item.id,
        "status": _session_state(item.analysis_jobs),
        "analyses": [_job_response(job) for job in item.analysis_jobs],
    }


@router.get("/measurement-sessions/{session_id}/analyses/{analysis_id}")
def analysis_status(
    session_id: str,
    analysis_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return _job_response(
        _service(request, session).get_analysis(
            session_id=session_id, analysis_id=analysis_id, user_id=user.id
        )
    )


@router.post(
    "/measurement-sessions/{session_id}/analyses/{analysis_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_analysis(
    session_id: str,
    analysis_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    job = _service(request, session).retry(
        session_id=session_id, analysis_id=analysis_id, user_id=user.id
    )
    background_tasks.add_task(request.app.state.analysis_dispatcher.dispatch_pending)
    return _job_response(job)
