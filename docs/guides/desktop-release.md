# BAP Windows Desktop Prototype 發行方式

## 用途

這份說明供 Developer 建立 Windows Desktop App 測試安裝檔。Desktop installer 與 Backend 部署是兩條分開的流程；執行本流程不會更新遠端 Backend。

## 建立未簽章 Prototype installer

在 Developer 電腦的 repository 根目錄執行：

```powershell
C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\repos\BAP\packaging\windows\Build-BapDesktop.ps1"
```

Script 會先用 PyInstaller 建立 one-folder `dist\BAP\`，再用 Inno Setup 建立 `BAP-Setup-<version>.exe`。安裝檔採 per-user 安裝，預設位置是 `%LOCALAPPDATA%\Programs\BAP`，不要求 user 先安裝 Python。

Prototype 預設不簽章，因此 Windows 可能顯示 SmartScreen 警告。不要把未簽章版本描述成正式可信任發行版。

## 日後加入 Code Signing

取得 code-signing certificate 後，傳入 SignTool 與 certificate thumbprint：

```powershell
C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\repos\BAP\packaging\windows\Build-BapDesktop.ps1" -SignToolPath "C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe" -CertificateThumbprint "<certificate-thumbprint>"
```

Certificate、Private Key 與實際 thumbprint 不得提交到 Git。

## 乾淨 Windows Smoke Test

在沒有安裝 Python 的乾淨 Windows 測試環境執行：

```powershell
C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\repos\BAP\packaging\windows\Smoke-Test-BapInstaller.ps1" -InstallerPath "D:\repos\BAP\dist\BAP-Setup-0.1.0.exe"
```

測試會安裝 BAP、啟動登入畫面 smoke mode、執行移除，並確認 `%LOCALAPPDATA%\BAP\temp\imu-diagnostics` 沒有殘留。Refresh Token 只能由 Windows Credential Manager 保存；`settings.json`、Log 及暫存 CSV 不應包含 Token。

