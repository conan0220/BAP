## 名詞定義

| 名詞 | 定義 |
|---|---|
| Desktop Candidate | PR CI 建立並完成安裝測試的 BAP Windows Installer。 |
| GitHub Release | user 可從 GitHub 下載指定 Desktop 版本 Installer 的發布頁面。 |
| Draft Release | 尚未公開給 user、可先加入 Asset 與 metadata 的 GitHub Release。 |
| app_releases | Backend Database 中提供 Desktop 更新檢查所需的版本紀錄。 |
| Desktop 版本來源 | `bap_desktop/VERSION`，是 Desktop Installer、GitHub Release tag 與 App 執行時版本的唯一來源。 |
| Runtime 版本 | user 實際啟動已安裝 App 時，App 回報的 Desktop 版本。 |
| Release Metadata | 隨 GitHub Release 發布的 JSON，記錄 Desktop 版本、Source Tree SHA、Installer 檔名與 SHA-256。 |
| Inactive Record | 已寫入 `app_releases` 但更新檢查 API 不會回傳給 user 的版本紀錄。 |
| Active Record | 更新檢查 API 可以回傳給 user 的正式版本紀錄。 |
| Asset Verification | Release 公開後，確認 Installer 與 Metadata 可下載且 checksum 正確的步驟。 |
| Compensation | 發布流程部分失敗時，將未完成版本停止對 user 公開並保留可恢復資訊的處理。 |

## Purpose

確保 BAP Desktop App 發布到 GitHub Release 的 Installer，就是 Pull Request CI 已實際安裝並通過前後端 E2E 的同一個檔案，而且 user 能透過更新檢查取得正確版本資訊。

## Requirements

### Requirement: Desktop Release 必須使用同一個 CI Installer

CD MUST 從 Candidate 取得 CI 已驗證的 Installer 與 checksum，且 MUST NOT 重新 Build、重新簽出另一份 source 或替換 EXE。

#### Scenario: Desktop-only Promotion

- **WHEN** verified scope 只包含 Desktop
- **THEN** CD MUST 將 Candidate 中的同一個 Installer 送入 Draft Release

#### Scenario: Installer checksum 不同

- **WHEN** Release 前計算的 SHA256 與 Candidate manifest 不同
- **THEN** CD MUST 停止，且 MUST NOT 發布 Release

### Requirement: 每個 Desktop 版本必須唯一且可追溯

Desktop version、tag、Installer、Runtime 版本、Release Metadata、Source Tree SHA 與 Promotion record MUST 形成唯一對應。Desktop version MUST 讀取 `bap_desktop/VERSION`，不得從 `pyproject.toml` 或其他 Desktop source code 取得另一個版本號。Backend Release MUST 繼續使用 Git SHA 識別。

#### Scenario: 發布新版本

- **WHEN** Candidate version 尚未被使用且 metadata 完整
- **THEN** 系統 MUST 使用 `bap_desktop/VERSION` 建立 `desktop-v<version>` Release
- **AND** Installer filename、Installer metadata、Release Metadata 與 Release tag MUST 使用相同版本
- **AND** Release MUST 附加 Installer、checksum、Release Metadata 與來源資訊

#### Scenario: Candidate 版本不一致

- **WHEN** Candidate manifest、Installer filename、Installer metadata、Release Metadata 或 Runtime 版本與 `bap_desktop/VERSION` 不一致
- **THEN** CD MUST 停止發布
- **AND** CD MUST NOT 自行猜測或改寫版本號

#### Scenario: Version 或 tag 已存在

- **WHEN**相同 version 或 tag 已對應不同 checksum／Source Tree
- **THEN** CD MUST fail closed，不得覆寫既有 Release

#### Scenario: Release Metadata 無法驗證

- **WHEN** Release Metadata 缺少必要欄位，或其中的 Installer SHA-256 與 Candidate 不同
- **THEN** CD MUST 停止發布
- **AND** 不得啟用對應的 `app_releases` 紀錄

### Requirement: Backend-first 必須保護 Desktop user

當同一 scope 同時變更 Backend 與 Desktop 時，新 Desktop MUST 在相容 Backend 部署成功後才公開。

#### Scenario: Backend Health 成功

- **WHEN** Backend Promotion、Scheduled Task、local與 public Health 全部成功
- **THEN** CD MAY 將 Draft Release 公開

#### Scenario: Backend Promotion 失敗

- **WHEN** Backend 部署或 Rollback 未得到可用 Production
- **THEN** Draft Release MUST 保持未公開或被移除，user MUST NOT 收到新版本

### Requirement: 發布後必須更新 App Release 資訊

系統 MUST 先建立不會被更新檢查 API 回傳的 Inactive Record，再公開 GitHub Release；只有公開 Installer 與 Release Metadata 通過 Asset Verification 後，系統才能原子啟用新紀錄並停用上一筆紀錄。

#### Scenario: Release 與 app_releases 都成功

- **WHEN** Inactive Record 已建立
- **AND** GitHub Release 已公開
- **AND** 公開 Installer 與 Release Metadata 可下載且 checksum 正確
- **AND** Database 啟用操作成功
- **THEN** update-check API MUST 回傳新版本的 version、下載 URL、Source Tree SHA 與 checksum
- **AND** 上一個 Active Record 不再被當成最新版本回傳

#### Scenario: GitHub Release 公開失敗

- **WHEN** Inactive Record 已建立但 GitHub Release 無法公開
- **THEN** 新紀錄 MUST 保持 inactive
- **AND** update-check API MUST 繼續回傳上一個可用版本
- **AND** CD MUST 回報失敗

#### Scenario: 公開 Asset 驗證失敗

- **WHEN** GitHub Release 已公開但 Installer 或 Release Metadata 無法下載或 checksum 不符
- **THEN** 新紀錄 MUST 保持 inactive
- **AND** CD MUST 嘗試將 Release 恢復為 Draft 或移除
- **AND** 若補償失敗，CD MUST 清楚回報需人工處理的 Release 與版本
- **AND** update-check API MUST 繼續回傳上一個可用版本

#### Scenario: app_releases 啟用失敗

- **WHEN** 公開 Asset 已驗證但 Database 無法啟用新紀錄
- **THEN** CD MUST 不宣告完整成功
- **AND** 新紀錄 MUST 不得被更新檢查 API 回傳
- **AND** CD MUST 嘗試將 GitHub Release 恢復為 Draft 或移除
- **AND** 上一個 Active Record MUST 保持可用

### Requirement: Cutover 後不得保留重複 Desktop Build Workflow

新的 PR CI 上線後，舊 Desktop-only Workflow MUST 被移除，避免相同 commit 產生兩個來源不同的 Installer。

#### Scenario: Repository Workflow contract test

- **WHEN** 自動測試檢查 `.github/workflows`
- **THEN** MUST 只有新 PR CI 負責 Candidate Desktop Build，`build-desktop.yml` MUST 不存在
