## 名詞定義

| 名詞 | 定義 |
|---|---|
| 有效分配 | 每個必要 Input Role 都分配到一顆本次探索找到的可用 IMU，且不違反該 Analysis Specification 的重複使用規則。 |
| Registered Analysis | Desktop App 與 Backend 支援相同 Analysis Specification，而且 Backend 已提供可執行 Executor 的分析項目。 |
| Session 準備 | 完成 IMU 分配後、正式錄製開始前，用來確認分析能力與本次設定的畫面。 |
| 待開發 | Analysis Specification 或 Executor 尚未提供，因此不能開始正式測量的狀態。 |

## ADDED Requirements

### Requirement: 完成選擇後必須依分析能力決定下一步
Desktop App MUST 在 user 完成目前拳擊項目的有效 IMU 分配後，確認相同版本的 Analysis Specification 與 Backend Executor 是否可用。可執行時 MUST 進入 Session 準備流程；不可執行時 MUST 顯示待開發，且不得錄製或上傳正式測量資料。三秒探索資料在來源確認完成後 MUST 清除，不得混入正式 Session CSV。

#### Scenario: 已註冊分析完成有效分配
- **WHEN** user 已為 Registered Analysis 的所有 Input Roles 完成有效 IMU 分配並執行「繼續」
- **THEN** Desktop App 進入 Session 準備畫面
- **AND** 正式錄製尚未開始

#### Scenario: 分析 Executor 尚未提供
- **WHEN** user 完成 IMU 分配，但 Backend 沒有該 Analysis Type 與版本的 Executor
- **THEN** Desktop App 顯示該項目待開發或目前無法分析
- **AND** Desktop App 不錄製或上傳正式測量資料

#### Scenario: 探索資料與正式資料分離
- **WHEN** Desktop App 使用三秒探索資料完成 IMU 來源確認
- **THEN** Desktop App 在不再需要後清除探索暫存資料
- **AND** user 按下「開始測量」後才建立正式 Session CSV

#### Scenario: 尚有必要 Input Role 未分配
- **WHEN** 目前項目仍有至少一個必要 Input Role 尚未選擇 IMU
- **THEN** 「繼續」操作保持不可使用
- **AND** Desktop App 不進入 Session 準備畫面

## REMOVED Requirements

### Requirement: 完成選擇後只顯示待開發

**Reason**: 系統開始提供共用的正式錄製、上傳與 Backend 分析流程，已註冊且可執行的項目不能再一律停在待開發畫面。

**Migration**: 改由「完成選擇後必須依分析能力決定下一步」判斷；尚未提供 Executor 的項目仍維持待開發且不收集正式資料。
