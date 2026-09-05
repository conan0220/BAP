from pathlib import Path

from bap_backend.tools.check_scenario_coverage import missing_scenarios


ROOT = Path(__file__).parents[2]


def test_automated_ci_cd_scenarios_have_pytest_markers() -> None:
    missing = sorted(missing_scenarios(ROOT, "automated-ci-cd"))
    assert not missing, "Missing pytest.mark.scenario links:\n" + "\n".join(
        f"- {capability}: {scenario}" for capability, scenario in missing
    )


def test_redesign_desktop_app_ui_scenarios_have_pytest_markers() -> None:
    change = "redesign-desktop-app-ui"
    changes = ROOT / "openspec" / "changes"
    if not (changes / change).is_dir():
        archived = list((changes / "archive").glob(f"????-??-??-{change}"))
        assert len(archived) == 1, "Expected one archived UI change, not an empty coverage check"
        change = archived[0].relative_to(changes).as_posix()
    assert list((changes / change / "specs").glob("*/spec.md"))
    missing = sorted(missing_scenarios(ROOT, change))
    assert not missing, "Missing pytest.mark.scenario links:\n" + "\n".join(
        f"- {capability}: {scenario}" for capability, scenario in missing
    )
