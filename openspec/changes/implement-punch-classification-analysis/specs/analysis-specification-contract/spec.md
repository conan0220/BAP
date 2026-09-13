## 名詞定義

| 名詞 | 定義 |
|---|---|
| `punch_classification` | 拳種辨識使用的穩定 Analysis Type。 |
| `holder_left_pad` | 綁定持靶人左手拳靶背面 IMU CSV 的 Input Role。 |
| `holder_right_pad` | 綁定持靶人右手拳靶背面 IMU CSV 的 Input Role。 |
| `punch_type` | 拳擊手單次出拳的分類結果。 |
| 模型信心 | Classifier 對單次分類結果輸出的 `0.0` 至 `1.0` 數值，不等於已驗證的準確率。 |

## ADDED Requirements

### Requirement: punch_classification version 2 必須使用明確的輸入與 Result schema
`punch_classification` version 2 MUST 使用 `holder_left_pad` 與 `holder_right_pad` 兩個必要 Input Roles，user-facing display name MUST 為「拳種辨識」，且 MUST 不要求額外 Analysis Parameters。Result schema MUST 定義 `algorithm_version`、`total_punch_count`、`counts_by_type` 與 `punches`，不得再以 version 1 內容未定義的 `summary` object 代表成功結果。Backend MUST NOT 讓只認得 version 1 placeholder 的舊 Desktop App 執行 version 2。

#### Scenario: Backend 回傳完整拳種辨識 Result
- **WHEN** Executor 回傳所有必要欄位，且欄位型別、數值關係及每拳明細符合 `punch_classification` version 2
- **THEN** Backend 接受並保存 Result
- **AND** Desktop App 能用相同規格顯示結果

#### Scenario: Result 仍使用舊的 summary placeholder
- **WHEN** Executor 只回傳 `summary` 或缺少任一必要拳種辨識欄位
- **THEN** Backend 拒絕將 Result 標示為成功
- **AND** Desktop App 不把該內容顯示成有效的拳種結果

#### Scenario: 舊 Desktop App 只要求 version 1
- **WHEN** Client 以 `punch_classification` version 1 建立 Analysis Job
- **THEN** Backend 回報該版本目前不可執行
- **AND** Backend 不以 version 2 Result 回覆 version 1 Client

### Requirement: punch_classification version 2 Result 必須維持摘要與明細一致
`counts_by_type` MUST 且只能包含 `left_jab`、`right_jab`、`left_hook`、`right_hook`、`left_upper` 與 `right_upper` 六個非負整數。`punches` 中每筆明細 MUST 包含從 1 連續增加的 `punch_index`、六種值之一的 `punch_type`、`start_elapsed_us`、`end_elapsed_us` 與介於 `0.0` 至 `1.0` 的 `confidence`。`total_punch_count` MUST 等於六種拳數總和及 `punches` 長度，每個分類的摘要數量也 MUST 等於對應明細數量。

#### Scenario: 摘要與每拳明細一致
- **WHEN** Result 的總拳數、六種分類數量、明細數量及明細時間都符合 version 2 契約
- **THEN** Backend 可以將 Result 保存為成功結果

#### Scenario: 摘要與每拳明細不一致
- **WHEN** 總拳數、任一分類數量、明細數量或拳序彼此不一致
- **THEN** Result 契約驗證失敗
- **AND** Backend 不保存為成功 Result

#### Scenario: 明細使用未知拳種
- **WHEN** 任一 `punch_type` 不是 version 2 定義的六種值之一
- **THEN** Result 契約驗證失敗
- **AND** Desktop App 不把未知值猜成任一支援拳種
