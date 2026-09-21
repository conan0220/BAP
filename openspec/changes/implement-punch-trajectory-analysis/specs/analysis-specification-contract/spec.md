## 名詞定義

| 名詞 | 定義 |
|---|---|
| punch_trajectory | 出拳軌跡使用的穩定 Analysis Type。 |
| Specification version 3 | 不含 user 校正階段、直接錄製出拳軌跡的契約版本。 |
| measurement_start_elapsed_us | user 按下「開始測量」後，正式 IMU 資料開始的位置。 |
| Trajectory | Result 中一隻手某一拳的相對三維路徑與摘要。 |
| Trajectory point | Trajectory 中具有時間與三軸公尺座標的一個顯示點。 |

## ADDED Requirements

### Requirement: punch_trajectory version 3 必須使用直接錄製契約
`punch_trajectory` version 3 MUST 使用不同的 `left_wrist` 與 `right_wrist` Input Roles，且 MUST 只要求正整數 `measurement_start_elapsed_us` 作為錄製時間邊界，不得要求 `calibration_end_elapsed_us`。Result MUST 以明確欄位定義演算法版本、座標系統、距離單位、左右手拳數、總拳數、品質警告及逐拳軌跡。Backend MAY 保留 version 2 Executor 讀取舊 Session，但新版 Desktop App MUST 使用 version 3。

#### Scenario: 前後端使用相同的 version 3
- **WHEN** Desktop App 與 Backend 都支援 `punch_trajectory` version 3
- **THEN** Desktop App 提交左右手腕 Input Bindings 與正式測量開始時間
- **AND** 不提交校正結束時間
- **AND** Backend 依 version 3 驗證輸入及 Result

#### Scenario: version 3 收到校正參數
- **WHEN** version 3 Analysis Parameters 包含 `calibration_end_elapsed_us`
- **THEN** 契約將它視為未知參數並拒絕請求
- **AND** 系統不會暗中回到兩階段校正流程

#### Scenario: Result 的拳數與 trajectories 不一致
- **WHEN** 總拳數不等於左右手拳數相加，或拳數無法由 `trajectories` 重新得到
- **THEN** Result 契約驗證失敗
- **AND** Backend 不保存為成功 Result
