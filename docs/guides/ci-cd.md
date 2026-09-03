# BAP CI/CD 操作指南

## 名詞定義

| 名詞 | 定義 |
|---|---|
| CI Gate | Pull Request 必須通過的固定 GitHub check。 |
| Candidate | PR CI 已 Build、安裝並通過 E2E 的 Backend ZIP 與 Desktop Installer。 |
| CD | 人工 Merge 後驗證並交付同一份 Candidate 的流程。 |
| production-backend | 保存 Backend SSH Secret 與 Variables 的 GitHub Environment。 |
| Branch Protection | GitHub 用來禁止直接 push 並要求 CI Gate 的 master 規則。 |

## GitHub 設定

master Branch Protection 應設定：

- 禁止直接 push。
- 必須經 Pull Request。
- 必須通過 CI Gate。
- Merge 前 branch 必須是最新狀態。
- 不啟用 auto-merge。

production-backend Environment 需要：

- Secret：BAP_BACKEND_SSH_PRIVATE_KEY
- Variables：BAP_BACKEND_HOST、BAP_BACKEND_USER、BAP_BACKEND_SSH_PORT

目前依專案決策不驗證 BAP_BACKEND_HOST_KEY。

Workflow 失敗會出現在 Actions 與 PR checks。要收到 Email，開發者需在自己的 GitHub Notifications 設定啟用 Actions 失敗通知；repository 不保存 SMTP credential。

## PR CI 的 I/O

輸入 PR test merge tree。Windows Runner 建立 Backend ZIP 與 Desktop Installer，再解壓 Backend、建立暫存 SQLite、執行 Alembic、Silent install Desktop，並讓安裝後的 App 透過 http://127.0.0.1:12345/api/ 測試註冊、錯誤登入、重複註冊、正常登入、Refresh、登出與更新檢查。

輸出保存 14 天的 bap-candidate-pr-<PR number>、test-summary、manifest、checksums 與失敗 diagnostics。

## Merge 後 CD 的 I/O

輸入 master commit。CD 找回對應 PR、成功 CI run 與 Candidate，驗證 Source Tree SHA、scope、checksums 及測試結果；它不重新執行 Backend Build、PyInstaller 或 Inno Setup。

- Backend changed：SCP 到 C:\BAP\incoming，再透過 SSH 呼叫 Bootstrap。
- Desktop changed：用已測 Installer 建立 desktop-v<version> Draft Release，寫入 app_releases 後才公開。
- Shared changed：Backend Health 成功後才發布 Desktop。
- Docs only：不啟動 Windows Runner，也不交付。
- 任一身分或驗證不一致：fail closed。

~~~mermaid
flowchart LR
    A["feature branch"] --> B["PR CI"]
    B --> C["保存 14 天的 Candidate"]
    C --> D["人工 Merge"]
    D --> E["CD 驗證同一 Candidate"]
    E --> F{"scope"}
    F -->|Backend| G["SCP／SSH／Scheduled Task"]
    F -->|Desktop| H["Draft Release／app_releases／Publish"]
    F -->|Shared| I["Backend-first gate"]
~~~

## 一次性的 Backend Server Initialize

只有第一次建立或修復 C:\BAP host contract 時，才以系統管理員 PowerShell 執行：

~~~powershell
C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe -NoProfile -ExecutionPolicy Bypass -File "<repository>\deployment\windows\backend\Initialize-BapBackendHost.ps1"
~~~

Initialize 建立目錄、固定 Bootstrap 與 BAPBackend Scheduled Task，保留 config\.env 與 data\bap.db。它不會重新開機，也不會部署 Candidate。第一次啟用新流程前，Server 管理者必須先執行新版 Initialize。

詳細腳本 I/O 與 Rollback 請見 deployment\windows\backend\README.md。
