## 名詞定義

| 名詞 | 定義 |
|---|---|
| 統一 Backend 交付包 | 包含 Backend、Migration、locked dependency metadata 與 runtime deployment code 的單一 ZIP。 |
| Runtime deployment code | 隨 Backend 版本交付，用於驗證、部署、狀態、Health 與 Rollback 的 PowerShell code。 |
| BAPBackend | 遠端 Windows Server 上維持 Backend 運行的 Scheduled Task 名稱。 |
| current | `C:\BAP\current` Junction，指向目前正式 Backend Release。 |
| Bootstrap | 第一次安裝於 Server、只負責安全驗證與啟動 Candidate deployment 的最小入口。 |

## Purpose

讓 GitHub CD 能把 CI 已驗證的統一 Backend 交付包安全送到遠端 Windows Server，透過 Scheduled Task 更新服務，並在任何失敗時自動保留或還原可用版本。

## Requirements

### Requirement: Backend 必須以單一可驗證交付包交付

Backend Candidate MUST 同時包含執行服務與部署該版本所需的檔案，且 MUST NOT 另外依賴 Deployment Scripts ZIP。

#### Scenario: CI 建立 Backend ZIP

- **WHEN** CI 打包 Backend Candidate
- **THEN** ZIP MUST 包含 Backend、shared code、Migration、locked dependency metadata、runtime deployment code 與 manifest

#### Scenario: ZIP 含敏感或非正式檔案

- **WHEN** ZIP 含有 `.env`、Database、Token、Private Key、log、test output、Desktop source 或 `.venv`
- **THEN** Artifact validation MUST 失敗

#### Scenario: Server 收到 Backend ZIP

- **WHEN** Bootstrap 收到 Candidate
- **THEN** 它 MUST 驗證 filename、checksum、manifest、Source Tree SHA 與 PowerShell syntax，通過後才可執行 runtime deployment code

### Requirement: CD 必須透過受控 SSH 介面部署

系統 MUST 限制只有使用 `production-backend` Environment 的 CD Promotion Job 才可對正式 Server 執行 SCP／SSH。

#### Scenario: Merge 後部署 Backend

- **WHEN** verified scope 包含 Backend
- **THEN** CD MUST 使用設定的 Private Key、host `140.114.75.84`、user `user` 與 port `22` 上傳同一 Candidate Backend ZIP並呼叫 Bootstrap

#### Scenario: SSH 或 SCP 失敗

- **WHEN**驗證、連線、上傳或遠端命令回傳失敗
- **THEN** CD MUST 回報失敗，且 MUST NOT 將未完成 Release 標記為正式

### Requirement: Backend 必須由 Scheduled Task 持續運行

正式 Backend MUST 由 `BAPBackend` Scheduled Task 啟動，且不能依賴 SSH session 或前景 Terminal持續存在。

#### Scenario: Server 開機

- **WHEN** 遠端 Windows Server 完成開機
- **THEN** `BAPBackend` MUST 自動啟動目前 `current` Release

#### Scenario: SSH session 結束

- **WHEN** 建立或觸發 Backend 的 SSH session 結束
- **THEN** Backend MUST 繼續運行並可通過 local Health Check

#### Scenario: Cutover 後檢查舊 Process Scripts

- **WHEN** repository contract test 掃描正式 Backend Scripts
- **THEN** 前景 `Start-BapBackend.ps1`、`Stop-BapBackend.ps1` 與 PID process 管理 MUST 不存在

### Requirement: 部署必須依安全順序執行

遠端部署 MUST 依序驗證 Candidate、準備 immutable Release、停止 Scheduled Task、備份 SQLite、執行 Migration、切換 `current`、啟動 Task並檢查 Health。

#### Scenario: 正常部署

- **WHEN** Candidate、Migration、Task與 Health 全部成功
- **THEN** `current` MUST 指向 `C:\BAP\releases\<master-commit-sha>`，且 Promotion record MUST 記錄 Candidate Source Tree SHA與 checksum

#### Scenario: config 或 Database 已存在

- **WHEN** 部署新 Release
- **THEN** 系統 MUST 保留 `C:\BAP\config` 與 `C:\BAP\data`，不得把它們複製進或刪除於 Release

#### Scenario: Deployment 重複執行

- **WHEN** 同一 master commit 與 Candidate 被再次要求部署
- **THEN** 系統 MUST 回報既有一致結果或安全拒絕，不得建立內容不同的同名 Release

### Requirement: 部署失敗必須自動 Rollback

切換前後任何會影響可用性的步驟失敗時，系統 MUST 還原 Last Known Good Release 與必要的 SQLite backup。

#### Scenario: Migration 失敗

- **WHEN** 新 Release 的 Alembic Migration 失敗
- **THEN** `current` MUST 保持或還原舊 Release，Database MUST 使用可驗證 backup，且 Scheduled Task MUST 回到可用狀態

#### Scenario: Scheduled Task 或 Health 失敗

- **WHEN** Task 無法啟動、port 12345 未監聽、local Health 或 public HTTPS Health 失敗
- **THEN** 系統 MUST 停止新版本、還原 Last Known Good、重新啟動並回報 Rollback 結果

#### Scenario: Rollback 也失敗

- **WHEN** 自動 Rollback 無法恢復 Health
- **THEN** CD MUST 清楚回報需要人工處理，且不得宣告 Deployment success

### Requirement: 部署必須有鎖並可查詢狀態

系統 MUST 防止重疊部署，並提供 Scheduled Task、port、Health、current Release 與版本身分的狀態輸出。

#### Scenario: 兩個部署同時到達

- **WHEN** 已有 Deployment lock 時另一個 Backend Promotion 開始
- **THEN** 後者 MUST 等待或失敗，不得同時執行 Migration 或切換 `current`

#### Scenario: 管理者查詢狀態

- **WHEN** 管理者或 CD 要求 Backend status
- **THEN** 系統 MUST 回報 Task state、port 12345、local Health、master commit、Source Tree SHA、checksum 與 current Release

### Requirement: Bootstrap 必須可重跑且不破壞資料

Initialize MUST 可在既有 Server 上重跑，用來補齊目錄與 Scheduled Task設定，但不得覆寫 Secret、Database 或既有 Release。

#### Scenario: Server 第一次 Initialize

- **WHEN** 必要的 Windows、Python、uv、OpenSSH 與權限條件已滿足
- **THEN** 系統 MUST 建立持久目錄、最小 Bootstrap 與 `BAPBackend` Scheduled Task

#### Scenario: Server 再次 Initialize

- **WHEN** `C:\BAP` 已有 config、Database、Release 與 Task
- **THEN** Initialize MUST 保留資料與相容設定，只補齊缺少且安全的部分
