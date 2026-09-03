"""Typed HTTPS client for Desktop App release information."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin

import httpx

from bap_desktop.api_client.auth import ApiRejectedError, ApiUnavailableError


@dataclass(frozen=True, slots=True)
class ReleaseData:
    platform: str
    version: str
    download_url: str
    sha256: str
    source_tree_sha: str
    published_at: datetime


class ReleaseApiClient:
    def __init__(self, base_url: str, *, client: httpx.Client | None = None) -> None:
        self.base_url = base_url if base_url.endswith("/") else base_url + "/"
        self.client = client or httpx.Client(timeout=10.0)

    def latest(self, platform: str) -> ReleaseData:
        try:
            response = self.client.get(
                urljoin(self.base_url, "v1/releases/latest"),
                params={"platform": platform},
            )
        except httpx.HTTPError as error:
            raise ApiUnavailableError("目前無法取得更新資訊") from error
        if response.is_error:
            raise ApiRejectedError("目前沒有可用的更新資訊", response.status_code)
        try:
            payload = response.json()
            payload["published_at"] = datetime.fromisoformat(payload["published_at"].replace("Z", "+00:00"))
            return ReleaseData(**payload)
        except (KeyError, TypeError, ValueError) as error:
            raise ApiRejectedError("更新資訊格式不正確", response.status_code) from error
