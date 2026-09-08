## 名詞定義

| 名詞 | 定義 |
|---|---|
| Benchmark case | 一次經人工標記左右手拳數的 Shadow boxing 錄製資料。 |
| Ground Truth | user 實際完成並人工確認的左手、右手與總出拳次數。 |
| wireless receiver | 透過同一個無線接收器 Port 收集不同 Group ID／Node ID IMU 資料的連線方式。 |

## 用途

這個目錄保存已由開發者審查、可供出拳次數演算法開發與回歸測試使用的真實 Benchmark bundles。每個 ZIP 都包含一份 `metadata.json`，以及左、右手腕各一份 Common IMU CSV。

第一批資料全部使用 `COM6`、Group ID `1` 的兩顆無線 IMU：左手腕為 Node ID `0`，右手腕為 Node ID `1`。本批資料不包含有線 IMU。

## 已核准資料

| Session ID 前綴 | 錄製秒數 | 左手拳數 | 右手拳數 | 總拳數 |
|---|---:|---:|---:|---:|
| `d7a88d4e` | 10 | 5 | 5 | 10 |
| `362bf285` | 10 | 7 | 7 | 14 |
| `4ef96ab6` | 15 | 11 | 11 | 22 |
| `877a4a9c` | 10 | 10 | 0 | 10 |
| `d7230646` | 10 | 0 | 10 | 10 |

## 自動驗證

`tests/test_punch_count_benchmark_fixtures.py` 會逐一使用正式 Benchmark loader 解開並驗證 ZIP，包含 Metadata、Common IMU CSV schema、row count、檔案大小、SHA-256、左右手角色、Ground Truth 與無線來源資訊。
