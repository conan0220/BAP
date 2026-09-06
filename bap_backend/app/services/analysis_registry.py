"""Analysis contracts and explicitly injected executors."""

from __future__ import annotations

from typing import Protocol

from bap_common.analysis_contracts import AnalysisSpecification, ContractError


class AnalysisExecutor(Protocol):
    def execute(self, *, inputs: dict[str, bytes], parameters: dict) -> dict: ...


class AnalysisRegistry:
    def __init__(self, specifications=()) -> None:
        self._specifications: dict[tuple[str, int], AnalysisSpecification] = {
            (item.analysis_type, item.spec_version): item for item in specifications
        }
        self._executors: dict[tuple[str, int], AnalysisExecutor] = {}

    def register_specification(self, specification: AnalysisSpecification) -> None:
        self._specifications[(specification.analysis_type, specification.spec_version)] = specification

    def register_executor(self, analysis_type: str, spec_version: int, executor: AnalysisExecutor) -> None:
        key = (analysis_type, spec_version)
        if key not in self._specifications:
            raise ContractError("unknown_analysis_spec", "必須先註冊 Analysis Specification")
        self._executors[key] = executor

    def specification(self, analysis_type: str, spec_version: int) -> AnalysisSpecification:
        try:
            return self._specifications[(analysis_type, spec_version)]
        except KeyError as error:
            raise ContractError(
                "unknown_analysis_spec",
                f"不支援 Analysis Type {analysis_type} version {spec_version}",
            ) from error

    def executor(self, analysis_type: str, spec_version: int) -> AnalysisExecutor | None:
        return self._executors.get((analysis_type, spec_version))

    def capabilities(self) -> list[dict]:
        return [
            {**spec.model_dump(mode="json"), "executable": key in self._executors}
            for key, spec in sorted(self._specifications.items())
        ]
