## 名詞定義

| 名詞 | 定義 |
|---|---|
| 沙袋上方 IMU | 固定在沙袋剛性核心上方、對應 `bag_top` 的 IMU。 |
| 沙袋下方 IMU | 固定在沙袋剛性核心下方、對應 `bag_bottom` 的 IMU。 |
| 共同 Packet 時間基準 | 同一個無線接收器為多個 Nodes 提供的共同 `packet_index`。 |
| 有效分配 | 兩顆不同 IMU 來自相同 Port 與 Group ID，且分別指定為沙袋上、下方。 |

## ADDED Requirements

### Requirement: 出拳力量必須分配同一無線接收器的沙袋上下 IMU
Desktop App MUST 在出拳力量探索完成後顯示「沙袋上方」與「沙袋下方」兩個 IMU 位置，並 MUST 只接受相同 Port、相同 Group ID 的兩個不同無線 Node。來源未符合條件時，「繼續」操作 MUST 保持不可使用，且畫面 MUST 以白話說明原因。

#### Scenario: 找到同一 Group 的兩顆無線 IMU
- **WHEN** 三秒探索在同一個 Port 與 Group ID 找到至少兩個不同 Node IDs
- **THEN** user 可以將不同 Nodes 分別指定為沙袋上方與下方 IMU
- **AND** 完成有效分配後可以繼續

#### Scenario: user 選擇不同 Group 或不同 Port
- **WHEN** user 為沙袋上、下方選擇的來源不屬於相同 Port 與 Group ID
- **THEN** Desktop App 說明兩顆 IMU 必須連接到同一個無線接收器並使用相同 Group ID
- **AND** 「繼續」操作保持不可使用

#### Scenario: 探索只找到有線 IMU
- **WHEN** 出拳力量的探索結果沒有任何一組包含兩顆 Nodes 的有效無線接收器
- **THEN** Desktop App 顯示目前找不到可供出拳力量使用的 IMU 組合
- **AND** 不要求 user 以有線來源勉強建立無法可靠對齊的測量

## REMOVED Requirements

### Requirement: 出拳力量配置未決定前不得繼續

**Reason**：本 Change 已將出拳力量配置定為沙袋上方與下方各一顆 IMU，因此不再需要永久阻擋此項目。

**Migration**：Desktop App 改為顯示 `bag_top` 與 `bag_bottom` 的來源選擇，並以新的共同 Port、Group ID 與不同 Node IDs 規則驗證分配。

