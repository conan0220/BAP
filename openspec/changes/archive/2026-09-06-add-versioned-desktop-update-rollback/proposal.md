## 名詞定義

| 名詞 | 定義 |
|---|---|
| Versioned Release | 安裝在獨立版本資料夾中的一份完整 Desktop App，例如 `releases\0.1.7\`。 |
| Active Release | user 下一次啟動 BAP 時，穩定入口會開啟的版本。 |
| Stable Launcher | 不隨 App 版本更換的啟動程式，負責讀取 Active Release 並啟動對應的 BAP。 |
| Updater | 負責下載、驗證、安裝、檢查、切換與必要時回復版本的更新程式。 |
| Health Check | 切換版本前執行的本機檢查，用來確認新版可以啟動並載入必要元件。 |
| Rollback | 新版無法通過檢查或啟動時，將 Active Release 切回上一個可用版本。 |
| User Data | settings、登入狀態、logs、量測資料與更新暫存檔等不應隨程式版本被覆蓋的資料。 |
| Release Metadata | 說明版本、檔名、SHA-256、Source Tree SHA 與下載位置的機器可讀檔案。 |

## Why

目前 Desktop App 以同一個安裝目錄直接覆蓋舊版；若安裝中斷、新版無法啟動或舊檔沒有被清掉，user 可能同時失去新版與原本可用的版本。這個 Change 要讓新版先在獨立目錄完成安裝與檢查，再切換成正式版本，失敗時可以自動回到上一個可用版本。

## What Changes

- 每個 Desktop 版本安裝到自己的版本資料夾，不再直接覆蓋目前正在使用的程式檔。
- 提供固定的 Stable Launcher／Updater；桌面捷徑與開始功能表捷徑都指向固定入口。
- Updater 下載 Installer 後先驗證 SHA-256，再將新版安裝到新的版本資料夾。
- 新版通過本機 Health Check 後，系統才以原子方式切換 Active Release。
- 切換後若新版無法正常啟動，系統自動切回上一個已驗證版本並顯示白話錯誤。
- User Data 繼續存放在程式安裝目錄以外，升級與 Rollback 都不得刪除或改寫這些資料。
- 系統保留目前版本與上一個成功版本，並安全清除更舊且不再使用的版本。
- PR CI 以「已公開舊版 → Candidate 新版」執行真實升級測試，並驗證資料保留、版本切換與 Rollback。
- PR CI 提前檢查 Desktop version 是否已存在，CD 仍保留最後一道重複版本防線。
- GitHub Release 附上 Release Metadata；Backend 只在公開 Asset 可下載後才啟用對應的 `app_releases` 紀錄，失敗時必須執行補償。

## Capabilities

### New Capabilities

- `desktop-versioned-update-rollback`: 規範 Desktop App 的版本資料夾、固定啟動入口、更新前檢查、版本切換、自動 Rollback、User Data 保護與舊版本清理。

### Modified Capabilities

- `desktop-app-update-check`: 將目前的「靜默覆蓋安裝」改為「下載後交由 Versioned Updater 安裝、驗證及切換」，並要求 App 在交接更新前乾淨結束。
- `pull-request-ci`: 加入真實版本升級與 Rollback 測試，並在 Merge 前檢查 Desktop version 是否可發布。
- `desktop-automatic-release`: GitHub Release 必須發布 Release Metadata，且 `app_releases` 只能在公開 Asset 可下載後啟用；部分失敗時要有明確補償。

## Impact

- 主要影響 `bap_desktop` 的更新服務、App 關閉流程與啟動參數。
- Windows packaging 需要加入 Stable Launcher、Updater、版本化安裝目錄及版本清理行為。
- Desktop 捷徑的目標會從特定版本的 `BAP.exe` 改成固定 Launcher。
- PR CI 的 Installer smoke test 會增加跨版本升級、User Data 保存與故障 Rollback 測試。
- CD 的 Desktop Release 步驟會多發布 Metadata，並調整 GitHub Release 與 Backend `app_releases` 的啟用順序。
- Backend 版本仍使用 Git SHA 識別；本 Change 不改變 Backend 部署版本規則。
