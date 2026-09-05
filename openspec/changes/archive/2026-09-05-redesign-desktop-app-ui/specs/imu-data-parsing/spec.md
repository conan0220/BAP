## 名詞定義

| 名詞 | 定義 |
|---|---|
| frame | 一筆通過 CRC 檢查並能解析為感測資料的 ANROT 二進位封包。 |
| `AnrotFrame` | Parser 為一筆 frame 建立的 Python 資料物件。 |
| 獨立物件 | 不會因為後續 frame 被解析而一起改變內容的資料物件。 |

## MODIFIED Requirements

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
