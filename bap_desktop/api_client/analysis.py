"""HTTP client for Analysis capabilities and measurement Sessions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

import httpx

from bap_common.analysis_contracts import AnalysisSpecification
from bap_common.analysis_session import SessionMetadata
from bap_desktop.api_client.auth import ApiRejectedError, ApiUnavailableError


@dataclass(frozen=True, slots=True)
class AnalysisCapability:
    specification: AnalysisSpecification
    executable: bool


class AnalysisApiClient:
    def __init__(self, base_url: str, *, client: httpx.Client | None = None) -> None:
        self.base_url = base_url if base_url.endswith("/") else base_url + "/"
        self.client = client or httpx.Client(timeout=60.0)

    def _request(self, method: str, path: str, *, access_token: str, **kwargs) -> dict:
        try:
            response = self.client.request(
                method,
                urljoin(self.base_url, path),
                headers={"Authorization": f"Bearer {access_token}"},
                **kwargs,
            )
        except httpx.HTTPError as error:
            raise ApiUnavailableError("目前無法連線到伺服器") from error
        if response.is_error:
            try:
                message = response.json().get("error", {}).get("message")
            except ValueError:
                message = None
            raise ApiRejectedError(message or "伺服器拒絕要求", response.status_code)
        return response.json()

    def capabilities(self, access_token: str) -> tuple[AnalysisCapability, ...]:
        body = self._request("GET", "v1/analysis-capabilities", access_token=access_token)
        result = []
        for raw in body["capabilities"]:
            data = dict(raw)
            executable = bool(data.pop("executable"))
            result.append(AnalysisCapability(AnalysisSpecification.model_validate(data), executable))
        return tuple(result)

    def upload(self, directory: Path, metadata: SessionMetadata, access_token: str) -> dict:
        handles = []
        try:
            files = []
            for descriptor in metadata.csv_files:
                handle = (Path(directory) / descriptor.filename).open("rb")
                handles.append(handle)
                files.append(("files", (descriptor.filename, handle, "text/csv")))
            return self._request(
                "POST", "v1/measurement-sessions", access_token=access_token,
                data={"metadata": metadata.canonical_json()}, files=files,
            )
        finally:
            for handle in handles:
                handle.close()

    def session_status(self, session_id: str, access_token: str) -> dict:
        return self._request("GET", f"v1/measurement-sessions/{session_id}", access_token=access_token)

    def analysis_status(self, session_id: str, analysis_id: str, access_token: str) -> dict:
        return self._request(
            "GET", f"v1/measurement-sessions/{session_id}/analyses/{analysis_id}",
            access_token=access_token,
        )

    def retry_analysis(self, session_id: str, analysis_id: str, access_token: str) -> dict:
        return self._request(
            "POST", f"v1/measurement-sessions/{session_id}/analyses/{analysis_id}/retry",
            access_token=access_token,
        )


class AuthenticatedAnalysisClient:
    """Use SessionService and retry one 401 after refreshing the access token."""

    def __init__(self, api: AnalysisApiClient, session_service) -> None:
        self.api = api
        self.session_service = session_service

    def call(self, operation: str, *args):
        token = self.session_service.ensure_access_token()
        if token is None:
            raise ApiRejectedError("請先登入", 401)
        method = getattr(self.api, operation)
        try:
            return method(*args, token)
        except ApiRejectedError as error:
            if error.status_code != 401 or not self.session_service.refresh_access_token():
                raise
            token = self.session_service.ensure_access_token()
            if token is None:
                raise
            return method(*args, token)
