## 名詞定義

| 名詞 | 定義 |
|---|---|
| Metadata version 1 | 既有 Session Metadata 格式，不包含預定時間、實際時間與結束原因。 |
| Metadata version 2 | 新增 Session duration 與 stop reason 的 Session Metadata 格式。 |
| 相容 migration | 更新 Database schema，同時保留並可讀取既有資料的 migration。 |

## ADDED Requirements

### Requirement: Backend 必須相容新版 Session duration Metadata
Backend MUST 接受 Metadata version 2，驗證並保存 `requested_duration_seconds`、`actual_duration_seconds` 與 `stop_reason`。支援的結束原因 MUST 包含 `duration_reached`、`ended_by_user` 與 `source_interrupted`。Database migration MUST 保留既有 Session、CSV BLOB、Analysis Job 與 Result，不得要求刪除或重建正式 Database。

#### Scenario: Desktop 上傳 Metadata version 2
- **WHEN** 已登入 user 上傳包含有效 duration 欄位與完整 CSV 的 Metadata version 2 Session
- **THEN** Backend 保存預定時間、實際時間與結束原因
- **AND** Session 依既有流程建立並執行 Analysis Job

#### Scenario: duration 欄位不符合格式
- **WHEN** Metadata version 2 缺少必要 duration 欄位、數值超出允許範圍，或 `stop_reason` 不是支援的值
- **THEN** Backend 拒絕整個 Session package
- **AND** 不留下部分 Session 或 CSV

#### Scenario: Desktop 上傳來源中斷的部分 Session
- **WHEN** 左右手 CSV 都已有有效資料，且 Metadata version 2 的 `stop_reason` 為 `source_interrupted`
- **THEN** Backend 保存中斷前的完整 CSV rows 與實際錄製時間
- **AND** Session 依既有流程建立並執行 Analysis Job

#### Scenario: 既有 Metadata version 1 Session
- **WHEN** migration 前已保存的 Metadata version 1 Session 被查詢
- **THEN** Backend 仍能讀取其原始 Session、CSV 與 Analysis Result
- **AND** 不捏造不存在的預定時間或結束原因
