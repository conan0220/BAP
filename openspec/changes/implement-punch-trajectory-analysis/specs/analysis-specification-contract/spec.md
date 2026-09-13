## 名詞定義

| 名詞 | 定義 |
|---|---|
| punch_trajectory | 出拳軌跡使用的穩定 Analysis Type。 |
| Specification version 2 | 本 Change 定義的出拳軌跡輸入、校正參數與 Result 契約版本。 |
| Trajectory | Result 中一隻手某一拳的相對三維路徑與摘要。 |
| Trajectory point | Trajectory 中具有時間與三軸公尺座標的一個顯示點。 |

## ADDED Requirements

### Requirement: punch_trajectory version 2 必須使用明確契約
`punch_trajectory` version 2 MUST 使用不同的 `left_wrist` 與 `right_wrist` Input Roles，MUST 要求正整數 `measurement_start_elapsed_us` Parameter，並 MUST 以明確欄位定義版本、座標系統、距離單位、左右手拳數、總拳數及逐拳軌跡。Backend MUST NOT 讓只認得 version 1 `summary` placeholder 的舊 Desktop App 執行 version 2。

#### Scenario: 前後端使用相同的 version 2
- **WHEN** Desktop App 與 Backend 都支援 `punch_trajectory` version 2
- **THEN** Desktop App 能提交左右手腕 Input Bindings 與校正結束時間
- **AND** Backend 依 version 2 驗證輸入及 Result

#### Scenario: version 2 Result 仍使用 summary placeholder
- **WHEN** Executor 只回傳 `summary` 或缺少任一必要 version 2 欄位
- **THEN** Backend 拒絕將 Analysis Job 標示為完成
- **AND** Desktop App 不把該內容顯示成有效軌跡

#### Scenario: Result 的拳數與 trajectories 不一致
- **WHEN** 總拳數不等於左右手拳數相加，或拳數無法由 `trajectories` 重新得到
- **THEN** Result 契約驗證失敗
- **AND** Backend 不保存為成功 Result
