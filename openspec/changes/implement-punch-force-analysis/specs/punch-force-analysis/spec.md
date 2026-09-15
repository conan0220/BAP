## 名詞定義

| 名詞 | 定義 |
|---|---|
| 出拳力量 | 由沙袋上、下方 IMU 與沙袋物理參數估算出的單次最大打擊力。 |
| 打擊位置 | 最大力量發生時，打擊點從沙袋底部往上量的估算高度。 |
| `bag_top` | 安裝在沙袋剛性核心上方的 IMU Input Role。 |
| `bag_bottom` | 安裝在沙袋剛性核心下方的 IMU Input Role。 |
| 沙袋參數 | 本次分析使用的沙袋質量、長度、直徑與上下 IMU 間距。 |
| 校正資料 | user 正式打擊以前，沙袋保持靜止時錄製的 IMU 資料。 |
| 資料品質 | Backend 對取樣率、缺漏、Quaternion、打擊數量及兩顆 IMU 剛體一致性的判斷。 |
| 顯示曲線 | Backend 從完整運算資料選出的有限點數，供 Desktop App 顯示加速度、角加速度與力量變化。 |

## Purpose

讓 user 能以固定在同一沙袋上、下方的兩顆無線 IMU 完成一次打擊測量，由 Backend 估算最大打擊力與打擊位置，再由 Desktop App 清楚顯示數值、單位、曲線及資料品質。

## ADDED Requirements

### Requirement: 出拳力量必須使用兩顆固定在沙袋上的 IMU
`punch_force` version 1 MUST 要求不同的 `bag_top` 與 `bag_bottom` Common IMU CSV。兩顆 IMU MUST 牢固安裝在同一個沙袋的剛性核心上、下方，且 MUST 來自同一個 Port、同一個無線接收器及同一個 Group ID 的不同 Node IDs；第一版 MUST NOT 接受有線來源、不同 Port 或不同 Group ID 的組合。

#### Scenario: user 完成有效的沙袋 IMU 分配
- **WHEN** user 將同一個無線接收器與 Group ID 下的不同 Nodes 分別指定為沙袋上方與下方 IMU
- **THEN** Desktop App 將兩份 CSV 分別綁定到 `bag_top` 與 `bag_bottom`
- **AND** user 可以繼續確認沙袋參數

#### Scenario: 兩顆 IMU 沒有共同 Packet 時間基準
- **WHEN** user 選擇的來源為有線 IMU、不同 Port 或不同 Group ID
- **THEN** Desktop App 說明兩顆 IMU 無法可靠對齊
- **AND** Desktop App 不允許開始正式測量

### Requirement: 每次分析必須記錄完整且合理的沙袋參數
Desktop App MUST 讓 user 在校正前看見並確認 `bag_mass_kg`、`bag_length_m`、`bag_diameter_m` 與 `sensor_distance_m`。所有數值 MUST 是大於零的有限數值，且 IMU 間距 MUST NOT 大於沙袋長度；Backend MUST 依相同 Parameters 執行分析，不得改用未告知 user 的物理參數。

#### Scenario: user 使用預設沙袋參數
- **WHEN** user 沒有修改預填的 36 kg、1.24 m、0.335 m 與 1.24 m
- **THEN** Desktop App 在開始校正前顯示這些數值及單位
- **AND** Analysis Parameters 保存本次實際採用的四個數值

#### Scenario: user 輸入不合理的沙袋參數
- **WHEN** 任一參數為空白、非數值、非有限數值、零或負數，或 IMU 間距大於沙袋長度
- **THEN** Desktop App 顯示哪個欄位需要修正
- **AND** Desktop App 不開始校正或正式錄製

### Requirement: 正式打擊以前必須完成兩秒靜止校正
Desktop App MUST 在正式測量前提示 user 不要碰觸沙袋，並 MUST 錄製兩秒靜止校正資料。Metadata MUST 以 `calibration_end_elapsed_us` 標示校正資料結束，並以 `measurement_start_elapsed_us` 標示 user 按下「開始正式測量」後的正式資料起點；兩個時間點之間的等待與準備動作 MUST NOT 被當成校正或正式打擊。

#### Scenario: user 開始校正
- **WHEN** IMU 分配、沙袋參數及 Backend capability 都有效
- **THEN** Desktop App 提示 user 讓沙袋完全靜止且不要碰觸沙袋
- **AND** 畫面以「開始校正」作為主要操作
- **AND** 校正前不要求 user 輸入正式錄製時間

#### Scenario: 校正完成後準備打擊
- **WHEN** 兩顆 IMU 都完成兩秒有效校正
- **THEN** Desktop App 說明正式錄製期間只能打擊沙袋一次
- **AND** 讓 user 輸入 5 至 3600 秒的正式錄製時間
- **AND** 等 user 按下「開始正式測量」後才開始計算正式錄製時間

#### Scenario: 校正期間來源中斷
- **WHEN** 任一必要 IMU 在校正完成以前中斷
- **THEN** Desktop App 停止本次校正並顯示白話原因
- **AND** 不上傳不完整的正式 Session

### Requirement: Backend 必須使用共同 Packet 對齊兩顆 IMU
Backend MUST 以兩份 Common IMU CSV 的 `packet_index` 對齊同一個無線接收器 Packet 中的上、下方 IMU Frame，並 MUST 驗證來源描述、時間順序與 Packet 身分。Backend MAY 對有限且位於有效資料中間的遺漏 samples 進行可重現的插值，但 MUST 在 Result 中揭露插值警告；遺漏超過版本化品質規則時 MUST 拒絕分析。

#### Scenario: 上下方 CSV 具有共同 Packet
- **WHEN** 兩份 CSV 的有效資料具有相同 `packet_index`
- **THEN** Backend 只使用能可靠配對或依規則插值的 Packet 執行計算
- **AND** 不以兩份 CSV 的列號直接假設資料已對齊

#### Scenario: 少量無線 Packet 遺漏
- **WHEN** 少量且符合版本化限制的 Packet 只出現在其中一份 CSV
- **THEN** Backend 以確定且可重現的方法補齊分析用資料
- **AND** 原始 Common IMU CSV 不被改寫
- **AND** Result 的 `warnings` 說明曾處理 Packet 遺漏

#### Scenario: Packet 遺漏過多
- **WHEN** 共同 Packet 數量或連續性未達版本化品質規則
- **THEN** Analysis Job 標示為失敗
- **AND** Desktop App 說明兩顆 IMU 資料無法可靠對齊

### Requirement: Backend 必須依固定版本的物理模型計算單次打擊
Backend MUST 將兩顆 IMU 的加速度轉換為共同座標、移除靜止校正基準並套用版本化低通濾波。Backend MUST 以兩顆水平加速度的平均值估算沙袋質心加速度，以沙袋質量乘上質心加速度大小估算力量，並 MUST 在力量最大時刻依上、下方加速度差、IMU 間距與沙袋橫向轉動慣量估算打擊位置。所有內部運算 MUST 使用 SI units，kgf MUST 只由 Newton 以 `1 kgf = 9.80665 N` 換算。

#### Scenario: 有效資料包含一次打擊
- **WHEN** 校正與正式資料通過品質檢查且正式區段只包含一次有效打擊
- **THEN** Backend 回傳同一峰值時刻的最大打擊力、質心加速度與打擊位置
- **AND** Newton 與 kgf 數值使用固定換算關係
- **AND** 相同 Inputs、Parameters 與演算法版本得到相同 Result

#### Scenario: user 改變沙袋質量
- **WHEN** 兩次分析使用相同 IMU 資料但採用不同有效 `bag_mass_kg`
- **THEN** Backend 依每次 Analysis Parameters 分別計算力量
- **AND** Result 不偷偷沿用前一次或程式預設的沙袋質量

### Requirement: 無法可靠辨認單次打擊時不得回傳假力量
Backend MUST 驗證 Quaternion、有限 sensor 數值、校正穩定性、實際取樣率、有效打擊數量與計算結果。沒有明顯打擊、偵測到多次打擊、必要資料不足或運算產生非有限數值時，Analysis Job MUST 標示為失敗，不得以背景雜訊的最大值或固定數字假裝成功。

#### Scenario: 正式資料沒有有效打擊
- **WHEN** 正式資料只有靜止或背景雜訊，沒有符合版本化規則的打擊
- **THEN** Analysis Job 標示為失敗
- **AND** Desktop App 說明本次沒有偵測到有效打擊
- **AND** 不顯示虛假的力量數值

#### Scenario: 正式資料包含多次打擊
- **WHEN** 正式資料包含兩次以上符合規則的獨立打擊
- **THEN** Analysis Job 標示為失敗
- **AND** Desktop App 提醒一場出拳力量測量只能打擊一次

#### Scenario: 取樣率低於可靠分析範圍
- **WHEN** 實際取樣率低於演算法版本允許的最低值
- **THEN** Analysis Job 標示為失敗
- **AND** Desktop App 說明取樣率不足

### Requirement: 可完成但需要注意的資料品質必須顯示警告
Backend MUST 將不需要拒絕分析、但可能影響可信度的狀況放入 `warnings`，並將 `quality_status` 設為 `warning`。至少 MUST 涵蓋少量 Packet 插值、取樣率低於建議值、兩顆 IMU 的 Gyroscope 行為不一致，以及估算打擊位置超出沙袋長度；沒有警告時 `quality_status` MUST 為 `valid`。

#### Scenario: 上下 IMU 的旋轉行為不一致
- **WHEN** 一顆 IMU 在打擊期間明顯旋轉，而另一顆幾乎保持不動
- **THEN** Backend 仍可保留可計算的數值
- **AND** Result 標示 `warning`
- **AND** Desktop App 說明應檢查 IMU 是否牢固安裝及上下位置是否選對

#### Scenario: 打擊位置超出沙袋範圍
- **WHEN** 估算高度小於零或大於 `bag_length_m`
- **THEN** Backend 不把該位置標示為正常
- **AND** Desktop App 顯示位置超出合理範圍及結果可能不可靠

### Requirement: punch_force Result 必須版本化且限制曲線資料量
`punch_force` version 1 Result MUST 包含 `algorithm_version`、`peak_elapsed_us`、`peak_force_n`、`peak_force_kgf`、`peak_com_acceleration_g`、`impact_height_from_bottom_m`、`impact_offset_from_center_m`、`sample_rate_hz`、`quality_status`、`warnings` 與 `curve_points`。每一個顯示點 MUST 包含 `elapsed_us`、`top_horizontal_acceleration_mps2`、`bottom_horizontal_acceleration_mps2`、`angular_acceleration_x_radps2`、`angular_acceleration_y_radps2` 與 `force_kgf`；顯示點 MUST 依時間排列、不得超過 300 筆，且 MUST 保留峰值點。

#### Scenario: Backend 回傳有效 Result
- **WHEN** Backend 成功完成一次打擊分析
- **THEN** 所有力量、加速度、位置、取樣率與曲線數值都是有限數值
- **AND** 力量與取樣率為正數
- **AND** `quality_status` 只會是 `valid` 或 `warning`
- **AND** `warnings` 與品質狀態一致

#### Scenario: 原始運算點超過顯示上限
- **WHEN** 正式資料產生超過 300 個運算點
- **THEN** Backend 回傳不超過 300 個依時間排序的顯示點
- **AND** 第一點、最後一點及力量峰值點仍包含在 Result
- **AND** Backend 保存的原始 Common IMU CSV 不被改寫

### Requirement: Desktop App 必須清楚呈現力量、位置與品質
Desktop App MUST 在 Result 通過契約驗證後顯示最大打擊力的 kgf 與 N、打擊位置、峰值時間、實際取樣率、資料品質及 warnings。Desktop App MUST 以內嵌曲線顯示上、下方 IMU 加速度、角加速度與力量峰值，並 MUST 保留「重新測量」操作；畫面 MUST 說明力量與位置是 IMU 模型估算值，不是 Force Plate 直接量測值。

#### Scenario: user 查看正常 Result
- **WHEN** Backend 回傳 `quality_status` 為 `valid` 的有效 Result
- **THEN** Desktop App 顯示最大力量、兩種力量單位、打擊位置、峰值時間與取樣率
- **AND** 曲線能辨認力量峰值
- **AND** 畫面提供重新測量

#### Scenario: user 查看具有警告的 Result
- **WHEN** Backend 回傳 `quality_status` 為 `warning`
- **THEN** Desktop App 以文字逐項顯示 `warnings`
- **AND** 不只用顏色表示結果需要注意
- **AND** 不把警告 Result 宣稱為可靠的絕對力量量測

