## 名詞定義

| 名詞 | 定義 |
|---|---|
| Manual Merge | CI 通過與人工 Review 後，由人到 GitHub 按下 Merge。 |
| Candidate Resolver | 從 master commit 找回 merged PR、成功 CI run 與唯一 Candidate 的流程。 |
| Promotion Scope | 本次 master 內容需要部署 Backend、發布 Desktop、兩者都做或都不做的判定。 |
| Fail Closed | 無法證明 Candidate 正確時直接停止，不猜測、不重建也不修改 Production。 |

## Purpose

確保人工 Merge 後只交付該 Pull Request 已通過 CI 的同一份 Candidate，並依實際變更範圍安全地路由到 Backend 部署或 Desktop Release。

## Requirements

### Requirement: 人工 Merge 是 Production Gate

系統 MUST 等待 CI success 與人工 Merge，且 MUST NOT 由 CI 自動 Merge Pull Request。

#### Scenario: CI 通過但尚未 Merge

- **WHEN** PR 的 required CI 已通過但人尚未按下 Merge
- **THEN** 系統 MUST 保留 Candidate，但 MUST NOT 開始 Backend 或 Desktop Promotion

#### Scenario: 人工 Merge 到 master

- **WHEN** 人在 GitHub 將通過 CI 的 PR Merge 到 `master`
- **THEN** 系統 MUST 啟動 CD Candidate resolution

#### Scenario: 直接 push 到 master

- **WHEN** 有人嘗試略過 PR 直接 push 到受保護的 `master`
- **THEN** GitHub MUST 拒絕該 push

### Requirement: CD 必須取得同一份 Candidate且不得重新 Build

CD MUST 從 master commit 找回唯一 merged PR、成功 CI run 與 Candidate，並驗證 master Tree 與 Source Tree SHA 相同。

#### Scenario: 找到唯一相符 Candidate

- **WHEN** merged PR、成功 CI run、Source Tree SHA 與 Candidate 可唯一對應
- **THEN** CD MUST 下載該 Candidate並驗證 manifest、test summary 與所有 SHA256

#### Scenario: Candidate 身分或內容無法證明

- **WHEN** Candidate 缺少、過期、不唯一、CI 非 success、Tree SHA 不同、checksum 錯誤或 manifest 不完整
- **THEN** CD MUST fail closed，且 MUST NOT 修改 Backend 或 GitHub Release

#### Scenario: CD Workflow 被檢查

- **WHEN** repository contract test分析 CD Workflow
- **THEN** Workflow MUST 不包含 Backend package、PyInstaller、Inno Setup 或其他重建 Artifact 的步驟

### Requirement: CI 與 CD 必須使用同一套 Scope 規則

CI MUST 將 scope 寫入 manifest，CD MUST 重新計算並要求兩者一致。

#### Scenario: 只有 Backend 變更

- **WHEN**變更只影響 Backend、Migration 或 Backend deployment code
- **THEN** CD MUST 只執行 Backend Promotion

#### Scenario: 只有 Desktop 變更

- **WHEN** 變更只影響 Desktop 或 Windows packaging
- **THEN** CD MUST 只執行 Desktop Promotion

#### Scenario: Shared dependency 變更

- **WHEN**變更影響 `bap_common`、`anrot_imu_driver`、`pyproject.toml` 或 `uv.lock`
- **THEN** CD MUST 同時執行 Backend 與 Desktop Promotion

#### Scenario: 只有文件變更

- **WHEN** master commit 對應的 PR 是 docs-only
- **THEN** CD MUST 回報不需 Promotion，且 MUST NOT 修改 Production

#### Scenario: Scope 不一致

- **WHEN** CD 重新計算的 scope 與 Candidate manifest 不同
- **THEN** CD MUST fail closed

### Requirement: 同時交付時必須 Backend-first

當 scope 同時包含 Backend 與 Desktop 時，Desktop Release MUST 等 Backend Promotion 與 Production Health 成功後才可公開。

#### Scenario: Backend 成功

- **WHEN** Backend Promotion 與 local／public Health Check 都成功
- **THEN** CD MAY 繼續發布 Candidate 中的 Desktop Installer

#### Scenario: Backend 失敗

- **WHEN** Backend Promotion、Scheduled Task 或任一 Health Check 失敗
- **THEN** CD MUST Rollback Backend，且 MUST NOT 發布新 Desktop Release

### Requirement: 正式交付只能走 GitHub CI/CD

Cutover 後，repository MUST 不再提供開發者本機正式 Publisher 或重複的舊 Workflow。

#### Scenario: 開發者準備正式交付

- **WHEN** 開發者要發布新版本
- **THEN** 支援的入口 MUST 是 feature branch、PR、required CI、人工 Merge與 CD，而不是本機 SCP／SSH Publisher

#### Scenario: Repository 接受 Cutover contract test

- **WHEN** 自動測試掃描 Workflows、Scripts與文件
- **THEN** `build-desktop.yml`、`Publish-BapBackend.ps1`、`Publish-BapDeploymentScripts.ps1` 與舊正式操作指令 MUST 不存在

### Requirement: Production Promotion 必須序列化

系統 MUST 保證同一時間最多只有一個 Production Promotion。

#### Scenario: 新 Merge 發生在舊 CD 尚未結束時

- **WHEN** 新的 master commit 在前一次 Production Promotion 執行中出現
- **THEN** 系統 MUST 排隊或安全取消尚未進入不可中斷區段的舊 run，不得同時執行 Migration 或切換 `current`
