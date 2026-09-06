## 名詞定義

| 名詞 | 定義 |
|---|---|
| Previous Public Version | GitHub Release 上目前可供 user 下載的上一個 Desktop 正式版本。 |
| Candidate | 這次 PR CI 建立、尚未正式發布的新 Desktop Installer。 |
| Upgrade Test | 先安裝 Previous Public Version，再透過正式更新入口更新到 Candidate 的測試。 |
| Rollback Test | 故意讓 Candidate 的 Health Check 或啟動失敗，確認系統會恢復 Previous Public Version 的測試。 |
| Sentinel Data | CI 在 User Data Root 建立的測試資料，用來確認更新與 Rollback 沒有破壞 user 資料。 |
| Desktop Delivery Scope | 共用變更範圍規則判定這次 PR 是否需要發布新的 Desktop 版本。 |

## ADDED Requirements

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

## MODIFIED Requirements

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
