from __future__ import annotations

from pathlib import Path
import sys

import pytest

import bap_desktop
from bap_desktop.app import main
from bap_desktop.services.credential_store import SERVICE_NAME
from bap_desktop.settings import DesktopSettings


ROOT = Path(__file__).parents[2]


def test_desktop_settings_use_localappdata_and_create_only_expected_directories(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    settings = DesktopSettings()
    settings.prepare_local_directories()

    assert settings.data_dir == tmp_path / "BAP"
    assert settings.settings_file == tmp_path / "BAP" / "settings.json"
    assert settings.log_dir.is_dir()
    assert settings.temp_imu_dir.is_dir()
    assert settings.update_dir.is_dir()
    assert SERVICE_NAME == "BAP"
    assert not settings.settings_file.exists()


def test_pyinstaller_spec_collects_qt_platform_plugins_translations_and_resources() -> None:
    spec = (ROOT / "packaging/windows/bap-desktop.spec").read_text(encoding="utf-8")
    assert 'name="BAP"' in spec
    assert 'includes=["resources/**", "VERSION"]' in spec
    assert 'includes=["translations/**"]' in spec
    assert 'search_patterns=["plugins/platforms/*"]' in spec
    assert '"icuuc.dll", "icudt78.dll"' in spec
    assert "console=False" in spec
    assert "COLLECT(" in spec


@pytest.mark.scenario("desktop-app-shell", "user 查看 App 與安裝資訊")
@pytest.mark.scenario("desktop-app-shell", "在支援的 Windows 電腦安裝")
def test_inno_setup_is_per_user_and_removes_only_managed_temporary_csv_area() -> None:
    installer = (ROOT / "packaging/windows/bap-installer.iss").read_text(encoding="utf-8")
    assert 'AppName={#MyAppName}' in installer
    assert 'AppVerName={#MyAppFullName} {#MyAppVersion}' in installer
    assert 'DefaultDirName={localappdata}\\Programs\\BAP' in installer
    assert 'PrivilegesRequired=lowest' in installer
    assert 'Source: "..\\..\\dist\\BAP\\*"' in installer
    assert 'Name: "{localappdata}\\BAP\\temp\\imu-diagnostics"' in installer
    assert "settings.json" not in installer
    assert "Credential Manager" not in installer

    smoke_test = (ROOT / "packaging/windows/Smoke-Test-BapInstaller.ps1").read_text(
        encoding="utf-8"
    )
    assert "WaitForExit($TimeoutSeconds * 1000)" in smoke_test
    assert 'Arguments @("--write-version", $VersionProbe)' in smoke_test
    assert "does not match Installer version" in smoke_test
    assert 'Arguments @("--api-e2e-test")' in smoke_test


def test_desktop_candidate_is_built_in_pr_and_only_promoted_in_cd() -> None:
    guide = (ROOT / "docs/guides/desktop-release.md").read_text(encoding="utf-8")
    pr = (ROOT / ".github/workflows/pull-request-ci.yml").read_text(encoding="utf-8")
    cd = (ROOT / ".github/workflows/continuous-delivery.yml").read_text(encoding="utf-8")
    assert "Code Signing" in guide
    assert "Smoke Test" in guide
    assert "Build-BapDesktop.ps1" in pr
    assert "Smoke-Test-BapInstaller.ps1" in (
        ROOT / "deployment/ci/Test-BapCandidate.ps1"
    ).read_text(encoding="utf-8")
    assert "Build-BapDesktop.ps1" not in cd
    assert "gh release create" in cd


def test_desktop_build_reads_the_single_desktop_version_source() -> None:
    build_script = (ROOT / "packaging/windows/Build-BapDesktop.ps1").read_text(
        encoding="utf-8"
    )
    assert 'Join-Path $RepoRoot "bap_desktop\\VERSION"' in build_script
    assert "pyproject.toml" not in build_script
    assert '__BAP_VERSION__' in build_script
    assert 'bap-installer.iss") -Raw -Encoding UTF8' in build_script


@pytest.mark.scenario("desktop-app-update-check", "Build 與 Runtime 使用相同版本")
def test_desktop_runtime_and_installer_use_only_desktop_version_file() -> None:
    expected = (ROOT / "bap_desktop/VERSION").read_text(encoding="utf-8").strip()
    init_source = (ROOT / "bap_desktop/__init__.py").read_text(encoding="utf-8")
    installer = (ROOT / "packaging/windows/bap-installer.iss").read_text(encoding="utf-8")

    assert bap_desktop.__version__ == expected
    assert '__version__ = "' not in init_source
    assert 'with_name("VERSION")' in init_source
    assert '{param:BAPAUTOSTART|0}' in installer
    assert "IsAutomaticUpdate" in installer


def test_runtime_version_probe_reports_the_project_version(tmp_path, monkeypatch) -> None:
    output = tmp_path / "version.txt"
    monkeypatch.setattr(sys, "argv", ["BAP.exe", "--write-version", str(output)])

    assert main() == 0
    assert output.read_text(encoding="utf-8") == bap_desktop.__version__


def test_refresh_token_storage_is_separate_from_non_sensitive_settings() -> None:
    settings_source = (ROOT / "bap_desktop/settings.py").read_text(encoding="utf-8").lower()
    credentials_source = (ROOT / "bap_desktop/services/credential_store.py").read_text(encoding="utf-8")
    assert "refresh_token" not in settings_source
    assert "keyring.set_password" in credentials_source
    assert "keyring.get_password" in credentials_source
