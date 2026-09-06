## 名詞定義

| 名詞 | 定義 |
|---|---|
| Contract test | 確認 Desktop 與 Backend 對相同 schema、欄位、版本及錯誤有一致理解的自動測試。 |
| Reference Executor | 只在測試環境執行、用來驗證 Session 到 Result 完整流程的替代分析元件。 |
| Fake IMU adapter | 在自動測試中提供可預測 Frames，不需要實體序列埠的測試元件。 |
| Integration test | 將 API、Service、Repository 與測試 Database 接在一起驗證的測試。 |
| E2E | 從 Desktop App 經真正 HTTP 到 Backend，再回到 Desktop Result view 的端到端測試。 |

## 1. 建立前後端共用契約

- [x] 1.1 在 `bap_common` 建立 Analysis Specification、Input Role、Input Binding、Parameters 與 Result 的版本化 models，並以 tests 驗證未知 Analysis Type、版本不符、缺少或重複 Role、跨 Session CSV 引用及禁止重複使用同一 CSV 等情境。
- [x] 1.2 建立 Session Metadata、CSV descriptor 與 Analysis Job request models，讓第一版 Desktop 只建立一個 Job，但 models 與 tests 能接受同一 Session 的多個 Jobs及多個 Jobs 共用 CSV。
- [x] 1.3 建立 Common IMU CSV version 1 的唯一 header、欄位單位、空值與逐列 validator，並測試 UTF-8、`.` 小數點、未知 schema version、錯誤欄位數、sample index 及 elapsed time 倒退。
- [x] 1.4 建立前後端共用的 contract serialization tests，確認 Metadata canonical JSON、enum、UUID、SHA-256 與 Result validation 在 Desktop 和 Backend 使用相同規則。

## 2. 實作 Desktop Common IMU 錄製

- [x] 2.1 建立 Session 本機暫存目錄與 lifecycle model，使用新的 Session／CSV／Analysis IDs，並測試前後 Session 不會混用 CSV、Bindings 或 Result。
- [x] 2.2 建立一顆 IMU 一份 CSV 的 recorder，以共同 monotonic Session clock 寫入 `.part` 後安全完成為 `.csv`，並測試一列只包含一顆 IMU 的一幀資料。
- [x] 2.3 支援有線多 Port 錄製，測試每個 Port 使用獨立 parser 與 CSV、共同 `elapsed_us` 起點，以及未提供的 device fields 保持空白。
- [x] 2.4 支援無線 Gateway packet 分流，測試每個選定 Node 寫入自己的 CSV，而且同 packet 的 Nodes 保留相同 `packet_index`、`device_time_ms` 與 `elapsed_us`。
- [x] 2.5 在錄製結束時產生 CSV descriptors 與 Metadata，從實際檔案計算 row count、size、SHA-256 及有線／無線 source identity，並測試檔名與 CSV IDs 唯一。
- [x] 2.6 實作 App 關閉與異常中斷後的本機 Session 清理／恢復規則，測試未完成 `.part` 不會被上傳、已完成但未確認的 package 可以重試。

## 3. 建立 Backend Database 模型

- [x] 3.1 新增 Alembic migration、SQLAlchemy models 與 relationships，建立 `measurement_sessions`、`imu_csv_files`、`analysis_jobs`、`analysis_input_bindings` 及 `analysis_results`，並保留既有帳號、Token 與 Release 資料。
- [x] 3.2 建立 Session repository，以一個 Database transaction 保存 Session、原始 CSV BLOB、Jobs 與 Bindings，並用 failure injection 測試任一 CSV 寫入失敗時不留下部分資料。
- [x] 3.3 實作 owner-scoped 查詢與 package fingerprint idempotency，測試相同內容重送回傳既有 Session、相同 ID 不同內容被拒絕，以及不同 user 無法讀取彼此資料。
- [x] 3.4 測試 migration upgrade／downgrade、Foreign Key、唯一性與 cascade 規則，並驗證 rollback 前的 Database 備份程序不會刪除既有 user Session 資料。

## 4. 實作 Session 上傳與查詢 API

- [x] 4.1 建立 `GET /api/v1/analysis-capabilities`，回傳 Analysis Type、Specification version、Input Roles、是否可執行及 upload limits，並測試沒有 Executor 的項目回報不可執行。
- [x] 4.2 建立受 Access Token 保護的 multipart Session upload endpoint，將 Metadata 與 files 串流到 staging，並驗證缺少檔案、多餘檔案、重複 ID／檔名、未知 CSV 引用及未登入要求。
- [x] 4.3 在上傳 Service 驗證 CSV schema、row count、size、SHA-256、Input Bindings 及可設定的單檔／Session 大小限制，並測試每種錯誤在正式 Database 寫入前被拒絕。
- [x] 4.4 上傳成功時回傳 Session ID、Analysis IDs 與初始狀態；測試 commit 後 response 中斷再重送不會建立重複資料。
- [x] 4.5 建立 owner-scoped Session 與 Analysis status endpoints，測試 `pending`、`processing`、`completed`、`failed`、有效 Result 及安全 error code／message，不回傳 stack trace 或 Server 路徑。
- [x] 4.6 建立已保存 Analysis Job 的 retry endpoint，測試重試不要求重新上傳或複製 CSV，且只有允許的失敗狀態可以重新排程。

## 5. 實作 Analysis Registry 與 Dispatcher

- [x] 5.1 定義 Executor protocol 與 `(analysis_type, spec_version)` Registry，確認 Production 只執行已註冊 Executor，未知或版本不符時不建立偽造 Result。
- [x] 5.2 建立僅由 tests 注入的 Reference Executor，並加入防護測試，確認 Production App factory 不會註冊或向 user 公開它。
- [x] 5.3 建立 Database-backed in-process Dispatcher，安全地將 Job 從 `pending` claim 為 `processing`，完成時驗證並保存 Result，失敗時保存穩定 error code 與安全訊息。
- [x] 5.4 實作 Backend 啟動時的未完成 Job recovery，測試 process 中斷留下的 `processing` Job 可以回到可重試狀態，而且原始 CSV 不被修改。
- [x] 5.5 測試 Executor 回傳有效 Result 時 Job 成為 `completed`，回傳錯誤 schema 或丟出例外時成為 `failed` 且不保存成功 Result。

## 6. 串接 Desktop Session UI

- [x] 6.1 建立 Analysis API client，沿用 Access Token refresh 行為，支援 capabilities、multipart upload、Session／Analysis status polling 與 retry，並為連線錯誤及安全錯誤訊息加入 tests。
- [x] 6.2 將拳擊項目定義連到 Analysis Type 與 Input Roles；已註冊且可執行時完成分配後進入 Session 準備，未提供 Executor 時維持待開發且不錄製正式資料。
- [x] 6.3 實作 Session page 狀態機與背景 workers，依序顯示準備、等待開始、測量中、上傳中、分析中、完成或失敗，並確保同一時間只有一個明確主要操作。
- [x] 6.4 實作「開始測量」與「結束測量」，測試只有 user 開始後才寫正式 CSV、結束後先停止 Frames 並完成 Metadata 才上傳，且目前 UI 一個 Session 只建立一個 Analysis Job。
- [x] 6.5 實作 upload retry 與本機資料保留，測試網路中斷時不要求重新錄製、Backend 完整接收後才清除暫存資料、本機 CSV 損壞時才要求重新測量。
- [x] 6.6 建立可插拔 Result presenter 容器，只有 `completed` 且通過 Result schema 驗證才顯示；測試有效 Result、未知欄位、缺少欄位、分析失敗及不偽造結果。
- [x] 6.7 實作離開頁面與 App shutdown cleanup，停止 serial readers 與 polling，同時保留尚未得到 Backend 接收確認的完整 Session package。

## 7. 完成自動化與端到端驗證

- [x] 7.1 以 Fake IMU adapter 驗證兩顆無線 Nodes、兩個有線 Ports，以及混合來源都能產生一顆 IMU 一份 CSV 並共用 Session 時間基準。
- [x] 7.2 建立 Backend integration tests，使用真正 multipart HTTP、臨時 SQLite 與 Reference Executor，涵蓋登入權限、atomic save、idempotent retry、多 Analysis Jobs 共用 CSV、狀態轉換與 Result schema。
- [x] 7.3 建立 Qt tests，從進入單一出拳項目、三秒探索、IMU 分配、開始／結束、上傳失敗重試、分析中到 Result view，驗證按鈕、文字狀態、鍵盤操作與視窗 resize。
- [x] 7.4 擴充 Windows PR CI E2E，從 Candidate 安裝 Backend 與 Desktop，透過真正 `127.0.0.1:12345`、測試帳號、Fake IMU input 與 Reference Executor 驗證 Session 到 Result 完整流程。
- [x] 7.5 執行完整 pytest、scenario coverage、OpenSpec strict validation、Backend migration tests 與 Windows packaging tests，修正所有 regression。
- [x] 7.6 使用實體有線 IMU 與同一 Gateway 下兩顆 Nodes 進行人工錄製 smoke test，確認每顆 IMU 各產生一份 CSV、rows 持續變化且同 packet 時間可以對齊；不驗證任何拳擊演算法結果。

## 8. 文件與交付

- [x] 8.1 在 `docs/knowledge/` 記錄已實作的 Common IMU CSV 與 Session／Analysis 名詞和版本規則，在 `docs/guides/` 記錄開發者如何執行本機 E2E、檢查暫存 Session 及處理上傳失敗。
- [x] 8.2 更新根目錄 README 的開發測試入口，但維持簡潔的 feature branch → PR CI → 人工 Merge 工作流程。
- [x] 8.3 建立包含 migration 的 Backend Candidate，於測試 Database 完成 upgrade、啟動、API smoke test 與 rollback rehearsal，確認既有帳號、登入及更新檢查仍正常。
- [x] 8.4 確認 Production 未註冊實際拳擊 Executor 時，所有分析項目仍清楚顯示待開發，Reference Executor 不存在於正式設定，且不會收集無法產生真實 Result 的正式資料。
