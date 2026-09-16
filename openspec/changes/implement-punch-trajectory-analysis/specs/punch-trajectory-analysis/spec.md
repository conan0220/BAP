## 名詞定義

| 名詞 | 定義 |
|---|---|
| 出拳軌跡 | 根據手腕 IMU 資料估算出的拳頭相對移動路徑。 |
| 相對軌跡 | 以每一拳的起點作為原點得到的路徑，不代表精密量測的絕對空間位置。 |
| 校正階段 | 正式錄製前，user 面向出拳方向並保持準備姿勢不動的兩秒資料區段。 |
| Session Local Coordinate System | 以校正姿勢建立的本次測量座標系統，其中 X 表示左右、Y 表示前後、Z 表示上下。 |
| 軌跡點 | Result 中具有時間及 `x_m`、`y_m`、`z_m` 座標的一筆資料。 |
| 使用者視角 | Camera 位於 user 身後並朝正前方觀看軌跡的預設視角。 |
| Drift | IMU 誤差經過積分後逐漸累積，使估算路徑偏離合理位置的現象。 |

## Purpose

讓 user 能以左右手腕 IMU 完成出拳軌跡測量，由 Backend 將一場 Session 分成每一拳的相對三維路徑，再由 Desktop App 以容易操作的互動式 3D 圖呈現結果。

## ADDED Requirements

### Requirement: 出拳軌跡必須使用左右手腕資料與明確校正階段
`punch_trajectory` version 2 MUST 要求不同的 `left_wrist` 與 `right_wrist` Common IMU CSV。Desktop App MUST 在正式測量以前錄製兩秒校正資料，MUST 以 `calibration_end_elapsed_us` 標示校正資料結束的位置，並 MUST 以 `measurement_start_elapsed_us` 標示 user 按下按鈕後正式資料開始的位置。兩個時間點之間的等待與準備動作 MUST NOT 被 Backend 當成校正資料或正式出拳。

#### Scenario: user 準備校正
- **WHEN** user 已為左、右手腕分配不同 IMU，且 Backend 回報 `punch_trajectory` version 2 可執行
- **THEN** Desktop App 提示 user 面向預計出拳方向，保持準備姿勢並讓雙手暫時不動
- **AND** 畫面以「開始校正」作為主要操作
- **AND** 畫面尚不要求 user 輸入正式錄製時間

#### Scenario: 校正完成後開始正式測量
- **WHEN** 左右手腕都完成兩秒校正資料錄製
- **THEN** Desktop App 說明校正已完成
- **AND** 讓 user 輸入 5 至 3600 秒的正式錄製時間
- **AND** 等 user 按下「開始正式測量」後才開始計算正式錄製時間
- **AND** Session Metadata 的 Analysis Parameters 包含有效的 `calibration_end_elapsed_us` 與 `measurement_start_elapsed_us`
- **AND** user 在兩個時間點之間的操作或準備動作不影響校正穩定性判斷

#### Scenario: 校正期間姿態不穩定
- **WHEN** 校正資料可讀取及運算，但 Quaternion 變動超過穩定門檻
- **THEN** Backend MUST 使用 deterministic fallback 繼續產生軌跡
- **AND** Result 的 `quality_status` MUST 為 `warning`
- **AND** `warnings` MUST 說明方向或位置漂移可能較大
- **AND** Desktop App MUST 顯示警告及分析結果，不得只因校正不穩定而停止分析

#### Scenario: 校正期間 IMU 中斷
- **WHEN** 任一必要 IMU 在校正完成以前中斷
- **THEN** Desktop App 停止本次校正並顯示白話原因
- **AND** 不上傳不完整的正式 Session
- **AND** 提供重新檢測 IMU 的操作

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
`punch_trajectory` version 2 Result MUST 包含 `algorithm_version`、`coordinate_system`、`distance_unit`、`left_punch_count`、`right_punch_count`、`total_punch_count`、`quality_status`、`warnings` 與 `trajectories`。每一筆 trajectory MUST 包含 `hand`、`punch_index`、`start_elapsed_us`、`end_elapsed_us`、`duration_seconds`、`path_length_m`、`maximum_displacement_m` 與 `points`；每拳回傳的顯示用 `points` MUST 介於 2 至 300 筆，且原始高頻 Common IMU CSV MUST 保持不變。

#### Scenario: Backend 回傳一拳的有效軌跡
- **WHEN** Backend 成功重建一拳軌跡
- **THEN** `distance_unit` 為 `m`
- **AND** `coordinate_system` 能辨認 X 為左右、Y 為前後、Z 為上下的 Session Local Coordinate System
- **AND** 軌跡點依時間排列且所有時間與座標都是有限數值
- **AND** 第一個軌跡點的 `x_m`、`y_m`、`z_m` 都是 0
- **AND** `path_length_m` 與 `maximum_displacement_m` 都是非負有限數值

#### Scenario: 軌跡原始點數超過顯示上限
- **WHEN** 一拳的有效原始資料超過 300 個軌跡點
- **THEN** Backend 回傳不超過 300 個依時間排序的顯示點
- **AND** 第一個與最後一個有效軌跡點仍包含在 Result
- **AND** Backend 保存的原始 Common IMU CSV 不因降採樣而被改寫

### Requirement: 無法可靠分析時不得回傳假軌跡
Backend MUST 驗證必要欄位、時間順序、Quaternion、校正資料與取樣品質。校正姿態不穩定但資料仍可運算時 MUST 以 warning 完成分析；只有輸入資料不足、無效或運算產生非有限數值時，Analysis Job 才 MUST 標示為失敗並回傳不含內部敏感資訊的說明，不得用零值、隨機點或固定圖形假裝成功。

#### Scenario: CSV 缺少有效 Quaternion
- **WHEN** 任一必要 CSV 缺少有效且可正規化的 Quaternion
- **THEN** Backend 將 Analysis Job 標示為失敗
- **AND** Desktop App 說明 IMU 姿態資料不足並提供重新測量操作
- **AND** 不顯示軌跡圖

#### Scenario: 校正資料不足
- **WHEN** `calibration_end_elapsed_us` 以前沒有足夠的靜止校正資料
- **THEN** Backend 拒絕產生軌跡 Result
- **AND** Desktop App 以白話說明校正資料不足

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
