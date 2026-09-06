## 名詞定義

| 名詞 | 定義 |
|---|---|
| Session page | user 在單一拳擊分析項目中進行 IMU 準備、正式錄製、上傳、等待分析及查看 Result 的頁面。 |
| Measurement state | Session page 顯示的準備、等待開始、測量中、上傳中、分析中、完成或失敗狀態。 |
| Result view | 將 Backend Result JSON 依 Analysis Specification 呈現給 user 的畫面。 |
| Retry action | 上傳或狀態查詢失敗後，讓 user 在不重新錄製的情況下再次嘗試的操作。 |

## ADDED Requirements

### Requirement: 拳擊分析 UI 必須維持一次一個項目
Desktop App MUST 維持由主畫面一次進入一個拳擊分析項目的設計，不得在本 Change 增加讓 user 於同一個 Session 同時勾選多個分析項目的操作。

#### Scenario: user 進入出拳次數
- **WHEN** user 從主畫面選擇出拳次數
- **THEN** Session page 只顯示出拳次數需要的 IMU 分配、錄製狀態與 Result
- **AND** 不顯示同時加入其他分析項目的選項

### Requirement: Session page 必須依狀態提供單一明確主要操作
Session page MUST 依目前 Measurement state 顯示最重要的下一步；尚未符合條件的操作 MUST 停用，且同一時間不得同時把互相衝突的動作顯示為主要操作。

#### Scenario: IMU 分配完成且分析可執行
- **WHEN** 所有必要 Input Roles 已有效分配，而且 Backend Executor 可用
- **THEN** 畫面以「開始測量」作為主要操作

#### Scenario: 正在錄製
- **WHEN** Session 正在接受正式 IMU Frames
- **THEN** 畫面顯示測量中與經過時間
- **AND** 以「結束測量」作為主要操作

#### Scenario: 正在上傳或分析
- **WHEN** Desktop App 正在上傳 Session，或 Backend 正在分析
- **THEN** 畫面顯示相符的狀態文字
- **AND** 不允許 user 再次開始同一個 Session

### Requirement: Result view 必須依共同契約呈現
Desktop App MUST 只在 Backend 回傳 `completed` 且 Result 通過對應 Analysis Specification 驗證後顯示 Result view。Result view MUST 顯示分析項目及本次 Session，且不得將未知或不完整欄位猜成有效結果。

#### Scenario: 收到有效 Result
- **WHEN** Backend 回傳 `completed` 與符合 Result schema 的 JSON
- **THEN** Desktop App 以該分析項目的 Result view 呈現資料

#### Scenario: 收到不符合規格的 Result
- **WHEN** Backend 回傳的 Result 缺少必要欄位或型別錯誤
- **THEN** Desktop App 顯示結果格式錯誤
- **AND** 不把內容呈現為分析成功

### Requirement: 可重試錯誤不得要求不必要的重新測量
上傳或分析狀態查詢發生可重試錯誤時，Desktop App MUST 保留本機 Session 資料並顯示 Retry action。只有正式 CSV 無效、遺失或 IMU 錄製失敗時，才可要求 user 重新測量。

#### Scenario: 上傳時網路中斷
- **WHEN** Metadata 與 CSV 尚未得到 Backend 完整接收確認，且網路中斷
- **THEN** 畫面顯示上傳失敗與重試操作
- **AND** 不直接要求 user 重新錄製

#### Scenario: 本機 CSV 已損壞
- **WHEN** 上傳前驗證發現必要 CSV 無法讀取或 checksum 無法建立
- **THEN** 畫面說明本次測量資料無法使用
- **AND** user 可以返回重新測量
