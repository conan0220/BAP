## 名詞定義

| 名詞 | 定義 |
|---|---|
| Analysis Specification | 前後端共同遵守的分析規格，定義 Analysis Type、版本、Input Roles、Parameters 與 Result schema。 |
| Analysis Type | 一種分析能力的唯一且穩定名稱，例如 `punch_count`。 |
| Input Role | Analysis Specification 要求的資料用途，例如 `left_wrist`。 |
| Input Binding | 在 Analysis Job 中將 Input Role 對應到實際 CSV ID 的關係。 |
| Parameters | 某次 Analysis Job 可調整的輸入設定。 |
| Result schema | Analysis Job 成功後允許回傳的 JSON 結構。 |
| Executor | Backend 中負責依某份 Analysis Specification 執行實際分析的可替換元件。 |

## Purpose

建立 Desktop App 與 Backend 都能驗證的 Analysis Specification，讓分析名稱、必要 IMU 用途、實際 CSV 對應及 Result 格式不會在前後端各自解讀。

## ADDED Requirements

### Requirement: 每種 Analysis 必須有唯一且版本化的規格
每種可提交的分析 MUST 具有唯一 `analysis_type`、正整數 `spec_version`、user 可閱讀的名稱、Input Roles、Parameters schema 與 Result schema。Desktop App 與 Backend MUST 使用相同版本的規格判斷輸入與輸出是否有效。

#### Scenario: 前後端支援相同規格
- **WHEN** Desktop App 以 Backend 支援的 Analysis Type 與 Specification version 建立 Analysis Job
- **THEN** Backend 依該版本驗證 Input Bindings、Parameters 與 Result

#### Scenario: 前後端規格版本不一致
- **WHEN** Desktop App 提交 Backend 不支援的 Specification version
- **THEN** Backend 拒絕建立該 Analysis Job
- **AND** 回應包含可辨認的 specification version 錯誤

### Requirement: Input Role 必須描述需求而不是實際裝置
Analysis Specification MUST 以穩定的 Input Role 名稱定義每個必要或選填資料用途及數量，不得在規格中寫死 Port、Group ID、Node ID 或 CSV ID。某次 Session 使用的實際裝置 MUST 透過 Input Binding 指定。

#### Scenario: 出拳次數輸入規格
- **WHEN** 系統讀取 `punch_count` 的初始 Analysis Specification
- **THEN** 規格要求一份 `left_wrist` IMU CSV 與一份 `right_wrist` IMU CSV
- **AND** 規格不指定實際 Port、Group ID、Node ID 或 CSV ID

#### Scenario: Session 建立實際輸入對應
- **WHEN** user 為左右手腕選定兩顆 IMU 並建立 `punch_count` Analysis Job
- **THEN** Metadata 以 Input Bindings 將 `left_wrist` 與 `right_wrist` 分別對應到實際 CSV ID

### Requirement: Backend 必須完整驗證 Input Bindings
Backend MUST 確認每個必要 Input Role 都有符合數量與資料類型的 Binding、所有 CSV ID 都屬於同一個 Session，且沒有未知或重複的 Role。若規格不允許同一份 CSV 滿足多個 Roles，Backend MUST 拒絕該對應。

#### Scenario: 必要 Role 缺少 Binding
- **WHEN** `punch_count` Analysis Job 只提供 `left_wrist` Binding
- **THEN** Backend 拒絕建立該 Analysis Job
- **AND** 回應指出缺少 `right_wrist`

#### Scenario: Binding 引用其他 Session 的 CSV
- **WHEN** Input Binding 引用不屬於目前 Session 的 CSV ID
- **THEN** Backend 拒絕該 Input Binding

#### Scenario: 左右手綁定同一份 CSV
- **WHEN** `punch_count` 的 `left_wrist` 與 `right_wrist` 指向相同 CSV ID
- **THEN** Backend 拒絕建立該 Analysis Job

### Requirement: 同一份 CSV 必須可以被多個 Analysis Jobs 重複使用
Session 中的一份 IMU CSV MUST 能被不同 Analysis Jobs 的 Input Bindings 引用，且重複使用時 MUST NOT 複製或改寫原始 CSV。

#### Scenario: 同一對左右手 CSV 供兩種分析使用
- **WHEN** 一個 Session 的 `punch_count` 與另一個 Analysis Job 都把相同兩份 CSV 綁定為左右手輸入
- **THEN** Backend 為兩個 Jobs 保存各自的 Input Bindings
- **AND** Session 仍只保存原本的兩份 IMU CSV

### Requirement: 未註冊的分析不得產生偽造 Result
Backend MUST 只執行已註冊且版本相符的 Executor。Analysis Type 已知但 Executor 尚未提供時，系統 MUST 回報不可執行；不得使用固定數字、空物件或隨機資料假裝分析成功。

#### Scenario: Analysis Type 沒有 Executor
- **WHEN** Client 要求執行沒有已註冊 Executor 的 Analysis Type
- **THEN** Backend 回報該分析目前不可執行
- **AND** 不建立成功 Result

#### Scenario: 測試使用替代 Executor
- **WHEN** 自動測試明確注入符合相同介面的測試用 Executor
- **THEN** 系統可以用它驗證 Session 到 Result 的完整流程
- **AND** Production 不會將測試用 Result 當成真實拳擊分析結果

### Requirement: Result 必須符合 Analysis Specification
Backend MUST 在將 Analysis Job 標示為完成以前，以對應的 Result schema 驗證 Executor 輸出。Desktop App MUST 依 Analysis Type 與版本解讀 Result，且 MUST 拒絕把不符合契約的內容顯示成成功結果。

#### Scenario: Executor 回傳有效 Result
- **WHEN** Executor 回傳符合該 Analysis Specification 的 JSON
- **THEN** Backend 保存 Result 並將 Analysis Job 標示為完成

#### Scenario: Executor 回傳錯誤格式
- **WHEN** Executor 回傳缺少必要欄位或型別錯誤的 JSON
- **THEN** Backend 將 Analysis Job 標示為失敗
- **AND** 不保存為成功 Result
