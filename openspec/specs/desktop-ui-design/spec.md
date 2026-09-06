## 名詞定義

| 名詞 | 定義 |
|---|---|
| App shell | 包住各功能頁面的共用介面，包含側邊導覽、上方頁面標題與帳號操作。 |
| 主要操作 | user 在目前頁面最需要執行的動作，例如「重新測試」或「繼續」。 |
| 目前頁面 | user 當下正在查看的功能頁面。 |
| 支援的最小視窗 | 內容區至少為 `900 × 650` logical pixels 的 Desktop App 視窗。 |
| 自適應 Layout | 依目前可用寬度重新排列元件，讓內容利用視窗空間，而不是維持固定欄數或固定欄位寬度。 |
| 狀態文字 | 直接以文字說明結果，例如「已連線」、「未辨識」或「待開發」。 |
| Session page | user 在單一拳擊分析項目中進行 IMU 準備、正式錄製、上傳、等待分析及查看 Result 的頁面。 |
| Measurement state | Session page 顯示的準備、等待開始、測量中、上傳中、分析中、完成或失敗狀態。 |
| Result view | 將 Backend Result JSON 依 Analysis Specification 呈現給 user 的畫面。 |
| Retry action | 上傳或狀態查詢失敗後，讓 user 在不重新錄製的情況下再次嘗試的操作。 |

## Purpose

提供一致、清楚且能以滑鼠或鍵盤操作的 BAP Desktop App 介面，讓 user 容易辨認目前所在頁面、下一個操作，以及各功能目前是否可用。

## Requirements

### Requirement: Desktop App 必須使用一致的 App shell
Desktop App MUST 在登入後以共用 App shell 呈現功能頁面；App shell MUST 包含工作區與拳擊分析導覽、目前頁面名稱、登入帳號及登出操作。

#### Scenario: user 登入後查看主畫面
- **WHEN** user 成功登入並進入主畫面
- **THEN** 畫面顯示工作區與拳擊分析導覽
- **AND** 畫面顯示目前登入帳號及登出操作

#### Scenario: user 切換功能頁面
- **WHEN** user 從導覽選擇另一個功能頁面
- **THEN** 內容區顯示所選頁面
- **AND** App shell 顯示該頁面名稱
- **AND** 導覽以不只依賴顏色的方式標示目前頁面

### Requirement: 頁面必須清楚區分主要操作與次要操作
每個頁面 MUST 只將目前最重要的動作顯示為主要操作；重新掃描、匯出、返回等輔助動作 MUST 使用較低的視覺層級，且停用的操作 MUST 清楚呈現不可使用狀態。

#### Scenario: IMU Report 已完成
- **WHEN** user 查看已完成的 IMU 連線狀態 Report
- **THEN** 「重新測試」顯示為主要操作
- **AND** 「匯出 CSV」顯示為次要操作

#### Scenario: IMU 尚未完成分配
- **WHEN** 拳擊項目要求的 IMU 位置尚未全部完成有效分配
- **THEN** 「繼續」操作顯示為不可使用
- **AND** user 無法透過滑鼠或鍵盤觸發該操作

### Requirement: 主要狀態不得只使用顏色表達
Desktop App MUST 以文字搭配顏色或圖示呈現連線、錯誤、目前頁面及待開發狀態，不得要求 user 只靠顏色理解結果。

#### Scenario: 顯示 IMU 連線結果
- **WHEN** 系統顯示某個 Port 的測試結果
- **THEN** 畫面直接顯示「已連線」、「未連線」或其他相符的狀態文字
- **AND** 即使忽略狀態顏色，user 仍能從文字了解結果

#### Scenario: 顯示待開發項目
- **WHEN** user 查看尚未提供分析功能的拳擊項目
- **THEN** 畫面直接顯示「待開發」或「分析功能待開發」
- **AND** 不只使用顏色表示該功能尚未完成

### Requirement: 介面必須支援鍵盤操作
Desktop App MUST 讓 user 使用鍵盤依合理順序移動焦點並觸發所有可用的主要及次要操作；目前取得鍵盤焦點的控制項 MUST 有可看見的焦點提示。

#### Scenario: 使用鍵盤切換頁面
- **WHEN** user 不使用滑鼠，改用鍵盤移動到導覽項目並觸發它
- **THEN** Desktop App 切換到所選頁面
- **AND** 焦點移動期間有可看見的焦點提示

#### Scenario: 使用鍵盤分配 IMU
- **WHEN** user 使用鍵盤操作 IMU 分配欄位
- **THEN** user 可以選擇可用 IMU 並移動到下一個位置欄位
- **AND** 操作順序與畫面閱讀順序一致

### Requirement: 支援的視窗大小不得遮住必要操作
Desktop App MUST 在支援的最小視窗及更大視窗中，讓導覽、頁面標題、必要輸入欄位、狀態文字與主要操作保持可閱讀且可操作；內容超出可見範圍時 MUST 提供捲動，不得讓元件互相重疊。

#### Scenario: 使用支援的最小視窗
- **WHEN** Desktop App 內容區為 `900 × 650` logical pixels
- **THEN** 目前頁面的必要操作與狀態文字沒有互相重疊
- **AND** user 可以透過可見內容或捲動到達所有必要操作

#### Scenario: 系統使用高 DPI 顯示比例
- **WHEN** 作業系統放大 Desktop App 的文字與控制項
- **THEN** 必要文字不會被固定高度截斷
- **AND** user 仍能操作導覽、輸入欄位及頁面按鈕

#### Scenario: user 調整 App 視窗大小
- **WHEN** user 改變 Desktop App 視窗的寬度或高度
- **THEN** 主畫面的功能卡片會依可用寬度自動調整每列欄數
- **AND** 登入、註冊及 IMU 選擇欄位會使用可用寬度，空間不足時改為上下排列
- **AND** IMU Report 摘要與表格會使用可用空間，必要時提供表格捲動而不截斷資料

#### Scenario: IMU 測試進行中顯示完整百分比
- **WHEN** IMU 連線狀態頁面正在收集五秒測試資料
- **THEN** 進度條會顯示完整的百分比數字與百分比符號
- **AND** 百分比文字不會被進度條邊界裁切或遮住

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
