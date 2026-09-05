## 名詞定義

| 名詞 | 定義 |
|---|---|
| Pull Request | 將 feature branch 的修改送交檢查，準備合併到 `master` 的 GitHub 變更請求。 |
| Test Merge Tree | GitHub 將 PR 內容暫時套到最新 `master` 後得到的完整檔案樹。 |
| CI Candidate | 同一次 CI 建立並驗證的 Backend ZIP、Desktop Installer、checksums、manifest 與 test summary。 |
| docs-only | 只修改文件，不會改變程式、Build、部署或 Workflow 行為的 PR。 |
| Production-like E2E | 在乾淨 Runner 從實際 Artifact 安裝前後端，再透過真正 HTTP API 驗證 user flow。 |
| Desktop 版本來源 | `bap_desktop/VERSION`，是 Desktop Installer、Candidate metadata 與 App 執行時版本的唯一來源。 |
| Runtime 版本 | CI 安裝並啟動 Candidate 後，由 App 本身回報的 Desktop 版本。 |

## Purpose

確保每個準備合併到 master 的程式變更，都先由同一台 Windows Runner 建立可交付 Artifact，從 Artifact 安裝並完成可驗證的前後端整合測試。

## Requirements

### Requirement: Pull Request 必須經過固定 CI Gate

系統 MUST 對所有以 `master` 為目標的 Pull Request 回報同一個可設為 required check 的最終結果。未通過時 MUST 阻止正式交付。

#### Scenario: 程式 PR 通過完整 CI

- **WHEN** PR 修改程式、dependency、Build、deployment、packaging 或 Workflow
- **THEN** 系統 MUST 執行 Windows Build/Test 並以其結果決定 required check

#### Scenario: docs-only PR 不使用 Windows Runner

- **WHEN** PR 經共用規則判定為 docs-only
- **THEN** 系統 MUST 不配置 Windows Build/Test Runner，並回報成功的同名 required check

#### Scenario: 同一 PR 推送新 commit

- **WHEN** 同一個 PR 在舊 CI 尚未結束前收到新 commit
- **THEN** 系統 MUST 取消舊 run，且只有最新 commit 的結果可作為 Merge 依據

### Requirement: CI 必須從同一 Test Merge Tree 建立正式 Candidate

非 docs-only CI MUST 從同一個 Test Merge Tree 建立 Backend ZIP 與 Desktop Installer。正式輸出 MUST 寫入 Runner 暫存空間，不得讀取或依賴開發者電腦的 `dist\` 或 `build\`。

#### Scenario: 建立前後端 Artifact

- **WHEN** 非 docs-only CI 開始 Build
- **THEN** Backend ZIP 與 Desktop Installer MUST 具有相同 Source Tree SHA，並各自產生 SHA256

#### Scenario: 任一 Build 失敗

- **WHEN** Backend ZIP 或 Desktop Installer 無法建立
- **THEN** CI MUST 失敗，且 MUST NOT 上傳可供 CD 使用的 Candidate

#### Scenario: Repository checkout 含舊本機輸出

- **WHEN** repository 中存在被忽略或外部帶入的舊 `dist\`、`build\` 或 package metadata
- **THEN** CI MUST 不使用這些檔案建立或驗證 Candidate

### Requirement: CI 必須測試實際 Artifact

CI MUST 從剛建立的 Backend ZIP 與 Desktop Installer安裝測試環境，不得只執行 repository source entry point 來代替交付物驗證。

#### Scenario: 從 Backend ZIP 建立測試服務

- **WHEN** Backend ZIP 建立完成
- **THEN** CI MUST 將它展開成暫存 Release、安裝 locked dependencies、執行 Migration並等到 `127.0.0.1:12345/health` 成功

#### Scenario: 從 Installer 安裝 Desktop

- **WHEN** Desktop Installer 建立完成
- **THEN** CI MUST silent install、啟動已安裝 App，並在測試後完成 uninstall

#### Scenario: 驗證已安裝 App 的版本

- **WHEN** CI 已完成 Desktop Installer 的 silent install
- **THEN** CI MUST 從已安裝的 App 讀取 Runtime 版本
- **AND** Runtime 版本、Installer filename、Installer metadata、Candidate manifest 與 `bap_desktop/VERSION` MUST 全部一致
- **AND** 任一版本不一致時 CI MUST 失敗

#### Scenario: 執行真實 HTTP user flow

- **WHEN** 暫存 Backend 與已安裝 Desktop 都可使用
- **THEN** CI MUST 讓 Desktop 透過 `http://127.0.0.1:12345` 驗證註冊、登入、Token refresh、登出、更新檢查及已定義的 API 錯誤

#### Scenario: 測試或清理失敗

- **WHEN** Build、安裝、Migration、啟動、API、Desktop E2E、uninstall 或 cleanup 任一步驟失敗
- **THEN** CI MUST 回報失敗、保留安全 diagnostics，且 MUST NOT 產生可交付 Candidate

### Requirement: 通過的 Candidate 必須可追溯且有期限

CI MUST 將 Backend ZIP、Desktop Installer、checksums、delivery manifest 與 test summary 包成唯一 Candidate，並保存足以讓 Merge 後 CD 找回的識別資料。

#### Scenario: Candidate 上傳成功

- **WHEN** 所有 required tests 通過
- **THEN** manifest MUST 記錄 PR number、head/base/test commit、Source Tree SHA、CI run、scope、版本、檔名、checksums 與 test results

#### Scenario: Candidate 超過保存期限

- **WHEN** CD 找到的 Candidate 已超過 14 天或已被 GitHub 刪除
- **THEN** 系統 MUST 停止 Promotion，且 MUST NOT 在 CD 重新 Build

### Requirement: PR CI 不得接觸 Production

PR CI MUST NOT 讀取 `production-backend` Environment、SSH Private Key、正式 Database 或正式 API 寫入權限。

#### Scenario: PR 來自不受信任的程式碼

- **WHEN** 任一 Pull Request 觸發 CI
- **THEN** Workflow MUST 只授予 Build、Test 與 Candidate upload 所需的最小權限，且不得連線正式 Server
