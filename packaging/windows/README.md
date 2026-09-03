# BAP Windows Desktop Candidate

## 名詞定義

| 名詞 | 定義 |
|---|---|
| Desktop Candidate | PR CI 建立並完成安裝測試的 Windows Installer。 |
| Source Tree SHA | 代表已測試完整檔案內容的 Git tree SHA。 |
| Smoke Test | Silent install、啟動、API E2E、uninstall 與清理檢查。 |

Build-BapDesktop.ps1 接收 Source Tree SHA，使用 PyInstaller 與 Inno Setup，在 Runner 暫存目錄輸出 Installer、checksum 與 metadata JSON。

Smoke-Test-BapInstaller.ps1 會安裝 Installer、啟動 smoke mode；CI 傳入 ApiBaseUrl 時，還會以安裝後的 App 執行真實 HTTP user flow，最後 uninstall 並檢查暫存 CSV 已清除。

CD 只能發布這份已測 Installer，不可重新執行 PyInstaller 或 Inno Setup。
