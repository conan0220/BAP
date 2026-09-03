from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_readme_referenced_developer_entry_points_exist() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "open_BAP.cmd" in readme
    assert (ROOT / "open_BAP.cmd").is_file()
    assert "docs/guides/ci-cd.md" in readme
    assert (ROOT / "docs/guides/ci-cd.md").is_file()


def test_readme_explains_only_the_supported_daily_developer_workflow() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for operation in ("feature branch", "Pull Request", "CI Gate", "人工 Merge", "Candidate"):
        assert operation in readme
    assert "~~~mermaid" in readme
    assert "git switch -c feature/" in readme
    assert "SCP、SSH" in readme
    assert "Publish-BapBackend.ps1" not in readme
    assert "Start-BapBackend.ps1" not in readme


def test_operator_guide_documents_automation_without_embedding_secrets() -> None:
    guide = (ROOT / "docs/guides/ci-cd.md").read_text(encoding="utf-8")
    assert "production-backend" in guide
    assert "BAP_BACKEND_SSH_PRIVATE_KEY" in guide
    assert "continuous-delivery" not in guide or "CD" in guide
    assert "GitHub Notifications" in guide
    assert "SMTP" in guide
    assert "不會重新開機" in guide
    assert "development-only-key" not in guide
    assert "BEGIN OPENSSH PRIVATE KEY" not in guide
