## 名詞定義

| 名詞 | 定義 |
|---|---|
| Session | user 從開始到結束的一次拳擊測量，包含一份以上的 IMU CSV 與一個以上的 Analysis Job。 |
| Analysis Job | Session 中要求 Backend 執行的一次分析工作。 |
| Registered Analysis | 已有有效 Analysis Specification，而且 Backend 已提供可執行 Executor 的分析類型。 |
| Session Status | Session 當下所處的狀態，例如錄製中、上傳中、分析中、完成或失敗。 |
| Result | Analysis Job 完成後由 Backend 保存並回傳的 JSON 結果。 |

## Purpose

建立所有拳擊分析項目共用的 Session 生命週期，讓 Desktop App 可以錄製 IMU、交給 Backend 保存與分析，並把可驗證的狀態或 Result 顯示給 user。

## ADDED Requirements

### Requirement: 第一版 UI 一次只能執行一個分析項目
Desktop App MUST 維持目前一次只進入一個拳擊分析項目的操作方式。每次從分析頁面建立的 Session MUST 只要求一個 Analysis Job，但 Session 與 Backend API 的資料格式 MUST 能表示一個以上的 Analysis Job。

#### Scenario: 從出拳次數頁面建立 Session
- **WHEN** user 在出拳次數頁面完成 IMU 分配並開始測量
- **THEN** Desktop App 建立一個新的 Session
- **AND** 該次 Desktop 操作只建立一個 `punch_count` Analysis Job

#### Scenario: Backend 接收包含多個 Analyses 的有效 Session
- **WHEN** 符合共用契約的 Client 提交一個包含多個 Analysis Jobs 的 Session
- **THEN** Backend 能以同一個 Session 保存並分別追蹤每個 Analysis Job

### Requirement: Session 必須有明確且不可混用的生命週期
系統 MUST 以唯一 Session ID 識別每次測量，並 MUST 區分準備、錄製、等待上傳、已接收、分析中、完成與失敗狀態。Desktop App MUST NOT 把前一次 Session 的 CSV、Input Bindings 或 Result 混入新的 Session。

#### Scenario: user 開始新的測量
- **WHEN** user 在有效 IMU 分配後按下「開始測量」
- **THEN** Desktop App 建立新的 Session ID 並開始本次錄製
- **AND** 畫面顯示測量中的狀態與結束操作

#### Scenario: user 結束測量
- **WHEN** user 在錄製中按下「結束測量」
- **THEN** Desktop App 停止接受本次 Session 的新 IMU Frames
- **AND** Desktop App 完成本次 CSV 與 Metadata 後才開始上傳

#### Scenario: user 再次開始相同項目
- **WHEN** 前一次 Session 已完成或失敗，而 user 再次開始測量
- **THEN** Desktop App 使用新的 Session ID、CSV IDs 與 Analysis ID
- **AND** 新 Session 不沿用前一次 Result

### Requirement: 只有可執行的分析項目才能開始正式錄製
Desktop App MUST 在開始正式錄製前確認 Analysis Type、Specification version 與 Backend Executor 目前可用。若分析尚未提供，Desktop App MUST 清楚顯示待開發或目前無法分析，且 MUST NOT 要求 user 完成一場無法得到 Result 的正式錄製。

#### Scenario: Analysis Executor 可用
- **WHEN** Desktop App 確認所選 Analysis Type 與版本可由 Backend 執行
- **THEN** 有效完成 IMU 分配的 user 可以開始正式錄製

#### Scenario: Analysis Executor 尚未提供
- **WHEN** Backend 回報所選 Analysis Type 沒有可執行的 Executor
- **THEN** Desktop App 顯示該項目尚未提供分析功能
- **AND** Desktop App 不開放「開始測量」操作

### Requirement: Desktop App 必須顯示端到端進度
Desktop App MUST 以文字顯示準備 IMU、等待開始、測量中、上傳中、Backend 分析中、分析完成或失敗等狀態，且 MUST NOT 只使用顏色表示狀態。

#### Scenario: Backend 尚未完成分析
- **WHEN** Session 已上傳且 Analysis Job 尚未完成
- **THEN** Desktop App 顯示「分析中」或意思相同的狀態
- **AND** Desktop App 不把尚未完成的資料顯示成 Result

#### Scenario: Backend 完成分析
- **WHEN** Backend 回報 Analysis Job 已完成並提供符合契約的 Result
- **THEN** Desktop App 顯示該 Result
- **AND** user 能辨認本次 Session 與分析項目

#### Scenario: Backend 回報分析失敗
- **WHEN** Backend 回報 Analysis Job 失敗
- **THEN** Desktop App 顯示不包含敏感內部資訊的失敗說明
- **AND** Desktop App 不偽造或猜測分析結果

### Requirement: 暫存資料必須保留到 Backend 確認接收
Desktop App MUST 在 Backend 明確確認 Session Metadata 與所有 CSV 已完整保存以前保留本機暫存資料。上傳失敗時 MUST 允許重試，不得要求 user 立刻重新錄製；Backend 已保存但分析失敗時 MUST 保留 Backend 原始 CSV 供重新分析。

#### Scenario: 上傳中斷
- **WHEN** Desktop App 上傳 Session 時發生網路或 Backend 錯誤
- **THEN** Desktop App 保留本次 Metadata 與 CSV
- **AND** user 可以重試上傳

#### Scenario: Backend 確認完整接收
- **WHEN** Backend 回覆 Session 與所有 CSV 已完整保存
- **THEN** Desktop App 可以清除本次本機暫存資料

#### Scenario: 分析失敗但資料已保存
- **WHEN** Backend 已保存 Session 與 CSV，但 Analysis Job 執行失敗
- **THEN** Backend 保留原始 CSV
- **AND** 重新分析不要求 user 再次上傳相同資料
