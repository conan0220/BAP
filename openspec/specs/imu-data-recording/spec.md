# imu-data-recording 規格

## 名詞定義

| 名詞 | 定義 |
|---|---|
| Requirement | 系統必須符合的單一可驗證需求。 |
| Scenario | 以特定條件與預期結果描述 Requirement 的可驗證案例；英文標題同時作為 pytest 追溯識別符。 |
| `SHALL` | OpenSpec 的規範性關鍵字，表示「必須」。 |
| `WHEN` | Scenario 中觸發行為的條件或輸入。 |
| `THEN` | Scenario 中系統應產生的可觀察結果。 |
| recorder | 從序列埠讀取並解析資料，再將量測結果寫入檔案的記錄元件。 |
| recording command | 啟動 recorder 並接收連接埠、baud rate、output path 與 duration 等選項的命令列介面。 |
| serial port | 作業系統提供、用於和實體裝置交換 bytes 的序列通訊端點。 |
| baud rate | 序列通訊每秒傳送的 symbol 數率設定；所有選取的連接埠共用同一設定值。 |
| duration | 一次記錄持續的秒數。 |
| output path | 使用者指定的輸出檔案路徑，包含基礎檔名與可選 suffix。 |
| suffix | 檔名最後一個副檔名部分，例如 `.csv`。 |
| incremental parser state | Parser 為尚未完成的輸入保留的狀態；不同序列埠的狀態彼此獨立。 |
| gateway packet | Gateway 送出的解碼資料單位，可包含一個或多個 node measurements。 |
| gateway ID | 識別 packet 來源 gateway 的值，也用於產生專屬輸出檔名。 |
| CSV | Comma-Separated Values，以逗號分隔欄位的文字表格格式。 |
| CSV schema | CSV header、欄位順序、欄位數量及各欄位語意的定義。 |
| node | Gateway packet 中的一個 IMU 感測器資料來源。 |
| node slot | 固定 16-node CSV schema 中保留給特定 packet position 的 17 個欄位。 |
| packet position | Node measurement 在 gateway packet 中從 0 開始的位置索引，用於選擇對應的 node slot。 |
| Unix time | 從 Unix epoch 起算的主機時間；本規格中的 `UnixTimeStamp(sec)` 以整秒表示。 |
| system time | Gateway packet 第一個 frame 提供的時間；本規格中的 `SystemTime(ms)` 以毫秒表示。 |
| numeric precision | 將數值寫入 CSV 時保留的小數位數。 |
| flush | 將應用程式緩衝區中尚未落盤的輸出要求寫入檔案。 |
| resource cleanup | 結束記錄時關閉已開啟的序列連線與 CSV 檔案。 |
| failure status | 命令因錯誤終止時回傳的非成功狀態。 |

## Purpose

定義既有的離線命令列記錄行為：從一個或多個序列埠收集已解析的 ANROT gateway measurements，並存入 gateway-specific CSV files。

## Requirements

### Requirement: 記錄命令輸入
系統 SHALL 提供記錄命令，接受必要的 comma-separated serial-port list、預設為 `115200` 的正整數 baud rate、預設為 `recorded_data.csv` 的 output path，以及預設為 `10` 的正數秒數 duration。

#### Scenario: Start with valid recording inputs
- **WHEN** 操作人員提供至少一個非空白序列埠及有效的 option values
- **THEN** 系統會以共同的 baud rate 開啟每個選取的連接埠，並持續記錄直到設定的 duration 經過或操作人員中斷

#### Scenario: Reject an empty port list
- **WHEN** 提供的連接埠清單不含任何非空白的 port name
- **THEN** 命令會在開始記錄前拒絕該輸入

#### Scenario: Reject an invalid baud rate or duration
- **WHEN** 提供的 baud rate 不是正整數，或 duration 不是正數
- **THEN** 命令會在開始記錄前拒絕無效值

### Requirement: 獨立的多連接埠解析
Recorder SHALL 為每個選取的序列埠維護獨立的增量 binary-parser state，使來自某個連接埠的 partial input 不會影響從其他連接埠讀取的 frames。

#### Scenario: Frames are interleaved across two ports
- **WHEN** 兩個選取的連接埠以交錯順序提供 frame fragments
- **THEN** 每個 fragment 只會與同一連接埠先前的 bytes 結合，且兩個連接埠的完整有效 frames 都能被記錄

### Requirement: Gateway-specific CSV 輸出
Recorder SHALL 依 gateway ID 將每個 decoded packet 導向對應的 CSV file。File name SHALL 在設定的 suffix 前附加 `_<gateway-id>`、在設定的輸出沒有 suffix 時使用 `.csv`，並在 decoded packet 沒有 gateway ID 時使用 `unknown`。

#### Scenario: Record two gateway IDs
- **WHEN** 一次記錄期間收到來自兩個 gateway IDs 的 decoded packets
- **THEN** recorder 會將各 gateway 的 rows 寫入帶有該 gateway ID 的獨立 output file

#### Scenario: No packet is decoded for a gateway
- **WHEN** 記錄期間沒有收到某 gateway 可解碼的 packet
- **THEN** recorder 不會為該 gateway 建立 output file

### Requirement: 固定的 16-node CSV schema
每個 gateway CSV SHALL 以 `UnixTimeStamp(sec)` 與 `SystemTime(ms)` 開頭，後接 16 個 node groups。每個 node group SHALL 包含 node ID、三個以 g 為單位的 acceleration values、三個以 degrees per second 為單位的 angular-velocity values、三個以 microtesla 為單位的 magnetic-field values、以 degrees 為單位的 roll、pitch 與 yaw，以及 quaternion W、X、Y、Z。

#### Scenario: Write a gateway packet row
- **WHEN** recorder 處理一個 decoded gateway packet
- **THEN** 它會寫入一列，使用以整秒表示的 host Unix time、packet 第一個 frame 以毫秒表示的 system time，以及置於 packet-position slots 中的 decoded node measurements

#### Scenario: A node slot is absent
- **WHEN** gateway packet 的 16 個 node positions 之一沒有 decoded frame
- **THEN** recorder 會將該 node position 的全部 17 個欄位留空

### Requirement: 既有的 CSV 數值精度
Recorder SHALL 將 acceleration 與 quaternion values 格式化為小數點後三位，將 angular velocity、magnetic field 與 Euler angles 格式化為小數點後兩位，並將不可用的 values 留空。

#### Scenario: Write available and unavailable measurements
- **WHEN** decoded frame 包含部分支援的 measurement fields，其他欄位則不可用
- **THEN** CSV row 會依定義的精度格式化可用 values，並為不可用 values 寫入空白欄位

### Requirement: 記錄終止與持久保存
Recorder SHALL 在擷取期間至少每秒 flush 開啟的 gateway files 一次、在設定的 duration 經過或操作人員中斷記錄時將其關閉，並在序列存取或權限失敗時以 failure status 終止。

#### Scenario: Configured duration elapses
- **WHEN** 到達記錄 deadline
- **THEN** recorder 會關閉所有開啟的 serial connections 與 gateway CSV files，並將控制權交還操作人員

#### Scenario: Operator interrupts recording
- **WHEN** 操作人員在擷取期間送出 keyboard interrupt
- **THEN** recorder 會關閉所有開啟的資源，同時保留已寫入的 rows

#### Scenario: A selected serial port cannot be accessed
- **WHEN** 開啟或讀取選取的序列埠引發 serial-access 或 permission error
- **THEN** recorder 會關閉該命令開啟的資源，並以 failure status 終止
