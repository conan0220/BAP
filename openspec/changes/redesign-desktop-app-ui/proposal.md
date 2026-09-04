## 名詞定義

| 名詞 | 定義 |
|---|---|
| BAP | Boxing Analysis Platform，本專案與 Desktop App 的正式名稱。 |
| Desktop App | 安裝在 user 電腦上的 PySide6 桌面應用程式。 |
| IMU 位置 | 某個拳擊測量項目要求放置 IMU 的身體或器材位置，例如拳擊手左手腕。 |
| IMU 分配 | user 將自動探索到的 IMU 指定給測量項目要求的位置。 |
| 拳種辨識 | 使用 IMU 資料辨識出拳種類的分析項目；本 Change 只建立入口及 IMU 分配介面。 |
| 待開發 | 畫面入口與前置設定已存在，但目前不會開始拳擊資料錄製或分析。 |

## 原因

目前 Desktop App 雖然已有可操作的 Prototype，但畫面仍偏向基本 Qt 元件排列，而且每個拳擊項目只能選擇一顆 IMU，無法表達不同測量項目需要多顆 IMU、不同安裝位置及不同角色的實際需求。這次 Change 將已確認的 UI Prototype 轉成可實作、可驗證的需求，讓操作流程更清楚，也為未來各項拳擊分析功能保留正確的 IMU 分配方式。

## 變更內容

- 將 Desktop App 改成一致的 BAP 視覺與頁面架構，包括側邊導覽、上方頁面標題、總覽、IMU 連線狀態、拳擊項目、登入及註冊畫面。
- 「IMU 連線狀態」只顯示有意義的整體數量與逐 Port Report，不計算或顯示全部 Port 的平均取樣率。
- 每次進入拳擊測量項目後，仍先自動探索當下可用的 IMU，再依該項目要求的位置讓 user 分別指定 IMU。
- 出拳次數、出拳速度及出拳軌跡各需要兩顆 IMU，分別指定給拳擊手的左手腕與右手腕。
- 拳種辨識需要兩顆 IMU，分別放在持把人的左手把背面與右手把背面。
- 同一顆 IMU 不得同時分配給同一測量項目的兩個位置。
- 出拳力量所需的 IMU 數量與位置尚未決定；畫面要清楚標示配置待決定，且不允許 user 進入下一步。
- 將既有介面中的「拳型辨識」統一改名為「拳種辨識」。
- 本 Change 只完成介面與 IMU 分配前置流程，不開始錄製拳擊資料，也不產生分析結果。
- IMU 連線測試會依連線方式產生不同的逐 Port CSV：無線接收器使用固定 16 個 Node 欄位的 Gateway packet schema，有線 IMU 使用單顆裝置的 20 欄 schema。
- 無線接收器的取樣率以 Gateway packet 對應的 CSV 資料列數計算，不會因同一個 packet 包含多顆 Node 而重複加總。

## 能力

### 新增能力

- `desktop-ui-design`：定義 BAP Desktop App 共用的視覺架構、頁面導覽、互動狀態、鍵盤操作及不同視窗寬度下的呈現方式。

### 修改能力

- `desktop-app-shell`：將拳擊分析名稱統一為「拳種辨識」，並讓已確認的總覽、導覽與項目頁面成為可驗證的 Desktop App 行為。
- `imu-connection-diagnostics`：禁止顯示將不同 Port 混合計算的平均取樣率，保留逐 Port 取樣率。
- `imu-source-discovery`：把「一個項目只能選擇一個來源」改成「依項目要求，將一顆以上的 IMU 分配給不同位置」。

## 影響

- 主要影響 `bap_desktop/ui/` 下的 App shell、登入／註冊、總覽、IMU 連線狀態及拳擊項目頁面。
- 需要新增共用 Style Sheet、可重複使用的 UI 元件與項目別 IMU 配置資料。
- 需要更新現有 PySide6 UI tests，並新增頁面導覽、IMU 分配、防止重複分配、出拳力量阻擋及小視窗版面測試。
- 不修改遠端 Backend API、帳號資料庫、IMU parser、三秒來源探索規則或五秒連線測試規則。
- IMU 連線測試的本機 CSV schema、逐 Port 檔案輸出與無線取樣率計算會調整；資料仍不會上傳遠端 Backend。
- 不修改 `ANROT-IMU-v1.3.6-windows-x64/` 下的 vendor material。
