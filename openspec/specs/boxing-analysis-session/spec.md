## 名詞定義

| 名詞 | 定義 |
|---|---|
| Session | user 從開始到結束的一次拳擊測量，包含一份以上的 IMU CSV 與一個以上的 Analysis Job。 |
| Analysis Job | Session 中要求 Backend 執行的一次分析工作。 |
| Registered Analysis | 已有有效 Analysis Specification，而且 Backend 已提供可執行 Executor 的分析類型。 |
| Session Status | Session 當下所處的狀態，例如錄製中、上傳中、分析中、完成或失敗。 |
| Result | Analysis Job 完成後由 Backend 保存並回傳的 JSON 結果。 |
| Session duration | user 在正式錄製前指定的預定錄製秒數。 |
| actual duration | Session 從正式開始到實際結束的秒數。 |
| duration_reached | 預定錄製時間到達，因此由系統自動結束。 |
| ended_by_user | user 在預定時間到達前按下按鈕提前結束。 |
| source_interrupted | 任一必要無線 Node 連續一秒沒有產生有效 Frame，因此由系統自動停止整個 Session。 |

## Purpose

建立所有拳擊分析項目共用的 Session 生命週期，讓 Desktop App 可以錄製 IMU、交給 Backend 保存與分析，並把可驗證的狀態或 Result 顯示給 user。

## Requirements
### Requirement: 第一版 UI 一次只能執行一個分析項目
Desktop App MUST 維持目前一次只進入一個拳擊分析項目的操作方式。每次從分析頁面建立的 Session MUST 只要求一個 Analysis Job，但 Session 與 Backend API 的資料格式 MUST 能表示一個以上的 Analysis Job。

#### Scenario: 從出拳次數頁面建立 Session
- **WHEN** user 在出拳次數頁面完成 IMU 分配並開始測量
- **THEN** Desktop App 建立一個新的 Session
- **AND** 該次 Desktop 操作只建立一個 `punch_count` Analysis Job

#### Scenario: Backend 接收包含多個 Analyses 的有效 Session
- **WHEN** 符合共用契約的 Client 提交一個包含多個 Analysis Jobs 的 Session
- **THEN** Backend 能以同一個 Session 保存並分別追蹤每個 Analysis Job

### Requirement: Session 必須有明確且不可混用的生命週期
系統 MUST 以唯一 Session ID 識別每次測量，並 MUST 區分準備、錄製、等待上傳、已接收、分析中、完成與失敗狀態。Desktop App MUST NOT 把前一次 Session 的 CSV、Input Bindings 或 Result 混入新的 Session。

#### Scenario: user 開始新的測量
- **WHEN** user 在有效 IMU 分配後按下「開始測量」
- **THEN** Desktop App 建立新的 Session ID 並開始本次錄製
- **AND** 畫面顯示測量中的狀態與結束操作

#### Scenario: user 結束測量
- **WHEN** user 在錄製中按下「結束測量」
- **THEN** Desktop App 停止接受本次 Session 的新 IMU Frames
- **AND** Desktop App 完成本次 CSV 與 Metadata 後才開始上傳

#### Scenario: user 再次開始相同項目
- **WHEN** 前一次 Session 已完成或失敗，而 user 再次開始測量
- **THEN** Desktop App 使用新的 Session ID、CSV IDs 與 Analysis ID
- **AND** 新 Session 不沿用前一次 Result

### Requirement: 只有可執行的分析項目才能開始正式錄製
Desktop App MUST 在開始正式錄製前確認 Analysis Type、Specification version 與 Backend Executor 目前可用。若分析尚未提供，Desktop App MUST 清楚顯示待開發或目前無法分析，且 MUST NOT 要求 user 完成一場無法得到 Result 的正式錄製。

#### Scenario: Analysis Executor 可用
- **WHEN** Desktop App 確認所選 Analysis Type 與版本可由 Backend 執行
- **THEN** 有效完成 IMU 分配的 user 可以開始正式錄製

#### Scenario: Analysis Executor 尚未提供
- **WHEN** Backend 回報所選 Analysis Type 沒有可執行的 Executor
- **THEN** Desktop App 顯示該項目尚未提供分析功能
- **AND** Desktop App 不開放「開始測量」操作

### Requirement: Desktop App 必須顯示端到端進度
Desktop App MUST 以文字顯示準備 IMU、等待開始、測量中、上傳中、Backend 分析中、分析完成或失敗等狀態，且 MUST NOT 只使用顏色表示狀態。

#### Scenario: Backend 尚未完成分析
- **WHEN** Session 已上傳且 Analysis Job 尚未完成
- **THEN** Desktop App 顯示「分析中」或意思相同的狀態
- **AND** Desktop App 不把尚未完成的資料顯示成 Result

#### Scenario: Backend 完成分析
- **WHEN** Backend 回報 Analysis Job 已完成並提供符合契約的 Result
- **THEN** Desktop App 顯示該 Result
- **AND** user 能辨認本次 Session 與分析項目

#### Scenario: Backend 回報分析失敗
- **WHEN** Backend 回報 Analysis Job 失敗
- **THEN** Desktop App 顯示不包含敏感內部資訊的失敗說明
- **AND** Desktop App 不偽造或猜測分析結果

### Requirement: 暫存資料必須保留到 Backend 確認接收
Desktop App MUST 在 Backend 明確確認 Session Metadata 與所有 CSV 已完整保存以前保留本機暫存資料。上傳失敗時 MUST 允許重試，不得要求 user 立刻重新錄製；Backend 已保存但分析失敗時 MUST 保留 Backend 原始 CSV 供重新分析。

#### Scenario: 上傳中斷
- **WHEN** Desktop App 上傳 Session 時發生網路或 Backend 錯誤
- **THEN** Desktop App 保留本次 Metadata 與 CSV
- **AND** user 可以重試上傳

#### Scenario: Backend 確認完整接收
- **WHEN** Backend 回覆 Session 與所有 CSV 已完整保存
- **THEN** Desktop App 可以清除本次本機暫存資料

#### Scenario: 分析失敗但資料已保存
- **WHEN** Backend 已保存 Session 與 CSV，但 Analysis Job 執行失敗
- **THEN** Backend 保留原始 CSV
- **AND** 重新分析不要求 user 再次上傳相同資料

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

### Requirement: 分析完成後必須允許重新測量
Desktop App MUST 在顯示 Backend Result 後提供「重新測量」操作。user 按下後，系統 MUST 清除上一個 Session 的畫面狀態，重新檢測所有 Port，並要求 user 重新分配本次要使用的 IMU。

#### Scenario: user 在結果頁重新測量
- **WHEN** Backend 已完成分析並且 Desktop App 已顯示 Result
- **THEN** Desktop App 顯示可操作的「重新測量」按鈕
- **AND** 畫面不再顯示上一個 Session 的錄製時間控制與計時資訊
- **WHEN** user 按下「重新測量」
- **THEN** Desktop App 清除上一個 Session 的 Result 與識別資訊
- **AND** 自動重新檢測所有 Port
- **AND** 回到 IMU 分配階段
