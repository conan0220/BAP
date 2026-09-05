## 名詞定義

| 名詞 | 定義 |
|---|---|
| App shell | 包住各功能頁面的共用介面，包含側邊導覽、上方頁面標題與帳號操作。 |
| 主要操作 | user 在目前頁面最需要執行的動作，例如「重新測試」或「繼續」。 |
| 目前頁面 | user 當下正在查看的功能頁面。 |
| 支援的最小視窗 | 內容區至少為 `900 × 650` logical pixels 的 Desktop App 視窗。 |
| 自適應 Layout | 依目前可用寬度重新排列元件，讓內容利用視窗空間，而不是維持固定欄數或固定欄位寬度。 |
| 狀態文字 | 直接以文字說明結果，例如「已連線」、「未辨識」或「待開發」。 |

## Purpose

提供一致、清楚且能以滑鼠或鍵盤操作的 BAP Desktop App 介面，讓 user 容易辨認目前所在頁面、下一個操作，以及各功能目前是否可用。

## ADDED Requirements

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
