# imu-data-parsing 規格

## 名詞定義

| 名詞 | 定義 |
|---|---|
| Requirement | 系統必須符合的單一可驗證需求。 |
| Scenario | 以特定條件與預期結果描述 Requirement 的可驗證案例；英文標題同時作為 pytest 追溯識別符。 |
| `SHALL`／`SHALL NOT` | OpenSpec 的規範性關鍵字，分別表示「必須」與「不得」。 |
| `WHEN` | Scenario 中觸發行為的條件或輸入。 |
| `THEN` | Scenario 中系統應產生的可觀察結果。 |
| ANROT | HI221 裝置通訊所使用的二進位資料協定。 |
| frame | 具備同步標記、payload 長度、payload 與 CRC 等結構的一個完整二進位傳輸單位。 |
| synchronization sequence | 用來辨識 frame 起點的固定 bytes；本規格中的值為 `0x5A 0xA5`。 |
| payload | frame 中承載實際裝置資料的內容；其格式由 payload type 決定。 |
| parser | 接收原始 bytes 或文字，並將其解碼為結構化量測資料的元件。 |
| incremental parsing | 可跨多次呼叫保留未完成輸入，待資料完整後再解碼的解析方式。 |
| byte | 二進位資料的基本單位，由 8 個 bits 組成。 |
| chunk | 單次 parser call 收到的一段輸入資料；不保證包含完整 frame 或 sentence。 |
| CRC-16 | 用於檢查 ANROT frame 完整性的 16-bit cyclic redundancy check。 |
| checksum | 用於檢查 NMEA sentence 傳輸內容是否正確的驗證值。 |
| NMEA | 以文字 sentence 表示導航或感測器資料的通訊格式。 |
| sentence | 一筆以 newline 結尾、包含 sentence type、fields 與 checksum 的 NMEA 訊息。 |
| structured measurement | Parser 解碼後，以具名欄位表示的感測器量測資料。 |
| gateway | 彙整一個或多個 IMU node 資料並送出 gateway payload 的裝置。 |
| gateway ID | 用來識別資料來源 gateway 的識別碼。 |
| node | 由 gateway 管理並產生感測器量測資料的單一 IMU 裝置。 |
| node ID | 用來識別 gateway 中特定 node 的識別碼。 |
| gateway timestamp | Gateway 提供且由同一 packet 內 nodes 共用的時間值；本規格以毫秒表示。 |
| packet position | Node measurement 在 gateway packet 中的位置索引；本規格從 0 開始。 |
| scale factor | 將 protocol 中的原始數值轉換為物理單位數值所使用的倍率。 |
| quaternion | 以 W、X、Y、Z 四個分量表示三維姿態旋轉的方法。 |
| roll／pitch／yaw | 分別描述繞三個軸旋轉的 Euler angles，本規格以 degrees 表示。 |
| newline | 表示 NMEA sentence 結束的換行字元。 |
| `AnrotFrame` | Parser 為一筆 frame 建立的 Python 資料物件。 |
| 獨立物件 | 不會因為後續 frame 被解析而一起改變內容的資料物件。 |

## Purpose

定義既有的增量解碼行為：將支援的 ANROT 二進位 frame 與含 checksum 的 NMEA 文字 sentence 轉換為結構化感測器量測資料。

## Requirements

### Requirement: 增量 ANROT 二進位 framing
Binary parser SHALL 緩衝任意分段的輸入 bytes、識別以 `0x5A 0xA5` 開頭的 frames、使用宣告的 payload length 等待完整 frame，且僅對計算出的 CRC-16 與接收 CRC 相符的 frames 輸出量測資料。每個成功解析的單一裝置 frame SHALL 使用獨立的 `AnrotFrame` 物件，後續解析不得改變先前已輸出的 frame 內容。

#### Scenario: A valid frame arrives in multiple chunks
- **WHEN** 有效 ANROT frame 的 bytes 分散在多次 parser calls 中提供
- **THEN** parser 會保留不完整的 bytes，並僅在取得 CRC 有效的完整 frame 後輸出 decoded frame

#### Scenario: Noise precedes a valid frame
- **WHEN** 有效 ANROT synchronization sequence 前存在無關 bytes
- **THEN** parser 會捨棄 synchronization sequence 之前的 bytes，並解碼有效 frame

#### Scenario: A complete frame has an invalid CRC
- **WHEN** 完整 ANROT frame 的計算 CRC 不等於接收的 CRC
- **THEN** parser 不會為該 frame 輸出任何量測資料，並會繼續接受後續輸入

#### Scenario: Sequential valid frames retain their own values
- **WHEN** parser 依序解析兩筆內容不同且 CRC 有效的單一裝置 frames
- **THEN** parser 會為兩筆 frame 回傳不同的 `AnrotFrame` 物件
- **AND** 解析第二筆 frame 不會覆寫第一筆 frame 的量測內容

### Requirement: 支援的單一裝置 ANROT payloads
Binary parser SHALL 使用各格式專屬的 scale factors，將支援的 `0x91`、`0x92` 與 `0x81` payloads 解碼為其中可用的 timestamp、acceleration、angular velocity、magnetic field、orientation、environment、navigation 與 status 欄位。

#### Scenario: Decode a supported single-device payload
- **WHEN** CRC 有效的 ANROT frame 包含支援的 `0x91`、`0x92` 或 `0x81` payload
- **THEN** parser 會輸出一個 structured frame，其中該 payload 提供的欄位已轉換為 parser format mapping 所定義的單位

### Requirement: 緊湊型多 node gateway payload 解碼
Binary parser SHALL 將 ANROT `0x63` gateway payload 解碼為不超過 16 筆 node measurements。每筆輸出的 node measurement SHALL 包含 gateway ID、node ID、以毫秒為單位的 shared gateway timestamp、node count、zero-based packet position、以 g 為單位的三軸 acceleration、以 microtesla 為單位的三軸 magnetic field、以 degrees per second 為單位的三軸 angular velocity、quaternion，以及以 degrees 為單位的 roll、pitch 與 yaw。

#### Scenario: Decode a complete multi-node gateway payload
- **WHEN** CRC 有效的 `0x63` payload 宣告的 node blocks 均完整存在
- **THEN** parser 會為每個 decoded node block 輸出一筆 structured measurement，並包含 shared gateway metadata 與縮放後的 sensor values

#### Scenario: Gateway declares more than 16 nodes
- **WHEN** `0x63` payload 宣告超過 16 個 nodes
- **THEN** parser 最多只會輸出前 16 個 node blocks 的量測資料

#### Scenario: Final node block is incomplete
- **WHEN** 剩餘的 `0x63` payload bytes 無法提供完整的 34-byte node block
- **THEN** parser 會輸出在不完整 block 之前已解碼的 node blocks，且不會捏造遺漏的量測資料

### Requirement: 增量解析含 checksum 的 NMEA
NMEA parser SHALL 緩衝文字，直到有以 newline 結尾的 sentence 可用為止、驗證其 checksum，且僅為支援的 `GGA`、`RMC`、`VTG`、`GSA`、`GSV` 與 `SXT` sentence types 輸出 structured data。

#### Scenario: A supported valid sentence is complete
- **WHEN** 以 newline 結尾、受支援的 NMEA sentence 具有有效 checksum 與有效 field values
- **THEN** parser 會輸出一個 structured dictionary，識別 sentence type 與 decoded fields

#### Scenario: A sentence is incomplete
- **WHEN** parser call 在 NMEA sentence 的結尾 newline 之前結束
- **THEN** parser 會保留 partial sentence，且在完成前不為其輸出任何資料

#### Scenario: A sentence has an invalid checksum or unsupported type
- **WHEN** 完整 NMEA sentence 未通過 checksum validation，或其 sentence type 不在支援集合中
- **THEN** parser 不會為該 sentence 輸出 structured data，並會繼續接受後續輸入
