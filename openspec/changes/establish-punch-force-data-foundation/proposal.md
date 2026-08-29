## 原因

拳力研究需要可信賴的訓練資料，將身體動作量測與 force plate ground truth 配對。現有 recorder 能擷取 IMU samples，但尚未定義可重複執行的離線 trial、將 force plate data 與 IMU data 一併保存、對齊來源，或回報某次記錄是否適合研究用途。

## 變更內容

- 為位於右手腕、右手臂、左手臂與 force plate contact surface 的四個 nine-axis IMUs，導入以 trial 為導向的離線記錄。
- 在同一 trial 中，將 force plate 的原始 force-time signal 記錄為 ground truth。
- 在不進行 destructive preprocessing 的情況下保存 source data，並記錄解讀與重現每次 trial 所需的 metadata。
- 將 IMU 與 force plate sources 對齊至共同 trial timeline，同時保留 source timestamps 與 alignment provenance。
- 評估記錄完整性、timing integrity、遺漏或重複的 samples 與 sensor saturation，並揭露產生的 quality findings，不在未告知的情況下修復 source data。
- 本變更不包含拳力預測、應用程式使用者介面、即時分析，以及拳種或軌跡演算法的整合。

## 能力

### 新增能力

- `punch-force-trial-recording`：擷取並保存一次離線 research trial，其中包含四個 nine-axis IMU streams、force plate ground truth，以及解讀該記錄所需的 metadata。
- `punch-force-time-alignment`：為具有獨立 timestamp 的 IMU 與 force plate measurements 產生可追溯的共同 trial timeline。
- `punch-force-data-quality`：評估並回報已記錄 trial 是否完整，且適合後續拳力研究。

### 修改能力

無。

## 影響

- 將 `anrot_imu_driver/` 下的 IMU recording workflow 從 gateway-oriented CSV output 擴充為 trial-oriented research capture。
- 導入拳擊 force plate 的 integration boundary；device protocol 與 connection details 仍待確認。
- 在 raw recordings 旁新增 versioned trial manifest 與 quality/alignment outputs。
- 需要針對記錄結構、time alignment、source preservation 與 quality reporting 的 automated tests。
- 不修改 `ANROT-IMU-v1.3.6-windows-x64/` 下的 vendor material。
