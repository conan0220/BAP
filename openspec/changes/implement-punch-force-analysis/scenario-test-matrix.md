## 名詞定義

| 名詞 | 定義 |
|---|---|
| Scenario test | 直接對應 delta spec 中一個 Scenario 的自動測試。 |
| Source-level test | 直接使用 repository 內程式碼執行的測試，不代表安裝檔或部署壓縮檔已驗證。 |
| Artifact E2E | 從正式 Candidate Artifact 安裝或解壓後，透過真實 HTTP 走完整流程的測試。 |
| Hardware test | 必須使用實體沙袋、無線接收器與兩顆 IMU 才能完成的人工測試。 |

## Scenario 與測試對應

| Capability | Scenario 範圍 | 測試位置 | 層級 |
|---|---|---|---|
| analysis-specification-contract | punch_force 規格、必要參數、Result 單位與關聯 | `tests/test_analysis_contracts.py`、`tests/backend/test_punch_force.py`、`tests/backend/test_punch_force_api.py` | Contract／API |
| desktop-app-shell | 五個項目入口、進入單一項目、punch_force version 1 與 Executor 可用 | `tests/desktop/test_punch_force_ui.py`、`tests/backend/test_analysis_registry.py` | Desktop／Backend |
| imu-source-discovery | 同一 Port 與 Group 的兩顆無線 IMU、不同 Gateway、有線來源 | `tests/desktop/test_desktop_ui_design.py` | Desktop |
| punch-force-analysis | 來源分配、參數、兩階段錄製、Packet 對齊、演算法、Result 與 warning | `tests/backend/test_punch_force.py`、`tests/backend/test_punch_force_api.py`、`tests/desktop/test_punch_force_ui.py`、`tests/desktop/test_punch_force_recording.py` | Backend／API／Desktop |

## 驗證指令

Scenario 名稱的完整性由 pytest 的 `--scenario-spec-root` 檢查。Source-level test 使用完整 pytest suite 驗證既有分析不會回歸。Candidate Artifact 建立後，仍須另外執行 Artifact E2E；實體沙袋準確性則必須由 Hardware test 驗證。

## 尚需人工完成

1. 將兩顆 IMU 固定在實體沙袋上方與下方，完成一次單次打擊流程。
2. 確認校正提示、力量結果、warning 與重新測量流程符合實際操作。
3. 本版沒有 Force Plate Ground Truth，因此只能視為 Prototype 的力學估算，不能當作精準力量儀器。
