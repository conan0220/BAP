## Purpose

定義透明且可重現的品質檢查，以顯示已記錄的拳力 trial 是否完整並適合後續 force-analysis 研究。

## ADDED Requirements

### Requirement: 必要來源完整性檢查
系統 SHALL 驗證 trial 包含 force plate stream 及全部四個已指定的 IMU streams，並 SHALL 回報遺漏、空白、過早終止或未指定的 sources。

#### Scenario: Trial 遺漏一個 IMU stream
- **WHEN** 已記錄的 trial 包含少於四個已指定的 IMU streams
- **THEN** quality report 會識別遺漏的 placement，並將 trial disposition 設為 `fail`

### Requirement: 各來源量測完整性檢查
系統 SHALL 評估每個 source 是否有 timestamp regression、duplicate timestamps、sampling gaps、observed sampling rate、遺漏或無效的 measurement fields，以及達到或超出設定 sensor range 的 values。

#### Scenario: IMU timestamps 重複
- **WHEN** IMU stream 包含重複的 source timestamps
- **THEN** quality report 會識別受影響的 source，並回報重複 timestamps 的數量或 intervals

#### Scenario: 感測器量測達到設定範圍
- **WHEN** IMU 或 force plate measurement 達到或超過其設定的有效範圍
- **THEN** quality report 會識別 source、channel、受影響 interval 與可能的 saturation

### Requirement: 可追溯的品質報告
系統 SHALL 產生 machine-readable quality report，其中包含 `pass`、`warning` 或 `fail` 的 trial disposition、附有 severity 與受影響 source 或 interval 的個別 findings、套用的 thresholds，以及 quality-check version。

#### Scenario: 審查 trial 品質
- **WHEN** trial 的 quality validation 完成
- **THEN** report 會透過個別 findings 說明 trial disposition，並記錄使用的 thresholds 與 checker version

### Requirement: 品質驗證不得掩蓋來源缺陷
系統 SHALL NOT 修改 raw source data 以移除或掩蓋 quality validation 期間發現的 defects。任何經清理或修正的 derivative SHALL 可與 raw data 區分，並 SHALL 記錄套用的 transformation。

#### Scenario: Derivative 移除重複 samples
- **WHEN** downstream processing step 建立已移除 duplicate samples 的 derivative
- **THEN** raw samples 維持不變，且 derivative 會識別 transformation 與受影響的 samples

### Requirement: 對齊品質納入 trial disposition
系統 SHALL 在判斷 trial 是否適合需要對齊的拳力研究時，納入 time-alignment success 與 diagnostics。

#### Scenario: 對齊未通過 acceptance criteria
- **WHEN** 任一必要 source 標示為 alignment-failed
- **THEN** quality report 會將 trial 對 alignment-dependent use 的 disposition 設為 `fail`，並引用 alignment diagnostics
