"""Desktop App release persistence operations."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from bap_backend.app.models import AppRelease


class ReleaseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_active(self, platform: str) -> list[AppRelease]:
        return list(
            self.session.scalars(
                select(AppRelease).where(
                    AppRelease.platform == platform,
                    AppRelease.is_active.is_(True),
                )
            )
        )

    def upsert(self, release: AppRelease) -> AppRelease:
        current = self.session.scalar(
            select(AppRelease).where(
                AppRelease.platform == release.platform,
                AppRelease.version == release.version,
            )
        )
        if current is None:
            self.session.add(release)
            self.session.flush()
            return release
        current.download_url = release.download_url
        current.sha256 = release.sha256
        current.published_at = release.published_at
        current.is_active = release.is_active
        return current
