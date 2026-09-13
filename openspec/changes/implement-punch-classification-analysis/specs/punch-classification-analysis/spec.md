## 名詞定義

| 名詞 | 定義 |
|---|---|
| 拳種辨識 | 根據持靶人左右手拳靶背面的 IMU 資料，辨識拳擊手打出的拳種。 |
| 持靶人手別 | IMU 實際安裝在持靶人左手或右手拳靶的位置。 |
| 拳擊手手別 | 分析結果所描述的出拳者左手或右手，與持靶人手別分開定義。 |
| 同步 Frame | 來自同一個無線接收器 packet，且可由共同識別與裝置時間配對的兩顆 IMU Frames。 |
| 出拳區段 | Segmentation 判定為一次完整出拳的連續資料範圍。 |
| 模型信心 | Classifier 對分類結果輸出的信心數值，不代表已證明的實際準確率。 |
| Model Bundle | 一個版本的拳種辨識模型及其欄位、正規化、標籤與完整性資訊。 |

## Purpose

讓 user 能在 Desktop App 使用同一個無線接收器下、安裝於持靶人左右拳靶背面的兩顆 IMU 完成測量，並由 Backend 回傳六種拳種的數量及依時間排列的每拳明細。

## ADDED Requirements

### Requirement: 拳種辨識必須使用持靶人左右拳靶的兩顆無線 IMU
`punch_classification` version 2 MUST 各使用一份綁定至 `holder_left_pad` 與 `holder_right_pad` 的 Common IMU CSV。兩個來源 MUST 是同一個 Port、同一個 Group ID、同一個無線接收器資料流中的不同 Node ID，且兩個 Roles MUST NOT 綁定同一份 CSV。

#### Scenario: user 分配同一個 Gateway 下的兩顆 IMU
- **WHEN** user 將同一個 Port 與 Group ID 下的兩個不同 Node 分別選為持靶人左手與右手拳靶
- **THEN** Desktop App 允許 user 進入正式錄製
- **AND** Session Metadata 保存兩個 Roles 與實際 CSV IDs 的對應

#### Scenario: user 選擇不同 Gateway 的 IMU
- **WHEN** 左右拳靶來源的 Port 或 Group ID 不同
- **THEN** Desktop App 以白話說明兩顆 IMU 必須使用同一個無線接收器
- **AND** 不允許開始正式錄製

#### Scenario: user 對左右拳靶選擇同一個 Node
- **WHEN** `holder_left_pad` 與 `holder_right_pad` 指向相同 Node 或相同 CSV
- **THEN** Desktop App 拒絕該分配
- **AND** Backend 也拒絕執行該 Analysis Job

### Requirement: Desktop App 必須清楚引導 IMU 安裝與左右分配
Desktop App MUST 在正式錄製前，以文字清楚區分「持靶人左手拳靶 IMU」、「持靶人右手拳靶 IMU」與結果中的「拳擊手左／右手」，並 MUST 顯示符合模型版本的安裝位置及方向提示。user MUST 明確確認安裝與分配後才能開始錄製。

#### Scenario: user 準備進行拳種辨識
- **WHEN** Desktop App 完成 Port 掃描並顯示可用 Nodes
- **THEN** 畫面分別要求 user 指定持靶人左手與右手拳靶 IMU
- **AND** 畫面說明結果中的左右拳是拳擊手手別
- **AND** 畫面顯示 IMU 安裝位置與方向提示

#### Scenario: user 尚未完成安裝確認
- **WHEN** 兩個 Roles 已分配但 user 尚未確認安裝位置及方向
- **THEN** Desktop App 不允許開始正式錄製

### Requirement: Backend 必須先驗證並同步雙 IMU 資料
Backend MUST 驗證兩份 CSV 的 schema、必要 sensor 欄位、來源關係、取樣率及共同資料範圍，並 MUST 以同一 Gateway packet 所保留的共同識別與裝置時間建立同步 Frames。無法得到足夠且一致的同步資料時，Analysis Job MUST 失敗，不得以列號硬配、補零或沿用前一次資料假裝分析成功。

#### Scenario: 左右 CSV 含有足夠同步 Frames
- **WHEN** 兩份 CSV 中有足夠資料列具有相同 `packet_index` 與相容的 `device_time_ms`
- **THEN** Backend 只使用通過同步驗證的 Frames 建立模型輸入
- **AND** 保留每個模型輸入 Frame 對應的 Session 時間

#### Scenario: 左右 CSV 無法同步
- **WHEN** 兩份 CSV 來自不同資料流、共同 Frames 不足或裝置時間互相矛盾
- **THEN** Analysis Job 標示為失敗
- **AND** Desktop App 顯示需要重新檢查連線與錄製的白話訊息

#### Scenario: 必要 sensor 欄位缺少或不是有效數值
- **WHEN** 模型需要的 acceleration、gyroscope、magnetometer、姿態或 Quaternion 資料缺少或無效
- **THEN** Backend 不以零值代替必要資料
- **AND** Analysis Job 標示為失敗

### Requirement: Backend 必須辨識六種拳種並提供可追查的每拳結果
成功分析 MUST 將每個有效出拳區段分類為 `left_jab`、`right_jab`、`left_hook`、`right_hook`、`left_upper` 或 `right_upper`，並 MUST 回傳總拳數、六種拳數、演算法版本與依開始時間排列的每拳明細。每筆明細 MUST 能追查到該次 Session 的開始與結束時間，且 MUST 將模型輸出的分數標示為 `confidence`。

#### Scenario: Session 包含多種有效出拳
- **WHEN** Backend 在有效同步資料中找到並分類多個出拳區段
- **THEN** Result 依時間列出每一拳的拳種、開始時間、結束時間與模型信心
- **AND** 六種拳數及總拳數可由明細重新計算

#### Scenario: Session 沒有偵測到出拳
- **WHEN** 兩份輸入資料品質有效，但正式錄製期間沒有有效出拳區段
- **THEN** Analysis Job 可以成功完成
- **AND** 總拳數及六種拳數都是零
- **AND** `punches` 為空陣列

#### Scenario: 模型信心偏低
- **WHEN** Classifier 仍將有效出拳區段分類為六種拳種之一，但該分類的 `confidence` 偏低
- **THEN** Backend 保留實際模型信心
- **AND** Desktop App 不將該數值稱為準確率

### Requirement: Desktop App 必須顯示拳種摘要與依時間排列的明細
Desktop App MUST 在 Result 通過 version 2 契約後，顯示總拳數、左／右刺拳、左／右鉤拳、左／右上鉤拳的數量及每拳時間明細。畫面 MUST 使用繁體中文顯示拳種，並 MUST 提供既有「重新測量」操作。

#### Scenario: Backend 回傳有效 Result
- **WHEN** `punch_classification` Analysis Job 完成且 Result 通過契約驗證
- **THEN** Desktop App 顯示總拳數與六種拳種統計
- **AND** user 能查看依時間排列的每拳明細
- **AND** user 能按下「重新測量」回到 Port 檢測與 IMU 分配階段

#### Scenario: Backend 回傳分析失敗
- **WHEN** Backend 回報資料品質、模型或輸入關係錯誤
- **THEN** Desktop App 顯示不包含內部路徑或 stack trace 的白話錯誤
- **AND** 不顯示猜測或前一次的拳種結果

### Requirement: 模型版本與驗證範圍必須可以辨認
每個成功 Result MUST 包含穩定的 `algorithm_version`，讓相同輸入可以追查所使用的模型版本。模型轉換後的輸出 MUST 以固定資料與原始可信任模型比對；文件及 UI MUST NOT 將交接實驗結果宣稱為所有 user、IMU 型號、安裝方向或環境下的保證準確率。

#### Scenario: 相同模型版本重複分析相同輸入
- **WHEN** 相同 Backend 環境使用相同 `algorithm_version`、CSV 與 Analysis Specification 重複分析
- **THEN** 系統產生相同的出拳區段、拳種與數量

#### Scenario: 部署轉換後的模型
- **WHEN** Candidate Artifact 使用部署格式的模型分析固定回歸資料
- **THEN** 其出拳區段與拳種結果符合該模型版本定義的原始模型容許差異
- **AND** CI 在不符合時阻止該 Candidate 進入部署流程
