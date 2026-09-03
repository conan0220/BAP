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

1. bap_desktop\VERSION 必須是新的 semantic version。
2. desktop-v<version> tag 不可已存在。
3. Release asset checksum 與 Source Tree SHA 必須和 Candidate 一致。
4. 同時修改 Backend 時，Backend promotion 與 Health Check 必須先成功。
5. app_releases 寫入失敗時，Release 保持 Draft。
6. Prototype 尚未 Code Signing，Windows 可能顯示 SmartScreen 警告。

Build 與 Smoke Test scripts 仍可供除錯，但不再是人工正式發布流程。
