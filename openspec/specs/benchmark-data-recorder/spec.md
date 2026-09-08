## 名詞定義

| 名詞 | 定義 |
|---|---|
| Benchmark 資料錄製 | Desktop App 在本機擷取 IMU、加入 Ground Truth 並匯出測試資料的流程。 |
| Benchmark bundle | 包含一份 Metadata JSON 與每顆 IMU 各一份 Common IMU CSV 的 ZIP。 |
| Ground Truth | user 在錄製完成後輸入的左右手實際出拳次數。 |
| Input Role | 某顆 IMU 在資料中的用途；第一版為 `left_wrist` 與 `right_wrist`。 |
| unsaved recording | 已完成錄製但尚未成功匯出的本機 Benchmark 資料。 |

## Purpose

提供一個不依賴 Backend 的 Desktop App 開發工具，讓 user 能可靠地錄製左右手腕 Shadow boxing IMU、輸入人工拳數，並匯出可加入演算法開發與 CI 測試的 labeled Benchmark bundle。

## Requirements

### Requirement: 第一版 Recorder 必須建立 punch_count Shadow boxing 資料
Benchmark 資料錄製頁面 MUST 在第一版固定使用 `punch_count`、`shadow_boxing`、`left_wrist` 與 `right_wrist`。系統 MUST 清楚顯示這是建立開發與測試資料的工具，不得將它表示為正式 Backend 分析結果。

#### Scenario: user 進入 Benchmark 資料錄製
- **WHEN** 已登入 user 從「開發工具」開啟 Benchmark 資料錄製
- **THEN** 畫面顯示資料用途為出拳次數及 Shadow boxing
- **AND** 畫面要求分配左手腕與右手腕 IMU
- **AND** 畫面說明錄製完成後仍需輸入人工拳數

### Requirement: Recorder 必須自動探索並驗證兩顆 IMU
進入頁面後，系統 MUST 依既有 IMU source discovery 規則自動掃描所有候選 Port。user MUST 能將不同的有效來源分別指定給左手腕與右手腕；無線來源 MUST 顯示 Port、Group ID 與 Node ID，有線來源 MUST 顯示 Port。

#### Scenario: 使用同一個無線接收器的兩顆 IMU
- **WHEN** 掃描結果在同一個 Port 找到相同 Group ID 下的兩個 Node IDs
- **THEN** user 可以把不同 Node 分別指定給左手腕與右手腕
- **AND** Metadata 保存兩個 Input Roles 對應的 Port、Group ID 與 Node ID

#### Scenario: 使用兩顆有線 IMU
- **WHEN** 掃描結果在兩個 Ports 找到有效有線 IMU
- **THEN** user 可以將不同 Port 分別指定給左右手腕
- **AND** Metadata 的 Group ID 與 Node ID 保持空值

#### Scenario: 同一來源被重複指定
- **WHEN** user 嘗試將同一顆 IMU 指定給左右手腕
- **THEN** 系統顯示來源不得重複的說明
- **AND** 「開始錄製」保持不可使用

### Requirement: Recorder 必須支援限時錄製與提前結束
user MUST 在開始前指定 5 至 3600 之間的整數秒數，預設為 60 秒。錄製期間 MUST 顯示已錄製時間與剩餘時間；時間到時 MUST 自動結束，user 也 MUST 能按下「提前結束」結束本次錄製。

#### Scenario: 預定時間到達
- **WHEN** 錄製時間到達 user 指定的秒數
- **THEN** 系統停止接受新 Frames
- **AND** finalization 只執行一次
- **AND** Metadata 的結束原因為 `duration_reached`

#### Scenario: user 提前結束
- **WHEN** user 在預定時間到達前按下「提前結束」
- **THEN** 系統停止接受新 Frames
- **AND** Metadata 保存實際錄製時間
- **AND** 結束原因為 `ended_by_user`

#### Scenario: 錄製期間無線 Node 中斷
- **WHEN** 左手腕或右手腕的無線 Node 連續一秒沒有產生有效 Frame
- **THEN** 系統自動停止本次錄製
- **AND** 保留中斷前已成功寫入的左右手資料
- **AND** Metadata 的結束原因為 `source_interrupted`
- **AND** UI 說明 IMU 已中斷及資料已保留
- **AND** user 完成人工 Ground Truth 後仍可匯出 Benchmark bundle

#### Scenario: 來源完全沒有有效資料或讀取失敗
- **WHEN** 任一必要來源完全沒有產生有效 Frame、Serial read 發生錯誤或 CSV 無法完成寫入
- **THEN** 系統將本次錄製標示為失敗
- **AND** 不得讓 user 把無法驗證的資料匯出成有效 Benchmark bundle

### Requirement: 匯出前必須取得並驗證 Ground Truth
錄製成功後，系統 MUST 要求 user 分別輸入大於或等於零的左手與右手實際出拳次數，並 MUST 自動計算總拳數。Ground Truth 不完整或格式錯誤時 MUST 禁止匯出。

#### Scenario: Ground Truth 有效
- **WHEN** user 輸入有效的左右手非負整數
- **THEN** 系統自動顯示左右手相加的總拳數
- **AND** 允許 user 進行匯出

#### Scenario: Ground Truth 無效
- **WHEN** 任一欄為空白、負數、小數或非數字
- **THEN** 系統顯示白話錯誤
- **AND** 「匯出 Benchmark」保持不可使用

### Requirement: Recorder 必須匯出完整且可驗證的 ZIP
成功匯出的 ZIP MUST 只有一份 `metadata.json` 與左右手各一份 Common IMU CSV。Metadata MUST 記錄 Benchmark schema version、Common IMU CSV schema version、Session ID、analysis type、activity type、預定與實際時間、結束原因、Input Role bindings、來源資訊、row count、size、SHA-256、Ground Truth、Desktop version 與選填備註。

#### Scenario: 匯出成功
- **WHEN** 錄製、CSV validation 與 Ground Truth validation 全部通過，且 user 選擇可寫入的位置
- **THEN** 系統以單一 ZIP 匯出 Metadata 與兩份 CSV
- **AND** ZIP 內檔名與 Metadata descriptors 完全一致
- **AND** 每份 CSV 的實際 row count、size 與 SHA-256 符合 Metadata

#### Scenario: user 取消儲存對話框
- **WHEN** user 在選擇匯出位置時取消
- **THEN** 系統不建立不完整 ZIP
- **AND** 保留本次 unsaved recording 供 user 再次匯出

#### Scenario: 匯出寫入失敗
- **WHEN** 儲存空間、權限或其他 I/O 錯誤使 ZIP 無法完整寫入
- **THEN** 系統顯示安全的失敗訊息
- **AND** 目的位置不留下看似成功的部分 ZIP
- **AND** 保留本機錄製資料供重試

### Requirement: Recorder 必須保持本機流程與隱私邊界
Benchmark Recorder MUST NOT 自動把 CSV、Metadata 或 Ground Truth 上傳到 Backend，也 MUST NOT 自動修改或 commit repository。Bundle MUST NOT 包含 Username、Password、Access Token、Refresh Token、電腦名稱或未在此規格列出的個人識別資訊。

#### Scenario: user 完成匯出
- **WHEN** Benchmark ZIP 成功寫入 user 選擇的位置
- **THEN** 資料只存在 user 電腦選定的位置
- **AND** 是否審查及加入 repository 由開發者另行決定

#### Scenario: user 離開但尚未匯出
- **WHEN** user 嘗試離開頁面或關閉 App，且目前有 unsaved recording
- **THEN** 系統提示 user 匯出或確認捨棄
- **AND** 未經確認不得悄悄刪除尚未匯出的錄製資料
