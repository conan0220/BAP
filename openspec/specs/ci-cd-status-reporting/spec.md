## 名詞定義

| 名詞 | 定義 |
|---|---|
| Job Summary | GitHub Actions 頁面中供開發者快速了解該階段輸入、輸出與結果的摘要。 |
| Diagnostics | 失敗時保存的安全 log、report、manifest 或 screenshot，不包含 Secret。 |
| Promotion Record | 將 master commit、PR、CI run、Candidate 與 Production 結果串在一起的稽核紀錄。 |
| Last Known Good | 最近一次 Backend 與必要 Desktop 交付都通過正式驗證的版本。 |
| Email 通知 | GitHub Actions 依 repository／帳號通知設定寄出的失敗通知，不使用 repository 內自建 SMTP Secret。 |

## Purpose

讓開發者能從 GitHub Actions 清楚知道 CI、Candidate、Merge 後 CD、Backend、Desktop 與 Rollback 的結果，並在失敗時收到不洩漏 Secret 的可追查資訊。

## Requirements

### Requirement: 每個階段必須提供一致狀態

CI 與 CD MUST 為分類、Build、Test、Candidate、verification、Backend、Desktop與 Rollback 提供清楚的 Job result 與 Summary。

#### Scenario: CI 成功

- **WHEN** PR CI 完成
- **THEN** Summary MUST 顯示 Source Tree SHA、scope、Artifact checksums、測試結果與 Candidate識別

#### Scenario: CD 成功

- **WHEN**所有需要的 Promotion 完成
- **THEN** Summary MUST 顯示 master commit、PR、CI run、Candidate、Backend Release、Desktop Release與 Health 結果

#### Scenario: docs-only 完成

- **WHEN** PR 或 master commit 只改文件
- **THEN** Summary MUST 清楚顯示沒有建立 Candidate或修改 Production

### Requirement: 失敗必須提供安全 Diagnostics 與 Email

任一 required CI 或 CD 階段失敗時，系統 MUST 保留足以判斷失敗位置的 diagnostics，並允許 GitHub Actions 通知寄送失敗 Email。

#### Scenario: Build 或 E2E 失敗

- **WHEN** CI 的 Build、安裝、Migration、API、Desktop或 cleanup 失敗
- **THEN** 系統 MUST 上傳該階段安全 log／report，並讓 Workflow conclusion 為 failure

#### Scenario: Deployment 或 Release 失敗

- **WHEN** CD 的 Candidate validation、SSH、Migration、Scheduled Task、Health、Rollback或 Release 失敗
- **THEN** 系統 MUST 記錄失敗 stage、已完成動作、Production 最終狀態與可執行的下一步

#### Scenario: GitHub 通知啟用

- **WHEN** CI 或 CD Workflow conclusion 為 failure
- **THEN** GitHub MUST 能依使用者通知設定寄送 Email，而 repository MUST NOT 保存 SMTP password

### Requirement: Secret 必須從輸出移除

Logs、Summary、diagnostics、Artifact 與 Promotion record MUST NOT 包含 SSH Private Key、Token、Password、正式 `.env` 或 Database 內容。

#### Scenario: 錯誤文字包含敏感值

- **WHEN** 外部工具把已知 Secret 寫到 stdout、stderr 或 exception
- **THEN** Workflow MUST 遮蔽該值，且安全檢查 MUST 阻止未遮蔽輸出上傳

### Requirement: Promotion 與 Rollback 必須可追溯

系統 MUST 保存 Promotion record 與 Last Known Good，使人能從 Production 版本回查 Candidate 與 CI。

#### Scenario: Promotion 成功

- **WHEN** 所有需要的 Production驗證成功
- **THEN** 系統 MUST 更新 Last Known Good，記錄 master commit、PR、CI run、Source Tree SHA、checksums、scope、Database revision與 Release結果

#### Scenario: Backend Rollback 成功

- **WHEN** 新 Backend 失敗後成功還原
- **THEN** record MUST 保留失敗 Candidate與 Rollback 目標，且 Last Known Good MUST 仍指向還原後可用版本

#### Scenario: 不完整交付

- **WHEN** Backend 成功但 Desktop Release或 `app_releases` 失敗
- **THEN** 系統 MUST 記錄 partial failure，且 MUST NOT 將整體流程標記為完整 success

### Requirement: Cutover 狀態必須可驗證

系統 MUST 能證明正式流程已不再依賴開發者 workspace、舊 Publisher、前景 Terminal或獨立 Deployment Scripts Artifact。

#### Scenario: Cutover E2E 完成

- **WHEN** 新 PR→CI→人工 Merge→CD 全流程完成
- **THEN** Summary 或 contract report MUST 顯示 Artifact 來自 GitHub Candidate、CD 無 rebuild、Backend 由 Scheduled Task 運行且舊入口不存在
