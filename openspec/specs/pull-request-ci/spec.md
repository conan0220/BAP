## 名詞定義

| 名詞 | 定義 |
|---|---|
| Pull Request | 將 feature branch 的修改送交檢查，準備合併到 `master` 的 GitHub 變更請求。 |
| Test Merge Tree | GitHub 將 PR 內容暫時套到最新 `master` 後得到的完整檔案樹。 |
| docs-only | 只修改文件，不會改變程式、Build、部署或 Workflow 行為的 PR。 |
| Production-like E2E | 在乾淨 Runner 從實際 Artifact 安裝前後端，再透過真正 HTTP API 驗證 user flow。 |
| Desktop 版本來源 | `bap_desktop/VERSION`，是 Desktop Installer、Candidate metadata 與 App 執行時版本的唯一來源。 |
| Runtime 版本 | CI 安裝並啟動 Candidate 後，由 App 本身回報的 Desktop 版本。 |
| Previous Public Version | GitHub Release 上目前可供 user 下載的上一個 Desktop 正式版本。 |
| Candidate | 同一次 PR CI 建立並驗證、尚未正式發布的 Backend ZIP、Desktop Installer、checksums、manifest 與 test summary。 |
| Upgrade Test | 先安裝 Previous Public Version，再透過正式更新入口更新到 Candidate 的測試。 |
| Rollback Test | 故意讓 Candidate 的 Health Check 或啟動失敗，確認系統會恢復 Previous Public Version 的測試。 |
| Sentinel Data | CI 在 User Data Root 建立的測試資料，用來確認更新與 Rollback 沒有破壞 user 資料。 |
| Desktop Delivery Scope | 共用變更範圍規則判定這次 PR 是否需要發布新的 Desktop 版本。 |
| Punch-count Benchmark | 固定版本、包含左右手 Common IMU CSV 與人工 Ground Truth 的測試資料集。 |
| Benchmark ZIP | Benchmark Recorder 匯出的自包含測試檔，內含 `metadata.json` 與兩份 Common IMU CSV。 |
| 回歸 | 修改後的演算法讓原本通過的 Benchmark case 產生錯誤結果。 |
| Source-level Benchmark test | 直接從 repository 載入 Executor 與 fixtures，不經 Installer 或正式 Server 的 pytest。 |

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

CI MUST 從剛建立的 Backend ZIP 與 Desktop Installer 安裝測試環境，不得只執行 repository source entry point 來代替交付物驗證。當 Desktop Delivery Scope 為 true 且已有 Previous Public Version 時，CI MUST 另外使用真實 Installer 驗證跨版本升級與 Rollback。

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

#### Scenario: 從公開舊版升級到 Candidate

- **WHEN** Desktop Delivery Scope 為 true 且存在 Previous Public Version
- **THEN** CI MUST 先安裝 Previous Public Version
- **AND** CI MUST 在 User Data Root 建立 Sentinel Data
- **AND** CI MUST 透過正式更新入口安裝同一次 CI 建立的 Candidate
- **AND** Stable Launcher MUST 啟動 Candidate 版本
- **AND** Sentinel Data MUST 保持不變
- **AND** Previous Public Version MUST 仍可供 Rollback

#### Scenario: Candidate 故障時自動 Rollback

- **WHEN** CI 在隔離測試環境使 Candidate 的 Health Check 或切換後啟動確認失敗
- **THEN** Updater MUST 恢復 Previous Public Version
- **AND** Stable Launcher MUST 再次啟動 Previous Public Version
- **AND** Sentinel Data MUST 保持不變
- **AND** 測試 MUST 使用同一個 Candidate Artifact，而不是另外 Build 測試專用 Installer

#### Scenario: 尚無 Previous Public Version

- **WHEN** 專案尚未發布任何可供升級測試的 Desktop 版本
- **THEN** CI MUST 完成 Candidate 的全新安裝、Health Check 與啟動測試
- **AND** CI MUST 在 test summary 註明沒有執行跨版本測試的原因

#### Scenario: 測試或清理失敗

- **WHEN** Build、安裝、Migration、啟動、API、Desktop E2E、Upgrade、Rollback、uninstall 或 cleanup 任一步驟失敗
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

### Requirement: 需要發布 Desktop 的 PR 必須在 Merge 前檢查版本可用性
當 Desktop Delivery Scope 為 true 時，PR CI MUST 確認 `bap_desktop/VERSION` 符合版本格式，且相同的 GitHub Release tag 尚未被其他 Source Tree 使用。CD MUST 保留相同檢查作為最後一道防線。

#### Scenario: PR 使用新的 Desktop 版本
- **WHEN** PR 需要交付 Desktop 且 `desktop-v<version>` 尚不存在
- **THEN** PR CI 繼續建立與測試 Candidate

#### Scenario: PR 重複使用已發布版本
- **WHEN** PR 需要交付 Desktop 且相同 tag 已對應既有 Release
- **THEN** PR CI 失敗並提示開發者提升 `bap_desktop/VERSION`
- **AND** 開發者不必等到 Merge 後才知道版本衝突

#### Scenario: Backend-only PR 沒有提升 Desktop 版本
- **WHEN** 共用範圍規則判定 PR 不需要交付 Desktop
- **THEN** PR CI 不因目前 Desktop 版本已發布而失敗

### Requirement: Source-level CI 必須執行出拳次數 Benchmark
非 docs-only PR 的 source-level tests MUST 對 repository 內所有已核准的 Punch-count Benchmark cases 執行 Production `punch_count` Executor，並分別比較左手、右手與總拳數。任一 case 與 Ground Truth 不符時，CI MUST 失敗。

#### Scenario: 所有 Benchmark cases 計算正確
- **WHEN** Production Executor 對每個固定 case 都產生與 Ground Truth 相同的左右手與總拳數
- **THEN** Punch-count Benchmark test 通過
- **AND** CI 可以繼續執行後續 Candidate Build 與 Artifact E2E

#### Scenario: 任一手的拳數發生回歸
- **WHEN** 任一 case 的左手、右手或總拳數與 Ground Truth 不同
- **THEN** pytest 回報失敗並指出 case ID、預期值與實際值
- **AND** CI MUST NOT 將該次 Candidate 視為可交付

### Requirement: Benchmark 內容必須可追溯且不被測試修改
每個 case MUST 使用既有的自包含 Benchmark ZIP 契約，並具有固定 case ID、Benchmark schema version、左右手 CSV、Ground Truth 與檔案完整性資訊。CI MUST 直接載入 Repository 中的 ZIP，不得要求另一份跨案例 Manifest。測試 MUST 以唯讀方式使用 fixtures，且重複執行 MUST 產生相同結果。

#### Scenario: 同一 commit 重跑 Benchmark
- **WHEN** CI 對相同 Source Tree 重複執行 Punch-count Benchmark
- **THEN** 測試使用相同 fixtures 與 Ground Truth
- **AND** 產生相同通過或失敗結果

#### Scenario: Fixture 缺少必要內容
- **WHEN** case 缺少任一手 CSV、Ground Truth、schema version 或完整性資訊
- **THEN** pytest 將該 case 視為無效並失敗
- **AND** 不略過該 case 或以零拳代替

#### Scenario: CI 載入既有 Benchmark ZIP
- **WHEN** CI 掃描 `tests/fixtures/punch_count/` 中已核准的 Benchmark ZIP
- **THEN** 共用 Loader 從每份 ZIP 的 `metadata.json` 取得 CSV、Ground Truth 與完整性資訊
- **AND** CI 不需要另外產生或維護第二份 Manifest
