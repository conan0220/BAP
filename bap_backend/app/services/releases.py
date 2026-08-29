"""Release selection according to semantic version."""

from packaging.version import InvalidVersion, Version
from sqlalchemy.orm import Session

from bap_backend.app.models import AppRelease
from bap_backend.app.repositories import ReleaseRepository


class ReleaseService:
    def __init__(self, session: Session) -> None:
        self.repository = ReleaseRepository(session)

    def latest(self, platform: str) -> AppRelease | None:
        candidates: list[tuple[Version, AppRelease]] = []
        for release in self.repository.list_active(platform):
            try:
                candidates.append((Version(release.version), release))
            except InvalidVersion:
                continue
        return max(candidates, key=lambda item: item[0])[1] if candidates else None
