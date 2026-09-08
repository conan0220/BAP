## 名詞定義

| 名詞 | 定義 |
|---|---|
| Session duration | user 在正式錄製前指定的預定錄製秒數。 |
| actual duration | Session 從正式開始到實際結束的秒數。 |
| duration_reached | 預定錄製時間到達，因此由系統自動結束。 |
| ended_by_user | user 在預定時間到達前按下按鈕提前結束。 |
| source_interrupted | 任一必要無線 Node 連續一秒沒有產生有效 Frame，因此由系統自動停止整個 Session。 |

## ADDED Requirements

### Requirement: Session 必須支援預定時間與提前結束
Desktop App MUST 讓 user 在開始正式測量前指定整數 Session duration，預設為 60 秒，可接受範圍為 5 至 3600 秒。正式錄製開始後，系統 MUST 在時間到時自動結束，並 MUST 同時提供「提前結束測量」操作。

#### Scenario: 使用預設時間開始
- **WHEN** user 沒有修改預設 Session duration 並按下「開始測量」
- **THEN** Desktop App 以 60 秒作為預定時間
- **AND** 畫面顯示已錄製時間與剩餘時間

#### Scenario: 輸入有效的自訂時間
- **WHEN** user 輸入 5 至 3600 之間的整數秒數
- **THEN** Desktop App 允許開始測量
- **AND** 該次 Session 使用 user 指定的預定時間

#### Scenario: 輸入無效時間
- **WHEN** user 輸入小於 5、大於 3600、非整數或空白的 Session duration
- **THEN** Desktop App 顯示白話錯誤
- **AND** 不開始正式錄製

#### Scenario: 預定時間到達
- **WHEN** Session 實際錄製時間到達預定時間
- **THEN** Desktop App 自動停止接受新 Frames
- **AND** 只執行一次 CSV finalization 與後續上傳
- **AND** 結束原因記錄為 `duration_reached`

#### Scenario: user 提前結束
- **WHEN** user 在預定時間到達前按下「提前結束測量」
- **THEN** Desktop App 停止接受新 Frames
- **AND** 只執行一次 CSV finalization 與後續上傳
- **AND** 結束原因記錄為 `ended_by_user`

#### Scenario: 錄製期間無線 Node 中斷
- **WHEN** 任一必要無線 Node 連續一秒沒有產生有效 Frame
- **THEN** Desktop App 自動停止整個 Session
- **AND** CSV finalization 只執行一次
- **AND** 左右手都已有有效資料時，保留並上傳中斷前資料
- **AND** 可上傳時，後續上傳也只執行一次
- **AND** 結束原因記錄為 `source_interrupted`

#### Scenario: 中斷來源完全沒有有效資料
- **WHEN** 錄製停止時任一必要 Input Role 完全沒有有效 Frame
- **THEN** Desktop App 顯示本次錄製失敗
- **AND** 不上傳無法執行分析的 Session package

### Requirement: Session 必須記錄預定與實際錄製資訊
新版 Session Metadata MUST 記錄 `requested_duration_seconds`、`actual_duration_seconds` 與 `stop_reason`。實際時間 MUST 由 monotonic clock 計算，且 `started_at` 與 `ended_at` MUST 繼續保存人可閱讀的日期時間。

#### Scenario: 60 秒 Session 正常完成
- **WHEN** user 指定 60 秒且系統因時間到而結束
- **THEN** Metadata 的 `requested_duration_seconds` 為 60
- **AND** `actual_duration_seconds` 保存實際經過時間
- **AND** `stop_reason` 為 `duration_reached`

#### Scenario: Session 提前結束
- **WHEN** user 指定 60 秒但在時間到以前提前結束
- **THEN** `actual_duration_seconds` 小於預定時間
- **AND** `stop_reason` 為 `ended_by_user`

#### Scenario: Session 因來源中斷而結束
- **WHEN** user 指定的時間尚未到達，但必要無線 Node 中斷
- **THEN** `actual_duration_seconds` 小於預定時間
- **AND** `stop_reason` 為 `source_interrupted`
