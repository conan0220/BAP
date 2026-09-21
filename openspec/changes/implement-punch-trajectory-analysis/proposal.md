## 名詞定義

| 名詞 | 定義 |
|---|---|
| 出拳軌跡 | 由手腕 IMU 資料估算出的拳頭相對移動路徑。 |
| 相對軌跡 | 以每一拳的起點作為原點得到的路徑；不是精密量測出的絕對空間位置。 |
| Session Local Coordinate System | Backend 以錄製開頭的有效 IMU 姿態建立的本次顯示座標系統。 |
| 互動式 3D 圖 | user 可以用滑鼠旋轉、縮放及平移的三維軌跡圖。 |
| 使用者視角 | Camera 位於 user 身後並朝出拳方向觀看的預設視角。 |
| Trajectory Executor | Backend 中負責把左右手腕 Common IMU CSV 轉成逐拳三維軌跡 Result 的元件。 |
| Drift correction | 降低加速度經過兩次積分後持續累積偏移的修正方法。 |

## Why

BAP 目前保留「出拳軌跡」入口，但 user 尚無法完成真實測量並看到結果。`kaipo_research` 已提供姿態轉換、移除重力與兩次積分重建軌跡的研究基礎，本 Change 要把這些概念整理成可測試、可部署且符合現有 Session flow 的正式功能。

## What Changes

- 新增 `punch_trajectory` version 3 Analysis Specification 與 Production Executor，以左右手腕 Common IMU CSV 產生逐拳相對三維軌跡。
- 沿用 BAP 既有的 IMU 探索、左右手腕分配、Session 上傳、Backend Job 與 Result 查詢流程。
- user 完成 IMU 分配後直接輸入錄製時間並開始測量，不再顯示或要求通過軌跡校正。
- 每一拳獨立執行世界座標轉換、重力與偏移移除、速度積分、Drift correction 及位置積分，避免整段 Session 的誤差持續累積。
- Backend 回傳版本化、可驗證且限制點數的 JSON Result；原始高頻資料繼續由 Session 的 CSV BLOB 保存。
- Desktop App 將「出拳軌跡」改為可使用，並用互動式 3D 圖顯示左手或右手的指定拳次。
- 3D 圖預設使用 user 從自身位置朝出拳方向看出去的視角，並提供使用者視角、側面、上方與重設縮放操作。
- 不直接部署研究資料中的 `imu.exe`、繪圖 EXE、固定路徑或整包資料集；必要的演算法概念會改寫成 BAP Backend 的 Python 元件。

## Capabilities

### New Capabilities

- `punch-trajectory-analysis`: 定義出拳軌跡的直接錄製、左右手腕輸入、Backend 軌跡重建、Result schema，以及 Desktop 互動式 3D 顯示行為。

### Modified Capabilities

- `desktop-app-shell`: 將具有 version 3 Production Executor 的出拳軌跡入口從待開發改成可完成端到端測量與查看 Result。
- `analysis-specification-contract`: 加入 `punch_trajectory` version 3 的 Input Roles、正式錄製開始參數與明確 Result schema。
- `desktop-ui-design`: Result view 增加可用鍵盤操作、可重設且能適應支援視窗大小的互動式 3D 軌跡圖。

## Impact

- Backend 將新增共用 IMU 運動運算元件、Trajectory Executor、Result 驗證與錯誤處理。
- Desktop App 將移除軌跡校正轉場，並保留正式錄製、軌跡 Result view 與互動式 3D Widget，並提升 Desktop version。
- 現有 Analysis Session API 與 Database tables 不需要改版；軌跡 Result 繼續存入 `analysis_results.result_json`。
- Desktop installer 可能需要加入 3D 顯示相依套件，CI 與 installer smoke test 必須涵蓋無實體 IMU 的 3D Widget 建立與基本操作。
- `kaipo_research` 只作為研究參考與驗證來源，不會把約 1.6 GB 的交接壓縮檔、重複資料集或來源不明的執行檔加入正式 Artifact。
