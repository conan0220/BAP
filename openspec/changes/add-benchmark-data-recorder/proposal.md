## 名詞定義

| 名詞 | 定義 |
|---|---|
| Benchmark 資料錄製 | 在 Desktop App 本機擷取 IMU 資料、輸入人工答案並匯出測試資料的開發工具。 |
| Labeled data | 同時包含原始 IMU CSV、來源與 Session Metadata，以及人工確認 Ground Truth 的資料。 |
| Ground Truth | user 在錄製後輸入的左右手實際出拳次數。 |
| Input Role | IMU 在分析中的用途；第一版為 `left_wrist` 與 `right_wrist`。 |
| IMU source | 由有線 Port，或無線接收器的 Port、Group ID 與 Node ID 唯一識別的資料來源。 |
| Benchmark bundle | 一個包含 Metadata JSON 與每顆 IMU 各一份 Common IMU CSV 的可攜 ZIP。 |
| 匯出 | Desktop App 讓 user 選擇本機儲存位置並寫出 Benchmark bundle；不是從遠端網站下載。 |
| Sentinel-free data | 不包含 Username、Token、密碼、電腦名稱或其他不需要個人資訊的 Benchmark 內容。 |

## 原因

目前建立演算法 Benchmark 需要開發者自行操作 IMU recorder、整理左右手 CSV、手動建立 Metadata 並補上正確拳數，容易發生來源綁錯、格式不一致或漏填完整性資訊。Desktop App 需要一個專用頁面，把真實 Shadow boxing Session 可靠地匯出成可直接審查與加入 source-level tests 的 labeled data。

## 變更內容

- 在 Desktop App 的「開發工具」加入「Benchmark 資料錄製」頁面，第一版固定支援 `punch_count` 與 Shadow boxing。
- 進入頁面後自動掃描所有候選 Port，讓 user 將不同 IMU source 分別指定為左手腕與右手腕；同一顆 IMU 不得同時分配給兩個位置。
- 無線來源顯示 Port、Group ID 與 Node ID；有線來源以 Port 識別。
- 讓 user 輸入預定錄製時間、開始錄製，並可等待時間到或使用按鈕提前結束。
- 錄製完成後要求 user 輸入左手與右手實際出拳次數，總拳數由系統計算，並允許加入不含敏感資訊的備註。
- 在匯出前驗證 CSV schema、row count、檔案大小、SHA-256、Input Bindings 與 Ground Truth。
- 以單一 ZIP 匯出 Metadata JSON 及左右手各一份 Common IMU CSV；第一版不自動上傳 Backend，也不自動修改或 commit repository。
- 匯出內容不保存 Username、Password、Token、電腦名稱或其他不必要的個人識別資訊。

## 能力

### 新增能力

- `benchmark-data-recorder`：定義 Benchmark 錄製頁面、IMU 位置分配、限時錄製、Ground Truth 輸入、資料驗證與本機 ZIP 匯出格式。

### 修改能力

- `desktop-app-shell`：在登入後的 App shell 新增「開發工具」區域與「Benchmark 資料錄製」入口，同時保持正式拳擊分析流程獨立。

## 影響

- Desktop App 側邊導覽、Benchmark 錄製頁面、IMU 探索與來源分配 UI。
- 現有 Live Analysis Recording 與 Common IMU CSV writer 的可重用錄製邊界；正式 Session 上傳行為不受影響。
- 新增 versioned Benchmark Metadata schema、ZIP exporter、checksum 與內容驗證。
- 新增 Fake IMU source-level tests、匯出 bundle contract tests，以及後續真實硬體人工驗證。
- 匯出的資料需由開發者人工審查後，才可加入 `tests/fixtures/punch_count/` 並成為 CI Benchmark。