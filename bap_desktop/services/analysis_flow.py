"""Desktop orchestration for capability checks, upload, polling, and cleanup."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bap_common.analysis_contracts import ContractError, builtin_analysis_specifications
from bap_desktop.api_client.analysis import AnalysisCapability, AuthenticatedAnalysisClient
from bap_desktop.services.analysis_recording import SessionDraft
from bap_common.imu_csv import CommonImuCsvError, inspect_common_imu_csv


class LocalSessionDataError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ValidatedAnalysisResult:
    session_id: str
    analysis_id: str
    analysis_type: str
    result: dict


class AnalysisFlowService:
    def __init__(self, client: AuthenticatedAnalysisClient, *, local_specifications=None) -> None:
        self.client = client
        self._capabilities: dict[tuple[str, int], AnalysisCapability] = {}
        local_specifications = local_specifications or builtin_analysis_specifications()
        self._local_specifications = {
            (item.analysis_type, item.spec_version): item for item in local_specifications
        }

    def refresh_capabilities(self) -> tuple[AnalysisCapability, ...]:
        items = self.client.call("capabilities")
        self._capabilities = {}
        for item in items:
            key = (item.specification.analysis_type, item.specification.spec_version)
            local = self._local_specifications.get(key)
            if local == item.specification:
                self._capabilities[key] = item
        return tuple(self._capabilities.values())

    def capability(self, analysis_type: str, spec_version: int) -> AnalysisCapability | None:
        if not self._capabilities:
            self.refresh_capabilities()
        return self._capabilities.get((analysis_type, spec_version))

    def upload(self, draft: SessionDraft) -> dict:
        if draft.metadata is None:
            raise ValueError("Session 尚未完成")
        for descriptor in draft.metadata.csv_files:
            path = Path(draft.directory) / descriptor.filename
            try:
                inspection = inspect_common_imu_csv(
                    path, schema_version=draft.metadata.imu_csv_schema_version
                )
            except (OSError, CommonImuCsvError) as error:
                raise LocalSessionDataError("本機 CSV 已損壞或遺失，請重新測量") from error
            if (
                inspection.row_count != descriptor.row_count
                or inspection.size_bytes != descriptor.size_bytes
                or inspection.sha256 != descriptor.sha256
            ):
                raise LocalSessionDataError("本機 CSV 已損壞或遭到修改，請重新測量")
        response = self.client.call("upload", draft.directory, draft.metadata)
        draft.mark_uploaded()
        return response

    def poll(self, session_id: str, analysis_id: str) -> dict:
        return self.client.call("analysis_status", session_id, analysis_id)

    def validate_completed(self, payload: dict) -> ValidatedAnalysisResult:
        if payload.get("status") != "completed":
            raise ContractError("analysis_not_completed", "Analysis 尚未完成")
        key = (payload.get("analysis_type"), payload.get("spec_version"))
        capability = self._capabilities.get(key)
        if capability is None:
            raise ContractError("unknown_analysis_spec", "找不到對應的 Analysis Specification")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise ContractError("invalid_result", "Backend Result 格式不正確")
        capability.specification.validate_result(result)
        return ValidatedAnalysisResult(
            session_id=str(payload.get("session_id", "")),
            analysis_id=str(payload["analysis_id"]),
            analysis_type=str(payload["analysis_type"]),
            result=result,
        )

    @staticmethod
    def remove_uploaded_package(draft: SessionDraft) -> None:
        if draft.state.value != "uploaded":
            return
        import shutil

        if Path(draft.directory).exists():
            shutil.rmtree(draft.directory)
        draft.close()
