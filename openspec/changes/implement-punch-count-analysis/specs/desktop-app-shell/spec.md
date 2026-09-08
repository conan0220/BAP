## 名詞定義

| 名詞 | 定義 |
|---|---|
| 可使用 | user 可以完成 IMU 分配、錄製、上傳並取得真實 Backend Result。 |
| 待開發 | 畫面可保留入口，但不能錄製正式資料或顯示假分析結果。 |

## MODIFIED Requirements

### Requirement: 拳擊測量項目分開呈現
Desktop App MUST 將出拳次數、出拳速度、出拳力量、出拳軌跡及拳種辨識分成五個獨立入口，不得提供同時選擇兩個以上項目的量測流程；所有 user 可見位置 MUST 使用「拳種辨識」，不得再顯示「拳型辨識」。出拳次數 MUST 顯示為可使用；其他尚未提供 Production Executor 的項目 MUST 顯示為待開發。

#### Scenario: 查看拳擊測量項目
- **WHEN** user 查看主畫面或拳擊測量導覽
- **THEN** Desktop App 分別顯示五個拳擊測量項目
- **AND** 出拳次數顯示為可使用
- **AND** 出拳速度、出拳力量、出拳軌跡與拳種辨識顯示為待開發
- **AND** 第五個項目顯示為「拳種辨識」

#### Scenario: 進入單一拳擊項目
- **WHEN** user 點選一個拳擊測量項目
- **THEN** Desktop App 只為該項目啟動 IMU 來源探索流程
- **AND** Desktop App 不要求 user 同時選擇其他拳擊測量項目
- **AND** 項目頁面標題與 user 所選的項目一致

### Requirement: 待開發項目不得假裝已有分析功能
Desktop App MUST 在 user 選擇尚未提供 Production Executor 的拳擊測量項目後顯示該項目仍待開發，且不得開始正式拳擊資料錄製、產生分析數值或顯示假結果。已提供 Production Executor 的出拳次數不受此限制。

#### Scenario: 完成待開發項目的 IMU 來源選擇
- **WHEN** user 為出拳速度、出拳力量、出拳軌跡或拳種辨識選好 IMU 來源
- **THEN** Desktop App 顯示該項目「待開發」
- **AND** Desktop App 不開始正式拳擊資料錄製
- **AND** Desktop App 不顯示力量、速度、軌跡或拳種結果

#### Scenario: 出拳次數 Executor 可用
- **WHEN** user 進入出拳次數並且 Backend 回報 `punch_count` version 1 可執行
- **THEN** Desktop App 允許 user 完成該項目的正式測量流程
- **AND** Desktop App 只顯示 Backend 實際回傳且通過契約驗證的拳數 Result