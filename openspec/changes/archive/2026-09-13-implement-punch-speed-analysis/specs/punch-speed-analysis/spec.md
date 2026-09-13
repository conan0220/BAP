## 名詞定義

| 名詞 | 定義 |
|---|---|
| 拳頭速度 | UI 顯示給 user 的速度名稱；由手腕 IMU 資料推算，單位為 `m/s`。 |
| 出拳事件 | 一隻手從相對穩定狀態開始伸拳、到達主要動作高峰並進入收拳的單次 Shadow boxing 動作。 |
| 最高拳頭速度 | 一個出拳事件中最高的拳頭速度。 |
| 平均拳頭速度 | 同一隻手所有有效出拳事件之最高拳頭速度的算術平均值。 |
| 靜止校正 | 正式測量前，user 保持預備姿勢，讓系統收集估算初始狀態與 sensor bias 所需的資料。 |
| Ground Truth | 外部測速設備提供的參考速度；第一版尚未取得。 |
| 決定性結果 | 相同輸入、Parameters、Analysis Specification 與演算法版本重複分析時得到相同結果。 |

## Purpose

讓 user 能在 Desktop App 使用左右手腕 IMU 完成一次 Shadow boxing 測量，並從 Backend 取得左右手摘要及每一拳的拳頭速度，同時清楚處理校正失敗、資料不足與尚未具有外部 Ground Truth 的限制。

## ADDED Requirements

### Requirement: 拳頭速度分析必須使用左右手腕資料
`punch_speed` version 2 MUST 各使用一份 `left_wrist` 與 `right_wrist` Common IMU CSV，並 MUST 分開分析兩隻手。第一個可執行版本 MUST 只分析沒有擊中物體的 Shadow boxing。

#### Scenario: 左右手輸入完整
- **WHEN** Analysis Job 將兩份不同且有效的 CSV 分別綁定至 `left_wrist` 與 `right_wrist`
- **THEN** Backend 分別計算左手與右手的出拳事件及拳頭速度
- **AND** 每一筆明細都能辨認來自左手或右手

#### Scenario: 左右手輸入缺少或重複
- **WHEN** Analysis Job 缺少任一必要 Input Role，或左右手綁定同一份 CSV
- **THEN** Backend 拒絕執行該分析
- **AND** 不產生成功 Result

### Requirement: 正式測量前必須完成靜止校正
Desktop App MUST 在校正開始前，以文字清楚告訴 user 要先將雙手自然放下並保持不動。校正設定畫面與兩秒校正期間 MUST NOT 顯示正式錄製時間欄位。校正完成後，Desktop App MUST 才顯示錄製時間欄位，請 user 輸入正式 Session duration，並等待 user 按下「開始正式錄製」或意思相同的按鈕，不得自動開始正式錄製。校正期間的 IMU samples MUST 隨正式資料保存在同一份左右手 CSV，且 Analysis Parameters MUST 標示 user 按下按鈕後的正式測量開始時間邊界，讓 Backend 不會把校正或等待動作算成出拳。

#### Scenario: user 完成靜止校正
- **WHEN** user 按下「開始校正」並在兩秒校正期間保持左右手 IMU 可用
- **THEN** 畫面顯示「校正中，請保持預備姿勢」或意思相同的文字
- **AND** 校正開始前與校正期間不顯示正式錄製時間欄位
- **AND** 校正完成後才顯示正式錄製時間欄位與「開始正式錄製」按鈕
- **AND** user 按下該按鈕後，才開始計算 user 指定的 Session duration
- **AND** 校正資料與正式資料使用同一條 Session-relative time 軸

#### Scenario: 校正完成後輸入無效的正式錄製時間
- **WHEN** user 在校正完成後輸入空白、非整數或不在 5～3600 秒內的正式錄製時間
- **THEN** Desktop App 以白話說明有效範圍
- **AND** 系統保持在校正完成狀態，不開始正式錄製
- **AND** user 可以修正時間後再次按下「開始正式錄製」

#### Scenario: 校正期間必要 IMU 中斷
- **WHEN** 任一必要 IMU 在校正完成前中斷或沒有足夠有效資料
- **THEN** Desktop App 不開始正式 Session duration
- **AND** 畫面以白話說明校正未完成
- **AND** user 可以重新檢測及分配 IMU 後再試一次

### Requirement: 每一拳必須產生可追查的最高拳頭速度
Backend MUST 依有效時間軸辨認出拳事件，並為每一拳產生非負且有限的 `peak_speed_mps`。每一拳 MUST 同時提供手別、該手拳序、開始時間、最高速度發生時間及結束時間，且 MUST 滿足 `start_elapsed_us <= peak_elapsed_us <= end_elapsed_us`。

#### Scenario: 一隻手完成一次有效出拳
- **WHEN** 正式測量資料中有一個可辨認的完整出拳事件
- **THEN** 該手增加一筆每拳明細
- **AND** 明細包含以 `m/s` 表示的最高拳頭速度
- **AND** 同一拳的伸拳與收拳不會分別產生兩筆明細

#### Scenario: 相同輸入重複分析
- **WHEN** 相同版本的 Executor 使用相同 CSV 與 Parameters 重複分析
- **THEN** 每次產生相同的出拳事件、時間與速度結果

### Requirement: Result 必須提供左右手摘要與每拳明細
成功 Result MUST 包含 `algorithm_version`、左右手與總拳數、左右手平均拳頭速度、左右手最高拳頭速度及 `punches` 明細。總拳數 MUST 等於左右手拳數相加，也 MUST 等於明細數量；每隻手的拳數、平均速度與最高速度 MUST 能由該手明細重新算出。某隻手沒有有效出拳時，該手的拳數、平均速度與最高速度 MUST 都是零。

#### Scenario: 左右手都有有效出拳
- **WHEN** Backend 成功分析包含左右手出拳的 Session
- **THEN** Result 分別提供左手與右手的拳數、平均速度及最高速度
- **AND** `punches` 提供每一拳的手別、順序、時間範圍與最高速度

#### Scenario: 其中一隻手沒有出拳
- **WHEN** 一隻手的資料品質有效，但正式測量期間沒有可辨認的出拳事件
- **THEN** 該手的拳數為零
- **AND** 該手的平均速度與最高速度為 `0.0`
- **AND** Result 仍可成功呈現另一隻手的結果

### Requirement: 資料不足時不得猜測拳頭速度
Backend MUST 驗證必要 sensor 數值、時間軸、取樣率、Quaternion 與校正資料。任一必要 CSV 無法支援可靠計算時，Analysis Job MUST 失敗並提供安全的白話錯誤，不得以零、固定值、隨機值或前一次結果假裝成功。

#### Scenario: Quaternion 缺少或無效
- **WHEN** 正式計算需要的 Quaternion 為空白、不是有限數值或無法正規化
- **THEN** Analysis Job 標示為失敗
- **AND** user 看到 IMU 姿態資料不足、需要重新測量的白話說明

#### Scenario: 無法建立有效時間軸
- **WHEN** CSV 的時間沒有前進、取樣率太低或校正與正式測量邊界無效
- **THEN** Analysis Job 標示為失敗
- **AND** 不保存成功 Result

### Requirement: Desktop App 必須以拳頭速度呈現結果
Desktop App MUST 將此分析項目與 Result 的 user-facing 名稱顯示為「拳頭速度」，並 MUST 顯示單位 `m/s`。Result view MUST 顯示左手與右手的拳數、平均拳頭速度、最高拳頭速度及每拳明細，且完成後 MUST 提供既有「重新測量」操作。

#### Scenario: Backend 回傳有效 Result
- **WHEN** `punch_speed` Analysis Job 完成且 Result 通過契約驗證
- **THEN** Desktop App 顯示「拳頭速度」與 `m/s`
- **AND** user 能查看左右手摘要與每拳明細
- **AND** user 能按下「重新測量」回到 IMU 檢測及分配階段

#### Scenario: Backend 尚未提供可執行 Executor
- **WHEN** Desktop App 查詢到 `punch_speed` 目前不可執行
- **THEN** 畫面顯示拳頭速度目前無法使用
- **AND** 不允許 user 開始一場無法得到 Result 的正式測量

### Requirement: 第一個可執行版本必須揭露驗證範圍
`punch_speed` version 2 MUST 以 automated tests 驗證時間換算、單位換算、座標處理、積分、漂移修正、Result 契約與端到端資料流，並 MUST 保留一項實際 IMU 人工驗證。沒有 Ground Truth 時，文件與驗收結果 MUST NOT 宣稱已證明絕對速度誤差範圍。

#### Scenario: 執行自動測試
- **WHEN** 系統使用速度答案已知的合成 IMU 資料執行測試
- **THEN** 計算結果落在測試案例定義的數值容許誤差內
- **AND** CI 能自動驗證結果

#### Scenario: user 進行實際 IMU 測試
- **WHEN** user 依序完成靜止、慢速、一般速度與快速的 Shadow boxing 測量
- **THEN** user 能確認靜止時不產生拳頭速度，且快慢變化與畫面結果的相對順序合理
- **AND** 人工驗證記錄清楚註明沒有外部 Ground Truth
