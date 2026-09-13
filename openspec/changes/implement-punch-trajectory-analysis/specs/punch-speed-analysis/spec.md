## 名詞定義

| 名詞 | 定義 |
|---|---|
| `calibration_end_elapsed_us` | 校正資料結束時的 Session 相對時間。 |
| `measurement_start_elapsed_us` | 正式錄製開始時的 Session 相對時間。 |

## MODIFIED Requirements

### Requirement: 正式測量前必須完成靜止校正
Desktop App MUST 在校正開始前，以文字清楚告訴 user 要先將雙手自然放下並保持不動。校正設定畫面與兩秒校正期間 MUST NOT 顯示正式錄製時間欄位。校正完成後，Desktop App MUST 才顯示錄製時間欄位，請 user 輸入正式 Session duration，並等待 user 按下「開始正式錄製」或意思相同的按鈕，不得自動開始正式錄製。校正期間的 IMU samples MUST 隨正式資料保存在同一份左右手 CSV。Analysis Parameters MUST 以 `calibration_end_elapsed_us` 標示兩秒校正資料結束的位置，並以 `measurement_start_elapsed_us` 標示正式測量開始位置，讓 Backend 不會把兩個時間點之間的等待或準備動作當成校正資料或出拳。

#### Scenario: user 完成靜止校正
- **WHEN** user 按下「開始校正」並在兩秒校正期間保持左右手 IMU 可用
- **THEN** 校正完成後才顯示正式錄製時間欄位與「開始正式錄製」按鈕
- **AND** user 按下該按鈕後才開始計算正式錄製時間
- **AND** Analysis Parameters 分別保存校正結束及正式錄製開始時間

#### Scenario: 校正完成後輸入無效的正式錄製時間
- **WHEN** user 輸入的時間不是 5～3600 秒內的整數
- **THEN** 系統保持在校正完成狀態並請 user 修正

#### Scenario: 校正期間必要 IMU 中斷
- **WHEN** 任一必要 IMU 在校正完成前中斷或沒有足夠有效資料
- **THEN** 系統不開始正式 Session，並讓 user 重新檢測 IMU

#### Scenario: user 在兩個階段之間移動
- **WHEN** 校正已完成，但 user 尚未開始正式錄製
- **THEN** Backend 只以 `calibration_end_elapsed_us` 以前的資料檢查校正
- **AND** 等待期間的動作不會造成校正失敗，也不會被當成正式出拳
