## 名詞定義

| 名詞 | 定義 |
|---|---|
| Release Metadata | 隨 GitHub Release 發布的 JSON，記錄 Desktop 版本、Source Tree SHA、Installer 檔名與 SHA-256。 |
| Inactive Record | 已寫入 `app_releases` 但更新檢查 API 不會回傳給 user 的版本紀錄。 |
| Active Record | 更新檢查 API 可以回傳給 user 的正式版本紀錄。 |
| Asset Verification | Release 公開後，確認 Installer 與 Metadata 可下載且 checksum 正確的步驟。 |
| Compensation | 發布流程部分失敗時，將未完成版本停止對 user 公開並保留可恢復資訊的處理。 |

## MODIFIED Requirements

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
