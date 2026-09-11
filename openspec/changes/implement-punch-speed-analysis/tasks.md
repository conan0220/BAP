## 名詞定義

| 名詞 | 定義 |
|---|---|
| Contract test | 驗證 Desktop App 與 Backend 對 Analysis Specification、Parameters 和 Result 有相同理解的測試。 |
| Source-level test | 直接從 repository source 執行，不需要先安裝正式 Artifact 的自動測試。 |
| API E2E | 透過真實 HTTP API 提交 Session、CSV 與 Analysis Job，再取得 Result 的端到端測試。 |
| Hardware test | 使用實際無線接收器與左右手 IMU 進行的人工驗證。 |
| Regression test | 確認本 Change 沒有讓原本已通過的功能退步。 |

## 1. Analysis Contract

- [x] 1.1 將 Desktop App 與 Backend 共用的 `punch_speed` 規格升級為 version 2、顯示名稱改為「拳頭速度」，並加入 `measurement_start_elapsed_us` Parameter 與完整 Result fields。
- [x] 1.2 加入每拳明細的結構與語意驗證，拒絕無效手別、拳序、時間順序、非有限或負數速度，以及拳數、平均值、最高值與明細不一致的 Result。
- [x] 1.3 加入 Contract tests，驗證有效 version 2、舊 `summary` placeholder、version 1 Client、缺少欄位與不一致摘要等情境。

## 2. 共用出拳事件與時間軸

- [x] 2.1 從既有出拳次數演算法抽出回傳 peak indexes 的共用事件偵測函式，保持現有 peak 規則與常數不變。
- [x] 2.2 由 peak 與動作 threshold 建立不重疊的 Punch windows，限制 windows 只能落在 `measurement_start_elapsed_us` 之後，並排除 Session 結尾未完成的動作。
- [x] 2.3 實作速度分析時間軸，保留 `sample_index` 順序，並使用有效 device time 或 median sample interval 處理重複 timestamps。
- [x] 2.4 加入時間軸、快速連續出拳、左右手同時出拳、同一拳伸收不重複及不完整 window 的 source-level tests。
- [x] 2.5 執行既有五份 punch-count regression data，確認抽取共用事件函式後左右手及總拳數完全不變。

## 3. 拳頭速度演算法

- [x] 3.1 建立 `rule_v1` 設定與拳頭速度資料模型，讀取並驗證時間、acceleration、gyroscope、Quaternion 與校正 samples。
- [x] 3.2 實作 Quaternion 正規化與 sensor frame 到 World frame 的向量旋轉，並從校正區段取得重力及 bias baseline。
- [x] 3.3 實作 `g` 到 `m/s²` 換算、Linear acceleration 平滑、每個 Punch window 的 trapezoidal integration 與 Zero-velocity correction。
- [x] 3.4 為每一拳產生手別、該手拳序、開始／最高／結束時間與 `peak_speed_mps`，再計算左右手拳數、平均速度及最高速度。
- [x] 3.5 加入答案已知的 Synthetic data tests，涵蓋 identity／已知旋轉 Quaternion、固定 acceleration pulse、單位換算、漂移修正、零拳及相同輸入的決定性結果。
- [x] 3.6 加入缺少或無效 Quaternion、校正不足、時間無法前進、取樣率過低、非有限 sensor value 與無效 measurement boundary 的安全錯誤測試。

## 4. Backend 與 Session Flow

- [x] 4.1 新增並註冊 `punch_speed` version 2 Executor，確認 version 1 不會被誤當成可執行版本。
- [x] 4.2 讓 Executor 分別處理 `left_wrist` 與 `right_wrist`，合併完整 Result，並將演算法資料錯誤轉成不包含內部路徑或 stack trace 的 Contract error。
- [x] 4.3 加入 Backend service 與 API E2E tests，以兩份 Synthetic Common IMU CSV 建立 Session、上傳、執行分析、保存 Result 並透過 HTTP 取回。
- [x] 4.4 加入 API E2E 錯誤測試，驗證缺少／重複 Input Role、無效資料與 version mismatch 不會保存成功 Result，而 Backend 仍保留已接收的原始 CSV。

## 5. Desktop 校正與正式錄製

- [x] 5.1 在拳頭速度頁先說明校正姿勢與下一步；校正前與兩秒校正期間隱藏錄製時間，校正完成後才顯示錄製時間欄位與「開始正式錄製」按鈕，只有時間有效且 user 按下按鈕才啟動正式 Session timer。
- [x] 5.2 讓左右手 CSV 從校正開始持續記錄到正式測量結束，使用同一條 Capture timeline，並把實際 `measurement_start_elapsed_us` 寫入 Analysis Parameters。
- [x] 5.3 確認 `requested_duration_seconds` 與 `actual_duration_seconds` 不包含校正時間，且時間到、提前結束與來源中斷都只執行一次 CSV finalization 與上傳。
- [x] 5.4 加入 Desktop tests，驗證校正提示、錄製時間欄位只在校正後顯示、無效時間不開始錄製、兩秒邊界、正式 timer、校正期間 IMU 中斷與資料不足時不開始 Session 並允許重新檢測。

## 6. Desktop 拳頭速度結果

- [x] 6.1 將側邊導覽、主畫面、頁面標題、狀態與 Result 中的 user-facing「出拳速度」統一改成「拳頭速度」，但保持 Analysis Type `punch_speed` 不變。
- [x] 6.2 開放 Backend 已提供 version 2 Executor 時的拳頭速度錄製流程；Executor 不可用或只支援 version 1 時，維持不可開始並顯示白話原因。
- [x] 6.3 建立自適應 Result view，顯示左右手拳數、平均／最高拳頭速度、`m/s` 單位及可捲動的每拳明細，且零拳手別顯示 `0.0 m/s`。
- [x] 6.4 沿用「重新測量」操作，清除前一個 Session 的速度與時間資訊，重新掃描 Port 並回到 IMU 分配階段。
- [x] 6.5 加入 Qt tests，驗證有效 Result、無效 Result、Backend 錯誤、最小視窗、鍵盤操作、每拳明細與重新測量流程。
- [x] 6.6 依專案發版規則提升 Desktop `VERSION`，確保 installer、App runtime 與更新檢查共用相同版本來源。

## 7. 完整自動驗證

- [x] 7.1 執行格式、型別與完整 pytest suite，修正本 Change 造成的所有 regression，但不修改兩份 user PowerPoint 或 vendor material。
- [x] 7.2 執行 OpenSpec strict validation，確認所有 Scenario 都有對應的 automated、contract、API E2E 或 Hardware test。
- [ ] 7.3 以 CI 的同一台 Windows Runner 從 source 啟動真實 Backend，讓 Desktop API E2E 完成拳頭速度 Session flow，並確認失敗時會保存測試 logs。

## 8. 實際 IMU 人工驗證

- [x] 8.1 使用一個無線接收器與左右手兩顆 IMU，確認校正期間保持靜止時不會產生出拳明細，轉動手腕後回到靜止也不會出現持續增加的速度。
- [x] 8.2 由 user 依序完成慢速、一般速度與快速 Shadow boxing，確認左右手歸屬正確，且 UI 顯示的拳頭速度相對順序合理。
- [x] 8.3 由 user 驗證 Session 正常結束、提前結束、重新測量與必要 Node 中斷行為，並註記本次人工驗證沒有外部 Ground Truth，未宣稱絕對速度誤差範圍。
