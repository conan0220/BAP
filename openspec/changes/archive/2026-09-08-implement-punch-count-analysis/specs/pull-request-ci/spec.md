## 名詞定義

| 名詞 | 定義 |
|---|---|
| Punch-count Benchmark | 固定版本、包含左右手 Common IMU CSV 與人工 Ground Truth 的測試資料集。 |
| Benchmark ZIP | Benchmark Recorder 匯出的自包含測試檔，內含 `metadata.json` 與兩份 Common IMU CSV。 |
| 回歸 | 修改後的演算法讓原本通過的 Benchmark case 產生錯誤結果。 |
| Source-level Benchmark test | 直接從 repository 載入 Executor 與 fixtures，不經 Installer 或正式 Server 的 pytest。 |

## ADDED Requirements

### Requirement: Source-level CI 必須執行出拳次數 Benchmark
非 docs-only PR 的 source-level tests MUST 對 repository 內所有已核准的 Punch-count Benchmark cases 執行 Production `punch_count` Executor，並分別比較左手、右手與總拳數。任一 case 與 Ground Truth 不符時，CI MUST 失敗。

#### Scenario: 所有 Benchmark cases 計算正確
- **WHEN** Production Executor 對每個固定 case 都產生與 Ground Truth 相同的左右手與總拳數
- **THEN** Punch-count Benchmark test 通過
- **AND** CI 可以繼續執行後續 Candidate Build 與 Artifact E2E

#### Scenario: 任一手的拳數發生回歸
- **WHEN** 任一 case 的左手、右手或總拳數與 Ground Truth 不同
- **THEN** pytest 回報失敗並指出 case ID、預期值與實際值
- **AND** CI MUST NOT 將該次 Candidate 視為可交付

### Requirement: Benchmark 內容必須可追溯且不被測試修改
每個 case MUST 使用既有的自包含 Benchmark ZIP 契約，並具有固定 case ID、Benchmark schema version、左右手 CSV、Ground Truth 與檔案完整性資訊。CI MUST 直接載入 Repository 中的 ZIP，不得要求另一份跨案例 Manifest。測試 MUST 以唯讀方式使用 fixtures，且重複執行 MUST 產生相同結果。

#### Scenario: 同一 commit 重跑 Benchmark
- **WHEN** CI 對相同 Source Tree 重複執行 Punch-count Benchmark
- **THEN** 測試使用相同 fixtures 與 Ground Truth
- **AND** 產生相同通過或失敗結果

#### Scenario: Fixture 缺少必要內容
- **WHEN** case 缺少任一手 CSV、Ground Truth、schema version 或完整性資訊
- **THEN** pytest 將該 case 視為無效並失敗
- **AND** 不略過該 case 或以零拳代替

#### Scenario: CI 載入既有 Benchmark ZIP
- **WHEN** CI 掃描 `tests/fixtures/punch_count/` 中已核准的 Benchmark ZIP
- **THEN** 共用 Loader 從每份 ZIP 的 `metadata.json` 取得 CSV、Ground Truth 與完整性資訊
- **AND** CI 不需要另外產生或維護第二份 Manifest
