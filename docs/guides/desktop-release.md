# BAP Desktop 自動發布

## 名詞定義

| 名詞 | 定義 |
|---|---|
| Candidate | PR CI 已 Build 並測試完成的 Artifact。 |
| Draft Release | 尚未公開、可在 metadata 寫入失敗時安全保留的 GitHub Release。 |
| app_releases | Backend 提供 Desktop 更新檢查的資料表。 |

Desktop 正式發布不再由開發者人工執行 Publisher。

~~~mermaid
flowchart LR
    A["PR CI 建立 Installer"] --> B["安裝後 E2E"]
    B --> C["Candidate 保存 14 天"]
    C --> D["人工 Merge"]
    D --> E["CD 驗證同一份 Installer"]
    E --> F["建立 Draft Release"]
    F --> G["寫入 app_releases"]
    G --> H["公開 desktop-v<version> Release"]
~~~

規則：

1. `bap_desktop/VERSION` 是 Desktop 唯一版本來源，必須是新的 semantic version；Installer、GitHub Release 與 App 執行時顯示的版本都從這裡產生。
2. desktop-v<version> tag 不可已存在。
3. Release asset checksum 與 Source Tree SHA 必須和 Candidate 一致。
4. 同時修改 Backend 時，Backend promotion 與 Health Check 必須先成功。
5. app_releases 寫入失敗時，Release 保持 Draft。
6. Prototype 尚未 Code Signing，Windows 可能顯示 SmartScreen 警告。

## user 在 App 內更新

Desktop App 發現新版後會顯示「立即更新」。user 按下後，App 會在背景下載 GitHub Release 的 Installer，使用 Backend 提供的 SHA-256 驗證檔案，接著啟動靜默覆蓋安裝並關閉目前版本。安裝完成後，Installer 會重新啟動新版 BAP。user 不需要先解除安裝，也不需要自行開啟 GitHub Release。

下載、checksum 驗證或 Installer 啟動失敗時，App 不會修改現有安裝，user 可以繼續使用目前版本並稍後重試。

Build 與 Smoke Test scripts 仍可供除錯，但不再是人工正式發布流程。
