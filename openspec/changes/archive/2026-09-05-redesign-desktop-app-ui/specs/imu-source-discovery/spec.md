## 名詞定義

| 名詞 | 定義 |
|---|---|
| IMU 來源 | 本次三秒探索找到的一顆可用 IMU；有線來源以 Port 識別，無線來源以 Port、Group ID 與 Node ID 一起識別。 |
| IMU 位置 | 測量項目要求放置 IMU 的身體或器材位置。 |
| IMU 分配 | user 把一顆探索到的 IMU 指定給一個 IMU 位置。 |
| 有效分配 | 每個必要位置都有一顆可用 IMU，且同一項目中沒有重複使用同一顆 IMU。 |
| 手把背面 | 持把人握住的拳靶或手把背面，用來安裝拳種辨識需要的 IMU。 |

## ADDED Requirements

### Requirement: user 必須依測量項目需要分配 IMU 來源
Desktop App MUST 在三秒探索完成後，依目前拳擊測量項目顯示所需的 IMU 位置，並讓 user 為每個位置各自選擇一顆可用 IMU；同一顆 IMU MUST NOT 同時分配給同一項目的兩個位置。

#### Scenario: 設定出拳次數的 IMU
- **WHEN** user 進入出拳次數且三秒探索找到可用來源
- **THEN** Desktop App 顯示「左手腕」與「右手腕」兩個 IMU 位置
- **AND** user 可以分別為兩個位置選擇不同的 IMU

#### Scenario: 設定出拳速度的 IMU
- **WHEN** user 進入出拳速度且三秒探索找到可用來源
- **THEN** Desktop App 顯示「左手腕」與「右手腕」兩個 IMU 位置
- **AND** user 可以分別為兩個位置選擇不同的 IMU

#### Scenario: 設定出拳軌跡的 IMU
- **WHEN** user 進入出拳軌跡且三秒探索找到可用來源
- **THEN** Desktop App 顯示「左手腕」與「右手腕」兩個 IMU 位置
- **AND** user 可以分別為兩個位置選擇不同的 IMU

#### Scenario: 設定拳種辨識的 IMU
- **WHEN** user 進入拳種辨識且三秒探索找到可用來源
- **THEN** Desktop App 顯示持把人的「左手把背面」與「右手把背面」兩個 IMU 位置
- **AND** user 可以分別為兩個位置選擇不同的 IMU

#### Scenario: user 將同一顆 IMU 分配給兩個位置
- **WHEN** user 在同一測量項目的兩個位置選擇相同 IMU 來源
- **THEN** Desktop App 顯示同一顆 IMU 不能重複分配的提示
- **AND** 「繼續」操作保持不可使用

#### Scenario: 可用 IMU 少於項目需求
- **WHEN** 三秒探索找到的不同 IMU 數量少於目前項目要求的數量
- **THEN** Desktop App 顯示已找到的可用來源
- **AND** Desktop App 說明可用 IMU 數量不足
- **AND** 「繼續」操作保持不可使用

### Requirement: 出拳力量配置未決定前不得繼續
Desktop App MUST 在出拳力量所需的 IMU 數量與位置尚未定案期間，顯示「IMU 配置待決定」，且 MUST NOT 顯示可提交的 IMU 分配或允許 user 繼續。

#### Scenario: user 進入出拳力量
- **WHEN** user 進入出拳力量且三秒探索完成
- **THEN** Desktop App 顯示出拳力量的 IMU 數量與位置尚未決定
- **AND** 畫面不要求 user 猜測應選擇哪些 IMU
- **AND** 「繼續」操作保持不可使用

## MODIFIED Requirements

### Requirement: 完成選擇後只顯示待開發
Desktop App MUST 在 user 為目前拳擊測量項目的所有必要位置完成有效分配後，才允許 user 繼續並顯示該項目「待開發」；系統不得繼續錄製拳擊資料或呼叫遠端後端上傳 IMU 資料。

#### Scenario: 完成所有必要位置的分配並繼續
- **WHEN** user 已為目前項目的所有必要位置選好不同的可用 IMU，並執行「繼續」
- **THEN** Desktop App 顯示目前拳擊測量項目「待開發」
- **AND** 三秒探索資料在不再需要後從本機暫存中清除
- **AND** 遠端後端沒有收到探索資料

#### Scenario: 尚有位置未分配
- **WHEN** 目前項目仍有至少一個必要位置尚未選擇 IMU
- **THEN** 「繼續」操作保持不可使用
- **AND** Desktop App 不進入待開發結果頁面

## REMOVED Requirements

### Requirement: user 一次只能選擇一個 IMU 來源

**Reason**: 不同拳擊分析項目可能需要一顆以上的 IMU，原本只允許選擇單一來源的規則無法表達左、右手腕或持把人左右手把等位置需求。

**Migration**: 改用「user 必須依測量項目需要分配 IMU 來源」；原本的一顆 IMU 選擇介面改成由項目定義的一個或多個位置欄位。
