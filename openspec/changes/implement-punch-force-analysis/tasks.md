## 名詞定義

| 名詞 | 定義 |
|---|---|
| Scenario test | 直接驗證 delta spec 某個 Scenario 的自動測試。 |
| Synthetic data | 測試程式產生、具有已知取樣率、方向、力量峰值與缺口的 IMU 資料。 |
| Packet alignment | 透過共同 `packet_index` 配對 `bag_top` 與 `bag_bottom` 資料的處理。 |
| Production Executor | Backend 實際處理 `punch_force` version 1 Analysis Job 的元件。 |
| Hardware test | 使用固定在實體沙包上、下方的兩顆無線 IMU 完成的人工測試。 |
| Artifact E2E | 從正式 Windows candidate Artifact 執行的端到端測試。 |

## 1. 鎖定研究演算法與既有行為

- [x] 1.1 整理 `punch_force/README.md` 與研究程式的輸入、輸出、座標、單位、濾波、力量及擊中位置公式，並以程式註解或測試 fixture 說明 BAP 採用與不採用的部分。
- [x] 1.2 建立不依賴 `punch_force/` 研究資料夾的 synthetic 上、下方 IMU fixtures，包含靜止、單拳、無拳、多拳、不同質量與已知旋轉案例。
- [x] 1.3 為既有出拳次數、速度、軌跡與拳種辨識的 Executor 建立或補足基準回歸測試，供 input descriptor 重構前後比較。

## 2. 建立 punch_force version 1 契約

- [x] 2.1 在共用 Analysis Specifications 加入 `punch_force` version 1、`bag_top`／`bag_bottom` Input Roles、兩個時間邊界及四個沙包物理參數。
- [x] 2.2 實作 Parameters 驗證，涵蓋預設值、空白、非數值、非有限值、零、負數，以及 `sensor_distance_m` 大於 `bag_length_m`。
- [x] 2.3 實作完整 Result schema 與關聯驗證，涵蓋 N／kgf 固定換算、有限且合理的數值、品質狀態、warnings、曲線欄位、時間排序、300 點上限及峰值保留。
- [x] 2.4 新增契約 Scenario tests，驗證前後端使用相同 version 1、完整與缺漏 Parameters，以及單位、品質或曲線關聯不一致時拒絕 Result。

## 3. 一般化 Analysis input descriptor

- [x] 3.1 將分類專用的 input descriptor 一般化，保留 CSV ID、Input Role、Port、connection type、Group ID 與 Node ID，且不修改公開 API payload。
- [x] 3.2 將既有需要來源資訊的 Executor 切換到共用 descriptor，並執行出拳次數、速度、軌跡與拳種辨識回歸測試。
- [x] 3.3 新增來源驗證測試，確認出拳力量只接受同一 Port、同一 Group ID 的兩個不同無線 Nodes，並拒絕有線、不同 Port、不同 Group、相同 Node、缺漏或重複 Input Roles。

## 4. 實作 Packet 對齊與訊號處理

- [x] 4.1 建立 Common IMU CSV 解析與 typed models，驗證必要的 `packet_index`、`elapsed_us`、加速度、Gyroscope、Quaternion、數值有限性及時間順序。
- [x] 4.2 以共同 `packet_index` 對齊 `bag_top` 與 `bag_bottom`，不得直接使用兩份 CSV 的 row number 當作共同時間。
- [x] 4.3 實作 deterministic 內部線性插值；允許資料中間最多連續 5 個封包且總缺口不超過 5%，不改寫保存的原始 CSV。
- [x] 4.4 新增 Packet Scenario tests，涵蓋完全配對、CSV row 數或順序不同、少量中間缺口、開頭／結尾缺口、連續缺口過多、總缺口過多及原始 bytes／checksum 不變。
- [x] 4.5 實作實際取樣率估算、Quaternion 正規化、兩秒靜止基準、body-frame 低通濾波、world-frame 旋轉與重力／基線移除。
- [x] 4.6 將 SciPy 加入 Backend dependency 與 lockfile，確認 cutoff 會依實際取樣率安全限制，且 Backend 不新增 pandas 或 Matplotlib runtime dependency。
- [x] 4.7 新增訊號 Scenario tests，涵蓋有效校正、校正資料不足、校正期間動作過大、無效 Quaternion、非有限 sensor 值、低於最低取樣率及低於建議取樣率。

## 5. 實作 Backend 力量演算法與 Executor

- [x] 5.1 實作沙包橫向轉動慣量、質心加速度、N／kgf 力量、角加速度、從底部量起的擊中高度與中心偏移計算，並清楚固定所有 SI units。
- [x] 5.2 依 README 實作版本化力量選點：只在正式測量區間找力量曲線的 global maximum，並使用同一點計算最大力量與擊中位置。
- [x] 5.3 實作資料品質評估，至少涵蓋少量 Packet 插值、低於建議取樣率、上下 IMU Gyroscope 不一致及擊中位置超出沙包長度。
- [x] 5.4 實作不超過 300 筆的 deterministic `curve_points`，保留第一點、最後一點與力量峰值點。
- [x] 5.5 實作 `PunchForceExecutor`，將解析、對齊、校正、濾波、global maximum 選點、物理計算、品質檢查及 Result 組裝接到 Analysis Dispatcher。
- [x] 5.6 將 `punch_force` version 1 Production Executor 註冊到 Backend capability registry，並將內部例外轉成不含路徑、stack trace 或敏感資訊的安全錯誤。
- [x] 5.7 新增演算法 Scenario tests，驗證 deterministic Result、相同資料搭配不同質量、N／kgf 換算、無可用正力量、多個局部峰值選 global maximum、非有限運算、Gyroscope 不一致、位置超界與警告狀態。
- [x] 5.8 新增曲線 Scenario tests，驗證 300 點上限、時間排序、必要欄位有限、首尾與峰值保留，以及降採樣不修改完整計算資料。

## 6. 驗證 Session API 與資料保存

- [x] 6.1 新增 API integration test，以兩份 Fake Common IMU CSV、完整 metadata、兩個 Input Bindings 與沙包 Parameters 建立 `punch_force` version 1 Session 並取得成功 Result。
- [x] 6.2 驗證 `analysis_jobs.parameters_json`、兩份 `imu_csv_files.csv_blob`、bindings 與 `analysis_results.result_json` 都能保存及讀回，而且不需要 database migration 或力量專用 table。
- [x] 6.3 驗證相同 Inputs、Parameters 與 `algorithm_version` 重跑會得到相同 Result，改變有效 `bag_mass_kg` 則依新 Parameters 重新計算。
- [x] 6.4 新增 API failure tests，涵蓋缺少必要參數、來源不符、CSV 無資料／損壞、Packet 缺口過多、無可用正力量、取樣率不足與非有限結果，並確認 Job 失敗但原始 CSV 仍保留；多個局部峰值則驗證選擇 global maximum 並成功完成。

## 7. 實作 Desktop IMU 分配與沙包設定

- [x] 7.1 將出拳力量定義更新為 `punch_force` version 1，只有 Backend 回報相同版本 Production Executor 可執行時才顯示為可使用。
- [x] 7.2 在三秒探索後顯示「沙包上方」與「沙包下方」兩個位置，允許 user 從同一 Port／Group 的不同無線 Nodes 完成分配。
- [x] 7.3 實作分配驗證與白話錯誤，涵蓋不同 Port、不同 Group、相同 Node、只有一顆無線 IMU、只有有線 IMU及沒有有效來源，並在無效時停用「繼續」。
- [x] 7.4 實作沙包質量、長度、直徑與 IMU 間距設定畫面，預填 36 kg、1.24 m、0.335 m、1.24 m，顯示單位及欄位層級錯誤。
- [x] 7.5 新增 Desktop discovery／configuration Scenario tests，驗證五個獨立拳擊入口、力量可用／待開發狀態、單一項目 flow、合法分配、所有非法分配及沙包參數規則。

## 8. 實作 Desktop 校正與正式錄製

- [x] 8.1 在校正前顯示沙包必須靜止、不可碰撞且兩顆 IMU 必須固定的說明，將「開始校正」設為主要操作，且不顯示正式錄製時間。
- [x] 8.2 實作兩秒雙 IMU 校正；任一來源中斷、資料不足或穩定性不合格時停止流程、顯示白話原因且不上傳不完整 Session。
- [x] 8.3 校正成功後才顯示 5 至 3600 秒的正式錄製時間與「開始正式測量」，並提示第一版只能擊打沙包一次。
- [x] 8.4 將 `calibration_end_elapsed_us` 與 user 按下正式開始時產生的 `measurement_start_elapsed_us` 分別寫入 Parameters，不把兩者之間的等待資料算入校正或正式打擊。
- [x] 8.5 沿用提前結束與必要來源中斷處理；正式錄製完成後上傳兩份 CSV、metadata、Input Bindings 及實際沙包 Parameters。
- [x] 8.6 新增 Desktop recording Scenario tests，驗證校正前後畫面、兩秒校正、來源中斷、時間範圍、兩個獨立時間邊界、提前結束及上傳 payload。

## 9. 實作 Desktop Result 與錯誤呈現

- [x] 9.1 實作出拳力量 Result view，顯示最大力量 kgf／N、擊中高度、中心偏移、峰值時間、質心加速度、實際取樣率與品質狀態。
- [x] 9.2 以內嵌 Matplotlib 顯示上／下方水平加速度、X／Y 角加速度、力量曲線及峰值，圖表內可見文字使用英文，且不開外部視窗。
- [x] 9.3 逐項以文字顯示 warnings，不只用顏色表達；頁面明確說明結果是 IMU 與沙包模型的估算值，不是 Force Plate 直接量測。
- [x] 9.4 實作「重新測量」回到 IMU 掃描階段，並為無可用正力量、取樣率不足、Packet 無法對齊、Backend 不支援及網路失敗顯示對應白話訊息。
- [x] 9.5 新增 Result Scenario tests，驗證正常 Result、warning Result、單位與曲線、英文圖表文字、估算說明、安全錯誤、重新測量及 Matplotlib 建立失敗時仍保留文字摘要與操作。

## 10. 完整驗證與發布準備

- [x] 10.1 建立 Scenario-to-test 對照，逐一列出本 Change 四份 delta specs 的每個 Scenario，並確認每項至少有一個契約、Backend、API、Desktop、Artifact 或 Hardware test。
- [x] 10.2 執行完整 Source-level test suite，確認帳號、更新、Session、IMU 掃描、出拳次數、速度、軌跡、拳種辨識及部署測試沒有回歸。
- [ ] 10.3 提升 Desktop version，建立 Backend 與 Windows Desktop candidate Artifacts，驗證正式 Artifact 不包含 `punch_force/` 研究資料、批次輸出、pandas 或 Backend Matplotlib。
- [ ] 10.4 執行 Artifact E2E：從安裝後 Desktop 透過實際 HTTP 呼叫 candidate Backend，完成能力查詢、兩份 Fake CSV Session、Job polling、Result schema、曲線與重新測量。
- [ ] 10.5 以 Artifact E2E 驗證無可用正力量、多個局部峰值選 global maximum、非法來源、缺口過多及 warning Result，確認 UI 不顯示假力量且 logs 可供診斷。
- [ ] 10.6 使用固定在實體沙包上、下方的兩顆無線 IMU 人工完成一次單拳測量，檢查取樣率、曲線、力量、擊中位置、品質訊息與重新測量 flow。
- [ ] 10.7 使用實體 IMU 人工驗證靜止無拳、一次錄製多拳、鬆動或位置選反等案例；確認多拳錄製回傳 global maximum，其餘不可靠資料被拒絕或顯示正確警告。
- [x] 10.8 記錄 Prototype 尚未用 Force Plate Ground Truth 驗證絕對精度的限制；不得把人工合理性檢查寫成準確度已證明。

