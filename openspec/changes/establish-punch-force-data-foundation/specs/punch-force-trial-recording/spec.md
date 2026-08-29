## Purpose

定義可重複執行的離線 research trial，保存四個 nine-axis IMU streams、force plate ground truth，以及日後解讀量測資料所需的 context。

## ADDED Requirements

### Requirement: 完整的拳力 trial 擷取
系統 SHALL 將拳力 research trial 記錄為單一可識別單位，其中包含 force plate 的原始 force-time measurements，以及正好四個分別指定至右手腕、右手臂、左手臂與 force plate contact surface 的 IMU streams。

#### Scenario: 所有預期 sources 完成 trial
- **WHEN** 操作人員在四個已指定的 IMUs 與 force plate 均可用時記錄 trial
- **THEN** 系統會將全部五個 source streams 儲存於同一 trial identifier 下，並將 capture 回報為 complete

#### Scenario: 預期 source 無法使用
- **WHEN** trial 結束時缺少一個或多個預期 sources 的資料
- **THEN** 系統會保存任何已取得的 source data，但 SHALL NOT 將 trial 回報為完整擷取

### Requirement: 標準 nine-axis IMU measurements
每筆儲存的 IMU sample SHALL 揭露 source time、三軸 acceleration、三軸 angular velocity 與三軸 magnetic-field measurements，並附明確單位。Acceleration 與 angular-velocity fields SHALL 維持可個別存取，作為既有 analysis workflows 使用的 six-axis subset。

#### Scenario: 儲存 nine-axis sample
- **WHEN** recorder 從已指定的 IMU 收到有效 sample
- **THEN** 儲存的 sample 會包含 source timestamp，以及 acceleration、angular velocity 與 magnetic field 的全部三軸資料及其單位

#### Scenario: 讀取 six-axis subset
- **WHEN** downstream analysis 只讀取已記錄 IMU stream 的 acceleration 與 angular-velocity fields
- **THEN** 其可取得這六軸資料，而不要求以 magnetic-field values 作為 algorithm inputs

### Requirement: Raw source 保存
系統 SHALL 保存接收到的 IMU 與 force plate measurements 及其 source timestamps，不得因 filtering、interpolation、time alignment、unit conversion 或 derived-metric calculation 而覆寫。

#### Scenario: 產生 derived trial outputs
- **WHEN** 系統對齊或驗證已記錄的 trial
- **THEN** 原始 source measurements 仍會維持不變，並可與 derived outputs 一併取得

### Requirement: 可重現的 trial metadata
系統 SHALL 將每次 trial 與相關 metadata 建立關聯；metadata 應識別 participant pseudonym、session 與 trial identifiers、sensor-to-placement assignments、device identifiers、sensor orientation descriptions、設定的 sampling settings、coordinate 與 unit conventions、recording start 與 end times，以及 data-schema 與 recorder versions。

#### Scenario: 檢查已記錄的 trial
- **WHEN** 研究人員開啟已完成或不完整的 trial
- **THEN** 研究人員可判斷每個 stream 由哪個 device 產生、安裝位置與方式、設定方式，以及產生該記錄的 schema 與 recorder versions

### Requirement: Force plate ground-truth 保存
系統 SHALL 儲存 force plate 的原始 timestamped measurement channels 及其 physical units，以及該 trial 所提供的 calibration 或 conversion information。

#### Scenario: 記錄 force plate measurements
- **WHEN** force plate 在 trial 期間提供 measurements
- **THEN** 系統會在該 trial identifier 下保存原始 measurement sequence、timestamps、channel identities、units 與適用的 calibration information
