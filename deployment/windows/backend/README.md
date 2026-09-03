# BAP Backend 自動部署介面

## 名詞定義

| 名詞 | 定義 |
|---|---|
| Candidate | PR CI 已 Build、解壓、安裝並通過 E2E 的 Artifact。 |
| Bootstrap | 固定在 Server 上，先驗證 Candidate，再呼叫 Candidate 內部署程式。 |
| Scheduled Task | Windows 用來維持 Backend process 的 BAPBackend 工作。 |
| Promotion record | 記錄 master commit、PR、CI run、Source Tree SHA、checksum 與 scope 的 JSON。 |
| Last Known Good | 最近一次部署並通過 Health Check 的版本。 |

## Server 目錄

~~~text
C:\BAP\
├─ bootstrap\
├─ incoming\
├─ releases\<master-sha>\
├─ current\
├─ config\.env
├─ data\bap.db
├─ backups\
├─ logs\
└─ run\
~~~

舊的 scripts-releases、scripts Junction 與 PID file 不再屬於新流程。

## 腳本 I/O

### Initialize-BapBackendHost.ps1

輸入 Root、Windows user、uv 路徑與 Task 名稱。輸出必要目錄、固定 Bootstrap 與 BAPBackend Scheduled Task。只供第一次 Initialize 或修復 host contract；保留 config、Database、logs、backups 與 releases，也不會重開機。

### Build-BapBackendArtifact.ps1

輸入 PR test commit、Source Tree SHA 與乾淨 Git snapshot。輸出 bap-backend-tree-<source-tree-sha>.zip 及 checksum。ZIP 同時包含 Backend runtime 與部署 runtime code。

### Bootstrap-BapBackendCandidate.ps1

輸入 Backend ZIP、checksum、Source Tree SHA、master commit 與 Promotion record。先驗證 checksum、manifest、PowerShell 語法，再呼叫 ZIP 內的 Deploy script。

### Deploy-BapBackendRelease.ps1

依序取得 lock、建立 immutable Release、停止 Task、備份 DB、migration、切換 current、啟動 Task、檢查 Health。失敗時還原 current 與 Database，並嘗試啟動上一版。

### Run-BapBackendScheduledTask.ps1

讀取 config\.env、current 與 Promotion record，在 0.0.0.0:12345 執行 Uvicorn。SSH session 結束不會結束這個 Task。

### Get-BapBackendStatus.ps1

輸出 Task state、port 12345、Health、master commit、Source Tree SHA、checksum 與 current target。

### Test-BapBackendHealth.ps1

驗證 localhost 與公開 HTTPS health URL。

### Rollback-BapBackendRelease.ps1

輸入上一個 Release 與選用 Database backup，還原 current、Database 與 Scheduled Task。

## 自動部署 Pipeline

~~~mermaid
flowchart LR
    A["CD 下載已測 Candidate"] --> B["SCP 到 incoming"]
    B --> C["SSH 呼叫 Bootstrap"]
    C --> D["checksum／manifest／script syntax"]
    D --> E["停止 Scheduled Task"]
    E --> F["備份 DB 與 migration"]
    F --> G["切換 current"]
    G --> H["啟動 Scheduled Task"]
    H --> I["localhost + 公開 HTTPS Health"]
    I -->|成功| J["寫入 Last Known Good"]
    I -->|失敗| K["Rollback"]
~~~
