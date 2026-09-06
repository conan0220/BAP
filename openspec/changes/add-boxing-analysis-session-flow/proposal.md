## 名詞定義

| 名詞 | 定義 |
|---|---|
| Session | user 從開始到結束的一次拳擊測量；Backend 資料模型允許一個 Session 包含一個以上的 Analysis Job。 |
| Analysis Specification | Desktop App 與 Backend 共同遵守的分析規格，定義唯一名稱、Input Roles、參數與 Result 格式。 |
| Analysis Job | Session 中實際要求 Backend 執行的一次分析工作。 |
| Input Role | Analysis Specification 要求的資料用途，例如 `left_wrist`。 |
| Input Binding | 將 Input Role 對應到本次 Session 內實際 CSV ID 的關係。 |
| Common IMU CSV | 所有拳擊分析共同使用的 IMU 時序資料格式；一顆 IMU 對應一份 CSV，一列代表一幀資料。 |
| Metadata | 描述 Session、CSV、IMU 來源、Input Bindings 與要求執行之 Analyses 的 JSON。 |

## Why

目前 Desktop App 可以探索 IMU 並讓 user 分配位置，但完成分配後只會顯示「待開發」，尚未具備錄製、上傳、保存、建立分析工作與顯示 Backend Result 的共用流程。若每個拳擊項目各自實作這些步驟，CSV、API 與資料模型容易分歧，因此應先建立所有分析項目都能沿用的底層契約與端到端流程。

## What Changes

- 建立從拳擊項目頁面的 IMU 分配完成後，開始錄製、結束錄製、上傳、等待 Backend 分析及顯示 Result 的共用 Session 流程。
- 第一版 UI 仍維持「一個 Session 只選擇一個分析項目」；Backend 與 Metadata 則先支援「一個 Session 包含一個以上 Analysis Job」。
- 建立 Common IMU CSV schema：每顆 IMU 各有一份 CSV，每列代表該 IMU 的一幀資料，所有檔案共用同一個 Session monotonic clock。
- 建立前後端共用的 Analysis Specification，使用唯一 `analysis_type`、版本、Input Roles、參數契約與 Result 契約描述分析能力。
- 以 Input Bindings 將某個 Analysis Job 的 Input Roles 對應到 Session 中實際的 CSV IDs，讓同一份 CSV 未來可以被多個分析使用。
- Desktop App 以通過驗證的 Access Token，透過 HTTPS multipart request 一次上傳 Metadata 與一份以上的 CSV。
- Backend 驗證 Metadata、CSV schema、row count、檔案大小、SHA-256 及所有引用關係，再以完整交易保存 Session、原始 CSV、Analysis Jobs 與 Input Bindings。
- Backend 提供非同步分析狀態與 Result 查詢介面；Desktop App 顯示上傳中、分析中、完成或失敗等狀態。
- 建立可替換的 Analysis Executor 介面及測試用 Executor，驗證完整資料流；本 Change 不定義出拳次數、出拳速度等實際運算公式，也不回傳偽造的拳擊分析結果。
- Backend 未註冊某個 Analysis Executor 時，系統清楚回報該分析尚未提供，不要求 user 完成無法得到結果的錄製。

## Capabilities

### New Capabilities

- `boxing-analysis-session`: 定義 Desktop App 與 Backend 共同管理 Session、Analysis Job、狀態及 Result 的完整生命週期。
- `common-imu-csv`: 定義一顆 IMU 一份 CSV、每列一幀資料、跨檔案共用時間基準與版本化 schema。
- `analysis-specification-contract`: 定義 Analysis Specification、唯一 Analysis Type、Input Roles、Input Bindings、Parameters 與 Result 契約。
- `analysis-session-ingestion`: 定義登入後的 multipart 上傳、完整性驗證、Database 原始 CSV 保存及可重試的非同步分析狀態 API。

### Modified Capabilities

- `imu-source-discovery`: 對已註冊且可執行的拳擊分析項目，完成有效 IMU 分配後改為進入 Session 錄製流程；尚未提供 Executor 的項目仍清楚顯示待開發。
- `desktop-ui-design`: 增加拳擊測量的準備、錄製、上傳、分析及 Result 狀態，並維持目前一次只操作一個分析項目的 UI。

## Impact

- Desktop App：拳擊項目頁面、Session controller、IMU recorder、Common CSV writer、Metadata builder、Backend API client 與 Result 畫面。
- Backend：FastAPI Session／Analysis endpoints、Pydantic schemas、SQLAlchemy models、Repositories、Services、Analysis Executor registry 與 Alembic migration。
- Database：新增 Session、IMU CSV file、Analysis Job、Input Binding 與 Analysis Result 資料結構；原始 CSV 以完整 bytes 保存。
- 共用契約：新增版本化 Common IMU CSV 與 Analysis Specification models，供前端、後端及 contract tests 共用。
- 測試：新增 CSV contract、上傳驗證、Database transaction、Analysis 狀態、失敗重試及 Desktop-to-Backend E2E tests。
- 不包含：任何拳擊分析演算法、模型訓練、演算法門檻值，以及單一 Session 同時選取多個分析項目的新 UI。
