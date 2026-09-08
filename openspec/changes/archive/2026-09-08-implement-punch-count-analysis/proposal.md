## 名詞定義

| 名詞 | 定義 |
|---|---|
| 出拳次數分析 | Backend 根據左右手腕 IMU 資料，計算左右手與總出拳次數的分析能力。 |
| Shadow boxing | 沒有擊中沙包、手靶或其他物體的空擊訓練。 |
| Ground Truth | 人工確認的正確左右手出拳次數，用來衡量演算法結果。 |
| Benchmark | 固定保存在 repository、每次修改演算法時都會重新執行的已標記測試資料。 |
| Session duration | user 在開始測量前指定的預定錄製時間。 |
| actual duration | Session 從正式開始到自動結束或 user 提前結束的實際錄製時間。 |
| elapsed_us | Desktop App 從 Session 開始後，以 monotonic clock 計算的相對微秒時間。 |
| Executor | Backend 實際讀取 Analysis Inputs 並產生出拳次數 Result 的元件。 |

## 原因

目前 BAP 已能錄製、上傳並保存左右手腕 Common IMU CSV，但 `punch_count` 尚未提供真正的 Production Executor，因此 user 仍無法完成一次 Shadow boxing 測量並取得出拳次數。這次變更也需要用固定的真實 Benchmark 防止演算法後續修改造成準確度退步。

## 變更內容

- 新增第一版以 Shadow boxing 為範圍的 `punch_count` Rule-based Executor，分別處理 `left_wrist` 與 `right_wrist` Common IMU CSV。
- 將同一次伸拳、減速及收拳視為一個完整動作區段，避免單純計算 acceleration peaks 而把同一拳重複計數。
- 產生左右手拳數與總拳數，並在輸入資料不足或時間資料不可用時回報可辨認的安全錯誤。Session 的實際錄製時間保存在 Session Metadata，不重複放進分析 Result。
- 讓 user 在出拳次數頁面輸入 Session duration；時間到時自動結束，並允許 user 在錄製期間提前結束。
- 錄製期間任一必要無線 Node 連續一秒沒有有效 Frame 時，自動停止整個 Session；若左右手都已有有效資料，保留並上傳中斷前資料繼續分析。
- 保存預定時間、實際時間與 `duration_reached`、`ended_by_user` 或 `source_interrupted` 結束原因；所有時間相關判斷使用實際錄製時間，不使用原本預定時間。
- 直接重用既有 `tests/fixtures/punch_count/` 內的五份 Benchmark ZIP、Metadata、Ground Truth 與 checksum，不另外建立第二套 manifest／資料夾格式。
- 以這五份資料校正第一版規則並執行 source-level CI regression；它們只能證明已知 cases 沒有回歸，不作為獨立或無偏差的準確率評估。
- 第一版不包含擊中沙包或手靶的動作、不辨識拳種，也不導入 Machine Learning。

## 能力

### 新增能力

- `punch-count-analysis`：定義 Shadow boxing 出拳事件、左右手輸入、Result、資料品質檢查，以及由真實 Benchmark 驗證演算法的行為。

### 修改能力

- `desktop-app-shell`：將「出拳次數」從待開發入口改為可完成錄製、上傳、分析並顯示 Result 的功能；其他拳擊項目仍維持待開發。
- `boxing-analysis-session`：在正式錄製前加入 user 指定的 Session duration，並支援時間到自動結束、按鈕提前結束及實際錄製時間紀錄。
- `analysis-session-ingestion`：接受包含預定時間、實際時間與結束原因的新版 Session Metadata，同時維持既有 Session 的相容性。
- `pull-request-ci`：source-level tests 必須執行 versioned punch-count Benchmark，並在準確度低於已定門檻時讓 CI 失敗。

## 影響

- Desktop App 的出拳次數頁面、錄製計時器、Session Metadata 與 Result view。
- Backend Session schema 與 Database 需要相容的 migration，以保存預定時間、實際時間與結束原因。
- Backend 的 Analysis Specification registry、Punch Count Executor、Result schema 與安全錯誤處理。
- Common IMU CSV 的讀取與時間軸正規化；不修改 Common IMU CSV version 1 的 23 欄 schema。
- `tests/fixtures/punch_count/` 的五份既有 Benchmark ZIP、共用唯讀 loader 與 pytest regression tests。
- 既有 Session upload、SQLite CSV BLOB 保存及 Analysis Job 查詢 API 可繼續使用，不新增另一套上傳流程。
