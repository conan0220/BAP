## Purpose

定義既有的增量解碼行為：將支援的 ANROT 二進位 frame 與含 checksum 的 NMEA 文字 sentence 轉換為結構化感測器量測資料。

## ADDED Requirements

### Requirement: 增量 ANROT 二進位 framing
Binary parser SHALL 緩衝任意分段的輸入 bytes、識別以 `0x5A 0xA5` 開頭的 frames、使用宣告的 payload length 等待完整 frame，且僅對計算出的 CRC-16 與接收 CRC 相符的 frames 輸出量測資料。

#### Scenario: A valid frame arrives in multiple chunks
- **WHEN** 有效 ANROT frame 的 bytes 分散在多次 parser calls 中提供
- **THEN** parser 會保留不完整的 bytes，並僅在取得 CRC 有效的完整 frame 後輸出 decoded frame

#### Scenario: Noise precedes a valid frame
- **WHEN** 有效 ANROT synchronization sequence 前存在無關 bytes
- **THEN** parser 會捨棄 synchronization sequence 之前的 bytes，並解碼有效 frame

#### Scenario: A complete frame has an invalid CRC
- **WHEN** 完整 ANROT frame 的計算 CRC 不等於接收的 CRC
- **THEN** parser 不會為該 frame 輸出任何量測資料，並會繼續接受後續輸入

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
