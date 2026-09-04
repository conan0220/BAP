## 名詞定義

| 名詞 | 定義 |
|---|---|
| 整體摘要 | Report 上方整理 Port 數量或連線數量的簡短資訊。 |
| 逐 Port 取樣率 | 使用單一 Port 成功解析的資料列數除以該 Port 實際收集秒數得到的取樣率。 |
| 全部 Port 平均取樣率 | 將多個 Port 的取樣率再計算平均的數值；不同 Port 代表不同資料來源，因此本介面不顯示此數值。 |
| Report | IMU 連線狀態測試完成後，每個 Port 顯示一列的結果表格。 |
| Gateway packet | 無線接收器在同一個取樣時間送出的資料包，可同時包含一顆以上的 Node。 |
| 無線 CSV 資料列 | 一個 Gateway packet 寫成的一列資料；同一列包含該 packet 的所有 Node。 |
| 有線 CSV 資料列 | 有線 IMU 成功解析的一個 frame 寫成的一列資料。 |

## ADDED Requirements

### Requirement: 整體摘要不得顯示全部 Port 平均取樣率
「IMU 連線狀態」頁面的整體摘要 MUST NOT 計算或顯示全部 Port 平均取樣率；系統 MUST 保留 Report 中每個 Port 各自的取樣率。

#### Scenario: 多個 Port 有不同取樣率
- **WHEN** IMU 連線測試找到兩個以上具有不同取樣率的 Port
- **THEN** 整體摘要不顯示合併或平均後的取樣率
- **AND** Report 仍在每個 Port 的資料列顯示該 Port 自己的取樣率

#### Scenario: 只有一個 Port 成功連線
- **WHEN** IMU 連線測試只有一個 Port 成功解析資料
- **THEN** 整體摘要仍不顯示平均取樣率
- **AND** Report 在該 Port 的資料列顯示其取樣率

## MODIFIED Requirements

### Requirement: 取樣率依實際收集時間計算
系統 MUST 使用成功寫入該 Port CSV 的資料列數除以實際收集秒數計算取樣率，排除 CSV header，並以一位小數的 Hz 顯示。有線連接 MUST 將每個成功解析的 frame 算成一列；無線接收器 MUST 將同一個 Gateway packet 內的所有 Node 合併成一列，不得把 Node 數量重複算進取樣率。

#### Scenario: 五秒內寫入 2000 筆資料
- **WHEN** 某個 Port 的實際收集時間為 5.0 秒，且暫存 CSV 有 2000 筆資料列
- **THEN** Report 顯示取樣率 `400.0 Hz`

#### Scenario: 資料內容重複
- **WHEN** 暫存 CSV 的資料列內容重複，但總共有成功解析的資料列
- **THEN** 系統仍以資料列數除以實際收集時間計算 Prototype 取樣率
- **AND** 系統不在本次變更中計算排除重複資料後的有效取樣率

#### Scenario: 同一個無線封包包含多個 Node
- **WHEN** 無線接收器在 2.0 秒內收到 10 個 Gateway packet，且每個 packet 都包含兩顆 Node
- **THEN** 無線 CSV 寫入 10 筆資料列
- **AND** Report 顯示取樣率 `5.0 Hz`
- **AND** Report 不會因為每個 packet 有兩顆 Node 而顯示 `10.0 Hz`

### Requirement: 暫存 CSV 可以匯出但不會永久留存
系統 MUST 為每個成功連線的 Port 建立自己的暫存 CSV。無線接收器 CSV MUST 使用 `ts_ms(ms)`、`UnixTimeStamp(sec)` 加上固定 16 組 Node 欄位的 schema；有線 IMU CSV MUST 使用 `UnixTimeStamp(sec)`、`Time(ms)`、壓力、溫度、加速度、角速度、磁力、姿態角與四元數的 schema。檔名 MUST 包含錄製時間、Port 與連線類型，且同一秒重新測試不得覆蓋本次執行期間先前使用過的檔名。

#### Scenario: 產生無線接收器 CSV
- **WHEN** 某個 Port 成功解析無線接收器 Gateway packet
- **THEN** 該 Port 的 CSV header 與無線固定 16 Node schema 完全一致
- **AND** 每個 Gateway packet 只寫入一列

#### Scenario: 產生有線 IMU CSV
- **WHEN** 某個 Port 成功解析有線 IMU frame
- **THEN** 該 Port 的 CSV header 與有線 IMU schema 完全一致
- **AND** 每個成功解析的 frame 寫入一列

#### Scenario: 同時測試多個已連線 Port
- **WHEN** 本次測試有兩個以上的 Port 成功解析資料
- **THEN** 系統為每個 Port 分別保留符合其連線方式的 CSV
- **AND** user 匯出時可以把本次所有 Port 的 CSV 複製到選擇的資料夾

#### Scenario: 匯出 CSV
- **WHEN** user 在 Report 畫面按下「匯出 CSV」並選擇有效位置
- **THEN** Desktop App 匯出本次測試產生的逐 Port CSV
- **AND** 檔名包含可辨認來源的 Port

#### Scenario: App 關閉時存在未匯出的暫存 CSV
- **WHEN** Desktop App 關閉
- **THEN** 系統刪除由 IMU 連線測試建立的所有未匯出暫存 CSV
- **AND** 下次啟動 App 時不顯示上一次執行的 Report
