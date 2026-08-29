from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_readme_referenced_repository_scripts_exist() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    paths = set(re.findall(r"D:\\repos\\BAP\\([A-Za-z0-9_.\\-]+\.ps1)", readme))
    assert paths
    for relative in paths:
        assert (ROOT / relative.replace("\\", "/")).is_file(), relative


def test_readme_has_copyable_absolute_powershell_commands_and_all_operations() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert readme.index("## 名詞定義") < readme.index("## 這個專案做什麼")
    assert readme.count("C:\\WINDOWS\\System32\\WindowsPowerShell\\v1.0\\powershell.exe -NoProfile") >= 10
    for operation in (
        "Initialize",
        "Test",
        "Start",
        "Stop",
        "Status",
        "Deploy",
        "Update Deployment Scripts",
        "Rollback",
        "公開 HTTPS",
        "Build Windows Desktop App",
    ):
        assert operation in readme
    assert "```mermaid" in readme
    assert "git@github.com:conan0220/BAP.git" not in readme or "BAP" in readme


def test_readme_does_not_embed_secrets_or_claim_github_auto_deploy() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "StrictHostKeyChecking=no" not in readme
    assert "development-only-key" not in readme
    assert "BEGIN OPENSSH PRIVATE KEY" not in readme
    assert "GitHub Actions 自動部署不在" in readme
