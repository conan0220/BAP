## 名詞定義

| 名詞 | 定義 |
|---|---|
| 3D 軌跡 Widget | Desktop Result view 中繪製三維出拳軌跡的控制項。 |
| Camera preset | 將 3D 圖切換到使用者、側面或上方等預先定義視角的操作。 |
| Fallback view | 電腦無法建立 3D 繪圖環境時顯示的文字與摘要替代畫面。 |

## ADDED Requirements

### Requirement: 互動式 3D Result view 必須可閱讀且可復原
出拳軌跡的 3D Widget MUST 隨內容區調整大小，且 MUST 在支援的最小視窗與高 DPI 環境中保留手別、拳次、摘要、Camera presets、重新測量及必要狀態文字。任何 Camera 操作 MUST 能透過「使用者視角」與「重設縮放」恢復到可辨認狀態。

#### Scenario: user 縮小視窗
- **WHEN** 出拳軌跡 Result view 的內容區縮小到支援的最小尺寸
- **THEN** 3D 圖使用剩餘可用空間
- **AND** 必要選擇器、摘要與操作沒有互相重疊
- **AND** 空間不足時 user 能透過捲動到達所有操作

#### Scenario: user 只使用鍵盤操作視角
- **WHEN** user 使用鍵盤依序移動焦點
- **THEN** user 能切換手別、拳次及所有 Camera presets
- **AND** 目前焦點具有可看見的提示

### Requirement: 3D 繪圖不可用時不得讓 App 無法使用
Desktop App MUST 處理 3D 繪圖環境建立失敗，不得因此閃退或遺失 Backend Result。Fallback view MUST 顯示可理解的說明與該拳的文字摘要，並 MUST 保留重新測量操作。

#### Scenario: 電腦無法建立 3D 繪圖環境
- **WHEN** Desktop App 無法建立必要的 3D 繪圖環境
- **THEN** App 保持開啟並顯示 3D 圖目前無法使用
- **AND** 畫面仍顯示手別、拳次、持續時間、路徑長度與最大位移
- **AND** user 仍可重新測量

