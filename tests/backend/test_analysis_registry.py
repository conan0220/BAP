import pytest

from bap_common.analysis_contracts import ContractError, builtin_analysis_specifications
from bap_backend.app.services.analysis_registry import AnalysisRegistry
from bap_backend.app.main import create_default_analysis_registry


class ReferenceExecutor:
    def execute(self, *, inputs, parameters):
        return {"left_punch_count": 1, "right_punch_count": 1, "total_punch_count": 2}


@pytest.mark.scenario("analysis-specification-contract", "前後端規格版本不一致")
def test_registry_rejects_unknown_specification_version():
    registry = AnalysisRegistry(builtin_analysis_specifications())
    with pytest.raises(ContractError) as captured:
        registry.specification("punch_count", 99)
    assert captured.value.code == "unknown_analysis_spec"


@pytest.mark.scenario("analysis-specification-contract", "測試使用替代 Executor")
@pytest.mark.scenario("boxing-analysis-session", "Analysis Executor 可用")
def test_reference_executor_is_only_available_when_explicitly_injected():
    registry = AnalysisRegistry(builtin_analysis_specifications())
    assert registry.executor("punch_count", 1) is None
    registry.register_executor("punch_count", 1, ReferenceExecutor())
    assert registry.executor("punch_count", 1) is not None


@pytest.mark.scenario("desktop-app-shell", "出拳次數 Executor 可用")
def test_default_production_registry_exposes_real_punch_count_executor():
    registry = create_default_analysis_registry()
    assert registry.executor("punch_count", 1) is not None
    punch = next(
        item for item in registry.capabilities() if item["analysis_type"] == "punch_count"
    )
    assert punch["executable"] is True
