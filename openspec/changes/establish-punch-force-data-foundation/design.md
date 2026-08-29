## 背景

動機與範圍請參閱 `proposal.md`。Repository 目前提供 Python serial parser 與 `record` command，可將最多 16 個 HI221 nodes 的資料寫成以 gateway 為導向、固定寬度的 CSV rows。緊湊型 `0x63` gateway frame 為每個 node 提供共用的 millisecond timestamp 與 nine-axis measurements。目前格式未描述 research trial、保存 force plate data、保留 alignment provenance，或產生 quality decision。

四個 HI221 nodes 可共用一個 Dongle，並以文件記載的最高 200 Hz deployment tier 運作；force plate 可能使用不同的 clock 與 sampling rate。其 connection protocol、timestamp semantics、channel layout 與 calibration representation 尚未記錄於 repository。

## 目標／非目標

**目標：**

- 讓 capture、alignment 與 validation 可分別重複執行。
- 保存 source evidence，使 parser、alignment 與 quality logic 能在不重做實驗的情況下修訂。
- 讓每個 derived timeline 與 quality decision 都可追溯至 versioned method 與 configuration。
- 提供穩定的 nine-axis research representation，且其 acceleration 與 angular-velocity columns 也能作為 six-axis subset 使用。
- 允許加入 force-plate-specific communication，且不與 trial format 或 quality rules 耦合。

**非目標：**

- 定義拳力 prediction target，或計算 peak force、impulse、power 等 labels。
- 為 model training 對出拳動作進行 filtering、resampling、segmentation 或 featurization。
- 將初始 capture protocol 泛化至指定的四個 IMU placements 以外。
- 在 trial workflow 通過驗證前取代既有、以 gateway 為導向的 `record` command。

## 決策

### 1. 將每次 trial 儲存為 versioned、self-contained bundle

Trial bundle 將作為 capture、processing、validation、transfer 與 recovery 的單位，包含：

```text
<trial-id>/
  manifest.json
  source/
    <verbatim IMU transport capture>
    <verbatim force-plate capture or lossless received samples>
  measurements/
    imu.csv
    force-plate.csv
  derived/
    alignment.json
  reports/
    quality.json
```

`manifest.json` 將包含 schema version、capture state、participant pseudonym、session 與 trial identifiers、source inventory、sensor placement 與 orientation descriptions、device 與 capture configuration、units 與 coordinate conventions、recorder version，以及 file checksums。Canonical IMU table 將為每個 node sample 使用一列，並具有明確的 acceleration、angular-velocity 與 magnetic-field columns，而不是重複固定的 16 組寬型 node groups。

Capture 將在 staging bundle 中進行。正常完成時會 finalize manifest 與 checksums。遭中斷或部分完成的 capture 仍可檢查，但會以 incomplete state finalize，不會遭到捨棄或表示為成功。

**考慮過的替代方案：** 不繼續使用單一 wide CSV，因為它會遺失 trial context、產生未使用的 columns，並讓 consumers 與最大 node count 耦合。不採用 database-first design，因為目前階段更需要可攜、可檢查且無須執行服務的 research trials。若資料規模有需要，日後可加入 Parquet 作為 derived research export。

### 2. 將 source adapters 與 trial coordinator 分離

Trial coordinator 將負責 trial lifecycle、metadata、host timing 與 output finalization。IMU 與 force plate adapters 將透過相同的 conceptual boundary 揭露 timestamped sample batches 與 source metadata，同時保留 device-specific payloads 與 diagnostics。

HI221 adapter 將重用既有 `0x63` parser，但新增 lossless source capture 與 long-form canonical output。Force plate adapter 將在其 protocol 確認後實作。若 force plate 提供 exported file 而非 live stream，則只要能驗證 identity 與 timing，adapter 可將該檔案匯入相同的 trial lifecycle。

**考慮過的替代方案：** 不將 force plate parsing 直接加入目前的 IMU recording loop，因為這會讓兩個獨立裝置耦合，並使 protocol changes 影響 trial storage 與 validation。

### 3. 記錄三個層級的時間證據

在可取得的情況下，每筆 sample 或 batch 將保留：

1. device 或 gateway 的 source timestamp；
2. coordinator 擷取的 host monotonic receive timestamp；
3. offline alignment 產生的 derived shared-trial timestamp。

同一 HI221 gateway 的 nodes 共用其 `gw_ts_ms` clock mapping。其他 gateways 與 force plate 會分別取得 mapping。當只有一個可靠 anchor 時，alignment 最初會將 clock 建模為 offset；當多個 anchors 提供 drift 證據時，則建模為 affine mapping。

如果 force plate 支援 hardware synchronization markers，將優先採用。否則，由 contact-surface IMU 測得的 impact event 與 force-time signal 將提供 offline alignment anchors。Alignment artifact 將儲存選取的 method、parameters、anchors、residual diagnostics、acceptance thresholds 與 method version。

Alignment 會指定 mapped timestamps，但不會 resample 或覆寫 measurement streams。後續 analysis 可選擇 interpolation strategy，而不變更 trial evidence。

**考慮過的替代方案：** 不僅使用 host arrival time，因為 serial 與 operating-system latency 可能變動。不以 aligned timestamps 取代 source timestamps，因為這會阻礙稽核與改良後的重新對齊。未選擇強制 hardware synchronization，因為 force plate 支援情況尚不明確。

### 4. 將 force-time signal 視為 ground-truth evidence，而非最終 prediction label

本變更會保存 force plate 的 original channels、units、timestamps 與 calibration evidence。Peak force、impulse、contact duration 及任何 composite power score 的定義，會在 measurement protocol 確認後，於後續著重演算法的變更中導入。

**考慮過的替代方案：** 不在 capture 期間計算單一 force label，因為這會過早嵌入尚未定案的科學定義，並可能迫使實驗重做。

### 5. 在 capture 與 alignment 後執行具確定性的品質驗證

Validation 將作為獨立的 offline operation，在 finalized 或 incomplete trial bundle 上執行。Rules 與 thresholds 會採用 versioned configuration，並記錄於 `quality.json`。Findings 將識別其 source、channel、time interval 或 sample count、severity 與 evidence。Aggregate disposition 將為 `pass`、`warning` 或 `fail`。

第一套 rule set 將涵蓋 source inventory、assignment、空白與過早終止的 streams、timestamp regression 與 duplication、observed sample rate 與 gaps、missing 或 invalid values、configured-range saturation，以及 alignment acceptance。Validation 絕不編輯 source layer。若後續 cleanup operation 建立 derivative，其 transformation provenance 必須另行記錄。

**考慮過的替代方案：** 不在 capture 期間修復 duplicates 與 gaps，因為這會掩蓋 recorder 與 device behavior，並使替代 cleanup policies 無法評估。

### 6. 研究身分維持 pseudonymous

Trial metadata 將要求 participant pseudonym，而非個人姓名或 contact information。所有 identity mapping 均位於 trial bundle 與本變更之外。

**考慮過的替代方案：** 不在 manifest 中儲存 personal identity，因為技術 dataset 不需要這些資訊，且會增加 privacy risk。

## 風險／取捨

- **[四 node HI221 deployment 受限於文件記載的 200 Hz tier]** → 在大規模收集前執行 pilot、記錄設定與觀察到的 rates，並將是否足以用於 force prediction 視為後續的實證決策。
- **[Impact dynamics 可能使 IMU saturation，或發生速度快於其 usable bandwidth]** → 記錄 configured ranges、偵測 saturation，並拒絕不適用的 trials，而不是推測 clipped peaks。
- **[Software alignment 可能無法達到 force research 所需精度]** → 保存所有 clock evidence、回報 residual error、透過 adapter boundary 支援 hardware markers，並讓未符合設定 acceptance criteria 的 trials 失敗。
- **[Force plate 附近的磁性干擾可能降低 magnetometer data 品質]** → 保存 nine-axis measurements 並回報 range 或 integrity findings；本變更不以 magnetometer-derived orientation 作為 capture 被接受的必要條件。
- **[Force plate protocol 可能未提供 source timestamps 或原始 raw payloads]** → 保存最接近 lossless 的可用 representation、擷取 host monotonic timing，並在 source 與 alignment metadata 中記錄限制。
- **[可攜式 CSV 與 JSON artifacts 比緊湊型 binary formats 使用更多儲存空間]** → 優先維持研究透明度；僅在資料量足以合理化時加入 derived columnar export。

## 遷移計畫

1. 確認並記錄初始 four-IMU hardware profile 與 force plate interface。
2. 新增 trial bundle schema、source-adapter boundary 與 deterministic fixture data，且不變更既有 `record` behavior。
3. 新增 HI221 trial adapter 與 force plate adapter，再分別進行驗證。
4. 對 captured fixtures 新增 offline alignment 與 quality reporting。
5. 執行 pilot captures，並在將 trials 視為 research-ready 前調整 versioned acceptance thresholds。
6. 保留既有 recorder 作為 rollback path，直到 trial workflow 通過 automated 與 hardware-in-the-loop verification。

## 待確認問題

- 可使用的 force plate model、connection protocol、channel layout、timestamp resolution、sampling rate、measurement range 與 calibration format 為何？
- Force plate 或 acquisition hardware 是否提供可與 IMU data 一併記錄的 trigger、synchronization pulse 或 clock signal？
- `right arm` 與 `left arm` 的確切 anatomical locations 為何？要如何在不同 sessions 間重現 mounting orientation？
- Pilot 最初應採用哪個 HI221 output rate、acceleration range、angular-velocity range 與 alignment acceptance thresholds？
