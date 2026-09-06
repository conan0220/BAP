## 名詞定義

| 名詞 | 定義 |
|---|---|
| Unit Test | 不需要安裝完整 App，針對單一模組行為執行的自動測試。 |
| Integration Test | 將 Launcher、Updater、Installer 或 Backend 元件組合後執行的自動測試。 |
| Upgrade E2E | 在乾淨 Windows 環境先安裝公開舊版，再更新到 Candidate 的完整測試。 |
| Failure Injection | 在隔離測試環境故意移除必要檔案或阻止啟動，用來驗證 Rollback 的方法。 |
| Sentinel Data | 更新前放進 User Data Root、更新後必須保持不變的測試資料。 |
| Release Activation | 公開 Asset 驗證成功後，讓 Backend update-check API 開始回傳新版本的動作。 |

## 1. 版本狀態與檔案配置

- [x] 1.1 建立 Program Root、User Data Root、版本目錄、staging 與 operation 路徑模型，並用 Unit Test 證明程式檔與 User Data 不會寫到同一位置。
- [x] 1.2 定義並實作 `release-manifest.json` 的 schema、讀寫與驗證，測試版本、Source Tree SHA、入口檔及路徑不合法時會 fail closed。
- [x] 1.3 定義並實作 `active-release.json` 的 schema 與同磁碟原子 replace，測試正常寫入、寫入中斷、JSON 損壞與 active／previous 狀態。
- [x] 1.4 建立 Update Operation 狀態與 log 格式，讓成功、Health Check 失敗、啟動逾時、Rollback 失敗及清理失敗都有可追查結果。

## 2. Stable Launcher 與 App 健康檢查

- [x] 2.1 建立 Stable Launcher 入口，讀取 Active State、驗證 Release Manifest、啟動 active 並完整轉交 command-line arguments。
- [x] 2.2 為 Launcher 加入 previous fallback 與白話修復訊息，測試 active 不存在、manifest 損壞、active 無法啟動及 active／previous 都不可用的情境。
- [x] 2.3 新增 `BAP.exe --post-update-health-check --result-file <path> --isolated-check`，輸出包含版本、Source Tree、各檢查與安全錯誤碼的 JSON。
- [x] 2.4 為 Health Check 加入 Runtime 版本、PySide6／Qt plugin、必要資源、視窗元件與隔離寫入檢查，並用 Failure Injection 覆蓋每種失敗且證明不讀寫正式登入與量測資料。
- [x] 2.5 新增 `--update-operation <id>` Ready Signal，並測試 Qt event loop 成功、程序提早結束與 30 秒逾時三種結果。

## 3. Versioned Updater 與 Rollback

- [x] 3.1 建立 Updater handoff 協定，接收 Installer path、version、SHA-256、舊 PID 與 operation ID，複製 helper 到 User Data Root 後才回報已接手。
- [x] 3.2 加入單一更新工作的 lock 與舊程序等待機制，測試重複更新要求、Updater 未接手、舊程序正常結束與等待逾時。
- [x] 3.3 實作 Candidate 安裝交易，將新版放入獨立版本目錄，並測試安裝成功、安裝中斷與舊版程式檔未被覆蓋。
- [x] 3.4 串接切換前 Health Check，測試檢查失敗時 Active State 完全不變且原版本仍能由 Launcher 啟動。
- [x] 3.5 實作原子切換、由 Launcher 啟動 Candidate 與 Ready Signal 等待，測試成功後 active／previous 與 operation 結果正確。
- [x] 3.6 實作 Candidate 啟動失敗後的自動 Rollback，測試會原子切回 previous、重啟舊版並顯示已恢復訊息。
- [x] 3.7 實作 Rollback 失敗保護，測試不刪除任何 Release、保留 diagnostics，並提供可直接啟動版本路徑的人工修復訊息。
- [x] 3.8 實作舊版本清理器，只刪除未被 active、previous、目前程序或進行中 operation 引用的版本；測試檔案鎖定時只記錄並延後重試。

## 4. Desktop App 更新交接與關閉生命週期

- [x] 4.1 將現有 UpdateInstaller 從直接啟動 Inno Setup 改為驗證下載檔後交給 Updater，並保留下載大小限制、HTTPS、platform 與 SHA-256 驗證。
- [x] 4.2 建立可重入的 Shutdown Coordinator，讓 `closeEvent`、`aboutToQuit` 與更新關閉共用 IMU 停止、worker 等待及檔案 flush 流程。
- [x] 4.3 調整更新 UI 狀態，分別顯示下載中、交接中、安裝失敗、已恢復舊版與需人工修復的白話訊息。
- [x] 4.4 補齊更新服務與 UI 測試，涵蓋 checksum 不符、下載／寫入失敗、Updater 啟動失敗、未收到接手確認及成功 Clean Shutdown。

## 5. Windows Installer 與 Legacy Install 遷移

- [x] 5.1 建立 Launcher 與 Updater 的 Windows executable Build 入口，並讓 Candidate metadata 記錄三個 Runtime 入口與版本資訊。
- [x] 5.2 修改 Inno Setup，把 App payload 放到 `releases\<version>\`、Bootstrap 放在 Program Root，並把桌面與開始功能表捷徑改指向 Stable Launcher。
- [x] 5.3 實作全新安裝 finalization，Candidate 通過 Health Check 後才建立第一份 Active State；測試失敗時沒有半啟用版本。
- [x] 5.4 實作 Legacy Install 偵測、版本讀取、Runtime 複製與 Legacy Release Manifest，並以現行公開 Installer 驗證可成為 previous。
- [x] 5.5 測試 Legacy 複製、版本辨識或啟動驗證失敗時會停止更新、保留原安裝且不要求 user 先解除安裝。
- [x] 5.6 調整 uninstall 與 installer cleanup，只移除 Program Root 的程式與版本狀態，不刪除 User Data Root 或 Windows Credential Manager 資料。
- [x] 5.7 在提交 Desktop source／packaging 修改前提升 `bap_desktop/VERSION`，並驗證 Runtime、Installer filename、metadata 與 Release tag 使用同一版本來源。

## 6. PR CI 的版本升級與 Rollback 驗證

- [x] 6.1 在共用 scope 判定為 Desktop delivery 時，於 PR CI 檢查版本格式與 `desktop-v<version>` 是否已存在；測試 Backend-only scope 不因既有 Desktop 版本失敗。
- [x] 6.2 擴充 Windows Installer smoke test：下載並安裝 Previous Public Version、建立 Sentinel Data，再透過正式 Updater 升級到同一次 CI Build 的 Candidate。
- [x] 6.3 在 Upgrade E2E 驗證 Stable Launcher 啟動 Candidate、所有版本資訊一致、安裝版 HTTP user flow 通過且 Sentinel Data 保持不變。
- [x] 6.4 在另一個隔離環境對同一 Candidate 做 Failure Injection，驗證 Health Check 或 Ready Signal 失敗後會啟動 previous 且 Sentinel Data 保持不變。
- [x] 6.5 加入沒有 Previous Public Version 時的全新安裝分支，並在 test summary 明確記錄跳過跨版本測試的原因。
- [x] 6.6 確保 Upgrade、Rollback、uninstall 或 cleanup 任一步驟失敗時，PR check 失敗、上傳安全 logs，且不發布可供 CD 使用的 Candidate。
- [x] 6.7 更新 Workflow contract tests，驗證 PR CI 不取得 Production secrets、不重新 Build 測試專用 Installer，且 CD 仍保留重複版本檢查。

## 7. GitHub Release Metadata 與 Backend 啟用

- [x] 7.1 定義 Release Metadata JSON schema，從 Candidate manifest 產生 version、platform、architecture、Installer filename／size／SHA-256、Source Tree SHA、CI run 與建立時間。
- [x] 7.2 擴充 Candidate／CD 驗證，任何 Runtime、Installer、Candidate manifest、Release Metadata 或 `bap_desktop/VERSION` 不一致時都停止發布。
- [x] 7.3 擴充 Backend app release 工具，支援建立 inactive record，以及在單一 Database transaction 中啟用新版本並停用舊版本。
- [x] 7.4 補齊 update-check API 與 repository tests，證明 inactive 不會回傳、啟用成功只回傳新版本、啟用失敗仍回傳舊版本。
- [x] 7.5 調整 CD 順序為 Draft + Assets → inactive record → publish → 公開 Asset 下載與 SHA 驗證 → atomic activate，且 Release 必須包含 EXE、SHA256 與 Metadata。
- [x] 7.6 實作並測試 GitHub publish、Asset Verification 或 Database activation 失敗時的補償，確保新紀錄保持 inactive、舊紀錄仍可用，補償失敗時輸出 Release URL 與人工修復方式。
- [x] 7.7 更新 Workflow contract tests，確認 Desktop 與 Backend 同時變更時仍先完成 Backend promotion，再公開並啟用 Desktop Release。

## 8. 文件與整體驗證

- [x] 8.1 更新根目錄 README 與 Windows 發布指南，用白話說明 Versioned Release 結構、正常更新、Rollback、logs 位置與人工修復流程。
- [x] 8.2 執行 Desktop unit／Qt／integration tests、Backend tests、Installer smoke tests、Workflow contract tests與 OpenSpec scenario coverage，修正所有失敗。
- [x] 8.3 在乾淨 Windows 使用者環境完成現行公開版 → Candidate 的 Upgrade E2E，確認不需解除安裝、User Data 保留且新版由 Stable Launcher 啟動。
- [x] 8.4 在乾淨 Windows 使用者環境完成 Candidate 故障 Rollback E2E，確認 previous 自動恢復、可正常啟動且 diagnostics 足以排查。
- [x] 8.5 將 feature branch push 到 GitHub，確認 required PR CI 通過、Candidate 可追溯，並人工 Merge 後確認 CD 使用同一份 Candidate 完成 Release Metadata 發布與 update-check 啟用。
