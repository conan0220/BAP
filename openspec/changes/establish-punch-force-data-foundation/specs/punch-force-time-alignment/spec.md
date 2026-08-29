## Purpose

定義具有獨立 timestamp 的 IMU 與 force plate streams 如何取得可追溯的共同 trial timeline，以供離線比較，且不遺失原始 timing evidence。

## ADDED Requirements

### Requirement: 共用 trial timeline
系統 SHALL 為每個已記錄的 IMU 與 force plate source clock 提供至共同 trial timeline 的 time mapping，同時保留各自原始的 source timestamp。

#### Scenario: 對齊完整 trial
- **WHEN** 系統成功對齊包含所有預期 sources 的 trial
- **THEN** 每筆儲存的 measurement 均可定位於共同 trial timeline，且其原始 source timestamp 仍可取得

### Requirement: 對齊 provenance
系統 SHALL 為每個 source 記錄 alignment method、method version、input anchors 或 timing evidence、estimated clock mapping 或 offset、configuration parameters，以及使用的 alignment quality measurements。

#### Scenario: 檢查 source 的對齊方式
- **WHEN** 研究人員審查已對齊的 source stream
- **THEN** 研究人員可識別對齊的產生方式，以及支援該方式的 evidence 與 parameters

### Requirement: 具確定性的離線對齊
當相同 raw trial、alignment method version 與 configuration 再次進行處理時，系統 SHALL 產生相同的 aligned timeline。

#### Scenario: 重複執行對齊
- **WHEN** 使用相同的 method version 與 configuration 對同一 raw trial 執行兩次對齊
- **THEN** 產生的 time mappings 與回報的 alignment measurements 完全相同

### Requirement: 明確的對齊失敗
當可用的 timing evidence 無法滿足設定的 alignment acceptance criteria 時，系統 SHALL 將 source 或 trial 標示為 alignment-failed，且 SHALL NOT 在未告知的情況下將 estimated mapping 呈現為已接受。

#### Scenario: Timing evidence 不足
- **WHEN** source 缺乏足夠的 timing evidence，無法符合設定的 acceptance criteria
- **THEN** 系統會保存 source data、回報 alignment failure 與 supporting diagnostics，並依預設將 trial 排除於 alignment-dependent use
