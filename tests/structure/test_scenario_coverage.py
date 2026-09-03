from pathlib import Path

from bap_backend.tools.check_scenario_coverage import missing_scenarios


ROOT = Path(__file__).parents[2]


def test_automated_ci_cd_scenarios_have_pytest_markers() -> None:
    missing = sorted(missing_scenarios(ROOT, "automated-ci-cd"))
    assert not missing, "Missing pytest.mark.scenario links:\n" + "\n".join(
        f"- {capability}: {scenario}" for capability, scenario in missing
    )
