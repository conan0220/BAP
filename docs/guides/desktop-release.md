# BAP Desktop 發布、更新與 Rollback

## 名詞定義

| 名詞 | 定義 |
|---|---|
| Candidate | PR CI 建立且完成安裝、HTTP、升級與 Rollback 測試的交付檔。 |
| Stable Launcher | 捷徑固定指向的 `BAPLauncher.exe`；它依啟用狀態選擇真正要開啟的 App 版本。 |
| Updater | 下載完成後負責安裝、檢查、切換與必要時恢復舊版的 `BAPUpdater.exe`。 |
| Active Release | 目前應由 Stable Launcher 啟動的版本。 |
| Previous Release | 新版失敗時可立刻恢復的上一個可用版本。 |
| User Data Root | `%LOCALAPPDATA%\BAP`；保存設定、logs、量測資料與更新診斷。 |

## user 電腦上的目錄

~~~text
%LOCALAPPDATA%\Programs\BAP\
├─ BAPLauncher.exe
├─ launcher_runtime\
├─ BAPUpdater.exe
├─ updater_runtime\
├─ active-release.json
└─ releases\
   ├─ 0.1.6\
   │  ├─ BAP.exe
   │  └─ release-manifest.json
   └─ 0.1.7\
      ├─ BAP.exe
      └─ release-manifest.json

%LOCALAPPDATA%\BAP\
├─ logs\
├─ measurement-sessions\
├─ temp\
└─ updates\<operation-id>\
   ├─ operation.json
   ├─ health.json
   └─ ready.json
~~~

程式目錄可以重新安裝；User Data Root 不會因更新、Rollback 或解除安裝程式版本而刪除。Windows Credential Manager 內的登入資料也不由 Installer 清除。

## user 在 App 內更新

~~~mermaid
flowchart LR
    A["user 按立即更新"] --> B["下載 Installer 並驗證 SHA-256"]
    B --> C["Updater 確認接手"]
    C --> D["App 停止 IMU、worker 與檔案寫入後關閉"]
    D --> E["Installer 放置獨立 Candidate 目錄"]
    E --> F{"離線 Health Check"}
    F -->|失敗| OLD["保留並開啟舊版"]
    F -->|成功| G["原子切換 Active Release"]
    G --> H{"新版 30 秒內送出 Ready Signal"}
    H -->|成功| OK["保留新版與上一版"]
    H -->|失敗| RB["自動切回並開啟上一版"]
~~~

user 不需要先解除安裝，也不需要自行到 GitHub 下載。從舊式覆蓋安裝第一次升級時，Updater 會先複製並驗證現有版本；無法建立可用副本時會停止更新，不會先破壞原安裝。

## PR CI 與正式發布

### Installer Smoke Test

PR CI 會先用 Candidate Installer 做全新安裝測試；若已有公開舊版，也會實際安裝舊版，再透過正式 Updater 升級並故意製造一次啟動失敗，以確認自動 Rollback 與 User Data 保護都正常。

1. 只有 Desktop delivery 變更時，CI 才檢查 `bap_desktop/VERSION` 與 `desktop-v<version>` 是否重複。
2. CI 建立 Backend ZIP、BAP Installer、checksum 與 Release Metadata。
3. 若有公開舊版，CI 先安裝舊版，再用同一份 Candidate 測試升級、Sentinel Data 保存與故障 Rollback；沒有舊版時明確記錄只跑全新安裝。
4. 所有測試通過後，Candidate 保存 14 天；CD 不重新 Build。
5. 人工 Merge 後，CD 建立 Draft Release，附上 EXE、SHA256 與 Metadata。
6. Backend 先建立 inactive `app_releases` 紀錄；GitHub Release 公開且 Asset 可重新下載驗證後，才原子啟用新紀錄。
7. 發布或啟用失敗時，新紀錄保持 inactive，CD 嘗試把未完成 Release 轉回 Draft 或移除。

Desktop 唯一版本來源是 `bap_desktop/VERSION`。Backend 版本仍以 Git SHA 識別。

## 問題排查與人工修復

先查看：

- `%LOCALAPPDATA%\BAP\logs\bap-launcher.log`
- `%LOCALAPPDATA%\BAP\updates\<operation-id>\operation.json`
- 同一目錄的 `health.json`、`candidate-launch.json` 或 `rollback-launch.json`

一般處理順序：

1. `operation.json` 顯示 `rolled_back`：系統已恢復上一版，可直接繼續使用並回報該 operation 資料夾。
2. 顯示 `health_failed` 或 `install_failed`：Active Release 未被新版取代；重新開啟桌面捷徑即可。
3. 顯示 `rollback_failed`：不要刪除 `releases`。依 `operation.json` 內的完整路徑直接執行上一版 `BAP.exe`，再重新執行最新正式 Installer 修復 Stable Launcher 與狀態。
4. `active-release.json` 損壞且 Launcher 無法開啟任何版本：保留 User Data Root，重新執行最新正式 Installer；不要先解除安裝或刪除量測資料。

Prototype 尚未強制 Code Signing，因此 Windows 可能顯示 SmartScreen 警告。
