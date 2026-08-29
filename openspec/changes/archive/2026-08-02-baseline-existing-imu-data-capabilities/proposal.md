## 原因

BAP 已具備 IMU 序列通訊、協定解析與 CSV 記錄行為，但 `openspec/specs/` 尚未描述這些行為。現在建立經驗證的基準，可讓後續變更依據權威標準區分既有、已修改與新增的能力。

## 變更內容

- 記錄用於探索序列埠、讀取裝置輸出及傳送設定指令的可觀察命令列行為。
- 記錄支援的 ANROT 二進位與 NMEA 解析行為，包括增量輸入處理與 checksum 拒絕機制。
- 記錄既有的多連接埠、依 gateway 分組之 IMU CSV 記錄行為及目前的命令選項。
- 將 `pytest` 建立為特性描述測試的共用框架，在不刻意變更執行階段行為的情況下驗證記錄的基準。
- 建立全 repository 適用的 OpenSpec 政策，要求目前及未來的每個 spec Scenario 都必須可測試，且對應至少一個可識別的自動化、contract 或 hardware-in-the-loop 測試案例。
- 在封存前嚴格驗證 artifacts、執行測試套件，並進行完整性、正確性與一致性驗證。
- 本變更不包含出拳分析、force plate 整合、新記錄格式，以及既有 IMU 行為的修正或增強。

## 能力

### 新增能力

- `imu-device-communication`：列出序列埠、顯示解析後的裝置輸出，以及傳送已儲存之設定指令序列的既有命令列行為。
- `imu-data-parsing`：將支援的 ANROT 二進位 frame 與含 checksum 的 NMEA sentence 增量解碼為結構化量測資料的既有行為。
- `imu-data-recording`：將一個或多個序列埠所解析出的 IMU gateway packet，記錄至各 gateway 專屬 CSV 檔案的既有行為。

### 修改能力

無。

## 影響

- 在本變更下新增基準 delta specifications，以便在封存變更時成為權威 main specs。
- 在 `pyproject.toml` 加入 `pytest` 與 `pytest-cov` 開發設定，並在 `tests/` 中加入目前 command、parser 與 recorder 行為的特性描述測試涵蓋範圍。
- 在 `openspec/config.yaml` 加入適用於全 repository 的 Scenario-to-test 規則；本基準變更首次具體套用這些規則。
- 使用 `anrot_imu_driver/commands/record_data.py` 目前 working tree 的行為作為要保留的基準，包括使用者將預設記錄時間修改為 10 秒的變更。
- 本變更不修改 vendor material、公開命令行為、解析規則或記錄輸出。
