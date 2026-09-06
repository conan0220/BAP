"""Desktop App release persistence operations."""

from sqlalchemy import select, update
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

    def get(self, platform: str, version: str) -> AppRelease | None:
        return self.session.scalar(
            select(AppRelease).where(
                AppRelease.platform == platform,
                AppRelease.version == version,
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
        current.source_tree_sha = release.source_tree_sha
        current.published_at = release.published_at
        current.is_active = release.is_active
        return current

    def stage(self, release: AppRelease) -> AppRelease:
        """Create or refresh metadata without exposing it to update-check."""

        release.is_active = False
        return self.upsert(release)

    def activate(self, platform: str, version: str) -> AppRelease:
        """Atomically make one staged release the only active platform version."""

        target = self.get(platform, version)
        if target is None:
            raise ValueError("staged Desktop release was not found")
        self.session.execute(
            update(AppRelease)
            .where(AppRelease.platform == platform)
            .values(is_active=False)
        )
        target.is_active = True
        self.session.flush()
        return target
