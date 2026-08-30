## 名詞定義

| 名詞 | 定義 |
|---|---|
| 目前版本 | user 電腦上已安裝的 Desktop App 版本。 |
| 最新版本 | 遠端後端回報，目前適用於 user 作業系統的最新公開版本。 |
| 更新檢查 | Desktop App 啟動後，比較目前版本與最新版本的背景流程。 |
| 更新提示 | 發現新版時顯示的版本與下載操作，不會自動安裝。 |
| 更新資訊 | 最新版本號、適用作業系統、下載位置及必要的完整性資訊。 |

## Purpose

讓 Desktop App 在啟動後自動得知是否有新版，並用不打斷登入或本機 IMU 操作的方式通知 user，由 user 自己決定是否下載更新。

## 更新檢查流程

```mermaid
flowchart TD
    START[Desktop App 啟動] --> CHECK[背景要求更新資訊]
    CHECK --> RESULT{檢查結果}
    RESULT -->|已是最新| QUIET[不打斷 user]
    RESULT -->|發現新版| NOTICE[顯示版本與下載操作]
    RESULT -->|連線失敗| CONTINUE[顯示簡短狀態並繼續使用]
    NOTICE --> USER{user 決定}
    USER -->|下載| DOWNLOAD[開啟受支援版本下載位置]
    USER -->|稍後| CONTINUE
```

## ADDED Requirements

### Requirement: App 啟動時在背景檢查更新
Desktop App MUST 在每次啟動後透過 HTTPS 要求適用於目前作業系統的更新資訊，且更新檢查不得阻擋登入、主畫面或本機 IMU 功能。

#### Scenario: 更新服務正常回應
- **WHEN** Desktop App 啟動且遠端後端成功回傳更新資訊
- **THEN** Desktop App 比較目前版本與最新版本
- **AND** user 可以在檢查期間繼續操作 App

#### Scenario: 更新服務無法連線
- **WHEN** Desktop App 啟動但無法取得更新資訊
- **THEN** Desktop App 顯示不影響操作的簡短更新檢查狀態
- **AND** Desktop App 不因更新檢查失敗而阻擋登入或本機 IMU 功能

### Requirement: 發現新版時由 user 決定是否下載
當最新版本高於目前版本時，Desktop App MUST 顯示目前版本、最新版本及下載操作；不得在未取得 user 操作的情況下自動下載或安裝。

#### Scenario: 發現適用的 Windows 新版
- **WHEN** 遠端後端回報的 Windows 最新版本高於目前版本
- **THEN** Desktop App 顯示更新提示、目前版本、最新版本及「下載更新」操作
- **AND** user 可以選擇稍後處理

#### Scenario: user 選擇下載更新
- **WHEN** user 在更新提示中選擇「下載更新」
- **THEN** Desktop App 開啟遠端後端提供且適用於目前作業系統的 HTTPS 下載位置
- **AND** Desktop App 不自行執行安裝程式

### Requirement: 沒有新版時不打斷 user
當目前版本等於或高於遠端後端回報的最新版本時，Desktop App MUST 將狀態視為已是最新版本，且不得顯示要求 user 處理的彈出視窗。

#### Scenario: 已安裝最新版本
- **WHEN** 目前版本等於最新版本
- **THEN** Desktop App 不顯示需要 user 回應的更新提示
- **AND** App 可以在非阻擋位置顯示「已是最新版本」

### Requirement: 更新資訊必須對應作業系統
遠端後端 MUST 只把具有可用下載位置的版本回報為該作業系統的最新版本，Desktop App MUST 拒絕開啟不適用於目前作業系統的更新下載位置。

#### Scenario: Windows App 要求更新資訊
- **WHEN** Windows Desktop App 要求更新資訊
- **THEN** 遠端後端回傳 Windows 版本資訊與 Windows 安裝檔下載位置

#### Scenario: 更新資訊缺少適用下載位置
- **WHEN** Desktop App 收到的更新資訊沒有目前作業系統可用的 HTTPS 下載位置
- **THEN** Desktop App 不顯示可執行的「下載更新」操作
- **AND** Desktop App 將這次更新檢查顯示為無法取得有效更新資訊

