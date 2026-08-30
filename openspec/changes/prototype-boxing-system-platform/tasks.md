## 名詞定義

| 名詞 | 定義 |
|---|---|
| Scenario test | 以 `pytest.mark.scenario` 對應到 spec 中一個 Scenario 的測試。 |
| Contract test | 驗證 Desktop App 與遠端後端 request／response 是否一致的測試。 |
| Hardware-in-the-loop test | 需要實際序列埠、IMU 或無線接收器才能執行的測試。 |
| Port adapter | 包裝 `pyserial` 與作業系統 Port 列表，讓正式硬體與測試替身共用同一介面的模組。 |
| Installer smoke test | 在乾淨 Windows 環境安裝後，確認 App 能啟動及移除的基本測試。 |
| BAP | 專案與 Desktop App 的正式名稱，全名為 Boxing Analysis Platform。 |
| Backend Artifact | 檔名為 `bap-backend-<commit-sha>.zip`、可放入遠端 Release 的 Backend 壓縮檔。 |
| Release | 位於 `C:\BAP\releases\<commit-sha>\`、部署後不可原地覆寫的 Backend 版本。 |
| `current\` | 指向目前運行 Release 的 `C:\BAP\current\` Directory Junction。 |
| 發布 Script | Developer 在本機執行的 `Publish-BapBackend.ps1`，負責檢查 Git、打包、上傳及要求遠端部署。 |
| 乾淨 Git 快照 | 能以 commit SHA 從 Git 重新取得，且 Backend Artifact 輸入沒有未提交內容的檔案集合。 |
| Backend Python process | 由一般 Python command 啟動、不是 Windows Service 的 FastAPI Backend process。 |
| 前景 Backend Terminal | Server 管理者人工啟動 Backend 的 Terminal；Terminal 必須保持開啟，並以 `Ctrl+C` 停止 Backend。 |
| 部署 Script Artifact | 檔名為 `bap-deployment-scripts-<commit-sha>.zip`、用來更新遠端部署 Scripts 的壓縮檔。 |

## 1. 專案結構與相依套件

- [x] 1.1 將 project-owned 程式碼、文件、OpenSpec、Goals、目前與 archived Changes、測試、設定及 metadata 的產品名稱統一為 `BAP`／`Boxing Analysis Platform`，保留第三方 vendor material 與 `.git` 內部歷史物件原貌。
- [x] 1.2 建立 `bap_desktop/` 與 `bap_backend/` package 結構，保留既有 CLI entry point，並加入最小 import smoke tests，證明程式不再依賴舊 package 名稱。
- [x] 1.3 在 `pyproject.toml` 加入 PySide6、FastAPI、Uvicorn、SQLAlchemy、Alembic、Argon2、JWT、HTTP client、keyring、semantic version 與 Windows packaging 所需相依套件，鎖定可重現版本。
- [x] 1.4 建立 Desktop App 與 Backend 的 typed settings，預設 API base URL 為 `https://imuapp.lab2312.cs.nthu.edu.tw/api/`，Backend listen address 為 `0.0.0.0:12345`，並支援測試環境覆寫。
- [x] 1.5 建立統一 logging 設定，確認密碼、Access Token、Refresh Token、Secret 與 IMU payload 不會寫入 log。
- [x] 1.6 將 package metadata、App title、Windows installer 與可執行檔顯示名稱設定為 `BAP`，並在產品資訊保留完整名稱 `Boxing Analysis Platform`。
- [x] 1.7 依 design.md 的 Developer 電腦 tree 建立或整理 repository 目錄，將 importable packages、root `migrations/`、`tests/`、`deployment/windows/backend/`、`packaging/windows/` 與 ignored `dist/` 的責任分開，並加入結構 smoke tests。

## 2. Qt-independent Port 掃描核心

- [x] 2.1 建立 Port adapter，從作業系統列出 Port 與 Manufacturer，Manufacturer 缺少時回傳空值供 UI 顯示 `—`。
- [x] 2.2 建立 bounded Port worker，以固定 `921600` 開啟一個 Port、被動讀取至 deadline、使用獨立 `AnrotSerialParser` 解析並回傳結構化結果。
- [x] 2.3 建立多 Port coordinator，讓所有候選 Port 並行掃描、支援取消，並保證單一 Port 失敗不會中止其他 Port。
- [x] 2.4 建立 reason code 分類，涵蓋 Port 使用中、權限不足、測試中斷、沒有 bytes、收到但無法解析及其他可安全顯示的 Serial 錯誤。
- [x] 2.5 建立有線與 `0x63` 無線 frame 分類，輸出 Port、連線方式、一個 Group ID 與去重排序後的 Node IDs；不同 Port 的相同 Group ID／Node ID 不得合併。
- [x] 2.6 以 fake Port adapter 測試並行 deadline、取消、Manufacturer、固定 baud rate、錯誤隔離及 reason code，不使用實際硬體也能覆蓋主要分支。
- [x] 2.7 新增標記為 `hardware` 的 hardware-in-the-loop 測試，確認支援的有線 IMU 與無線接收器能在 `921600` 被 parser 辨識，且掃描服務不會傳送設定指令。

## 3. IMU 連線狀態與 CSV

- [x] 3.1 建立五秒 diagnostics service，進入頁面時自動取得所有 Port 並呼叫 scan core，不提供 Port、Baud rate 或開始按鈕。
- [x] 3.2 建立單一測試暫存 CSV writer，讓每筆成功解析資料包含 Port 與來源欄位，並用資料列數除以各 Port 實際收集時間計算一位小數取樣率。
- [x] 3.3 建立「IMU 測試中，請稍後。」進度畫面與分析階段，將 worker 進度透過 Qt signal 傳回 UI thread，保持視窗可回應。
- [x] 3.4 建立每個 Port 一列的 Report table，依序顯示 Port、Manufacturer、連線方式、Baud rate、Group ID／Node IDs、取樣率、連線狀態及白話說明。
- [x] 3.5 建立「重新測試」流程，每次重新列舉 Port、取代舊 Report，並清除不再需要的舊暫存資料。
- [x] 3.6 建立「匯出 CSV」save dialog 與複製流程，App 關閉時只刪除 App 管理的暫存 CSV，不刪除 user 匯出的檔案。
- [x] 3.7 加入依賴邊界測試，證明 diagnostics service 與 CSV service 不會呼叫遠端 API client 或送出 IMU payload。

## 4. 拳擊項目前的 IMU 來源探索

- [x] 4.1 建立三秒 discovery service，每次進入任一拳擊測量項目都重新列舉所有 Port 並執行 scan，不讀取五秒 diagnostics cache。
- [x] 4.2 建立「正在確認 IMU，請稍後。」進度畫面，完成後只列出本次成功解析的有線 Port 與無線 Group ID／Node ID。
- [x] 4.3 建立單選來源 UI；有線來源保存 Port，無線來源保存 Port、Group ID 與一個 Node ID，改選時取消原選擇。
- [x] 4.4 建立找不到來源的錯誤畫面，顯示逐 Port 簡化原因及「再次確認」，並在再次確認時執行全新的三秒 scan。
- [x] 4.5 完成來源選擇後顯示目前拳擊測量項目「待開發」，清除 discovery 暫存資料，且不啟動拳擊錄製或分析。

## 5. 遠端後端與 Database

- [x] 5.1 建立 FastAPI application factory、`/api/v1` route、統一 JSON error schema 與 dependency injection 入口，讓測試可以替換 settings、Database session、clock 及 Token generator。
- [x] 5.2 建立 `api`、`services`、`repositories`、`db`、`models`、`schemas` 與 `core` 分層，加入 dependency-boundary tests，禁止 API route 直接寫 SQL，並禁止 Repository 依賴 FastAPI request object。
- [x] 5.3 建立 `C:\BAP\config\.env` 與 process environment 的 typed settings schema，涵蓋 bind host、bind port、Database URL、JWT signing key、Token 有效期與 Log 目錄；缺少正式環境必要設定時安全地拒絕啟動。
- [x] 5.4 建立安全的 logging 與 error handling，將 Backend Log 寫到外部設定指定位置，並測試密碼、Token、Secret、Database credential 與完整 exception 不會出現在 API 回應或敏感 log 欄位。
- [x] 5.5 建立 SQLAlchemy session lifecycle、models、repository 與初始 Alembic migration，只包含 `users`、`refresh_sessions` 及 `app_releases`，Database file 使用 Release 外的設定路徑。
- [x] 5.6 設定 Username case-sensitive unique constraint，並以 migration／repository tests 確認 `Boxer01` 與 `boxer01` 可分別存在。
- [x] 5.7 建立 Username 與密碼 validator；Username 使用 `^[A-Za-z0-9._-]{5,64}$`，密碼使用 8 到 128 字元且至少一個英文字母與數字。
- [x] 5.8 建立 Argon2id password hashing、登入驗證與不透露帳號是否存在的統一錯誤回覆。
- [x] 5.9 建立 30 分鐘 JWT Access Token、30 天 opaque Refresh Token、Refresh Token hash 儲存、輪替、到期及撤銷流程。
- [x] 5.10 建立 register、login、refresh 與 logout Service 與 endpoints，明確劃分 transaction boundary，並加入 current-device session 行為的 API integration tests。
- [x] 5.11 建立 release repository、Service 與 `GET /api/v1/releases/latest`，只回傳指定 platform 的 active 最新 semantic version、HTTPS URL 與 SHA-256。
- [x] 5.12 建立 `python -m bap_backend.tools.publish_desktop_release` 管理 CLI，驗證 platform、semantic version、HTTPS download URL 與 SHA-256，並由 Server 管理者建立或更新 `app_releases`；不得提供一般 user 可呼叫的公開寫入 API。
- [x] 5.13 建立 `GET /health`，在 application 與 Database 可用時回傳 `200`、service 名稱及 commit SHA，尚未就緒時回傳 `503`，並加入不洩漏設定與 Secret 的 tests。
- [x] 5.14 加入 Backend schema／route 測試，證明 API 與 Database 沒有 IMU、CSV、拳擊測量或分析資料欄位與上傳 endpoint。

## 6. Desktop App 帳號與登入狀態

- [x] 6.1 建立註冊 UI，提供即時 Username／密碼規則提示，並處理成功、Username 重複及遠端連線錯誤。
- [x] 6.2 建立 Username 登入 UI、顯示／隱藏密碼與「記住登入狀態」，登入失敗時顯示統一錯誤且保留 Username。
- [x] 6.3 建立 auth API client 與 contract fixtures，讓 Desktop App request／response schema 與後端 endpoints 一致。
- [x] 6.4 建立 session service：Access Token 只放 memory；勾選記住登入時將 Refresh Token 放入作業系統 credential store，未勾選時只放 memory。
- [x] 6.5 建立 Access Token 到期自動 refresh、Refresh Token 輪替與 App 啟動時恢復登入流程；失效時清除本機憑證並回到登入畫面。
- [x] 6.6 建立登出流程，先清除本機 Token，再呼叫後端撤銷；離線時仍回到登入畫面且不得在下次啟動自行恢復。

## 7. Desktop App 主畫面與待開發項目

- [x] 7.1 建立 authenticated App shell、主畫面與導覽，提供「IMU 連線狀態」及五個分開的拳擊測量項目入口。
- [x] 7.2 將所有主要操作、狀態與錯誤整理成白話繁體中文 resource，保留 Port、Baud rate、Group ID、Node ID 等專有名詞的一致拼法。
- [x] 7.3 確認每次只能進入一個拳擊測量項目，不提供多選畫面，並將項目入口及完成來源選擇後的頁面清楚標示「待開發」。
- [x] 7.4 建立 App shutdown coordinator，取消仍在執行的 worker、刪除 diagnostics／discovery 暫存資料，並讓本次裝置結果失效。

## 8. 更新檢查

- [x] 8.1 建立背景 update service，在 App 啟動時以目前 platform 與 version 呼叫最新版本 endpoint，不阻擋登入或本機 IMU 功能。
- [x] 8.2 建立 semantic version 比較及 platform／HTTPS URL validation，無有效下載位置時不得提供下載操作。
- [x] 8.3 建立非阻擋更新提示，顯示目前與最新版本；user 可選擇稍後或開啟 GitHub Releases 的 Windows installer URL，不自動下載或安裝。
- [x] 8.4 建立更新服務正常、已是最新、發現新版、無效回覆及離線時的 Desktop App integration tests。

## 9. Windows 包裝

- [x] 9.1 建立 PyInstaller one-folder spec，收集 PySide6 platform plugin、translations 與 App resources，並在 Windows build runner 驗證可啟動。
- [x] 9.2 建立 BAP Inno Setup installer script，包含 `BAP` 顯示名稱、`Boxing Analysis Platform` 產品資訊、開始功能表捷徑、版本資訊及移除流程，不要求目標電腦預先安裝 Python。
- [x] 9.3 在乾淨 Windows 測試環境執行 BAP installer smoke test，驗證安裝、啟動、登入畫面、App 移除及無殘留暫存 IMU CSV。
- [x] 9.4 記錄 Prototype unsigned installer 的發行步驟，並預留日後 code-signing hook；Desktop installer 發行與 Backend GitHub Actions 自動部署保持分離。
- [x] 9.5 將第一版設定為 per-user 安裝到 `%LOCALAPPDATA%\Programs\BAP`，並建立 `%LOCALAPPDATA%\BAP` 下的非敏感設定、Log 與 `temp\imu-diagnostics`；測試 Refresh Token 只進入 Windows Credential Manager，匯出 CSV 不會被暫存清理刪除。

## 10. Backend Artifact 與部署介面

- [x] 10.1 建立 `bap_backend/VERSION` 作為 Backend semantic version 的唯一來源，並定義及驗證 Build 時產生的 `deployment-manifest.json` schema；manifest 至少包含 BAP 專案名稱、component、完整 commit SHA、Backend version、建立時間、Python 版本需求、application entry point 與 Alembic revision。
- [x] 10.2 建立 `Build-BapBackendArtifact.ps1`：取得完整 `HEAD` SHA、從該 commit 建立乾淨暫存工作區、執行 Backend tests，並產生 `bap-backend-<commit-sha>.zip`、manifest 與 `.zip.sha256`。
- [x] 10.3 將 Backend production dependencies 與 Desktop／Build dependencies 分開，讓遠端依 `pyproject.toml`、`uv.lock` 只安裝 Backend 必要套件；加入 Artifact contents tests，確認不包含 `.venv`、`.env`、Database、Log、Token、Secret、Desktop App 或測試資料。
- [x] 10.4 建立可安全重複執行的 `Initialize-BapBackendHost.ps1`，驗證 Python 3.12、uv、既有 `user` 帳號、OpenSSH、Public Key 登入與 ACL，建立 `C:\BAP` 的 `releases`、`incoming`、`config`、`data`、`logs`、`backups`、`scripts`、`scripts-releases`、`bootstrap`、`run`，且不得建立新帳號、覆寫 SSH 設定或刪除既有持久資料。
- [x] 10.5 建立 `Start-BapBackend.ps1`、`Stop-BapBackend.ps1` 與 `Get-BapBackendStatus.ps1`；使用 `C:\BAP\current\.venv\Scripts\python.exe` 在前景 Terminal 啟動 Backend，以 `Ctrl+C` 停止，並透過本機 `/health` 查看狀態，不使用可能誤指向 Python launcher 的 PID file。
- [x] 10.6 建立 `Deploy-BapBackendRelease.ps1`，驗證 `.sha256`、ZIP 檔名 SHA 與 manifest SHA，解壓縮到不可覆寫的 `C:\BAP\releases\<commit-sha>`，建立 `.venv` 並鎖定安裝 Backend production dependencies。
- [x] 10.7 在遠端部署 Script 中建立安全的 `current\` Junction 管理，能讀取舊目標、在 Backend Python process 停止後切換到指定 Release，且拒絕指向 `C:\BAP\releases` 以外的位置。
- [x] 10.8 建立 `Publish-BapBackend.ps1`，檢查所有 Artifact 輸入都已 commit、沒有未追蹤內容，且正式部署的 `HEAD` 已 push；預設使用 SSH host `140.114.75.84`、user `user`、port `22`、`BatchMode=yes` 與已固定的 SSH Host Fingerprint，通過後呼叫 Build Script、以 SCP 上傳 ZIP 與 checksum，再以 SSH 呼叫遠端 Deploy Script。
- [x] 10.9 對 `Publish-BapBackend.ps1` 建立 tests，確認 dirty Backend files、舊 SHA 包含新 working-tree 內容、未 push commit、Checksum 不符及 manifest 不符都會在修改遠端前停止；只有無關 Desktop dirty files 時顯示警告。
- [x] 10.10 建立 `Publish-BapDeploymentScripts.ps1`，從已 commit 且已 push 的 Git 快照產生 `bap-deployment-scripts-<commit-sha>.zip`、manifest 與 SHA-256，以 SCP 上傳後透過 SSH 呼叫固定的 `C:\BAP\bootstrap\Update-BapDeploymentScripts.ps1`。
- [x] 10.11 建立最小且穩定的 `Update-BapDeploymentScripts.ps1`，驗證 checksum、commit SHA 與允許的檔案，解壓縮到 `C:\BAP\scripts-releases\<commit-sha>`，安全切換 `C:\BAP\scripts`，失敗時保留舊版，且不得在執行途中覆寫自己。
- [x] 10.12 完成 Prototype 遠端 Backend 部署順序：Server 管理者先以 `Ctrl+C` 停止前景 Backend，發布 Script 再準備 Release、確認 port `12345` 未被使用、備份 SQLite、執行 Alembic migration、記錄舊 `current\` 並切換；完成後由管理者人工以前景 Terminal 啟動，再以 `Test-BapBackendHealth.ps1` 檢查 Server 本機與公開 `/health`。
- [x] 10.13 建立 `Rollback-BapBackendRelease.ps1` 與 rollback tests，確認 rollback 前要求前景 Backend 已停止、`current\` 指回上一個 Release、必要時還原 Database 備份；完成後由管理者人工啟動上一版並檢查 `/health`。
- [ ] 10.14 在隔離的 Windows 測試主機執行第一次初始化、部署 Script 更新及後續第二次 Backend 發布的端到端測試，確認初始化 Script 可重複執行、持久資料不被覆蓋、Server 管理者可在部署前後人工停止與啟動前景 Backend，且 Developer 的 Build、SCP、SSH、Migration 與 `current\` 切換只需執行本機發布 Script。
- [x] 10.15 以實際 Windows SSH 部署驗證背景 child process 會在 session 結束後失效，因此 Prototype 明確只支援 Terminal 前景啟動；確認 Terminal 關閉或 Windows 重新開機後不宣稱 Backend 會持續運行或自動啟動。
- [x] 10.16 驗證 `C:\BAP\bootstrap\Update-BapDeploymentScripts.ps1`、Private Key、`.env`、Database、Log、Token 與 user 資料都不會進入 Backend Artifact 或部署 Script Artifact。
- [x] 10.17 驗證 Backend 正確監聽 `0.0.0.0:12345`，並在既有 Caddy 前置條件下通過 `http://127.0.0.1:12345/health`、公開 `/health`、`/openapi.json` 與 `/docs`；本 Change 不修改 DNS、TLS certificate、HTTPS termination 或 Reverse Proxy。
- [x] 10.18 驗證本 Change 不建立 GitHub Actions Tag-triggered production deployment、production environment secrets、部署核准或 concurrency；後續自動部署 Change 必須重用本 Change 的 Build、Artifact、SCP、SSH、遠端部署、Health Check 與 rollback 介面。
- [x] 10.19 以白話繁體中文更新 repository 根目錄 `README.md`，說明 Initialize、Test、Start／Stop／Status、Deploy、Update Deployment Scripts、Rollback、公開 HTTPS 驗證與 Desktop App build；為主要操作加入 Mermaid pipeline，標示執行電腦、前置條件、完整可複製 PowerShell command、預期結果及常見錯誤，並以 automated documentation test 驗證提到的 Script 與 repository 路徑存在。

## 11. Scenario 對應測試

- [x] 11.1 為 `desktop-app-shell` 建立 Qt automated tests，使用精確 scenario marker 覆蓋「user 查看 App 與安裝資訊」、「登入後進入主畫面」、「成功恢復登入狀態」、「查看拳擊測量項目」、「進入單一拳擊項目」、「完成 IMU 來源選擇」、「顯示操作與錯誤」、「Desktop App 呼叫遠端 API」；以 task 9.3 的 installer smoke test 覆蓋「在支援的 Windows 電腦安裝」。
- [x] 11.2 為 `user-account-session` 建立 API、contract 與 Qt tests，使用精確 scenario marker 覆蓋「成功註冊」、「Username 已被使用」、「Username 格式正確」、「Username 格式錯誤」、「Username 英文大小寫不同」、「密碼符合規則」、「密碼不符合規則」、「登入成功」、「登入資料錯誤」、「登入時無法連線到後端」、「Access Token 到期後自動更新」、「Refresh Token 已到期」、「記住登入狀態並重新啟動 App」、「未選擇記住登入狀態」、「登出成功」、「離線時登出」。
- [x] 11.3 為 `imu-connection-diagnostics` 建立 fake serial、Qt 與 filesystem tests，使用精確 scenario marker 覆蓋「電腦有多個 Port」、「電腦沒有 Port」、「正在收集資料」、「正在產生 Report」、「成功解析有線 IMU」、「成功解析無線接收器資料」、「沒有成功解析資料」、「Manufacturer 可以取得」、「Manufacturer 無法取得」、「無線接收器有多個 Node」、「五秒內寫入 2000 筆資料」、「資料內容重複」、「Port 正被使用」、「沒有 Port 權限」、「測試期間 Port 消失」、「五秒內沒有收到 bytes」、「收到 bytes 但無法解析」、「按下重新測試」、「匯出 CSV」、「App 關閉時存在未匯出的暫存 CSV」、「完成 IMU 連線測試」。
- [x] 11.4 為 `imu-source-discovery` 建立 fake serial 與 Qt tests，使用精確 scenario marker 覆蓋「先前已查看 IMU 連線狀態」、「先前沒有執行 IMU 測試」、「正在探索多個 Port」、「發現有線 IMU」、「發現無線接收器與多個 Node」、「相同 ID 出現在不同 Port」、「選擇無線 Node」、「改選有線 Port」、「所有 Port 都沒有可解析資料」、「user 按下再次確認」、「選好來源並繼續」。
- [x] 11.5 為 `desktop-app-update-check` 建立 fake API 與 Qt tests，使用精確 scenario marker 覆蓋「更新服務正常回應」、「更新服務無法連線」、「發現適用的 Windows 新版」、「user 選擇下載更新」、「已安裝最新版本」、「Windows App 要求更新資訊」、「更新資訊缺少適用下載位置」。
- [x] 11.6 執行預設 automated test suite、API integration suite、Windows UI suite、Backend deployment-interface suite 及可用的 hardware-in-the-loop tests，輸出 Scenario coverage 報告並修正所有未對應 Scenario。

## 12. Repository 與資料夾完成更名

- [x] 12.1 以不分大小寫的全 repository 搜尋確認 project-owned 檔案沒有殘留舊專案名稱或舊 package 名稱，並確認 BAP、Boxing Analysis Platform、`bap_desktop`、`bap_backend`、installer 與 Backend process 命名一致。
- [x] 12.2 確認已改名的 GitHub repository 可由 `git@github.com:conan0220/BAP.git` 存取，更新本機 `origin` URL，並驗證 fetch、push 與 GitHub Actions workflow references 指向新 repository。
- [ ] 12.3 在所有測試與文件驗證完成後，將本機專案資料夾名稱改為 `D:\repos\BAP`，重新開啟 workspace，確認 OpenSpec、tests、package build 與 Git 操作不依賴舊絕對路徑。
