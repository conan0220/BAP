## 名詞定義

| 名詞 | 定義 |
|---|---|
| 自動測試 | 可由 pytest 或 CI 重複執行、不需要實體 IMU 的驗證。 |
| 人工硬體測試 | 需要 user、實體 IMU 與 Shadow boxing 動作才能完成的驗證。 |
| Benchmark fixture | 經人工確認並固定在 repository 的左右手 CSV 與 Ground Truth。 |

## 1. Session Metadata version 2

- [ ] 1.1 先新增 Metadata version 2 的 validation tests，涵蓋有效 duration、缺少欄位、範圍錯誤、未知 stop reason 與 version 1 相容讀取。
- [ ] 1.2 擴充共用 Session Metadata model，加入 `requested_duration_seconds`、`actual_duration_seconds` 與 `stop_reason`，並維持 version 1 payload 的解析能力。
- [ ] 1.3 新增 Alembic migration 與 ORM columns，以 nullable 欄位保存新版錄製資訊且不改寫既有 Session、CSV BLOB、Analysis Job 或 Result。
- [ ] 1.4 更新 repository 與 Session ingestion，驗證並 atomic save version 2，同時以 integration tests 證明無效 package 不留下部分資料且相同 package 仍可 idempotent retry。

## 2. Desktop 限時錄製

- [ ] 2.1 新增 5～3600 秒、預設 60 秒的輸入 validation 與 UI tests，涵蓋空白、非整數及範圍外資料。
- [ ] 2.2 讓錄製 coordinator 使用 monotonic clock 計算 actual duration，並以 single-finalization guard 統一處理自動到時與 user 提前結束。
- [ ] 2.3 在出拳次數頁面加入 Session duration、已錄製時間、剩餘時間與「提前結束測量」，並建立 timer drift、時間到自動停止及提前停止的 Qt tests。
- [ ] 2.4 產生 Metadata version 2，分別驗證 `duration_reached` 與 `ended_by_user`，並確認兩種結束競爭時 CSV finalization 與 upload 都只執行一次。

## 3. Shadow boxing 演算法核心

- [ ] 3.1 新增嚴格的單手 Common IMU CSV reader 與測試，涵蓋必要 sensor 欄位、sample 順序、空 CSV、無效數值及時間完全沒有前進。
- [ ] 3.2 實作有效時間軸選擇與重複 `elapsed_us` 處理，並以測試確認同批 Frames 保持順序、不被刪除且不會額外計數。
- [ ] 3.3 實作加速度與角速度合成強度、smoothing、baseline 與 versioned `rule_v1` configuration。
- [ ] 3.4 實作單手 Motion Episode 狀態機與 synthetic tests，涵蓋單拳只計一次、一般晃動零拳、同手快速兩拳及伸拳／收拳不重複計數。
- [ ] 3.5 實作左右手獨立分析與合併，並驗證左右手同時出拳時各自計數且總拳數為兩者相加。

## 4. Production Executor 與結果

- [ ] 4.1 實作 `punch_count` version 1 Production Executor，驗證兩個不同 Input Roles 並呼叫同一個純演算法核心。
- [ ] 4.2 在 Backend application startup 註冊 Production Executor，移除 Production 對 CI Reference Executor 的依賴，並測試 capability 回報 `executable=true`。
- [ ] 4.3 將資料品質問題轉成穩定安全錯誤，測試失敗 Job 不保存成功 Result、不洩漏路徑或 stack trace，且原始 CSV 仍保留。
- [ ] 4.4 新增 Result contract tests，確認三欄皆為非負整數、總數等於左右手相加，且相同輸入重跑得到相同結果。

## 5. 真實 Benchmark

- [ ] 5.1 建立 versioned Benchmark manifest model 與唯讀 loader，驗證 case ID、schema version、左右手檔案、Ground Truth、size 與 SHA-256。
- [ ] 5.2 接收並人工核對 user 提供的 Shadow boxing Sessions，移除個人資訊後分成校正資料與固定 Benchmark fixtures。
- [ ] 5.3 使用校正資料調整 `rule_v1`，記錄適用資料範圍且不得修改 Ground Truth 迎合預測。
- [ ] 5.4 新增 parametrized pytest，讓每個已核准 case 的左手、右手與總拳數必須完全符合 Ground Truth，失敗時顯示 case ID、expected 與 actual。
- [ ] 5.5 新增 fixture corruption tests，確認缺檔、checksum 錯誤、Ground Truth 缺少或 schema 不支援時測試明確失敗而不是略過。

## 6. Desktop 完整 user flow

- [ ] 6.1 更新主畫面與側邊導覽，只有出拳次數顯示為可使用，其餘四個拳擊項目仍顯示待開發。
- [ ] 6.2 更新出拳次數 Result view，顯示總拳數、左手拳數與右手拳數，並測試只接受 Backend completed 且符合契約的 Result。
- [ ] 6.3 以臨時 SQLite 與真實 HTTP 執行 Session duration、左右手 CSV upload、Production Executor、Job polling 與 Result 的 API integration test。
- [ ] 6.4 更新 packaged Desktop API E2E，使安裝後 App 對解壓後 Backend 完成真正的 `punch_count` Session flow，不再依賴固定假拳數。

## 7. 驗證與交付

- [ ] 7.1 執行完整 pytest，確認既有帳號、IMU、Session、部署、更新與 CI/CD contract tests 沒有回歸。
- [ ] 7.2 執行 Windows Candidate Build 與 Artifact E2E，驗證 Backend ZIP、Desktop Installer、Migration、真實 HTTP 與 cleanup。
- [ ] 7.3 使用兩顆實體 IMU 完成人工 Shadow boxing 測試，確認自動到時、提前結束、上傳、分析與 Result 顯示。
- [ ] 7.4 在提交 Desktop 程式修改前提升 `bap_desktop/VERSION`，並由 Pull Request CI 驗證版本與 Candidate。