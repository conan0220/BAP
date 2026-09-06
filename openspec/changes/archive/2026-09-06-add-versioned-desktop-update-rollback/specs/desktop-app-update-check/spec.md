## 名詞定義

| 名詞 | 定義 |
|---|---|
| Installer | Desktop App 從可信 HTTPS 位置下載的 Windows 安裝檔。 |
| Updater | 將已驗證 Installer 安裝成獨立版本並處理版本切換的程式。 |
| Clean Shutdown | Desktop App 停止 IMU、背景工作與檔案寫入後正常結束的流程。 |
| Active Release | user 目前透過 Stable Launcher 啟動的 Desktop 版本。 |
| SHA-256 | 用來確認下載檔內容與發布資訊完全一致的雜湊值。 |

## ADDED Requirements

### Requirement: App 必須先驗證 Installer 再交由 Updater 安裝
Desktop App MUST 使用更新資訊中的 SHA-256 驗證下載完成的 Installer；只有驗證成功，才能要求 Updater 將 Candidate 安裝到獨立版本目錄並執行 Health Check、切換與必要的 Rollback。

#### Scenario: Installer 通過完整性驗證
- **WHEN** Installer 下載完成且實際 SHA-256 等於更新資訊中的 SHA-256
- **THEN** Desktop App 啟動獨立 Updater
- **AND** Updater 將 Candidate 安裝到新的版本目錄
- **AND** Updater 不直接覆蓋 Active Release 的程式檔

#### Scenario: Installer checksum 不符
- **WHEN** Installer 的實際 SHA-256 不等於更新資訊中的 SHA-256
- **THEN** Desktop App 刪除未通過驗證的下載檔
- **AND** Desktop App 不啟動 Updater
- **AND** 現有版本可以繼續使用

#### Scenario: 更新下載或 Updater 啟動失敗
- **WHEN** Installer 無法下載、寫入、驗證或交給 Updater
- **THEN** Desktop App 顯示簡短的更新失敗訊息
- **AND** Active Release 與 User Data 不受影響

### Requirement: Desktop App 必須乾淨交接更新程序
Desktop App MUST 在 Updater 確認已接手更新後執行 Clean Shutdown，停止 IMU 連線、背景工作與檔案寫入；不得只直接結束 Qt 程序而略過既有的關閉清理流程。

#### Scenario: Updater 成功接手
- **WHEN** user 選擇立即更新且 Updater 已成功啟動並確認收到更新工作
- **THEN** Desktop App 執行與正常關閉相同的資源清理
- **AND** Desktop App 完成清理後結束
- **AND** Updater 等待舊程序結束後再安裝 Candidate

#### Scenario: Updater 未成功接手
- **WHEN** Desktop App 無法啟動 Updater 或沒有收到接手確認
- **THEN** Desktop App 保持運行
- **AND** Desktop App 顯示更新尚未開始
- **AND** 系統不得關閉目前版本

## REMOVED Requirements

### Requirement: App 必須先驗證 Installer 再覆蓋安裝

**Reason**: 直接覆蓋目前安裝目錄無法在安裝或啟動失敗時可靠保留舊版，也可能留下新版與舊版混合的程式檔。

**Migration**: 保留原本的下載與 SHA-256 驗證行為，但驗證成功後改交由 Updater 安裝到獨立版本目錄；版本切換與 Rollback 由 `desktop-versioned-update-rollback` 規範。
