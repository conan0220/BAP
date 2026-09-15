## 名詞定義

| 名詞 | 定義 |
|---|---|
| `punch_force` | 出拳力量 Analysis Type 的穩定名稱。 |
| Input Role | Analysis Specification 對輸入資料用途的命名。 |
| Parameters | 本次出拳力量分析使用的時間邊界與沙袋物理參數。 |
| Result schema | Backend 與 Desktop App 共同驗證的出拳力量結果格式。 |

## ADDED Requirements

### Requirement: punch_force version 1 必須使用明確的 Analysis Specification
`punch_force` version 1 MUST 使用 `bag_top` 與 `bag_bottom` Input Roles。Parameters MUST 包含 `calibration_end_elapsed_us`、`measurement_start_elapsed_us`、`bag_mass_kg`、`bag_length_m`、`bag_diameter_m` 與 `sensor_distance_m`。Result schema MUST 明確定義 `algorithm_version`、`peak_elapsed_us`、`peak_force_n`、`peak_force_kgf`、`peak_com_acceleration_g`、`impact_height_from_bottom_m`、`impact_offset_from_center_m`、`sample_rate_hz`、`quality_status`、`warnings` 與 `curve_points`。

#### Scenario: 前後端支援相同的 punch_force 規格
- **WHEN** Desktop App 以 `punch_force` version 1、完整 Parameters 及兩個必要 Input Bindings 建立 Analysis Job
- **THEN** Backend 依 version 1 契約驗證輸入並執行已註冊 Executor
- **AND** Desktop App 只將通過相同 Result schema 的內容顯示為成功

#### Scenario: 出拳力量缺少必要參數
- **WHEN** Analysis Job 缺少任一時間邊界或沙袋物理參數
- **THEN** Backend 拒絕該 Analysis Job
- **AND** 回應指出缺少或無效的 Parameter

#### Scenario: 出拳力量 Result 的單位或關聯不一致
- **WHEN** Result 的 Newton 與 kgf 不符合固定換算、品質狀態與 warnings 不一致，或顯示曲線超過上限
- **THEN** Result 契約驗證失敗
- **AND** Backend 不將該 Result 保存為成功

