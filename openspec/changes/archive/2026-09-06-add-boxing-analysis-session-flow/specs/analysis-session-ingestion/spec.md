## 名詞定義

| 名詞 | 定義 |
|---|---|
| Multipart request | 在同一個 HTTPS request 中一起傳送 Metadata JSON 與一份以上 CSV 的請求。 |
| Session owner | 由 Access Token 識別、擁有該 Session 的 user。 |
| Atomic save | Metadata 或任一 CSV 保存失敗時，不留下部分 Session 資料的保存方式。 |
| Idempotent retry | Client 使用相同 Session ID 與相同內容重試後，不會建立重複資料的行為。 |
| CSV blob | Database 中完整保存的一份原始 CSV bytes。 |
| Analysis Status | Analysis Job 的 `pending`、`processing`、`completed` 或 `failed` 狀態。 |

## Purpose

提供安全且可重試的 Session 上傳與查詢介面，確保 Metadata 和所有 IMU CSV 經過完整驗證後一起保存，並讓 Desktop App 取得可靠的分析狀態與 Result。

## ADDED Requirements

### Requirement: Session 上傳必須驗證登入身分
Backend MUST 只接受帶有有效 Access Token 的 Session 上傳與查詢要求，並 MUST 以 Token 中的 user 身分設定 Session owner，不得信任 Client 自行提交的 user ID。

#### Scenario: 已登入 user 上傳 Session
- **WHEN** Desktop App 使用有效 Access Token 上傳 Session
- **THEN** Backend 將目前 Token 對應的 user 設為 Session owner

#### Scenario: 未登入 Client 上傳 Session
- **WHEN** Client 未提供有效 Access Token
- **THEN** Backend 拒絕 Session 上傳
- **AND** 不保存 Metadata 或 CSV

#### Scenario: user 查詢別人的 Session
- **WHEN** 已登入 user 查詢不屬於自己的 Session 或 Analysis Job
- **THEN** Backend 不回傳該 Session 的 Metadata、CSV 或 Result

### Requirement: Client 必須一次提交完整的 Session package
Desktop App MUST 以 multipart request 提交一份 Metadata JSON 與 Metadata 宣告的所有 IMU CSV。Backend MUST 確認每個 CSV ID 與檔名唯一、每個 descriptor 都有對應檔案、沒有未宣告檔案，而且 Analysis Input Bindings 只引用本次 package 中的 CSV IDs。

#### Scenario: 完整提交兩顆 IMU 資料
- **WHEN** Metadata 宣告兩份 CSV，request 也包含兩份名稱與 ID 相符的 CSV
- **THEN** Backend 繼續執行 schema 與完整性驗證

#### Scenario: Metadata 引用缺少的 CSV
- **WHEN** Metadata 宣告或 Input Binding 引用的 CSV 沒有包含在 request 中
- **THEN** Backend 拒絕整個 Session package

#### Scenario: Request 包含未宣告 CSV
- **WHEN** multipart request 包含 Metadata 沒有宣告的 CSV
- **THEN** Backend 拒絕整個 Session package

### Requirement: Backend 必須驗證 CSV 內容與 descriptor
Backend MUST 驗證 Common IMU CSV schema version、header、資料列格式、row count、檔案大小及 SHA-256。Backend MUST 對單檔與整個 request 套用可設定的大小限制，超過限制時在寫入正式資料前拒絕 request。

#### Scenario: CSV 完整性資料相符
- **WHEN** 實際 CSV 的 schema、row count、大小與 SHA-256 都符合 descriptor
- **THEN** Backend 可以將該 CSV 視為有效輸入

#### Scenario: CSV SHA-256 不符
- **WHEN** Backend 計算的 SHA-256 與 descriptor 不同
- **THEN** Backend 拒絕整個 Session package
- **AND** 不建立部分 Session 紀錄

#### Scenario: 上傳超過設定限制
- **WHEN** 單一 CSV 或整個 request 超過 Backend 設定的大小限制
- **THEN** Backend 拒絕上傳
- **AND** 回應能讓 Desktop App 顯示檔案過大的訊息

### Requirement: Session 與原始 CSV 必須以 Atomic save 保存
所有驗證成功後，Backend MUST 以單一 Atomic save 建立 Session、每份原始 CSV blob、CSV descriptor、Analysis Jobs 與 Input Bindings。任一步驟失敗時 MUST 回復整個保存操作，不得留下可被誤認為完整的 Session。

#### Scenario: 完整保存成功
- **WHEN** Session package 的所有驗證與 Database 寫入都成功
- **THEN** Backend 保存 Metadata 所宣告的每份原始 CSV bytes
- **AND** 回傳 Session ID、每個 Analysis ID 與初始狀態

#### Scenario: 保存其中一份 CSV 時失敗
- **WHEN** Database 在保存多份 CSV 的其中一步發生錯誤
- **THEN** Backend 回復本次 Session 的所有新增資料
- **AND** Client 可以安全重試相同 package

### Requirement: 相同 Session 上傳必須可以安全重試
Backend MUST 以 Session ID、Session owner 與 package 內容識別重試。相同 user 以相同 Session ID 上傳完全相同內容時 MUST 回傳既有 Session，不得重複保存；Session ID 相同但內容不同時 MUST 拒絕覆寫。

#### Scenario: 網路中斷後重送相同 Session
- **WHEN** Backend 已保存 Session，但 Desktop App 沒收到回應並重送相同 package
- **THEN** Backend 回傳既有 Session 與 Analysis 狀態
- **AND** Database 不新增重複 CSV 或 Analysis Job

#### Scenario: 相同 Session ID 的內容不同
- **WHEN** 同一個 user 使用既有 Session ID 上傳不同 Metadata 或 CSV checksum
- **THEN** Backend 拒絕該 request
- **AND** 不修改既有 Session

### Requirement: Analysis 必須以非同步狀態提供查詢
Backend MUST 在 Session 保存成功後讓 Analysis Job 依序呈現 `pending`、`processing`、`completed` 或 `failed`，並提供 Desktop App 查詢。`completed` MUST 包含符合契約的 Result；`failed` MUST 提供穩定 error code 與可顯示訊息，但不得洩漏 stack trace、Database 路徑或敏感設定。

#### Scenario: Session 已保存但尚未分析
- **WHEN** Desktop App 在 Analysis Executor 開始前查詢 Analysis Job
- **THEN** Backend 回傳 `pending`

#### Scenario: Analysis 正在執行
- **WHEN** Executor 已開始且尚未結束
- **THEN** Backend 回傳 `processing`

#### Scenario: Analysis 完成
- **WHEN** Executor 成功產生並通過 Result schema 驗證
- **THEN** Backend 回傳 `completed` 與 Result JSON

#### Scenario: Analysis 失敗
- **WHEN** Executor 發生錯誤或輸出未通過 Result schema 驗證
- **THEN** Backend 回傳 `failed`、穩定 error code 與安全訊息
- **AND** 原始 CSV 仍保存在 Database
