"""Create or update one Desktop App release after GitHub publishes it."""

from __future__ import annotations

import argparse
import re
from datetime import datetime
from urllib.parse import urlparse

from packaging.version import InvalidVersion, Version

from bap_backend.app.core.config import BackendSettings
from bap_backend.app.db.session import create_database_engine, create_session_factory
from bap_backend.app.models import AppRelease
from bap_backend.app.repositories import ReleaseRepository


_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_TREE_SHA = re.compile(r"^[0-9a-fA-F]{40}$")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="發布 BAP Desktop App 更新資訊")
    parser.add_argument("--platform", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--download-url", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--source-tree-sha", required=True)
    parser.add_argument("--published-at", default=None, help="ISO 8601；預設使用目前 UTC")
    return parser


def validate_release_input(version: str, download_url: str, sha256: str, source_tree_sha: str) -> None:
    try:
        Version(version)
    except InvalidVersion as error:
        raise ValueError("version 必須符合 semantic version") from error
    parsed = urlparse(download_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("download URL 必須是完整 HTTPS URL")
    if _SHA256.fullmatch(sha256) is None:
        raise ValueError("sha256 必須是 64 個十六進位字元")
    if _TREE_SHA.fullmatch(source_tree_sha) is None:
        raise ValueError("source tree sha 必須是 40 個十六進位字元")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        validate_release_input(args.version, args.download_url, args.sha256, args.source_tree_sha)
        published_at = datetime.fromisoformat(args.published_at) if args.published_at else datetime.utcnow()
    except ValueError as error:
        raise SystemExit(str(error)) from error
    settings = BackendSettings()
    factory = create_session_factory(create_database_engine(settings.database_url))
    with factory() as session:
        ReleaseRepository(session).upsert(
            AppRelease(
                platform=args.platform.lower(),
                version=args.version,
                download_url=args.download_url,
                sha256=args.sha256.lower(),
                source_tree_sha=args.source_tree_sha.lower(),
                published_at=published_at,
                is_active=True,
            )
        )
        session.commit()
    print(f"已發布 {args.platform.lower()} {args.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
