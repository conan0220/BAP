## 1. 特性描述測試基礎

- [x] 1.1 將 `pytest` 與 `pytest-cov` 加入開發依賴項，並在 `pyproject.toml` 設定測試探索、嚴格設定，以及 `hardware`、`slow` 和 `dataset` markers。
- [x] 1.2 在 `tests/` 下新增共用、byte-accurate 的 ANROT frame fixtures 與含 checksum 的 NMEA fixtures，且不修改 runtime modules。
- [x] 1.3 新增可重複使用的 fake serial-port、controlled-clock、temporary-output 與 CLI invocation helpers。
- [x] 1.4 將全 repository 適用的 traceability 政策套用至本基準：記錄每個測試案例確切的 capability 與 Scenario 名稱，並確保參數化 Scenario 案例可在 pytest 輸出中個別識別。

## 2. IMU 資料解析基準

- [x] 2.1 為跨 chunks 分割的二進位輸入、前置 noise、無效 CRC，以及後續有效輸入的恢復行為，新增可個別追溯的 pytest 案例。
- [x] 2.2 為支援的單一裝置 `0x91`、`0x92` 與 `0x81` payload 欄位及格式專屬縮放，新增可個別追溯的 pytest 案例。
- [x] 2.3 為完整的 `0x63` gateway packets、16-node 上限與不完整的最後 node blocks，新增可個別追溯的 pytest 案例，包括 metadata、nine-axis scaling、shared timestamps 與 node ordering assertions。
- [x] 2.4 為支援且有效的 NMEA sentences、不完整的 NMEA 輸入、無效 checksum、不支援的 sentence types 與持續解析行為，新增可個別追溯的 pytest 案例。

## 3. IMU 裝置通訊基準

- [x] 3.1 為有內容與空白的作業系統連接埠清單新增可個別追溯的 pytest 案例。
- [x] 3.2 為混合有效輸入的即時監控、無效 baud rates、serial-access failures、frame-rate 顯示與中斷時清理，新增可個別追溯的 pytest 案例。
- [x] 3.3 為成功傳送已儲存指令、停止輸出的重試次數耗盡、後續指令失敗與無效的傳送 baud rates，新增可個別追溯的 pytest 案例，包括 8-N-1 設定、CRLF 結尾、順序、acknowledgements 與顯示的回應。

## 4. IMU 資料記錄基準

- [x] 4.1 為有效的記錄選項、遺漏的連接埠、無效 baud rates、無效 durations、輸出預設值，以及目前 10 秒的 duration 預設值，新增可個別追溯的 pytest 案例。
- [x] 4.2 新增一個可個別追溯的 pytest 案例，證明來自多個序列埠的交錯輸入會維持彼此隔離的增量 parser state。
- [x] 4.3 為兩個 gateway identifiers、未收到 gateway packet 時的惰性檔案建立、輸出命名、分開的檔案與 `unknown` gateway suffix，新增可個別追溯的 pytest 案例。
- [x] 4.4 為 gateway CSV rows、缺少的 node slots、可用與不可用的數值精度、兩個 timing columns、16 個 node groups 與 packet-position mapping，新增可個別追溯的 pytest 案例。
- [x] 4.5 為設定時長結束、鍵盤中斷、serial-access failure、定期 flush 與資源清理，新增可個別追溯的 pytest 案例。

## 5. 基準驗證

- [x] 5.1 將三份 delta specs 中的每個 `#### Scenario` 標題與已收集的 pytest 案例進行稽核，並解決所有遺漏或含糊的對應關係。
- [x] 5.2 執行聚焦的特性描述測試，再執行含 branch-coverage 報告的完整預設 pytest 套件；確認預設套件不需要 hardware-marked tests。
- [x] 5.3 確認本基準工作未變更任何 runtime source file，並透過縮小不準確的基準 requirements 範圍，或將期望的 runtime fixes 記錄為個別 OpenSpec changes，來處理失敗。
- [x] 5.4 執行 `openspec validate baseline-existing-imu-data-capabilities --type change --strict` 並解決所有 validation errors。
- [x] 5.5 執行 OpenSpec 的完整性、正確性與一致性驗證流程；若有官方 verifier 則使用之，否則執行並記錄等效審查，且在封存前確認沒有任何 Scenario 未被涵蓋。
