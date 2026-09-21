## 名詞定義

| 名詞 | 定義 |
|---|---|
| 出拳軌跡 | 根據手腕 IMU 資料估算出的拳頭相對移動路徑。 |
| 直接錄製 | user 設定正式錄製時間並按下「開始測量」後，系統立刻蒐集正式 IMU 資料，不先進行校正。 |
| 初始參考 | Backend 使用正式錄製開頭的有效 IMU 資料建立計算基準；這是演算法內部處理，不是 user 需要等待或通過的校正階段。 |
| 相對軌跡 | 以每一拳的起點作為原點得到的路徑，不代表精密量測的絕對空間位置。 |
| Session Local Coordinate System | 本次 Result 使用的 X 向右、Y 向前、Z 向上座標系統。 |
| 軌跡點 | Result 中具有時間及 `x_m`、`y_m`、`z_m` 座標的一筆資料。 |
| 使用者視角 | Camera 位於 user 身後並朝正前方觀看軌跡的預設視角。 |
| Drift | IMU 誤差經過積分後逐漸累積，使估算路徑偏離合理位置的現象。 |

## Purpose

讓 user 能以左右手腕 IMU 直接開始出拳軌跡測量，由 Backend 將一場 Session 分成每一拳的相對三維路徑，再由 Desktop App 以容易操作的互動式 3D 圖呈現結果。

## ADDED Requirements

### Requirement: 出拳軌跡必須跳過校正並直接錄製
新版 Desktop App MUST 使用 `punch_trajectory` version 3，要求不同的 `left_wrist` 與 `right_wrist` Common IMU CSV。user 完成 IMU 分配後，畫面 MUST 直接顯示 5 至 3600 秒正式錄製時間及「開始測量」，不得顯示「開始校正」、校正倒數或因校正方向不一致而阻擋測量。Session Metadata MUST 只以 `measurement_start_elapsed_us` 標示正式資料開始位置。

#### Scenario: user 準備正式錄製
- **WHEN** user 已為左、右手腕分配不同 IMU，且 Backend 回報 version 3 可執行
- **THEN** Desktop App 顯示正式錄製時間
- **AND** 主要操作為「開始測量」
- **AND** 畫面不要求 user 保持不動或執行校正

#### Scenario: user 開始出拳軌跡測量
- **WHEN** user 輸入有效時間並按下「開始測量」
- **THEN** Desktop App 立刻開始正式 IMU 資料蒐集
- **AND** Session Parameters 包含有效的 `measurement_start_elapsed_us`
- **AND** Session Parameters 不包含 `calibration_end_elapsed_us`

#### Scenario: 左右手 IMU 初始方向不同
- **WHEN** 兩顆 IMU 的初始 Quaternion 可運算，但方向差異超過原本的校正門檻
- **THEN** Backend 使用 deterministic fallback 繼續產生軌跡
- **AND** Result 以 `warning` 說明顯示方向可能較不準確
- **AND** Analysis Job 不得只因方向不同而失敗

### Requirement: Backend 必須逐拳建立相對三維軌跡
Backend MUST 對左右手腕分別找出有效出拳區段，並 MUST 對每一拳獨立建立相對三維軌跡。每一拳的第一個軌跡點 MUST 是 `(0, 0, 0)`，上一拳的積分誤差 MUST NOT 延續到下一拳；輸出 MUST 明確說明這是估算的相對軌跡，而不是絕對位置量測。

#### Scenario: 一場 Session 包含左右手多拳
- **WHEN** 左右手腕 CSV 包含多個可辨認的出拳區段
- **THEN** Backend 依手別及時間順序產生一個以上的軌跡
- **AND** 每隻手的拳次從 1 依序增加
- **AND** 每一拳都從自己的原點開始

#### Scenario: 正式資料沒有偵測到出拳
- **WHEN** 左右手腕的正式資料都沒有符合規則的出拳區段
- **THEN** Backend 完成分析並回傳總拳數 0 與空的 `trajectories`
- **AND** Desktop App 說明本次沒有偵測到可顯示的出拳軌跡
- **AND** 系統不捏造軌跡

### Requirement: 軌跡 Result 必須版本化且限制顯示資料量
`punch_trajectory` version 3 Result MUST 包含 `algorithm_version`、`coordinate_system`、`distance_unit`、`left_punch_count`、`right_punch_count`、`total_punch_count`、`quality_status`、`warnings` 與 `trajectories`。每一筆 trajectory MUST 包含 `hand`、`punch_index`、`start_elapsed_us`、`end_elapsed_us`、`duration_seconds`、`path_length_m`、`maximum_displacement_m` 與 `points`；每拳回傳的顯示用 `points` MUST 介於 2 至 300 筆，且原始高頻 Common IMU CSV MUST 保持不變。

#### Scenario: Backend 回傳一拳的有效軌跡
- **WHEN** Backend 成功重建一拳軌跡
- **THEN** `distance_unit` 為 `m`
- **AND** 軌跡點依時間排列且所有時間與座標都是有限數值
- **AND** 第一個軌跡點的 `x_m`、`y_m`、`z_m` 都是 0
- **AND** `path_length_m` 與 `maximum_displacement_m` 都是非負有限數值

#### Scenario: 軌跡原始點數超過顯示上限
- **WHEN** 一拳的有效原始資料超過 300 個軌跡點
- **THEN** Backend 回傳不超過 300 個依時間排序的顯示點
- **AND** 第一個與最後一個有效軌跡點仍包含在 Result
- **AND** Backend 保存的原始 Common IMU CSV 不因降採樣而被改寫

### Requirement: 無法運算時不得回傳假軌跡
Backend MUST 驗證必要欄位、時間順序、Quaternion、正式資料量與取樣品質。初始方向不同但資料仍可運算時 MUST 以 warning 完成分析；只有輸入資料不足、無效或運算產生非有限數值時，Analysis Job 才 MUST 標示為失敗並回傳不含內部敏感資訊的說明，不得用零值、隨機點或固定圖形假裝成功。

#### Scenario: CSV 缺少有效 Quaternion
- **WHEN** 任一必要 CSV 缺少有效且可正規化的 Quaternion
- **THEN** Backend 將 Analysis Job 標示為失敗
- **AND** Desktop App 說明 IMU 姿態資料不足並提供重新測量操作
- **AND** 不顯示軌跡圖

#### Scenario: 正式資料不足
- **WHEN** `measurement_start_elapsed_us` 以後沒有足夠的正式 IMU 資料
- **THEN** Backend 拒絕產生軌跡 Result
- **AND** Desktop App 以白話說明正式資料不足

### Requirement: Desktop App 必須以內嵌 Matplotlib 互動式 3D 圖顯示軌跡
Desktop App MUST 讓 user 選擇手別與拳次，並在目前的 BAP 結果頁面以內嵌 Matplotlib 3D 圖呈現該拳的軌跡，不得要求 user 開啟另一個程式視窗。圖形 MUST 標示起點、終點與 X／Y／Z 方向，預設 MUST 使用使用者視角，並 MUST 提供可用鍵盤觸發的使用者視角、側面、上方與重設縮放操作。

#### Scenario: 首次顯示有效軌跡 Result
- **WHEN** Desktop App 收到至少一拳且通過契約驗證的軌跡 Result
- **THEN** 畫面預設選擇時間最早的一拳
- **AND** 3D 圖預設由 user 身後朝出拳方向觀看
- **AND** 起點與終點能以文字、符號或圖例辨認
- **AND** 畫面同時顯示該拳的手別、拳次、持續時間、路徑長度與最大位移

#### Scenario: user 操作 3D 圖
- **WHEN** user 使用滑鼠旋轉、縮放或平移 3D 圖
- **THEN** 軌跡依操作改變 Camera 顯示
- **AND** 分析數值與原始 Result 不會被修改
- **WHEN** user 觸發「使用者視角」或「重設縮放」
- **THEN** 3D 圖回到定義好的預設 Camera 與可看見完整軌跡的範圍

#### Scenario: user 切換手別或拳次
- **WHEN** user 選擇另一隻手或另一拳
- **THEN** 3D 圖與摘要改為顯示所選軌跡
- **AND** 不重新上傳 Session 或重新執行 Backend 分析
