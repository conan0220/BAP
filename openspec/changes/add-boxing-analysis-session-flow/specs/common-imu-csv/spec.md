## 名詞定義

| 名詞 | 定義 |
|---|---|
| Common IMU CSV | 所有拳擊分析共同使用的 IMU 時序資料格式。 |
| IMU CSV | 一顆 IMU 在一個 Session 內產生的一份 Common IMU CSV。 |
| Frame | Desktop App 從一顆 IMU 成功解析出來的一幀感測資料。 |
| Session clock | 從本次 Session 開始後持續向前增加的共用 monotonic clock。 |
| Device time | IMU 或 Gateway 提供的裝置端時間。 |
| CSV ID | 在一個 Session 中唯一識別某份 IMU CSV 的 UUID。 |
| CSV descriptor | Metadata 中描述 CSV ID、檔名、來源、列數、大小及 SHA-256 的資料。 |

## Purpose

提供不依賴特定拳擊演算法的共同 IMU 資料格式，讓每顆 IMU 各自保存完整時序資料，並讓 Backend 能對齊、驗證及重複使用同一份資料。

## ADDED Requirements

### Requirement: 每顆 IMU 必須各自產生一份 Common IMU CSV
Desktop App MUST 為本次 Session 實際使用的每顆 IMU 建立不同的 CSV ID 與 Common IMU CSV。每個資料列 MUST 只表示該 CSV 所屬 IMU 的一個成功解析 Frame，不得在同一列放入多顆 IMU 的資料。

#### Scenario: Session 使用兩顆無線 IMU
- **WHEN** 本次 Session 使用同一個 Gateway 下的兩個 Nodes
- **THEN** Desktop App 建立兩份不同 CSV ID 的 Common IMU CSV
- **AND** 每份 CSV 只包含其中一個 Node 的 Frames

#### Scenario: Session 使用不同 Port 的兩顆有線 IMU
- **WHEN** 本次 Session 使用兩個不同 Port 的有線 IMU
- **THEN** Desktop App 為每個 Port 建立一份獨立的 Common IMU CSV

### Requirement: Common IMU CSV 必須使用固定且版本化的 schema
Common IMU CSV version 1 MUST 依序使用以下欄位：`sample_index`、`packet_index`、`elapsed_us`、`device_time_ms`、`frame_type`、`acc_x_g`、`acc_y_g`、`acc_z_g`、`gyro_x_dps`、`gyro_y_dps`、`gyro_z_dps`、`mag_x_ut`、`mag_y_ut`、`mag_z_ut`、`roll_deg`、`pitch_deg`、`yaw_deg`、`quat_w`、`quat_x`、`quat_y`、`quat_z`、`temperature_c`、`pressure_pa`。Metadata MUST 明確記錄 `imu_csv_schema_version`。

#### Scenario: 產生 version 1 CSV
- **WHEN** Desktop App 為 Session 建立 Common IMU CSV version 1
- **THEN** CSV header 與 version 1 的欄位名稱及順序完全一致
- **AND** Metadata 的 `imu_csv_schema_version` 為 `1`

#### Scenario: Backend 收到不支援的 schema version
- **WHEN** Backend 收到目前不支援的 `imu_csv_schema_version`
- **THEN** Backend 拒絕建立 Session
- **AND** 回應能讓 Client 辨認 schema version 不受支援

### Requirement: CSV 欄位必須遵守共同資料語意
`sample_index` MUST 是該 IMU 從零開始且逐列增加的整數；`elapsed_us` MUST 是相對同一個 Session clock 起點的非負微秒數；`device_time_ms` MUST 保存裝置或 Gateway 提供的毫秒時間；感測欄位 MUST 使用 header 所標示的單位。裝置沒有提供的選填欄位 MUST 留白，不得填入假資料。

#### Scenario: 裝置沒有提供溫度與氣壓
- **WHEN** 某個有效 Frame 沒有溫度或氣壓資料
- **THEN** 該列的 `temperature_c` 與 `pressure_pa` 留白
- **AND** 其他可用感測值仍照常寫入

#### Scenario: 一顆 IMU 連續寫入 Frames
- **WHEN** Desktop App 依序寫入同一顆 IMU 的多個 Frames
- **THEN** `sample_index` 從 `0` 開始逐列增加
- **AND** `elapsed_us` 不會倒退

### Requirement: 多份 IMU CSV 必須可以用共同時間對齊
同一個 Session 中所有 IMU CSV 的 `elapsed_us` MUST 使用同一個 Session clock 起點。無線 Gateway packet 中屬於不同 Nodes 的 Frames MUST 在各自 CSV 中保留相同的 `packet_index`、`device_time_ms` 與對應的 `elapsed_us`。

#### Scenario: 一個 Gateway packet 包含左右手 Nodes
- **WHEN** 一個 Gateway packet 同時包含已選定的左手與右手 Node Frame
- **THEN** 兩個 Frames 分別寫入各自的 CSV
- **AND** 兩列使用相同的 `packet_index`、`device_time_ms` 與 `elapsed_us`

#### Scenario: 兩個有線 Port 的接收時間不同
- **WHEN** 兩顆有線 IMU 的 Frames 在不同時間抵達 Desktop App
- **THEN** 各自 CSV 的 `elapsed_us` 都以相同 Session 起點計算
- **AND** Backend 可以依 `elapsed_us` 排列跨 CSV 的相對時間

### Requirement: CSV descriptor 必須能驗證檔案身分與完整性
每份 IMU CSV MUST 在 Metadata 中有且只有一個 CSV descriptor。Descriptor MUST 包含唯一 CSV ID、檔名、IMU source、row count、檔案大小與 SHA-256；靜態的 Port、連線方式、baud rate、Group ID 與 Node ID MUST 放在 descriptor，不得要求每個 CSV row 重複保存。

#### Scenario: Desktop App 完成一份 CSV
- **WHEN** Desktop App 結束錄製並關閉一份 IMU CSV
- **THEN** Desktop App 以實際檔案計算 row count、檔案大小及 SHA-256
- **AND** 將結果寫入對應的 CSV descriptor

#### Scenario: 有線 IMU 沒有 Group ID 與 Node ID
- **WHEN** CSV source 是有線 IMU
- **THEN** Descriptor 使用 Port 識別來源
- **AND** Group ID 與 Node ID 保持空值

### Requirement: Common IMU CSV 必須使用可攜的文字格式
CSV MUST 使用 UTF-8、逗號分隔及 `.` 作為小數點。Header MUST 只出現一次，資料列不得包含額外欄位；缺少的選填值 MUST 使用空欄位。

#### Scenario: Backend 讀取 Desktop App 產生的 CSV
- **WHEN** Backend 依 Metadata 宣告的 schema version 讀取 CSV
- **THEN** Backend 能在不依賴 Desktop 作業系統地區設定的情況下解析 header 與數值
