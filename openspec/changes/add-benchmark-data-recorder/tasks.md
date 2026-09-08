## 名詞定義

| 名詞 | 定義 |
|---|---|
| Fake IMU | 自動測試注入的可控制 IMU 資料來源，不需要實體 Serial Port。 |
| staging | 尚未成功匯出前，保存本次錄製檔案的 App 本機暫存區。 |
| Bundle contract test | 解開 ZIP 後重新驗證 Metadata、CSV schema、檔名與 checksum 的測試。 |

## 1. Benchmark bundle contract

- [x] 1.1 新增 Benchmark Metadata version 1 model，定義用途、活動類型、duration、stop reason、Input Roles、source descriptors、Ground Truth、Desktop version 與備註。
- [x] 1.2 新增 validation tests，涵蓋固定 `punch_count`／`shadow_boxing`、左右手角色、來源不得重複、非負整數 Ground Truth、總數相加及禁止未知欄位。
- [x] 1.3 新增 privacy contract tests，確認 Metadata 與 ZIP 不接受 Username、Password、Token、電腦名稱或絕對本機路徑。

## 2. 可重用 IMU capture

- [x] 2.1 將既有 serial read、Common IMU CSV writer、clock 與 source assignment 抽成正式 Session 與 Benchmark 都能重用的 capture service，避免複製錄製迴圈。
- [x] 2.2 新增 Fake wired 與 wireless capture tests，確認有線以 Port、無線以 Port／Group ID／Node ID 保存，且左右手各產生一份 CSV。
- [x] 2.3 實作 5～3600 秒、預設 60 秒的 monotonic duration 與 single-finalization guard，測試時間到和提前結束各自只 finalize 一次。
- [x] 2.4 新增必要來源中斷、解析失敗與零有效 Frame tests，確認失敗錄製不能進入可匯出狀態。

## 3. Recorder coordinator

- [x] 3.1 實作 scanning、ready、recording、labeling、ready-to-export、exported 與 failed 狀態及允許操作。
- [x] 3.2 串接既有全 Port discovery 與左右手 selector，測試同 Gateway 不同 Nodes、兩個 wired Ports 及重複來源被拒絕。
- [x] 3.3 實作 Ground Truth 與備註輸入模型，測試有效數字自動計算總數，以及空白、負數、小數與非數字禁止匯出。
- [x] 3.4 將錄製輸出保存在 `temp/benchmark-recordings/<session-id>/`，並確保取消或匯出失敗時保留 unsaved recording。

## 4. Atomic ZIP exporter

- [x] 4.1 實作固定 bundle filename、flat ZIP layout 與 `.partial` 同目錄暫存寫入。
- [x] 4.2 實作共用 Bundle validator，在寫入前後驗證 entry names、Metadata、Common IMU CSV、row count、size 與 SHA-256。
- [x] 4.3 新增成功、取消、權限／空間錯誤與 checksum corruption tests，確認失敗不留下看似完成的 ZIP 且可再次匯出。
- [x] 4.4 新增 Bundle contract test，將成功 ZIP 解開後交給 Punch Count Benchmark loader，確認角色與 Ground Truth 可直接讀取。

## 5. Desktop UI

- [x] 5.1 在 App shell 新增獨立「開發工具」區域與「Benchmark 資料錄製」入口，不將它列為拳擊分析項目。
- [x] 5.2 建立自適應且可鍵盤操作的 Recorder 頁面，顯示用途、Shadow boxing、來源欄位、duration、倒數、狀態及單一主要操作。
- [x] 5.3 串接掃描、分配、錄製、Ground Truth、總數預覽、儲存對話框與匯出成功位置。
- [x] 5.4 新增 Qt tests，涵蓋導覽狀態、控制項 enablement、完整流程、取消儲存，以及離開或關閉 App 時對 unsaved recording 提示匯出或確認捨棄。
- [x] 5.5 確認頁面清楚顯示「不會上傳 Backend」與「需人工審查」，且不把 Ground Truth 呈現為正式分析 Result。

## 6. 驗證與交付

- [x] 6.1 執行完整 pytest 與 Benchmark bundle contract tests，確認正式 Session upload 與既有 IMU 連線狀態沒有回歸。
- [ ] 6.2 使用同一 Gateway 的兩個實體 Nodes 完成人工錄製、提前結束、Ground Truth 與 ZIP 匯出驗證。
- [ ] 6.3 使用兩個有線 IMU Ports 完成人工錄製與 ZIP 匯出驗證。
- [ ] 6.4 在錄製期間中斷一個實體來源，確認 UI 回報失敗且不能匯出有效 bundle。
- [ ] 6.5 將人工匯出的 ZIP 用 Benchmark loader 驗證；只有經開發者審查的 cases 才能加入 repository。
- [ ] 6.6 在提交 Desktop 程式修改前提升 `bap_desktop/VERSION`，再執行 Windows Candidate Build、Installer smoke test 與 Pull Request CI。