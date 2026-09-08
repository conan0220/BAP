## 名詞定義

| 名詞 | 定義 |
|---|---|
| 開發工具 | 與正式拳擊分析分開、用來建立或檢查開發資料的 Desktop App 功能區。 |
| Benchmark 資料錄製 | 建立本機 labeled IMU 測試資料的頁面。 |

## ADDED Requirements

### Requirement: App shell 必須提供獨立的 Benchmark 開發工具入口
Desktop App MUST 在登入後的 App shell 提供「開發工具」區域與「Benchmark 資料錄製」入口。該入口 MUST 與正式拳擊分析項目分開呈現，並 MUST 以文字說明匯出的資料需由開發者人工審查後才能成為正式 Benchmark。

#### Scenario: user 查看側邊導覽
- **WHEN** user 已登入並查看 App shell
- **THEN** 側邊導覽顯示「開發工具」區域
- **AND** 該區域包含「Benchmark 資料錄製」入口
- **AND** 入口不會被列為第六種拳擊分析項目

#### Scenario: user 開啟 Benchmark Recorder
- **WHEN** user 選擇「Benchmark 資料錄製」
- **THEN** 內容區顯示 Recorder 頁面
- **AND** App shell 的目前頁面名稱與導覽狀態同步更新