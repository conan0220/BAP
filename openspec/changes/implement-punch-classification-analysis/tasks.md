## 名詞定義

| 名詞 | 定義 |
|---|---|
| Conversion test | 比較原 PyTorch checkpoint 與 ONNX 模型輸出的測試。 |
| Contract test | 驗證 Desktop App 與 Backend 對 version 2 輸入及 Result 有相同理解的測試。 |
| Regression test | 使用固定輸入與預期結果，確認模型或整合程式沒有意外改變的測試。 |
| API E2E | 透過真實 HTTP 上傳 Session、執行分析並取得 Result 的端到端測試。 |
| Artifact E2E | 從 Candidate Artifact 安裝或解壓後執行，不直接使用 repository source 的端到端測試。 |
| Hardware test | 使用一個無線接收器、兩顆 IMU 與左右拳靶進行的人工驗證。 |

## 1. 交接模型與資料確認

- [x] 1.1 以 `許明騏交接/Code/README_HANDOVER_REPRODUCE.md`、`許明騏交接/Code/essay/README_REPRODUCE.md` 與最終程式確認 canonical Segmentation／Classification checkpoints、模型架構、正規化資料、feature 順序、六種 label 順序及檔案 SHA-256，並記錄來源版本。
- [x] 1.2 執行交接提供的 inference-only reproduction，保存原 PyTorch 模型對固定輸入的 logits、probabilities、segments、labels 與交接摘要，確認本機可重現後才開始轉換。
- [x] 1.3 由原作者紀錄或左右拳種已知資料確認研究模型 `Node1`／`Node2` 對應的持靶人手別；分別測試兩種排列並保存證據，未確認以前不得啟用 Production Executor。
- [x] 1.4 確認 IMU 在左右拳靶背面的安裝位置、軸向與不可互換限制，整理成 Desktop 可顯示的白話文字及圖示需求。
- [ ] 1.5 確認可加入公開 repository 的去識別化測資範圍；未取得確認時讓完整「許明騏交接」資料夾、論文、簡報與原始資料維持 untracked。

## 2. Production Model Bundle

- [x] 2.1 建立可信任的 `tools/ml/convert_punch_classification_models.py`，明確要求 checkpoint 路徑與 Node role mapping，不接受未指定的左右手猜測。
- [x] 2.2 將 Segmentation 與 Classification checkpoints 轉成 ONNX，輸出 `segmentation.onnx`、`classifier.onnx`、`normalization.npz` 與 `manifest.json`，並在 manifest 記錄演算法版本、checksums、features、labels、400 Hz、384／128 window、20-frame minimum、96-frame resample 與 Role mapping。
- [x] 2.3 加入 Conversion tests，比較 PyTorch 與 ONNX 的 Segmentation／Classification 中間輸出，並確認最終出拳區段、順序與六種拳種完全一致或落在明確的數值容許差異內。
- [x] 2.4 加入 Bundle loader 與 checksum／shape／版本驗證測試，確認檔案被修改、缺少、label 順序錯誤或 normalization shape 錯誤時 Backend 不會啟動該 Executor。
- [x] 2.5 將 CPU `onnxruntime` 與必要 `numpy` dependency 加入 Backend 安裝範圍，確認 Desktop Installer 不包含 PyTorch、ONNX Runtime 或研究用工具。

## 3. Analysis Contract

- [x] 3.1 在共用 Analysis Specification 新增可執行的 `punch_classification` version 2，使用 `holder_left_pad` 與 `holder_right_pad`，且不要求額外 Analysis Parameters；保留 version 1 placeholder 不變。
- [x] 3.2 實作 version 2 Result schema，驗證 `algorithm_version`、`total_punch_count`、六個固定 `counts_by_type` 及每拳的 index、type、開始／結束時間與 `0.0`～`1.0` confidence。
- [x] 3.3 加入 Contract tests，涵蓋有效 Result、舊 `summary`、缺少欄位、未知拳種、無效 confidence、拳序不連續、時間錯誤，以及總拳數／分類摘要／明細不一致。
- [x] 3.4 加入 version compatibility tests，確認 version 1 Client 不會收到 version 2 Result，且只有 Backend 註冊 version 2 Executor 時新版 Desktop 才能開始測量。

## 4. 雙 IMU 輸入與同步

- [x] 4.1 建立拳種辨識 Input validator，確認兩份 descriptor 都是無線來源、Port 與 Group ID 相同、Node ID 及 CSV ID 不同，並將違規情境轉成安全的白話錯誤。
- [x] 4.2 建立同步器，以 `(packet_index, device_time_ms)` 配對左右 CSV，保留共同 `elapsed_us`，並拒絕重複 key、時間倒退、裝置時間矛盾或不同資料流。
- [x] 4.3 實作 400 Hz、至少 384 個同步 Frames、至少 95% 配對率及必要欄位品質檢查；缺值、非有限值或配對不足時不得補零或依 row number 硬配。
- [x] 4.4 實作 manifest-driven Role adapter，依已確認 mapping 將 `holder_left_pad`／`holder_right_pad` 放入模型 Node slots，建立每顆 16 欄、合計 32 欄的 Segmentation matrix。
- [x] 4.5 加入 source-level tests，涵蓋正常同步、掉包、CSV 起訖時間不同、不同 Gateway、相同 Node、左右對調、重複 packet、缺少欄位、低取樣率、配對率不足及最小有效資料。

## 5. Segmentation 與 Classification

- [x] 5.1 實作 batch sliding-window Segmentation inference，使用 window 384、stride 128，將重疊 probabilities 平均回原 Frame timeline。
- [x] 5.2 實作最終交接版本的 Segmentation 後處理：連續 positive Frames 形成區段、移除少於 20 Frames 的區段，並加入測試證明未執行論文舊版 gap merge／Gmax。
- [x] 5.3 實作 Classification 前處理，完整重現 `gravity_quat_add`、左右 IMU acceleration／gyroscope 12 欄選取、區段重採樣為 96 Frames 及正規化。
- [x] 5.4 實作 ONNX Classifier inference，固定六種 label 順序，將最高 probability 保存為 `confidence`，不自行新增 unknown threshold。
- [x] 5.5 依同步 Frame 對應的 `elapsed_us` 建立每拳開始與結束時間，依時間排序、建立連續拳序並計算六種拳數與總拳數。
- [x] 5.6 加入演算法 source-level tests，涵蓋六種拳種、連續出拳、無出拳、少於 20 Frames、低 confidence、相同輸入的決定性結果及 Result 摘要一致性。
- [x] 5.7 將模型、輸入或資料品質錯誤轉成穩定 error code 與安全訊息，測試 Result 不包含 checkpoint 路徑、stack trace 或其他 Backend 內部資訊。

## 6. Backend Session Flow

- [x] 6.1 建立並註冊 `punch_classification` version 2 Executor，從既有 Session repository 取得兩份原始 CSV，不建立新的上傳 API 或逐 Frame Database table。
- [x] 6.2 讓 Executor 依序完成 descriptor 驗證、同步、Role adaptation、Segmentation、Classification 與 Result contract 驗證，失敗時保留 Backend 已接收的原始 CSV。
- [x] 6.3 加入 Backend service tests，驗證有效雙 IMU Session、零拳 Session、不同 Gateway、相同 Node、資料不足、模型缺少及 version mismatch 的 Job 狀態與安全錯誤。
- [x] 6.4 加入真實 HTTP API E2E，以兩份 Common IMU CSV 建立 Session、上傳、等待 `pending`／`processing`／`completed` 並取回 version 2 Result。
- [x] 6.5 加入 API E2E failure cases，確認無效來源或模型輸入不會保存成功 Result，user 也無法查詢其他 user 的 Session、CSV 或分析結果。

## 7. Desktop 拳種辨識流程

- [x] 7.1 將「拳種辨識」從待開發項目改為要求 `punch_classification` version 2；Backend 沒有 Executor 或只支援 version 1 時保持不可開始並顯示白話原因。
- [x] 7.2 建立持靶人左手／右手拳靶 IMU selectors，只允許同一 Port、同一 Group ID 下的兩個不同無線 Node，並以 Qt tests 驗證不同 Gateway、同一 Node 與缺少 Role 都不能開始。
- [x] 7.3 在錄製前顯示安裝位置、方向與左右定義，要求 user 明確確認；加入鍵盤操作、最小視窗、自適應排版及未確認不能開始的 Qt tests。
- [x] 7.4 沿用既有 Session duration、錄製、來源中斷、上傳重試與 Backend polling，確認兩份 CSV 的 Input Bindings 分別使用 `holder_left_pad` 與 `holder_right_pad`。
- [x] 7.5 建立 Result view，顯示總拳數、左／右刺拳、左／右鉤拳、左／右上鉤拳統計，以及依時間排列的拳序、拳種、開始／結束時間與「模型信心」。
- [x] 7.6 加入 Result Qt tests，涵蓋有效多拳、零拳、低模型信心、無效 Result、Backend failure、上一個 Result 不殘留及「重新測量」會重新掃描 Port 與分配 IMU。
- [x] 7.7 依專案發版規則提升 Desktop `VERSION`，確認 App runtime、Installer 與更新檢查仍只使用同一個 Desktop 版本來源。

## 8. Regression Fixtures、文件與 Artifact

- [ ] 8.1 將經授權且去識別化的最小資料轉為 BAP Common IMU CSV 與 Metadata，建立六種拳種、連續出拳及無出拳的固定 expected Result；不得加入未獲確認的交接資料。
- [x] 8.2 建立 `docs/model-cards/punch-classification-v1.md`，記錄模型來源、兩階段架構、32／12 features、取樣率、安裝限制、交接 reproduction metrics、非 subject-independent 限制及 confidence 不等於準確率。
- [ ] 8.3 更新 Backend package 與 Artifact build，明確包含兩個 ONNX、normalization 與 manifest，並測試解壓後 Bundle 完整、checksum 正確且研究 checkpoint／資料集沒有被打包。
- [x] 8.4 更新開發者 README 或既有 guide，說明如何在可信任環境轉換模型、執行 parity／regression tests，以及為何不得直接部署整個交接資料夾。

## 9. 完整自動驗證

- [x] 9.1 執行格式、型別與完整 pytest suite，修正本 Change 造成的 regression，但不修改 user PowerPoint、vendor material 或完整「許明騏交接」資料夾。
- [x] 9.2 執行 OpenSpec strict validation，確認每個 Scenario 都由 contract、source-level、API E2E、Artifact E2E 或 Hardware test 覆蓋。
- [ ] 9.3 在 CI 的 Windows Runner 從 source 啟動真實 Backend，讓 Desktop API E2E 完成拳種辨識 Session flow，並確認失敗時上傳 Backend、Desktop 與 model logs。
- [ ] 9.4 在 Candidate Windows Runner 從 Backend Artifact 啟動服務，以固定雙 IMU fixtures 完成 Artifact E2E，確認 Model Bundle 可載入、version 2 可查詢且結果符合原模型 reference outputs。
- [x] 9.5 確認 CI 與 CD scope detection 會把 Model Bundle、Backend Executor、共用契約或拳種辨識 Desktop 改動送入正確的 Candidate build、Backend deploy 與 Desktop Release 流程。

## 10. 實際 IMU 人工驗證

- [ ] 10.1 使用一個無線接收器與兩顆依指引安裝的 IMU，確認 Desktop 能辨認同一 Group 的兩個 Nodes、完成左右拳靶分配、錄製、上傳並取得 Result。
- [ ] 10.2 以左右拳種已知的動作驗證持靶人 Role mapping 與拳擊手手別沒有混淆；交換左右 Roles 時測試必須能發現結果改變，避免錯誤 mapping 靜默通過。
- [ ] 10.3 分別測試左／右刺拳、左／右鉤拳與左／右上鉤拳，確認六種名稱、總拳數、分類統計、時間順序與模型信心能正常顯示；本項不把單次人工結果宣稱為整體準確率。
- [ ] 10.4 測試包含多種拳的連續組合、沒有出拳、提前結束、錄製中 Node 中斷、重新測量及 Backend 不可用，確認 UI 不偽造結果且能回復到可再次操作的狀態。
- [ ] 10.5 依正確方向、旋轉方向及左右 IMU 互換進行對照，確認安裝錯誤會被操作指引或驗證流程辨認，並將已確認的實體安裝方式更新至 model card。
