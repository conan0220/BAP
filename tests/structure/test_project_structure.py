from pathlib import Path

from click.testing import CliRunner


ROOT = Path(__file__).resolve().parents[2]


def test_expected_project_directories_exist() -> None:
    expected = (
        "anrot_imu_driver",
        "bap_backend",
        "bap_desktop",
        "deployment/windows/backend",
        "migrations",
        "packaging/windows",
        "tests",
    )
    assert all((ROOT / relative).is_dir() for relative in expected)


def test_runtime_packages_import_without_legacy_product_package() -> None:
    import bap_backend
    import bap_desktop

    assert bap_backend.__version__ == "0.1.0"
    assert bap_desktop.APP_NAME == "BAP"


def test_existing_imu_cli_entrypoint_is_preserved() -> None:
    from anrot_imu_driver.main import cli

    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "list" in result.output
    assert "read" in result.output
    assert "record" in result.output
    assert "send" in result.output


def test_windows_product_metadata_uses_bap_name() -> None:
    spec = (ROOT / "packaging/windows/bap-desktop.spec").read_text(encoding="utf-8")
    installer = (ROOT / "packaging/windows/bap-installer.iss").read_text(encoding="utf-8")
    assert 'name="BAP"' in spec
    assert '#define MyAppName "BAP"' in installer
    assert '#define MyAppFullName "Boxing Analysis Platform"' in installer
