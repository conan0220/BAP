## 名詞定義

| 名詞 | 定義 |
|---|---|
| 出拳力量 | 由沙袋上、下方兩顆 IMU 的加速度與沙袋物理參數估算出的單次最大打擊力。 |
| 打擊位置 | 最大力量發生時，打擊點從沙袋底部往上量的估算高度。 |
| `bag_top` | 安裝在沙袋剛性核心上方的 IMU Input Role。 |
| `bag_bottom` | 安裝在沙袋剛性核心下方的 IMU Input Role。 |
| 校正階段 | 正式打擊前讓沙袋保持靜止兩秒，用來估算加速度基準的資料區段。 |
| Common IMU CSV | BAP 為每顆 IMU 各自保存的共同 CSV 格式。 |
| `packet_index` | 同一個無線接收器 Packet 的編號，用來對齊上、下方 IMU 資料。 |
| Result | Backend 完成分析後保存並回傳給 Desktop App 的 JSON 結果。 |

## Why

目前 BAP 的「出拳力量」只有待開發入口，user 不能選擇 IMU 或完成測量。Repository 已有以兩顆沙袋 IMU 估算最大打擊力與打擊位置的研究程式，因此本 Change 要將其數學模型改造成可由 BAP Session、Backend 與 Desktop App 安全執行的正式分析功能。

## What Changes

- 將出拳力量的 IMU 配置定為沙袋上方 `bag_top` 與沙袋下方 `bag_bottom` 各一顆 IMU。
- 第一版只接受同一個 Port、同一個無線接收器與同一個 Group ID 下的兩個不同 Nodes，使用共同 `packet_index` 對齊資料；不同 Port、不同 Group ID 或有線來源不得開始正式測量。
- Desktop App 讓 user 確認沙袋質量、長度、直徑與兩顆 IMU 的實際間距，並把本次採用的完整物理參數寫入 Analysis Parameters。
- Desktop App 先錄製兩秒沙袋靜止校正，校正完成後才讓 user 設定正式錄製時間並開始一次打擊的測量。
- 新增 `punch_force` version 1 Analysis Specification 與 Production Executor，將兩份 Common IMU CSV 對齊、驗證、濾波，再計算最大打擊力及打擊位置。
- Backend Result 同時提供 N 與 kgf、峰值時間、峰值質心加速度、打擊高度、實際取樣率、品質狀態、警告與有限點數的顯示曲線。
- Desktop App 以摘要卡、打擊位置、品質文字及內嵌 Matplotlib 曲線顯示結果，並保留重新測量操作。
- 加入沒有有效打擊、多次打擊、來源不一致、資料遺漏、取樣率不足、Quaternion 無效、感測器安裝異常與非有限運算等安全失敗或警告規則。
- 以合成資料、API Integration、Desktop Scenario、完整回歸與 Windows Artifact 測試驗證整條流程；實機測試只驗證流程與相對趨勢，不在沒有 Ground Truth 的情況下宣稱絕對力量準確度。
- 原始 `punch_force/` 只作為研究參考，不直接複製 CLI、副作用式檔案輸出、批次模式或研究資料到正式 Artifact。

## Capabilities

### New Capabilities

- `punch-force-analysis`：定義兩顆沙袋 IMU 的單次打擊錄製、物理參數、Backend 計算、資料品質、Result schema 與 Desktop Result view。

### Modified Capabilities

- `analysis-specification-contract`：加入 `punch_force` version 1 的 Input Roles、Parameters 與 Result schema，讓前後端使用同一份契約。
- `imu-source-discovery`：以已決定的沙袋上、下方 IMU 配置取代「配置待決定」，並限制兩個來源必須來自同一無線接收器與 Group ID。
- `desktop-app-shell`：Backend 提供相同版本 Executor 時，將「出拳力量」由待開發入口改為可使用的完整 Session flow。

## Impact

- `bap_common/analysis_contracts.py`：新增 `punch_force` version 1 契約與參數、Result 關聯驗證。
- `bap_backend/app/services/`：新增力量分析、兩份 CSV 對齊、濾波與品質檢查程式，並在 Backend 啟動時註冊 Executor。
- `bap_desktop/ui/punch_items/` 與 `bap_desktop/services/analysis_recording.py`：新增 IMU 配置限制、沙袋設定、校正、一次打擊提示與 Result view。
- Backend dependency 加入 SciPy；不需要 pandas，Desktop 沿用既有 Matplotlib。
- 沿用現有 Session API、Common IMU CSV、SQLite tables 與 CSV BLOB 保存方式，不需要 Database migration。
- 新增 Contract、Backend、API、Desktop、Packaging 與硬體人工測試；不把 `punch_force/` 研究資料夾加入正式 Backend 或 Desktop Artifact。

