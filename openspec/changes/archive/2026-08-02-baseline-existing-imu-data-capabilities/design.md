## 背景

動機請參閱 `proposal.md`。已實作的 IMU 功能涵蓋命令列進入點、序列埠命令、ANROT 二進位與 NMEA parsers，以及依 gateway 分組的 CSV recorder。目前 repository 沒有自動化測試，也沒有主要 OpenSpec requirements。穩定的 HI221 事實與設定程序位於 `docs/` 下，但這些文件屬於證據與指引，而非產品 requirements。

Working tree 包含一項使用者變更，將記錄時間的預設值設為 10 秒。本基準必須保留該變更，不得在未告知的情況下改用 committed branch 的無限期預設值。

## 目標／非目標

**目標：**

- 建立能準確描述既有公開 IMU 行為的最小能力邊界集合。
- 為無須連接硬體即可驗證的行為加入具確定性的特性描述測試。
- 讓每個 OpenSpec Scenario 都可追溯到至少一個可識別的測試案例。
- 在封存基準前進行結構、可執行性與 change-level 驗證。
- 讓後續 proposal 能針對明確的基準辨識新增與修改內容。
- 明確呈現 implementation、documentation 與 proposed requirements 之間的任何不一致。

**非目標：**

- 在增加測試涵蓋率時重構 command 或 parser 內部實作。
- 在沒有使用者可見 contract 依賴的情況下，將意外的 implementation defects 視為期望的長期行為。
- 驗證需要連接硬體才能進行的電氣、無線、時間或吞吐量行為。
- 在具有代表性的基準測試存在之前，建立全域 coverage-percentage gate。
- 在本變更中導入 property-based testing。
- 為 tracked repository 中尚未實作的拳種辨識或出拳軌跡分析建立基準。

## 決策

### 1. 將基準分為三項使用者可觀察的能力

本基準使用 `imu-device-communication`、`imu-data-parsing` 與 `imu-data-recording`。這些邊界依循操作人員及 downstream code 可觀察的內容，而非逐一映照每個 Python module。

- Communication 涵蓋探索、即時監控與已儲存的裝置指令序列。
- Parsing 涵蓋不依賴序列硬體的增量二進位與 NMEA 解碼。
- Recording 涵蓋多連接埠命令及其 gateway-specific CSV artifacts。

**考慮過的替代方案：** 單一 `imu-driver` 能力遭到否決，因為後續 force-data 工作可能修改 recording，卻不會變更 command sending 或 protocol parsing。為每個 command 與 frame type 建立獨立能力也遭到否決，因為對目前系統而言粒度過細。

### 2. 將經驗證的 working-tree 行為視為基準

Requirements 源自目前 source 與可執行 examples，vendor references 僅用於解讀 data formats。未 commit 的 10 秒記錄預設值被明確納入，因為 repository 指引要求保留使用者目前的變更。

若特性描述發現 proposed requirement 與可執行行為不符，本基準變更將修正 requirement 或縮小其 Scenario 範圍，而不會為了讓期望性 requirement 通過而變更 runtime behavior。應修正的 defect 將建立獨立的後續變更。

**考慮過的替代方案：** 不採用 README 文字作為權威依據，因為其中未包含 recording command，且可能與 code 不一致。也不採用僅限 committed `HEAD` 的方式，因為這會捨棄使用者目前的變更。

### 3. 使用 pytest 在硬體邊界進行具確定性的特性描述

`pytest` 是共用 test runner。測試使用 pytest fixtures、parametrization、`tmp_path` 與 `monkeypatch`，並在明確的 fakes 更清楚時使用 `unittest.mock`。固定的 ANROT frames、含 checksum 的 NMEA sentences、fake serial ports、controlled clocks 與 temporary output directories，使測試不受連接硬體影響。

Test discovery 與 markers 在 `pyproject.toml` 中設定。至少以 `hardware`、`slow` 與 `dataset` markers 區分不適合快速預設套件的測試。基準套件維持為非硬體測試；未來的 hardware-in-the-loop tests 必須明確標記。`pytest-cov` 會將 branch coverage 作為診斷資訊回報，但本變更不導入任意的全域百分比門檻。若基於範例的 protocol fixtures 顯示輸入涵蓋不足，日後可再提出 property-based testing。

測試以可觀察的結果為目標：command output 與 exit behavior、command bytes 與順序、輸出的 structured measurements、file naming、CSV headers 與 rows、duration handling，以及 cleanup。內部 helper layout 不屬於基準的一部分。

**考慮過的替代方案：** 不採用僅限硬體的驗證，因為它速度慢、不具確定性，且無法用於 continuous integration。不採用 standard-library `unittest` runner，因為 pytest 能為規劃的 test matrix 提供簡潔的 fixture、parametrization、temporary-path 與 marker 支援。不採用整段 console session 的 snapshot，因為無關緊要的格式變更會造成脆弱測試。

### 4. 維護全 repository 適用的 Scenario-to-test traceability

`openspec/config.yaml` 定義全 repository 適用的政策：每個目前及未來的 Scenario 都必須可測試、對應至 test task，且在封存前具備 test evidence。本基準變更首次套用該政策；三份 delta specs 中的每個 `#### Scenario` 都對應至少一個測試案例。

確切的 capability 與 Scenario 名稱會記錄在 test identifier、docstring、marker metadata 或持續維護的 traceability audit 中。參數化測試可涵蓋多個 examples，但每個 Scenario 在 pytest 輸出中必須仍可個別識別。只有在 audit 明確列出每個 mapping 時，一個測試才能支援多個 Scenarios。

Scenario coverage 是主要完整性指標；line 與 branch coverage 是輔助診斷。最終 audit 會比較所有 scenario headings 與已收集的 pytest cases，並將任何未 mapping 的 scenario 視為工作未完成。

**考慮過的替代方案：** 不採用僅依賴 code coverage 的方式，因為執行一行 code 並不能證明 requirement scenario。不要求每個 scenario 都有一個 test function，因為 parametrization 能在維持不同 test cases 的同時，更清楚地表達 protocol variants。

### 5. 以三個層級驗證基準

封存前，會在三個不同層級檢查變更：

1. `openspec validate baseline-existing-imu-data-capabilities --type change --strict` 驗證 artifact structure 與 requirement syntax。
2. 聚焦及完整的 pytest suites 驗證可執行行為，並回報 branch coverage 以供審查。
3. OpenSpec change verification 檢查完整性、正確性與一致性，包括每個 scenario 是否都有對應的 test evidence。可用時採用官方 verification workflow；否則執行並記錄等效審查，因為目前的 core profile 未安裝 verification skill。

OpenSpec verification 是 evidence review，不能取代實際執行 pytest。即使 tooling 僅回報 warning，只要存在任何未涵蓋的 scenario，本專案便不得將變更視為可封存。

**考慮過的替代方案：** 不將 strict validation 視為足夠，因為它無法確立 runtime correctness。也不將 automated test success 視為足夠，因為僅憑此結果無法偵測遺漏的 scenario coverage 或 planning artifacts 之間的不一致。

### 6. 不以基準措辭掩蓋已知缺口

Specs 描述支援的行為，但不宣稱會完整診斷 malformed input、在 gateways 之間同步 timestamps、產生 research-ready CSV 輸出，或由 recorder 驗證 data quality。這些都不是既有能力，應歸屬後續變更。

**考慮過的替代方案：** 不在基準中描述期望的 robustness，因為這會使 main specs 宣稱系統具備實際上不存在的行為。

## 風險／取捨

- **[特性描述可能固化偶發行為]** → 規定穩定的 inputs、outputs 與 error boundaries，同時避免納入 private structure 與無關緊要的格式。
- **[Mocks 可能與實體序列裝置不同]** → 維持 protocol fixtures 的 byte-accurate 特性，並將硬體驗證記錄為獨立的未來活動，避免誇大 coverage。
- **[OpenSpec verification 可能只警告而不阻止封存]** → 將未涵蓋 scenario 數量為零訂為明確的專案封存條件，並獨立執行 pytest。
- **[Coverage metrics 可能鼓勵低價值測試]** → 優先審查 scenario coverage，只以 branch coverage 尋找尚未檢查的 paths。
- **[既有 examples 包含呈現缺陷]** → 測試 decoded values 與 required output fields，不測試無關的 labels 或 formatting mistakes；另行提出修正。
- **[使用者修改的 duration 預設值可能在實作前變更]** → 套用本變更前重新讀取 working tree；若使用者再次變更，則明確調整基準。

## 遷移計畫

1. 新增並設定 pytest 開發依賴項、markers、fixtures 與 scenario-traceability 慣例。
2. 為三份 capability specs 新增特性描述測試，且不編輯 runtime modules。
3. 執行聚焦及完整的套件並回報 branch coverage，再將每項 failure 與目前 working-tree behavior 比較。
4. 當基準 requirements 誇大目前行為時，縮小其範圍或予以修正；另行記錄期望的修正。
5. 執行嚴格 OpenSpec validation，以及完整性、正確性與一致性 verification review；解決每個未涵蓋的 scenario。
6. 封存已完成的變更，使其三份 delta specs 成為權威 main specs。

本變更沒有 runtime deployment 或 rollback。若基準在封存前遭到放棄，僅移除其 change artifacts，以及新加入的特性描述測試設定與檔案；既有 runtime behavior 維持不變。
