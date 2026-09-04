## 名詞定義

| 名詞 | 定義 |
|---|---|
| CI | Pull Request 階段的自動流程，負責 Build、安裝、測試並產生可供後續交付的 Candidate。 |
| CD | Pull Request 人工 Merge 到 `master` 後執行的流程，負責把 CI 已驗證的 Candidate 部署或發布，不重新 Build。 |
| CI Candidate | 同一次 PR CI 產生的完整交付包，包含 Backend ZIP、Desktop Installer、checksums、delivery manifest 與 test summary。 |
| Source Tree SHA | Git 對一份完整檔案樹計算出的識別值，用來證明 PR CI 測試的內容與 Merge 後要交付的內容相同。 |
| Promotion | 將 CI Candidate 中已驗證的檔案送到 Backend Server 或 GitHub Release 的動作。 |
| Scheduled Task | 遠端 Windows Server 用來持續運行 BAP Backend 的 `BAPBackend` 工作。 |
| 舊流程 | 開發者在本機 Build Artifact、執行 SCP／SSH、更新獨立 Deployment Scripts Artifact，並以前景 Terminal 維持 Backend 的流程。 |
| Last Known Good | 最近一次完成部署、Health Check 且可供 Rollback 的正式版本紀錄。 |

## Why

目前 repository 同時保留本機人工發布、獨立 Deployment Scripts Artifact、前景 Terminal 啟動，以及 Desktop-only Workflow，會讓開發者不知道哪一條才是正式交付流程，也容易在 workspace 留下 ZIP、EXE 與 log。這個 Change 要把正式 Build、測試、部署與發布集中到 GitHub Actions，讓開發者只需要處理 feature branch、Pull Request、CI 與人工 Merge。

## What Changes

- 採用 `feature branch → Pull Request → CI → 人工 Merge → CD` 作為唯一正式交付流程，禁止直接 push 到 `master`。
- 非 docs-only PR 由同一台 GitHub-hosted Windows CI Runner 建立 Backend ZIP 與 Desktop Installer，並用這兩個實際 Artifact 完成 Production-like 前後端 E2E。
- CI 通過後上傳單一 CI Candidate；Candidate 以 PR、workflow run、Source Tree SHA、checksums、scope 與測試結果識別。
- 人工 Merge 到 `master` 後才啟動另一台 Windows CD Runner；CD 下載同一份 Candidate、驗證身分與內容後進行 Promotion，絕不重新 Build。
- Backend 交付包會一起攜帶該版本需要的遠端部署程式，不再另外建立或發布 `bap-deployment-scripts-<commit-sha>.zip`。
- Backend CD 使用 `production-backend` Environment 的 SSH 設定連線到 `140.114.75.84`，停止 `BAPBackend` Scheduled Task、備份 SQLite、Migration、切換 `current`、重新啟動並驗證 Health。
- Backend 失敗時自動 Rollback；Backend 與 Desktop 同時變更時，必須先確認 Backend 成功，才發布 Desktop Release。
- docs-only PR 不啟動昂貴的 Windows Build/Test，但仍回報一個可作為 required check 的成功結果。
- GitHub Actions 提供 Job Summary、diagnostics 與失敗通知；Secret、Token、Private Key 與正式資料不得進入 log 或 Artifact。
- **BREAKING**：新流程通過正式 E2E 後，移除 `build-desktop.yml`、本機 `Publish-*` Scripts、獨立 Deployment Scripts 更新流程，以及前景 Terminal 的 Start／Stop Scripts。
- 正式 Build 輸出使用 Runner 暫存空間；開發者 repository 的 `dist\`、`build\`、`*.egg-info\` 與測試 cache 不再作為正式交付來源。

## Capabilities

### New Capabilities

- `pull-request-ci`：定義 PR 分類、Candidate Build、Artifact 安裝、Production-like E2E、取消舊 run 與 Candidate 上傳。
- `component-delivery-routing`：定義人工 Merge、Candidate 對應、驗證、變更範圍與 Backend／Desktop Promotion 順序。
- `backend-automatic-deployment`：定義統一 Backend 交付包、SSH 部署、Scheduled Task、Migration、Health Check 與自動 Rollback。
- `desktop-automatic-release`：定義使用同一份已驗證 Installer 建立 GitHub Release 與更新 `app_releases`。
- `ci-cd-status-reporting`：定義 CI／CD 狀態、診斷檔、Email 通知、Promotion record 與 Last Known Good。

### Modified Capabilities

無。本 Change 不改變既有 App user、IMU 或拳擊測量行為，只改變開發與交付系統。

## Impact

- 新增或取代 `.github/workflows/pull-request-ci.yml` 與 `.github/workflows/continuous-delivery.yml`。
- 改寫 Backend Artifact、manifest、change detection、Candidate resolver 與 Promotion helpers。
- 改寫 `Build-BapBackendArtifact.ps1`、`Initialize-BapBackendHost.ps1`、`Deploy-BapBackendRelease.ps1`、`Rollback-BapBackendRelease.ps1`、`Get-BapBackendStatus.ps1` 與相關測試。
- 保留 Desktop Build／Installer／Smoke Test Scripts，改由 PR CI 使用。
- 移除 `.github/workflows/build-desktop.yml`、`Publish-BapBackend.ps1`、`Publish-BapDeploymentScripts.ps1`、`Update-BapDeploymentScripts.ps1`、`Start-BapBackend.ps1` 與 `Stop-BapBackend.ps1`。
- 移除或改寫只描述人工 Release／前景 Terminal 的文件與測試。
- 遠端逐步淘汰 `C:\BAP\scripts-releases`、`C:\BAP\scripts` Junction、舊 Deployment Scripts ZIP 與 PID 殘留；保留 config、data、logs、backups、releases、current 與 incoming。
