# 驗證紀錄

## 範圍

- 變更：`baseline-existing-imu-data-capabilities`
- 驗證方法：採用等效的書面審查，因為已安裝的 OpenSpec core profile 未提供驗證 skill
- 已審查能力：`imu-data-parsing`、`imu-device-communication` 與 `imu-data-recording`

## 完整性

- 收集了 58 個可個別識別的 pytest 案例。
- 針對三份 delta specs 中的所有 `#### Scenario` 標題執行 pytest Scenario 稽核。
- 稽核未發現未涵蓋的 Scenarios，也未發現未知的 Scenario markers。
- `tasks.md` 中的每項實作任務皆有對應的測試或驗證證據。

## 正確性

- Parser 特性描述測試：18 項通過。
- 裝置通訊特性描述測試：17 項通過。
- Recorder 特性描述測試：23 項通過。
- 含 branch coverage 的完整預設套件：58 項通過，整體 branch-aware coverage 為 82%。
- 嚴格 OpenSpec 驗證回報此變更有效。
- 測試描述既有 working tree 行為的特性，未變更任何 runtime source files。唯一的 runtime diff 仍是先前已存在的使用者修改：將預設記錄時間設為 10 秒。

## 一致性

- Proposal、三份 delta specs、設計決策、實作任務與測試 Scenario markers 描述相同的三項基準能力。
- `openspec/config.yaml` 建立全 repository 適用的可測試性與 Scenario-to-test 指引；本變更提供第一套具體測試基礎及其應用。
- 硬體行為、出拳分析、force plate 整合、新記錄格式與 runtime 修正仍不在本變更範圍內。
- 不存在未涵蓋的 Scenario、artifact 矛盾或實作阻礙。

## 命令

```text
D:\repos\BAP\.venv\Scripts\python.exe -m pytest tests --collect-only -q --scenario-spec-root openspec\changes\baseline-existing-imu-data-capabilities\specs
D:\repos\BAP\.venv\Scripts\python.exe -m pytest tests --scenario-spec-root openspec\changes\baseline-existing-imu-data-capabilities\specs --cov=anrot_imu_driver --cov-branch --cov-report=term-missing
C:\Users\user\AppData\Roaming\npm\openspec.cmd validate baseline-existing-imu-data-capabilities --type change --strict --no-interactive
```

## 結果

此變更已具備完整性、正確性與一致性，可進行封存審查。
