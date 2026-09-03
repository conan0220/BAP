from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[2]
PR = ROOT / ".github/workflows/pull-request-ci.yml"
CD = ROOT / ".github/workflows/continuous-delivery.yml"


@pytest.mark.scenario("pull-request-ci", "程式 PR 通過完整 CI")
@pytest.mark.scenario("pull-request-ci", "建立前後端 Artifact")
@pytest.mark.scenario("pull-request-ci", "從 Backend ZIP 建立測試服務")
@pytest.mark.scenario("pull-request-ci", "從 Installer 安裝 Desktop")
@pytest.mark.scenario("pull-request-ci", "執行真實 HTTP user flow")
def test_pr_workflow_builds_installs_and_tests_one_candidate() -> None:
    text = PR.read_text(encoding="utf-8")
    assert "pull_request:" in text
    assert "Build-BapBackendArtifact.ps1" in text
    assert "Build-BapDesktop.ps1" in text
    assert "Test-BapCandidate.ps1" in text
    assert "--api-e2e-test" in (ROOT / "bap_desktop/app.py").read_text(encoding="utf-8")
    assert "bap-candidate-pr-${{ github.event.pull_request.number }}" in text
    assert "retention-days: 14" in text


@pytest.mark.scenario("pull-request-ci", "docs-only PR 不使用 Windows Runner")
@pytest.mark.scenario("pull-request-ci", "同一 PR 推送新 commit")
@pytest.mark.scenario("component-delivery-routing", "只有文件變更")
def test_pr_workflow_cancels_stale_runs_and_keeps_docs_gate_lightweight() -> None:
    text = PR.read_text(encoding="utf-8")
    assert "group: pr-ci-${{ github.event.pull_request.number }}" in text
    assert "cancel-in-progress: true" in text
    assert "if: needs.classify.outputs.docs_only != 'true'" in text
    assert "name: CI Gate" in text
    assert "Documentation-only PR passed without using a Windows runner." in text


@pytest.mark.scenario("pull-request-ci", "PR 來自不受信任的程式碼")
def test_pr_workflow_never_receives_production_credentials() -> None:
    text = PR.read_text(encoding="utf-8")
    for forbidden in ("production-backend", "BAP_BACKEND_SSH_PRIVATE_KEY", "BAP_BACKEND_HOST", "C:\\BAP\\incoming"):
        assert forbidden not in text


@pytest.mark.scenario("pull-request-ci", "任一 Build 失敗")
@pytest.mark.scenario("pull-request-ci", "測試或清理失敗")
@pytest.mark.scenario("ci-cd-status-reporting", "Build 或 E2E 失敗")
def test_pr_gate_and_always_diagnostics_fail_closed() -> None:
    text = PR.read_text(encoding="utf-8")
    assert "if: ${{ always() && !cancelled() }}" in text
    assert "Upload failure diagnostics" in text
    assert "if: always()" in text
    assert 'if [ "$CANDIDATE_RESULT" != "success" ]; then exit 1; fi' in text


@pytest.mark.scenario("pull-request-ci", "Repository checkout 含舊本機輸出")
def test_build_outputs_use_runner_temp_not_repository_dist() -> None:
    workflow = PR.read_text(encoding="utf-8")
    backend = (ROOT / "deployment/windows/backend/Build-BapBackendArtifact.ps1").read_text(encoding="utf-8")
    desktop = (ROOT / "packaging/windows/Build-BapDesktop.ps1").read_text(encoding="utf-8")
    assert "$env:RUNNER_TEMP" in backend
    assert "$env:RUNNER_TEMP" in desktop
    assert "runner.temp" in workflow


@pytest.mark.scenario("component-delivery-routing", "人工 Merge 到 master")
@pytest.mark.scenario("component-delivery-routing", "找到唯一相符 Candidate")
@pytest.mark.scenario("component-delivery-routing", "Candidate 身分或內容無法證明")
@pytest.mark.scenario("component-delivery-routing", "CD Workflow 被檢查")
def test_cd_resolves_and_verifies_the_pr_candidate_without_rebuilding() -> None:
    text = CD.read_text(encoding="utf-8")
    assert "push:" in text and "branches: [master]" in text
    assert "listPullRequestsAssociatedWithCommit" in text
    assert "pull-request-ci.yml" in text
    assert "actions/download-artifact@v7" in text
    assert "delivery_candidate validate" in text
    assert "Candidate PR does not match." in text
    assert "matchingRuns.length !== 1" in text
    assert "item.conclusion === \"success\"" in text
    assert "scope mismatch" in text.lower()
    for forbidden in ("Build-BapBackendArtifact.ps1", "Build-BapDesktop.ps1", "PyInstaller", "ISCC.exe"):
        assert forbidden not in text


@pytest.mark.scenario("component-delivery-routing", "只有 Backend 變更")
@pytest.mark.scenario("component-delivery-routing", "只有 Desktop 變更")
@pytest.mark.scenario("component-delivery-routing", "Shared dependency 變更")
@pytest.mark.scenario("component-delivery-routing", "Backend 成功")
@pytest.mark.scenario("component-delivery-routing", "Backend 失敗")
def test_cd_routes_components_and_enforces_backend_first_gate() -> None:
    text = CD.read_text(encoding="utf-8")
    assert "needs.resolve.outputs.backend_changed == 'true'" in text
    assert "needs.resolve.outputs.desktop_changed == 'true'" in text
    assert "needs.promote-backend.result == 'success'" in text
    assert "Delivery Gate" in text
    assert "group: bap-production" in text
    assert "cancel-in-progress: false" in text


@pytest.mark.scenario("backend-automatic-deployment", "Merge 後部署 Backend")
@pytest.mark.scenario("desktop-automatic-release", "Backend Health 成功")
@pytest.mark.scenario("desktop-automatic-release", "Backend Promotion 失敗")
def test_backend_promotion_uses_environment_ssh_and_public_health_gate() -> None:
    text = CD.read_text(encoding="utf-8")
    assert "environment: production-backend" in text
    assert "BAP_BACKEND_SSH_PRIVATE_KEY" in text
    assert "Bootstrap-BapBackendCandidate.ps1" in text
    assert "https://imuapp.lab2312.cs.nthu.edu.tw/health" in text
    assert "Restart-Computer" not in text


@pytest.mark.scenario("desktop-automatic-release", "Desktop-only Promotion")
@pytest.mark.scenario("desktop-automatic-release", "發布新版本")
@pytest.mark.scenario("desktop-automatic-release", "Version 或 tag 已存在")
@pytest.mark.scenario("desktop-automatic-release", "Release 與 app_releases 都成功")
@pytest.mark.scenario("desktop-automatic-release", "app_releases 寫入失敗")
@pytest.mark.scenario("desktop-automatic-release", "Repository Workflow contract test")
def test_desktop_release_uses_tested_asset_draft_and_update_metadata() -> None:
    text = CD.read_text(encoding="utf-8")
    assert "desktop-v${{ needs.verify.outputs.desktop_version }}" in text
    assert "gh release view" in text
    assert "gh release create" in text and "--draft" in text
    assert "publish_desktop_release" in text
    assert "--source-tree-sha" in text
    assert "Release remains a draft" in text
    assert "gh release edit" in text and "--draft=false" in text


@pytest.mark.scenario("ci-cd-status-reporting", "CI 成功")
@pytest.mark.scenario("ci-cd-status-reporting", "CD 成功")
@pytest.mark.scenario("ci-cd-status-reporting", "docs-only 完成")
@pytest.mark.scenario("ci-cd-status-reporting", "Deployment 或 Release 失敗")
@pytest.mark.scenario("ci-cd-status-reporting", "錯誤文字包含敏感值")
def test_workflows_report_status_without_printing_secret_values() -> None:
    pr = PR.read_text(encoding="utf-8")
    cd = CD.read_text(encoding="utf-8")
    assert "GITHUB_STEP_SUMMARY" in pr
    assert "GITHUB_STEP_SUMMARY" in cd
    assert "Upload failure diagnostics" in pr
    assert "bap-cd-verification-" in cd
    assert not re.search(r"(echo|Write-Output).*secrets\.", pr + cd, re.IGNORECASE)


@pytest.mark.scenario("component-delivery-routing", "開發者準備正式交付")
@pytest.mark.scenario("component-delivery-routing", "Repository 接受 Cutover contract test")
@pytest.mark.scenario("ci-cd-status-reporting", "GitHub 通知啟用")
def test_readme_documents_manual_merge_branch_protection_and_notifications() -> None:
    text = (ROOT / "docs/guides/ci-cd.md").read_text(encoding="utf-8")
    assert "CI Gate" in text
    assert "人工 Merge" in text
    assert "禁止直接 push" in text
    assert "GitHub Notifications" in text
    assert "SMTP" in text


@pytest.mark.scenario("backend-automatic-deployment", "config 或 Database 已存在")
@pytest.mark.scenario("backend-automatic-deployment", "Rollback 也失敗")
@pytest.mark.scenario("ci-cd-status-reporting", "Backend Rollback 成功")
@pytest.mark.scenario("ci-cd-status-reporting", "Cutover E2E 完成")
@pytest.mark.scenario("ci-cd-status-reporting", "Promotion 成功")
@pytest.mark.scenario("ci-cd-status-reporting", "不完整交付")
@pytest.mark.scenario("component-delivery-routing", "CI 通過但尚未 Merge")
@pytest.mark.scenario("component-delivery-routing", "Scope 不一致")
@pytest.mark.scenario("component-delivery-routing", "新 Merge 發生在舊 CD 尚未結束時")
@pytest.mark.scenario("component-delivery-routing", "直接 push 到 master")
@pytest.mark.scenario("desktop-automatic-release", "Installer checksum 不同")
@pytest.mark.scenario("pull-request-ci", "Candidate 超過保存期限")
def test_cutover_policy_has_fail_closed_evidence_and_operator_boundaries() -> None:
    pr = PR.read_text(encoding="utf-8")
    cd = CD.read_text(encoding="utf-8")
    deploy = (ROOT / "deployment/windows/backend/Deploy-BapBackendRelease.ps1").read_text(encoding="utf-8")
    initialize = (ROOT / "deployment/windows/backend/Initialize-BapBackendHost.ps1").read_text(encoding="utf-8")
    artifact = (ROOT / "bap_backend/deployment/artifact.py").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "retention-days: 14" in pr
    assert "push:" not in pr.split("jobs:", 1)[0]
    assert "branches: [master]" in cd
    assert "cancel-in-progress: false" in cd
    assert "Backend scope mismatch." in cd
    assert "Desktop scope mismatch." in cd
    assert "Desktop checksum does not match Candidate" in artifact
    assert "last-known-good.json" in deploy
    assert "rollback also failed" in deploy
    assert "Existing persistent data was preserved." in initialize
    assert "不要直接 push" in readme
    assert "Delivery Gate" in cd
