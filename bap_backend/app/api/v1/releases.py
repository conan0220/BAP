"""Read-only Desktop App release API."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from bap_backend.app.api.dependencies import get_session
from bap_backend.app.schemas import ReleaseResponse
from bap_backend.app.services import ReleaseService


router = APIRouter(prefix="/releases", tags=["releases"])


@router.get("/latest", response_model=ReleaseResponse)
def latest_release(
    platform: str = Query(min_length=2, max_length=32),
    session: Session = Depends(get_session),
):
    release = ReleaseService(session).latest(platform.lower())
    if release is None:
        raise HTTPException(status_code=404, detail="找不到適用的更新資訊")
    return release
