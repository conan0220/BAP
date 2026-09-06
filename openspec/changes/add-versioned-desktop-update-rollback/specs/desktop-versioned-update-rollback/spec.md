## 名詞定義

| 名詞 | 定義 |
|---|---|
| Program Root | BAP 程式安裝的根目錄：`%LOCALAPPDATA%\Programs\BAP`。 |
| Versioned Release | 放在 `releases\<version>\` 的一份完整 Desktop App。 |
| Active Release | Stable Launcher 目前應啟動的 Versioned Release。 |
| Previous Release | 最近一個已通過驗證、可在新版失敗時恢復使用的版本。 |
| Stable Launcher | user 透過桌面或開始功能表啟動 BAP 時所使用的固定入口。 |
| Updater | 負責安裝 Candidate、執行檢查、切換版本與 Rollback 的程式。 |
| Health Check | 在不依賴遠端 Backend 的情況下，確認 Candidate 能載入必要執行環境與 UI 資源的檢查。 |
| Ready Signal | 新版切換後成功啟動並進入可操作事件迴圈時產生的確認訊號。 |
| Rollback | 新版失敗時，將 Active Release 恢復成 Previous Release。 |
| User Data Root | `%LOCALAPPDATA%\BAP`，保存設定、登入資訊、logs、量測資料與更新暫存檔。 |

## Purpose

讓 Windows Desktop App 以彼此隔離的版本目錄完成更新，只有通過檢查的新版才會成為正式啟動版本；若新版無法正常工作，系統能自動回到上一個可用版本並保護 user 資料。

## ADDED Requirements

### Requirement: 每個 Desktop 版本必須安裝在獨立目錄
系統 MUST 將每個 Desktop 版本的程式檔安裝在 `Program Root\releases\<version>\`，且安裝 Candidate 時 MUST NOT 覆蓋目前 Active Release 的程式檔。

#### Scenario: 從既有版本安裝新版
- **WHEN** user 從版本 0.1.6 更新到 0.1.7
- **THEN** 0.1.7 的程式檔安裝在 `releases\0.1.7\`
- **AND** `releases\0.1.6\` 在新版確認成功前仍可使用

#### Scenario: Candidate 安裝中斷
- **WHEN** Candidate 尚未完整安裝就發生錯誤
- **THEN** Active Release 保持不變
- **AND** user 仍可啟動原本版本

### Requirement: user 必須透過固定入口啟動 Active Release
桌面捷徑與開始功能表捷徑 MUST 指向 Stable Launcher；Stable Launcher MUST 讀取原子更新的啟用狀態後啟動 Active Release，不得把捷徑直接綁定到某個版本目錄。

#### Scenario: 正常啟動 BAP
- **WHEN** user 從桌面或開始功能表啟動 BAP
- **THEN** Stable Launcher 啟動啟用狀態所指定版本的 `BAP.exe`

#### Scenario: Active Release 不存在或無法讀取
- **WHEN** 啟用狀態指定的版本不存在或無法啟動
- **THEN** Stable Launcher 嘗試啟動仍存在的 Previous Release
- **AND** 系統記錄可供排查的錯誤
- **AND** 若沒有可用版本，系統顯示白話的修復提示

### Requirement: 新版必須先通過本機 Health Check 才能切換
Updater MUST 在切換 Active Release 前，對 Candidate 執行不需連線正式 Backend 的 Health Check，至少驗證 Runtime 版本、Qt 執行環境、必要資源、主要視窗建立能力及 User Data Root 的可用性。

#### Scenario: Candidate 通過 Health Check
- **WHEN** Candidate 的所有必要檢查成功
- **THEN** Updater 才能進入版本切換階段
- **AND** 檢查結果記錄 Candidate 版本與成功狀態

#### Scenario: Candidate 未通過 Health Check
- **WHEN** Candidate 缺少必要檔案、無法載入 Qt、無法建立主要視窗或回報錯誤版本
- **THEN** Updater 不切換 Active Release
- **AND** 原本版本保持可用
- **AND** user 看到更新未完成的白話訊息

### Requirement: 切換後啟動失敗必須自動 Rollback
Updater MUST 以不可留下半份狀態的方式切換 Active Release，並在切換後透過 Stable Launcher 啟動新版；新版若未在限定時間內送出 Ready Signal或提早結束，Updater MUST 自動恢復 Previous Release。

#### Scenario: 新版成功送出 Ready Signal
- **WHEN** Updater 切換 Active Release 並啟動新版
- **AND** 新版在限定時間內送出對應更新工作的 Ready Signal
- **THEN** 新版保持為 Active Release
- **AND** 這次更新被記錄為成功

#### Scenario: 新版切換後無法正常啟動
- **WHEN** 新版在限定時間內沒有送出 Ready Signal或程序提早結束
- **THEN** Updater 將 Active Release 切回 Previous Release
- **AND** Updater 透過 Stable Launcher 重新啟動 Previous Release
- **AND** user 看到已恢復舊版的白話訊息

#### Scenario: Rollback 本身失敗
- **WHEN** Updater 無法恢復或啟動 Previous Release
- **THEN** 系統不得刪除任何可能可用的版本目錄
- **AND** 系統保留完整診斷紀錄
- **AND** user 看到可執行的人工修復方式

### Requirement: 更新與 Rollback 不得破壞 User Data
版本安裝目錄與 User Data Root MUST 分開。安裝、切換、Rollback、清除舊版本及解除安裝程式版本時，MUST NOT 因此刪除或重設 user 的設定、登入狀態、logs 或量測資料。

#### Scenario: 更新成功後讀取原有資料
- **WHEN** user 完成版本更新並開啟新版
- **THEN** 新版仍能讀取更新前保存在 User Data Root 的資料

#### Scenario: 更新失敗並 Rollback
- **WHEN** 新版啟動失敗且系統恢復 Previous Release
- **THEN** Previous Release 仍能讀取更新前的 User Data
- **AND** 失敗 Candidate 不得改寫正式登入狀態來完成 Health Check

### Requirement: 系統必須安全保留可回復版本並清理舊版本
更新成功後，系統 MUST 至少保留 Active Release 與一個 Previous Release。系統只能清除未被啟用狀態引用、不是目前程序來源且不再需要 Rollback 的更舊版本。

#### Scenario: 新版確認成功後清理
- **WHEN** 新版已送出 Ready Signal 且成為穩定的 Active Release
- **THEN** 系統保留新版與上一個成功版本
- **AND** 系統可以刪除更舊且未被引用的版本

#### Scenario: 舊版本暫時無法刪除
- **WHEN** 更舊版本因檔案鎖定或權限問題無法刪除
- **THEN** 更新仍可視為成功
- **AND** 系統記錄清理失敗並在之後重試
- **AND** 系統不得誤刪 Active Release 或 Previous Release

### Requirement: 第一個 Versioned Update 必須保護既有 Legacy Install
當 user 從覆蓋式 Legacy Install 第一次更新到 Versioned Release 時，Updater MUST 在安裝 Candidate 前建立並驗證可啟動的舊版副本；若無法建立副本，MUST 停止更新並保留原安裝。

#### Scenario: Legacy Install 成功轉成 Previous Release
- **WHEN** user 從 Legacy Install 執行第一個 Versioned Update
- **THEN** Updater 讀取既有 Runtime 版本
- **AND** Updater 將既有 Runtime 保存成對應的 Versioned Release
- **AND** 舊版副本通過啟動驗證後才繼續安裝 Candidate

#### Scenario: Legacy Install 無法建立可用副本
- **WHEN** Updater 無法辨識舊版版本、複製必要檔案或驗證舊版副本
- **THEN** Updater 停止更新
- **AND** 原本 Legacy Install 保持可啟動
- **AND** user 不需要先解除安裝目前版本
