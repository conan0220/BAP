## 名詞定義

| 名詞 | 定義 |
|---|---|
| `punch_speed` | 拳頭速度分析使用的穩定 Analysis Type。 |
| Result schema | Desktop App 與 Backend 共同用來驗證拳頭速度 Result 欄位與型別的契約。 |
| 每拳明細 | `punches` array 中描述單一出拳之手別、拳序、時間與最高速度的 object。 |

## ADDED Requirements

### Requirement: punch_speed version 2 必須使用明確的 Result schema
`punch_speed` version 2 MUST 使用 `left_wrist` 與 `right_wrist` Input Roles，user-facing display name MUST 為「拳頭速度」。Result schema MUST 明確定義 `algorithm_version`、`left_punch_count`、`right_punch_count`、`total_punch_count`、`left_average_speed_mps`、`left_max_speed_mps`、`right_average_speed_mps`、`right_max_speed_mps` 與 `punches`，不得再只以 version 1 內容未定義的單一 `summary` object 代表成功結果。Backend MUST NOT 讓只認得 version 1 placeholder 的舊 Desktop App 執行 version 2。

#### Scenario: Backend 回傳完整拳頭速度 Result
- **WHEN** Executor 回傳所有必要欄位，且欄位型別、數值關係及每拳明細符合 `punch_speed` version 2
- **THEN** Backend 接受並保存 Result
- **AND** Desktop App 能用相同規格顯示結果

#### Scenario: Result 仍使用舊的 summary placeholder
- **WHEN** Executor 只回傳 `summary` 或缺少任一必要拳頭速度欄位
- **THEN** Backend 拒絕將 Result 標示為成功
- **AND** Desktop App 不把該內容顯示成有效的拳頭速度

#### Scenario: 舊 Desktop App 只要求 version 1
- **WHEN** Client 以 `punch_speed` version 1 建立 Analysis Job
- **THEN** Backend 回報該版本目前不可執行
- **AND** Backend 不以 version 2 Result 回覆 version 1 Client

#### Scenario: Result 內的摘要與明細不一致
- **WHEN** 總拳數不等於左右手拳數相加、拳數不等於明細數量，或摘要速度無法由明細重新得到
- **THEN** Result 契約驗證失敗
- **AND** 不保存為成功 Result
