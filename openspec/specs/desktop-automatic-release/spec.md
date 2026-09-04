## 名詞定義

| 名詞 | 定義 |
|---|---|
| Desktop Candidate | PR CI 建立並完成安裝測試的 BAP Windows Installer。 |
| GitHub Release | user 可從 GitHub 下載指定 Desktop 版本 Installer 的發布頁面。 |
| Draft Release | 尚未公開給 user、可先加入 Asset 與 metadata 的 GitHub Release。 |
| app_releases | Backend Database 中提供 Desktop 更新檢查所需的版本紀錄。 |

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

Desktop version、tag、Installer、Source Tree SHA 與 Promotion record MUST 形成唯一對應。

#### Scenario: 發布新版本

- **WHEN** Candidate version 尚未被使用且 metadata 完整
- **THEN** 系統 MUST 建立 `desktop-v<version>` Release，附加 Installer、checksum與來源資訊

#### Scenario: Version 或 tag 已存在

- **WHEN**相同 version 或 tag 已對應不同 checksum／Source Tree
- **THEN** CD MUST fail closed，不得覆寫既有 Release

### Requirement: Backend-first 必須保護 Desktop user

當同一 scope 同時變更 Backend 與 Desktop 時，新 Desktop MUST 在相容 Backend 部署成功後才公開。

#### Scenario: Backend Health 成功

- **WHEN** Backend Promotion、Scheduled Task、local與 public Health 全部成功
- **THEN** CD MAY 將 Draft Release 公開

#### Scenario: Backend Promotion 失敗

- **WHEN** Backend 部署或 Rollback 未得到可用 Production
- **THEN** Draft Release MUST 保持未公開或被移除，user MUST NOT 收到新版本

### Requirement: 發布後必須更新 App Release 資訊

GitHub Release 成功公開後，系統 MUST 建立對應 `app_releases` 紀錄，讓 Desktop update-check API 回傳可下載資訊。

#### Scenario: Release 與 app_releases 都成功

- **WHEN** Release Asset 已可下載且 Database 紀錄建立成功
- **THEN** update-check API MUST 回傳 version、下載 URL、Source Tree SHA 與 checksum

#### Scenario: app_releases 寫入失敗

- **WHEN** GitHub Release 已建立但 Database 更新失敗
- **THEN** CD MUST 回報部分失敗並執行定義好的補償，不得宣告完整 success

### Requirement: Cutover 後不得保留重複 Desktop Build Workflow

新的 PR CI 上線後，舊 Desktop-only Workflow MUST 被移除，避免相同 commit 產生兩個來源不同的 Installer。

#### Scenario: Repository Workflow contract test

- **WHEN** 自動測試檢查 `.github/workflows`
- **THEN** MUST 只有新 PR CI 負責 Candidate Desktop Build，`build-desktop.yml` MUST 不存在
