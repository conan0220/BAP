## 名詞定義

| 名詞 | 定義 |
|---|---|
| Research checkpoint | 「許明騏交接」保存的 PyTorch 模型檔。 |
| Segmentation | 從連續手靶 IMU 資料找出每次出拳的開始與結束區段。 |
| Classification | 將一個已找出的出拳區段辨識為六種拳種之一。 |
| Aligned accuracy | 只比較已成功配對的預測區段與人工標籤，不包含未配對區段的分類準確率。 |
| Model confidence | Classifier 對單一分類結果輸出的機率，不是產品準確率。 |

## 模型來源

本模型來自 repository 根目錄下未納入 Git 的「許明騏交接」資料。Production 只會保存經驗證的部署模型，不會打包整份交接資料、論文、簡報或訓練資料。

Canonical checkpoints：

| 用途 | 交接相對路徑 | SHA-256 |
|---|---|---|
| Segmentation | `許明騏交接/Code/essay/exp/second/model_best.pt` | `828050393CE5B18A20C302C6EAE168606BAB343B1990CB29D251993F5F8AC42F` |
| Classification | `許明騏交接/Code/essay/exp/first/lstm/lstm_classifier.pt` | `D6810D97F96DE49EBF5B02A4ABC19E85FE25E1A44DA8110BBD4DE9F78CE2D128` |

`許明騏交接/Code/essay/models/` 內的備份檔具有相同 SHA-256。

判定最終行為的主要文件：

- `許明騏交接/Code/README_HANDOVER_REPRODUCE.md`
- `許明騏交接/Code/essay/README_REPRODUCE.md`
- `許明騏交接/Code/essay/reproduce_inference_only.py`
- `許明騏交接/Code/essay/eval_end_to_end_seg_lstm.py`
- `許明騏交接/Code/essay/train_segmentation_window_random45.py`
- `許明騏交接/Code/essay/run_random30_all_models_experiment.py`

## 輸入與感測器配置

- 使用安裝於持靶人左右拳靶背面的兩顆 IMU。
- 原始研究資料以同一列保存 Node1 與 Node2。
- 原作者確認 `Node1 = 持靶人左手拳靶`、`Node2 = 持靶人右手拳靶`。
- 預期取樣率為 400 Hz。
- 安裝方式以原作者提供的 `許明騏交接/手把IMU配置位置.jpg` 為準：兩顆 IMU 都固定在拳靶背面的白色固定板中央；左右固定板與感測器不可互換、翻面或旋轉。
- Desktop App 在錄製前要求 user 確認上述配置，並清楚說明 Result 的左右手是拳擊手手別，不是持靶人手別。

## 模型架構

### Segmentation

- Model：TemporalConvNet，包含 dilated residual convolution blocks 與雙向 LSTM。
- Classes：2，分別為背景與出拳。
- Hidden size：16。
- LSTM hidden：32。
- Convolution layers：2。
- Dropout：0.2。
- Feature mode：`raw`。
- Window size：384 Frames。
- Stride：128 Frames。
- 正規化 shape：`1 × 32`。

每顆 IMU 使用 16 個 features，依序為 acceleration XYZ、gyroscope XYZ、magnetometer XYZ、Roll／Pitch／Yaw 與 Quaternion W／X／Y／Z；兩顆 IMU 合計 32 個 features。

最終後處理只會：

1. 將重疊視窗 probabilities 平均回原 Frame timeline。
2. 產生背景／出拳 binary label。
3. 將連續 positive Frames 形成一個區段。
4. 移除少於 20 Frames 的預測區段。

最終程式不執行論文舊版描述的額外 gap merge 或 Gmax。

### Classification

- Model：單層雙向 LSTM。
- Hidden dimension：96。
- Dropout：0.25。
- Sequence length：96 Frames。
- Acceleration mode：`gravity_quat_add`。
- 正規化 shape：`1 × 12`。

輸入為 Node1 與 Node2 各自的 acceleration XYZ 及 gyroscope XYZ，合計 12 個 features。出拳區段先執行交接程式定義的 Quaternion 重力處理，再重採樣為 `96 × 12`。

固定 label 順序：

1. `left_hook`
2. `left_jab`
3. `left_upper`
4. `right_hook`
5. `right_jab`
6. `right_upper`

背景或假動作不是 Classification class。每個被 Segmentation 接受的區段都會被分到六種拳種之一。

## 2026-09-12 本機 reproduction

依交接建議執行：

```text
python reproduce_inference_only.py
```

本機重新產生 `許明騏交接/Code/essay/exp/reproduce_inference_only/summary_all.json`，結果與交接文件一致：

| 實驗 | 結果 |
|---|---|
| 單次拳 LSTM Classification | 180 segments，accuracy `0.9666666667` |
| Segmentation | 103 files，count match `1.0`，Boundary F1@10 `0.5210355987`，Mean IoU `0.7115578479` |
| 原 IMU end-to-end | 103 files，aligned label accuracy `0.9722222222`，count match `1.0` |
| 新實體 IMU end-to-end | 60 files，aligned label accuracy `0.9111111111`，count match `1.0`，Boundary F1@10 `0.6888888889`，Mean IoU `0.8042185839` |

Reproduction 使用 CPU 執行。舊 Random Forest／XGBoost 模型載入時出現 library version warning，但完整輸出仍與交接摘要一致；BAP Production 只使用 Segmentation 與 LSTM Classification checkpoints。

## 限制

- Aligned accuracy 只評估已成功配對的區段，必須與 count、Boundary F1 及 Mean IoU 一起解讀。
- 交接測試不是專門設計的 subject-independent production evaluation。
- 資料只涵蓋有限受試者、固定感測器配置及固定安裝方式。
- 尚未證明其他 IMU 型號、取樣率、安裝方向、手靶材質或使用環境能維持相同結果。
- Node mapping 已由原作者確認；若固定板、感測器朝向或左右配置改變，必須建立新模型版本重新驗證。
- `confidence` 只是模型輸出，不可稱為產品準確率。
- 在確認資料公開授權前，不得把交接原始 CSV 加入公開 repository。
