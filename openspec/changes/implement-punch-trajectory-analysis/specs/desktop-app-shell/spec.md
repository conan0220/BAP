## 名詞定義

| 名詞 | 定義 |
|---|---|
| 可使用 | Backend 已提供相同 Analysis Type 與版本的 Production Executor，user 能完成測量並取得真實 Result。 |
| 待開發 | Backend 尚未提供相同 Analysis Type 與版本的 Production Executor，不能開始正式測量。 |
| 出拳軌跡 | 以左右手腕 IMU 估算逐拳相對三維移動路徑的分析項目。 |

## MODIFIED Requirements

### Requirement: 拳擊測量項目分開呈現
Desktop App MUST 將出拳次數、出拳速度、出拳力量、出拳軌跡及拳種辨識分成五個獨立入口，不得提供同時選擇兩個以上項目的量測流程；所有 user 可見位置 MUST 使用「拳種辨識」，不得再顯示「拳型辨識」。Backend 已提供相同版本 Production Executor 的項目 MUST 顯示為可使用；尚未提供的項目 MUST 顯示為待開發。

#### Scenario: 查看拳擊測量項目
- **WHEN** user 查看主畫面或拳擊測量導覽
- **THEN** Desktop App 分別顯示五個拳擊測量項目
- **AND** 已提供 Production Executor 的項目顯示為可使用
- **AND** 尚未提供 Production Executor 的項目顯示為待開發
- **AND** 第五個項目顯示為「拳種辨識」

#### Scenario: 進入單一拳擊項目
- **WHEN** user 點選一個拳擊測量項目
- **THEN** Desktop App 只為該項目啟動 IMU 來源探索流程
- **AND** Desktop App 不要求 user 同時選擇其他拳擊測量項目
- **AND** 項目頁面標題與 user 所選的項目一致

#### Scenario: 出拳軌跡 version 3 可執行
- **WHEN** Backend 回報 `punch_trajectory` version 3 已有可執行的 Production Executor
- **THEN** 出拳軌跡入口顯示為可使用
- **AND** user 能進入該項目的 IMU 探索、直接錄製及 Result flow

### Requirement: 待開發項目不得假裝已有分析功能
Desktop App MUST 在 user 選擇尚未提供相同版本 Production Executor 的拳擊測量項目後顯示該項目仍待開發，且不得開始正式拳擊資料錄製、產生分析數值或顯示假結果。已提供相同版本 Production Executor 的項目不受此限制。

#### Scenario: 完成待開發項目的 IMU 來源選擇
- **WHEN** user 為尚未提供 Production Executor 的項目選好 IMU 來源
- **THEN** Desktop App 顯示該項目「待開發」或目前無法分析
- **AND** Desktop App 不開始正式拳擊資料錄製
- **AND** Desktop App 不顯示假分析結果

#### Scenario: 出拳軌跡 Executor 可用
- **WHEN** user 進入出拳軌跡，且 Backend 回報 `punch_trajectory` version 3 可執行
- **THEN** Desktop App 允許 user 設定時間並直接開始正式測量
- **AND** Desktop App 不顯示「開始校正」或校正倒數
- **AND** Desktop App 只顯示 Backend 實際回傳且通過契約驗證的軌跡 Result
