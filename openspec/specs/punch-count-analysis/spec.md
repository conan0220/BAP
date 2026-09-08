## 名詞定義

| 名詞 | 定義 |
|---|---|
| 出拳事件 | 一隻手從相對穩定狀態開始伸拳、到達主要動作高峰並進入收拳的單次 Shadow boxing 動作。 |
| 動作區段 | 演算法視為同一次連續手部動作的一段 IMU samples。 |
| Ground Truth | 人工確認的左右手正確出拳次數。 |
| 有效時間軸 | 能維持 sample 順序並支援時間區段判斷的 device time 或 Session-relative time。 |
| 決定性結果 | 相同輸入資料與相同規格版本重複分析時得到相同結果。 |

## Purpose

讓 Backend 能從左右手腕的 Common IMU CSV 計算沒有擊中物體的 Shadow boxing 出拳次數，並以穩定、可驗證的 Result 回傳左右手與總拳數。

## Requirements

### Requirement: 出拳次數分析必須使用左右手腕資料
`punch_count` version 1 MUST 各使用一份 `left_wrist` 與 `right_wrist` Common IMU CSV，並 MUST 分開分析兩隻手，不得先混合兩份 CSV 再猜測拳數來源。

#### Scenario: 左右手輸入完整
- **WHEN** Analysis Job 將兩份不同且有效的 CSV 分別綁定至 `left_wrist` 與 `right_wrist`
- **THEN** Backend 分別計算左手與右手的出拳次數
- **AND** 每個偵測結果都歸屬於其中一個 Input Role

#### Scenario: 左右手輸入缺少或重複
- **WHEN** Analysis Job 缺少任一必要 Input Role，或左右手綁定同一份 CSV
- **THEN** Backend 拒絕執行該分析
- **AND** 不產生成功 Result

### Requirement: 第一版只計算 Shadow boxing 的完整出拳動作
第一版出拳次數分析 MUST 以沒有擊中物體的 Shadow boxing 為適用範圍。系統 MUST 將同一次伸拳、主要動作高峰與收拳視為一個動作區段，且 MUST NOT 將同一拳的伸拳與收拳分別計數。

#### Scenario: 一隻手完成一次 Shadow boxing 出拳
- **WHEN** 一隻手的 IMU 資料呈現一次符合規則的完整出拳動作
- **THEN** 該手的出拳次數增加一
- **AND** 同一動作區段內的其他 acceleration 或 gyroscope peaks 不會再增加拳數

#### Scenario: 同一隻手快速連續出拳
- **WHEN** IMU 資料包含兩次可分開辨認的完整出拳動作
- **THEN** 系統將它們計為兩拳

#### Scenario: 左右手幾乎同時出拳
- **WHEN** 左右手 CSV 在相近時間各自出現一個有效出拳動作
- **THEN** 左手與右手各增加一拳
- **AND** 總拳數增加二

#### Scenario: 只有一般手腕晃動
- **WHEN** 動作沒有形成符合規則的完整 Shadow boxing 出拳區段
- **THEN** 系統不增加出拳次數

### Requirement: Result 必須符合既有 punch_count 契約
成功 Result MUST 包含非負整數 `left_punch_count`、`right_punch_count` 與 `total_punch_count`，且總拳數 MUST 等於左右手拳數相加。Session duration MUST 保存在 Session Metadata，不得以另一個版本來源重複定義在 Result。

#### Scenario: 成功完成分析
- **WHEN** 左右手 CSV 都通過驗證且分析完成
- **THEN** Backend 回傳三個必要拳數欄位
- **AND** `total_punch_count = left_punch_count + right_punch_count`

#### Scenario: 相同資料重複分析
- **WHEN** 相同版本的 Executor 使用相同 CSV 與 Parameters 重複分析
- **THEN** 每次產生完全相同的拳數 Result

### Requirement: 演算法必須辨認可用時間軸與資料品質
Backend MUST 依 sample 順序與可用時間欄位建立每隻手的時間軸。單次 serial read 造成相鄰 Frames 具有相同 `elapsed_us` 時，系統 MUST NOT 因此把它們視為同一筆資料或多算出拳；若資料不足以建立有效時間軸或計算動作，Analysis Job MUST 失敗並提供安全錯誤，不得回傳猜測的零拳。

#### Scenario: elapsed_us 有重複但仍有有效順序
- **WHEN** 相鄰 samples 的 `elapsed_us` 重複，但 `sample_index` 與其他可用時間證據仍可建立有效順序
- **THEN** Backend 繼續分析
- **AND** 不因重複 timestamp 額外增加拳數

#### Scenario: CSV 沒有足夠有效資料
- **WHEN** 任一必要 CSV 為空、必要 sensor 欄位無法解析，或時間軸不足以執行分析
- **THEN** Analysis Job 標示為失敗
- **AND** Result 不會被保存為成功
- **AND** user 只看到不包含內部路徑或 stack trace 的說明
