## 名詞定義

| 名詞 | 定義 |
|---|---|
| App shell | 登入後共用的側邊導覽、上方頁面列與內容區。 |
| QSS | 集中控制 PySide6 元件外觀的 Qt Style Sheet。 |
| 項目設定 | 定義一個拳擊項目名稱、說明與必要 IMU 位置的資料。 |
| Scenario marker | `pytest.mark.scenario` 與 capability／Scenario 的對應標記。 |
| UI smoke test | 由開發者使用 `open_BAP.cmd` 快速確認實際畫面與基本操作的測試。 |

## 1. BAP 視覺基礎

- [x] 1.1 建立集中式 BAP QSS 與載入入口，定義深色側邊欄、明亮內容區、拳擊紅主要操作、次要操作、停用狀態及可見鍵盤焦點。
- [x] 1.2 建立可重複使用的頁面標題、狀態標籤、功能卡片及按鈕外觀介面，避免各頁面重複撰寫 Style Sheet。
- [x] 1.3 加入 UI 需要的本機圖示資源或 Qt 內建圖示對應，確認 Windows installer 不需要連線下載圖示。
- [x] 1.4 更新繁體中文文字資源，將所有「拳型辨識」改成「拳種辨識」，並加入項目別 IMU 位置、來源不足、重複分配及配置待決定文字。

## 2. 登入、App Shell 與總覽

- [x] 2.1 建立登入後 App shell，包含工作區／拳擊分析側邊導覽、目前頁面名稱、帳號資訊、Backend 狀態與登出操作。
- [x] 2.2 重構 `MainWindow`，讓 Auth 畫面與登入後 App shell 分開，並保留 Session restore、UpdateBanner、登出與 ShutdownCoordinator 行為。
- [x] 2.3 將總覽頁改成已確認的卡片式入口，顯示 IMU 連線狀態及五個分開的拳擊項目，並清楚標示待開發。
- [x] 2.4 重做登入與註冊畫面配置，保留 Username／Password 驗證、顯示密碼、記住登入狀態及錯誤訊息行為。
- [x] 2.5 讓側邊導覽、總覽卡片及頁面標題同步顯示目前項目，並以文字或形狀搭配顏色表示目前頁面。

## 3. IMU 連線狀態頁面

- [x] 3.1 將五秒收集、分析、完成及錯誤狀態套用新的頁面標題、進度與操作配置，不改變既有非同步診斷流程。
- [x] 3.2 以每個 Port 一列呈現完整 Report 欄位，保留 Manufacturer、連線方式、Baud rate、Group ID／Node IDs、逐 Port 取樣率、狀態及說明。
- [x] 3.3 在 Report 上方只顯示 Port 數量與成功連線數量等摘要，移除全部 Port 平均取樣率的計算與畫面欄位。
- [x] 3.4 保留重新測試與匯出 CSV 行為，並依畫面層級將重新測試設為主要操作、匯出設為次要操作。

## 4. 項目別 IMU 分配

- [x] 4.1 建立項目設定資料，定義出拳次數、出拳速度及出拳軌跡需要拳擊手左／右手腕各一顆 IMU。
- [x] 4.2 定義拳種辨識需要持把人左手把背面與右手把背面各一顆 IMU，並讓出拳力量保持配置未決定。
- [x] 4.3 重構 `PunchItemPage`，在每次三秒探索完成後依項目設定建立一個或多個位置下拉欄位，完整顯示每個 ImuSource 的 Port、連線方式、Group ID 與 Node ID。
- [x] 4.4 使用「位置 → ImuSource」保存目前分配，只有所有必要位置都有不同來源時才啟用「繼續」。
- [x] 4.5 對重複分配顯示清楚提示；可用 IMU 少於項目需求時顯示來源不足，兩種情況都不得繼續。
- [x] 4.6 在出拳力量探索完成後顯示「IMU 配置待決定」，不建立可提交的分配欄位並保持「繼續」停用。
- [x] 4.7 完成有效分配後只顯示該項目待開發，清除探索暫存，且不得開始拳擊資料錄製或上傳 IMU 資料。

## 5. 視窗大小、鍵盤與生命週期

- [x] 5.1 使用可伸縮 Layout 與必要的 QScrollArea，確認 `900 × 650` logical pixels 下導覽、文字、欄位與操作不重疊且都能到達。
- [x] 5.2 設定 label buddy、accessible name、Tab focus 順序及快捷鍵行為，讓 Auth、導覽、IMU Report 與 IMU 分配能以鍵盤完成。
- [x] 5.3 確認高 DPI 或較大系統字型下，必要文字與控制項不會被固定高度截斷。
- [x] 5.4 驗證 user 在測試或探索期間切換頁面、登出或關閉 App 時，worker 會被取消且暫存資料會被清除。

## 6. Automated Tests 與 Scenario 對應

- [x] 6.1 為 `desktop-ui-design` 的所有 Scenario 建立 Qt automated tests 與 `pytest.mark.scenario` 對應，涵蓋 App shell、操作層級、文字狀態、鍵盤、最小視窗及高 DPI。
- [x] 6.2 為 `desktop-app-shell` 變更的所有 Scenario 建立 tests 與 marker，驗證五個獨立入口、拳種辨識名稱、單一項目頁面與標題同步。
- [x] 6.3 為 `imu-connection-diagnostics` 變更的所有 Scenario 建立 tests 與 marker，驗證不顯示平均取樣率且仍顯示每個 Port 的取樣率。
- [x] 6.4 為 `imu-source-discovery` 變更的所有 Scenario 建立 tests 與 marker，涵蓋三種手腕項目、拳種辨識、重複來源、來源不足、出拳力量、完整分配及未完成分配。
- [x] 6.5 更新既有 MainWindow、Auth、Diagnostics、Discovery 與 Windows packaging tests，確認 UI 重構沒有破壞 Session、更新檢查、CSV 匯出及 installer 啟動。
- [x] 6.6 執行 Scenario coverage checker，確認本 Change 沒有任何未對應 automated／contract／hardware-in-the-loop test 的 Scenario。

## 7. 最終驗證

- [x] 7.1 執行 OpenSpec strict validation、Desktop test suite 及完整 pytest，修正所有失敗。
- [x] 7.2 使用 `open_BAP.cmd` 執行人工 UI smoke test，逐頁核對已確認的登入、總覽、IMU Report 與五個拳擊項目畫面。
- [ ] 7.3 建立 Windows installer，於乾淨 Windows 測試安裝、啟動、鍵盤操作與解除安裝，確認本機圖示和 QSS 均包含在安裝包內。

## 8. 逐 Port CSV schema 與無線取樣率

- [x] 8.1 在 Port 掃描結果保存每個 parsed frame 的本機接收時間，供 CSV `UnixTimeStamp(sec)` 欄位使用。
- [x] 8.2 依 `data_20260904_213007.csv` 實作無線固定 16 Node schema，將同一個 Gateway packet 的所有 Node 合併成一列。
- [x] 8.3 依 `with_wire.csv` 實作有線 IMU schema，每個成功解析的 frame 寫入一列。
- [x] 8.4 每個成功 Port 建立獨立且可辨認來源的時間戳記 CSV；單檔可指定檔名，多檔可一次匯出到資料夾。
- [x] 8.5 使用實際 CSV 資料列數計算逐 Port 取樣率，並加入無線多 Node、有線、重測檔名與多檔匯出 automated tests。

## 9. 有線 Frame 解析修正

- [x] 9.1 修正單一裝置 parser 重複使用同一個 `AnrotFrame` 物件的問題，避免 CSV 中先前的資料全部被最後一筆覆寫。
- [x] 9.2 加入連續解析不同有線 frames 的回歸測試，確認每筆資料使用獨立物件並保留自己的內容。

## 10. 自適應視窗 Layout

- [x] 10.1 讓主畫面功能卡片與 IMU 測試入口依內容區寬度切換一欄、兩欄或三欄排列。
- [x] 10.2 讓登入／註冊區、頁面標題操作與拳擊項目 IMU 欄位在寬度不足時改成上下排列。
- [x] 10.3 讓 IMU Report 摘要自動換列，表格填滿可用高度並保留橫向捲動能力。
- [x] 10.4 加入視窗寬度切換的 Qt automated test，驗證主要頁面及欄位會重新排列。
- [x] 10.5 修正 PR #13 的螢幕尺寸相依測試：子元件以 600／900／1200 寬度驗證一／二／三欄及縮回排列；主視窗依實際可用寬度驗證，使用條件等待代替固定等待 10ms。測試不啟動 IMU 掃描，也不修改 Runner 的螢幕設定。

## 11. IMU 測試進度顯示

- [x] 11.1 調整 IMU 連線狀態進度條高度與文字格式，完整顯示測試百分比。
- [x] 11.2 加入 Qt automated test，確認進度文字可見且高度足以容納目前字型。
