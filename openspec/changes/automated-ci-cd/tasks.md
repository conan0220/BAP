## 名詞定義

| 名詞 | 定義 |
|---|---|
| CI Runner | PR 階段負責 Build、Production-like Test 與 Candidate upload 的 Windows Runner。 |
| CD Runner | 人工 Merge 後負責 Candidate verification 與 Promotion 的 Windows Runner。 |
| 統一 Backend 交付包 | 同時包含 Backend、Migration、metadata 與 runtime deployment code 的 ZIP。 |
| Scenario marker | 自動測試用來標記它對應哪一個 capability Scenario 的資訊。 |
| Cutover | 新 CI/CD 已驗證後，正式停止並移除舊流程的切換點。 |
| Workspace cleanup | 只清除可重新產生的 build／test 輸出，不刪除 source、`.venv` 或正式資料。 |

## 1. Candidate Metadata 與 Scope

- [x] 1.1 建立 Git helper，取得 PR head/base/test commit、`HEAD^{tree}` Source Tree SHA、master commit 與 workflow run URL。
- [x] 1.2 定義並驗證 `delivery-manifest.json`，包含 PR、CI run、所有 SHA、scope、版本、檔名、SHA256 與測試結果。
- [x] 1.3 建立 checksum、manifest schema、未知欄位、遺漏欄位與檔名驗證測試。
- [x] 1.4 建立共用 change-detection helper，輸出 `docs_only`、`backend_changed` 與 `desktop_changed`。
- [x] 1.5 建立 backend-only、desktop-only、shared、deployment、packaging、workflow 與 docs-only fixture tests。
- [x] 1.6 確保所有 helper 的錯誤輸出、cleanup 與 Job Summary 不會顯示 Secret。

## 2. 統一 Backend 交付包

- [x] 2.1 改寫 `Build-BapBackendArtifact.ps1`，從 PR test merge tree 建立 `bap-backend-tree-<source-tree-sha>.zip`。
- [x] 2.2 將允許的 runtime deployment code 納入 Backend ZIP，移除獨立 Deployment Scripts Artifact 相依。
- [x] 2.3 讓 builder 接受 Runner 提供的工具與輸出路徑，正式 CI 輸出只寫入 `RUNNER_TEMP`。
- [x] 2.4 將單元測試與 Build 分離，並建立 ZIP allowlist、secret exclusion、locked dependency、import、manifest 與 PowerShell parse tests。
- [x] 2.5 更新 Backend manifest，使它同時記錄 Source Tree SHA，且不把 PR test commit 偽裝成 master commit。

## 3. Desktop Candidate Build

- [x] 3.1 改寫 Desktop build metadata，使 Installer 記錄 App version、Source Tree SHA 與 SHA256。
- [x] 3.2 保留並調整 `Build-BapDesktop.ps1`、PyInstaller spec、Inno Setup 與 `Smoke-Test-BapInstaller.ps1` 供 CI 使用。
- [x] 3.3 建立 Installer version、metadata、checksum、silent install、launch、uninstall 與殘留檔案測試。
- [x] 3.4 確保開發者本機 `dist\` 與 `build\` 不會被 Candidate upload 或 CD 讀取。

## 4. Pull Request CI

- [x] 4.1 建立 `.github/workflows/pull-request-ci.yml`，支援 PR open、reopen、synchronize 並固定產生 required check。
- [x] 4.2 加入 `pr-ci-<PR number>` concurrency 與 cancel-in-progress。
- [x] 4.3 建立 docs-only 輕量路徑，不配置 Windows Runner但仍回報成功 required check。
- [x] 4.4 在 Windows Runner 1 從同一個 test merge tree 建立 Backend ZIP 與 Desktop Installer。
- [x] 4.5 從 Backend ZIP 安裝暫存 Release、建立測試 config／SQLite、執行 Alembic 並啟動 `127.0.0.1:12345`。
- [x] 4.6 Silent install Desktop Installer，設定 `BAP_API_BASE_URL=http://127.0.0.1:12345`，執行註冊、登入、Refresh、登出、更新檢查與錯誤處理 E2E。
- [x] 4.7 執行 Backend API contract／integration、Desktop installed E2E、packaging 與 cleanup tests。
- [x] 4.8 測試全部通過後建立 checksums、test summary 與 manifest，並以 14 天 retention 上傳單一 CI Candidate。
- [x] 4.9 使用 `always()` 與 `cancelled()` 關閉 Backend、移除測試 Installer／Database並上傳安全 diagnostics。
- [x] 4.10 建立 Workflow contract tests，確認 PR Job 不引用 `production-backend` 或 SSH Private Key。

## 5. 人工 Merge 與 Candidate Resolver

- [x] 5.1 設定 `master` Branch Protection：禁止直接 push、要求固定 CI check、要求 branch up to date，且不啟用 Auto-merge。
- [x] 5.2 建立 `.github/workflows/continuous-delivery.yml`，只在 PR 人工 Merge 形成新的 `master` commit 後啟動。
- [x] 5.3 建立 associated PR／required CI run／Candidate resolver，從 master commit 找回唯一 Candidate。
- [x] 5.4 在 Windows Runner 2 驗證 Source Tree SHA、PR、CI conclusion、manifest、test summary、checksums、版本與 scope。
- [x] 5.5 建立 Candidate 不存在、已到期、多份候選、Tree mismatch、checksum mismatch、scope mismatch 與 CI 非 success 的 fail-closed tests。
- [x] 5.6 建立 Workflow contract test，確認 CD 沒有 Backend package、PyInstaller、Inno Setup 或其他 rebuild step。
- [x] 5.7 加入單一 Production concurrency，避免兩次 Backend Promotion 同時執行。

## 6. Backend Scheduled Task 與自動部署

- [x] 6.1 改寫 `Initialize-BapBackendHost.ps1`，建立必要持久目錄、最小 Bootstrap 與開機啟動的 `BAPBackend` Scheduled Task，且重跑不覆寫 config／Database。
- [x] 6.2 改寫 `Deploy-BapBackendRelease.ps1`，接受同一 Candidate 的 Backend ZIP、checksum、Source Tree SHA、master commit 與 Promotion record。
- [x] 6.3 由 CD 使用 `production-backend` 的 Private Key、host、user 與 port 執行 SCP／SSH，且不要求 `BAP_BACKEND_HOST_KEY`。
- [x] 6.4 實作部署鎖、Release immutable／idempotent、Scheduled Task stop、SQLite backup、Migration、`current` 切換與 Scheduled Task start。
- [x] 6.5 改寫 `Get-BapBackendStatus.ps1`，回報 Task state、port 12345、local health、current master commit、Source Tree SHA 與 checksum。
- [x] 6.6 保留並調整 `Test-BapBackendHealth.ps1`，部署後同時驗證 localhost 與公開 HTTPS。
- [x] 6.7 改寫 `Rollback-BapBackendRelease.ps1`，自動停止 Task、還原 Release／Database、重新啟動並重跑 Health。
- [x] 6.8 建立暫存 `C:\BAP` contract tests，涵蓋 checksum、manifest、unexpected file、重複部署、Migration failure、Junction failure、Task failure、Health failure 與 Rollback。
- [x] 6.9 在遠端完成 SSH、Scheduled Task 啟停、SSH 結束後持續運行、Backend-only deployment、local／public Health 與 Promotion record E2E；不得為測試主動重新開機，開機 Trigger 只做設定與 contract 驗證。

## 7. Desktop Release 與 Backend-first Gate

- [x] 7.1 驗證 Candidate Desktop version 不得與既有 `desktop-v<version>` tag 衝突。
- [x] 7.2 使用 Candidate 中同一個 Installer 建立 Draft Release、附加 checksum／Promotion metadata，且不重新 Build。
- [x] 7.3 同時變更時先完成 Backend Promotion 與 Health；失敗時不得發布 Desktop。
- [x] 7.4 發布 GitHub Release 後建立 `app_releases`，驗證 update-check API 回傳 version、URL、Source Tree SHA 與 checksum。
- [x] 7.5 建立 version、tag、asset、Backend gate、Release publish 與 `app_releases` failure tests。

## 8. 狀態、通知與稽核

- [x] 8.1 為 PR classification、CI Build／Test、Candidate、Merge、CD verification、Backend、Desktop 與 Rollback建立一致的 Job Summary。
- [x] 8.2 失敗時上傳安全的 logs、reports、manifest 與 diagnostics，並加入 Secret redaction tests。
- [x] 8.3 建立 Promotion record 與 Last Known Good schema，記錄 master commit、PR、CI run、Source Tree SHA、checksums、scope、Database revision 與發布結果。
- [x] 8.4 驗證 GitHub Actions notification 設定可在 CI／CD 失敗時寄送 Email，repository 不保存 SMTP credential。
- [x] 8.5 更新根目錄 `README.md`，只保留 UI 快速預覽、feature branch、PR、等待 CI 與人工 Merge 的開發者流程。
- [x] 8.6 更新或移除只描述人工 Desktop Release、前景 Terminal與本機 Publisher 的 guides／component README。

## 9. 舊流程 Cutover 與 Repository 清理

- [x] 9.1 新 `pull-request-ci.yml` 通過後移除 `.github/workflows/build-desktop.yml`，避免重複 Build。
- [x] 9.2 Backend CD 驗證完成後移除 `Publish-BapBackend.ps1`。
- [x] 9.3 統一 Backend 交付包驗證完成後移除 `Publish-BapDeploymentScripts.ps1` 與 `Update-BapDeploymentScripts.ps1`。
- [x] 9.4 Scheduled Task 驗證完成後移除 `Start-BapBackend.ps1` 與 `Stop-BapBackend.ps1`。
- [x] 9.5 移除或重寫要求本機 Publish、獨立 script Artifact、前景 Terminal或禁止 GitHub Production Deployment 的舊測試。
- [x] 9.6 清理 repository 本機 `dist\`、`build\`、`bap.egg-info\`、`.pytest_cache\`、`__pycache__\` 舊產生物，但保留 `.venv`。
- [x] 9.7 清理遠端舊 `scripts-releases\`、`scripts\` Junction、`Update-BapDeploymentScripts.ps1`、Deployment Scripts ZIP 與 PID 檔，保留 config、data、logs、backups、releases、current、incoming。
- [x] 9.8 建立 repository contract test，確認被淘汰的 Workflow、Scripts、文件指令與相反 assertions 不再出現。
- [x] 9.9 驗證根目錄沒有正式流程會讀取本機 `dist\` 或要求開發者執行 SCP／SSH。

## 10. Scenario Coverage 與最終驗證

- [x] 10.1 為 `pull-request-ci` 的每個 Scenario 建立 automated／contract test與 `pytest.mark.scenario` 對應。
- [x] 10.2 為 `component-delivery-routing` 的每個 Scenario 建立 automated／contract test與 marker。
- [x] 10.3 為 `backend-automatic-deployment` 的每個 Scenario 建立 contract／遠端 E2E 與 marker。
- [x] 10.4 為 `desktop-automatic-release` 的每個 Scenario 建立 automated／contract test與 marker。
- [x] 10.5 為 `ci-cd-status-reporting` 的每個 Scenario 建立 automated／contract test與 marker。
- [x] 10.6 建立 Scenario coverage checker，缺少測試 marker 時使 CI 失敗。
- [x] 10.7 執行 OpenSpec strict validation、pytest、Workflow YAML／contract、API integration、Qt E2E、packaging、deployment-interface 與 Scenario coverage。
- [x] 10.8 建立測試 PR，驗證 Windows Runner 1 只 Build 一次、由 Artifact 安裝並上傳 Candidate。
- [x] 10.9 人工 Merge 測試 PR，驗證 Windows Runner 2 下載同一 Candidate、不重新 Build，並正確執行 scope routing。
- [x] 10.10 分別驗證 backend-only、desktop-only、shared 與 docs-only 流程。
- [ ] 10.11 故意造成 checksum／Tree／scope mismatch 與 Production health failure，驗證 fail closed、Rollback、Last Known Good 與 Email 通知。
- [x] 10.12 完成一次 Cutover 後的全新 PR→CI→人工 Merge→CD E2E，確認舊 Script 已移除且開發者 workspace 不產生正式 Artifact。
