## 名詞定義

| 名詞 | 定義 |
|---|---|
| Scenario test | 直接驗證 delta spec 某個 Scenario 的自動測試。 |
| Motion pipeline | 由拳頭速度與出拳軌跡共用的 CSV、姿態、校正、分拳與積分程式。 |
| Synthetic data | 測試程式產生、具有已知時間與運動特性的 IMU CSV。 |
| Hardware test | 使用實際左右手腕 IMU 完成校正、錄製、Backend 分析及 UI 檢查。 |
| Artifact E2E | 從正式 Windows 安裝 Artifact 執行的端到端測試。 |

## 1. 鎖定研究邊界與既有行為

- [x] 1.1 整理 `kaipo_research` 軌跡程式的輸入、輸出、400 Hz、姿態轉換、重力移除及兩次積分行為，並以測試或設計註解記錄哪些概念被採用；不要把整包交接檔、來源不明 EXE 或資料集加入 Git。
- [x] 1.2 為現有拳頭速度的 CSV 解析、Punch windows、世界座標加速度及速度結果補足回歸測試，確保抽共用程式前後輸出不變。
- [x] 1.3 確認新增的 Desktop 3D 相依套件能由目前 Python 與 PyInstaller 建置，鎖定相容版本並記錄授權資訊。

## 2. 建立 punch_trajectory version 2 契約

- [x] 2.1 在共用 Analysis Specifications 加入 `punch_trajectory` version 2、左右手腕 Input Roles、`measurement_start_elapsed_us` 與完整 Result fields，保留不可執行的 version 1 placeholder。
- [x] 2.2 實作軌跡 Result 關聯驗證，包含拳數、手別拳序、時間順序、有限座標、第一點原點、2 至 300 點及摘要非負條件。
- [x] 2.3 新增契約 Scenario tests，驗證前後端相同 version 2、舊 `summary` placeholder、缺少校正參數及拳數與 trajectories 不一致時的結果。

## 3. 抽出共用 Motion pipeline

- [x] 3.1 建立共用 IMU Motion 資料模型與 Common IMU CSV 解析，支援重複批次時間、實際取樣週期、Quaternion 正規化及所有必要 sensor 欄位驗證。
- [x] 3.2 抽出世界座標旋轉、靜止基準、Punch windows、加速度平滑與速度積分，讓拳頭速度改用共用介面。
- [x] 3.3 執行全部拳頭速度與出拳次數回歸測試，確認重構沒有改變既有 Analysis Result 或錯誤契約。
- [x] 3.4 實作 Session heading 建立與校正品質檢查，將結果統一為 X 向右、Y 向前、Z 向上的 Session Local Coordinate System。
- [x] 3.5 新增 Synthetic tests，涵蓋有效靜止校正、Quaternion 無效、校正資料不足、校正姿態變動過大及左右 heading 不一致。

## 4. 實作 Backend 逐拳軌跡

- [x] 4.1 實作單拳速度 Drift correction、位置梯形積分、起點歸零、路徑長度及最大位移計算。
- [x] 4.2 實作 deterministic display-point 選取，超過 300 點時保留首尾並縮減資料，且不修改原始 Common IMU CSV。
- [x] 4.3 實作左右手多拳 Trajectory Executor，產生版本、座標系統、單位、拳數與 trajectories Result；沒有偵測到拳時回傳有效空結果。
- [x] 4.4 將 `punch_trajectory` version 2 Production Executor 註冊到 Backend，並把資料問題轉成不含內部路徑或例外細節的安全錯誤。
- [x] 4.5 新增 Backend Scenario tests，涵蓋左右手多拳、每拳從原點開始、上一拳 Drift 不延續、沒有出拳、點數上限、缺少 Quaternion、非有限運算及 deterministic output。

## 5. 驗證 Session API 與資料保存

- [x] 5.1 新增 API Integration test，使用兩份 Fake Common IMU CSV 建立 version 2 Session，驗證 upload、Job processing、Result polling 與完整 Result schema。
- [x] 5.2 驗證 `analysis_results.result_json` 能保存並讀回最大允許點數的 Result，且 `imu_csv_files.csv_blob` 的內容與 checksum 沒有被降採樣流程改寫。
- [x] 5.3 驗證無效 CSV 或校正資料使 Job 失敗但保留原始 CSV，重新分析不要求 Desktop 再次上傳。

## 6. 實作 Desktop 校正與正式錄製流程

- [x] 6.1 將出拳軌跡定義更新為 `punch_trajectory` version 2，只有 Backend capability 回報 Executor 可執行時才顯示為可使用。
- [x] 6.2 將既有兩階段錄製元件擴充到出拳軌跡，先顯示面向出拳方向與靜止姿勢說明，再錄製兩秒校正；校正前不顯示正式錄製時間。
- [x] 6.3 校正完成後才開放 5 至 3600 秒時間輸入與「開始正式測量」，並將有效 `measurement_start_elapsed_us` 寫入 Analysis Parameters。
- [x] 6.4 實作校正期間來源中斷、校正失敗、正式錄製來源中斷及 Backend 安全錯誤的 UI 狀態與重新檢測／重新測量操作。
- [x] 6.5 新增 Desktop Scenario tests，驗證可用／待開發狀態、校正前後轉場、時間輸入、Session Parameters、中斷處理及無出拳 Result 說明。

## 7. 實作互動式 3D Result view

- [x] 7.1 加入並封裝 3D Widget，繪製軌跡線、起點、終點、X／Y／Z 方向及參考格線，不產生或依賴暫存 PNG。
- [x] 7.2 實作手別與拳次 selector，首次顯示時選取時間最早的一拳；切換時只更新本機 Result view，不重新呼叫 Backend。
- [x] 7.3 實作滑鼠旋轉、縮放、平移，以及可用鍵盤觸發的使用者、側面、上方與重設縮放 Camera presets。
- [x] 7.4 實作預設使用者視角：Camera 位於 user 身後朝 `+Y` 觀看，`+Z` 保持向上，並依所選軌跡自動計算可完整看見的距離。
- [x] 7.5 顯示所選軌跡的手別、拳次、持續時間、路徑長度與最大位移，並在 Result view 保留「重新測量」。
- [x] 7.6 實作 OpenGL／3D Widget 建立失敗的文字 Fallback，保留 Result 摘要與重新測量且不得讓 App 閃退。
- [x] 7.7 新增 UI Scenario tests，驗證 selector、Camera presets、Result 不被 Camera 操作修改、fallback、鍵盤焦點、`900 × 650` 視窗與高 DPI／捲動配置。

## 8. 完整驗證與發布準備

- [x] 8.1 建立 Scenario-to-test 對照，確認本 Change 每個 Scenario 至少由一個契約、Backend、API、Desktop 或 Artifact 測試覆蓋。
- [x] 8.2 執行完整 Source-level test suite，確認出拳次數、拳頭速度、拳種辨識、Session、登入、更新與部署相關測試沒有回歸。
- [x] 8.3 提升 Desktop version，執行 Windows build 與 Artifact E2E，驗證安裝後能建立 3D Widget；同時以強制失敗方式驗證 fallback。
- [x] 8.4 驗證正式 Desktop Artifact 與 Backend Artifact 都不包含 `kaipo_research`、巢狀壓縮檔、研究資料集或來源不明 EXE。
- [ ] 8.5 使用實際左右手腕 IMU 人工驗證 Jab、Hook、Uppercut 與靜止案例，確認預設 user 視角、方向、軌跡形狀、尺度及 Drift，並記錄 Prototype 限制。
- [ ] 8.6 由 user 在支援的最小視窗與一般螢幕上人工驗證旋轉、縮放、平移、Camera presets、切換手別／拳次與重新測量操作。

