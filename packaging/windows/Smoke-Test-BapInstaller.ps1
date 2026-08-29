[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InstallerPath
)

$ErrorActionPreference = "Stop"
$InstallerPath = (Resolve-Path -LiteralPath $InstallerPath).Path
$InstallDir = Join-Path $env:LOCALAPPDATA "Programs\BAP"
$DataDir = Join-Path $env:LOCALAPPDATA "BAP"
$AppExe = Join-Path $InstallDir "BAP.exe"
$Uninstaller = Join-Path $InstallDir "unins000.exe"

$Install = Start-Process -FilePath $InstallerPath -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER" -Wait -PassThru
if ($Install.ExitCode -ne 0) { throw "BAP installer exited with $($Install.ExitCode)." }
if (-not (Test-Path -LiteralPath $AppExe -PathType Leaf)) { throw "BAP.exe was not installed." }

$Smoke = Start-Process -FilePath $AppExe -ArgumentList "--smoke-test" -Wait -PassThru
if ($Smoke.ExitCode -ne 0) { throw "BAP launch smoke test exited with $($Smoke.ExitCode)." }

$TempDir = Join-Path $DataDir "temp\imu-diagnostics"
New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
Set-Content -LiteralPath (Join-Path $TempDir "installer-smoke.csv") -Value "temporary" -Encoding UTF8

if (-not (Test-Path -LiteralPath $Uninstaller -PathType Leaf)) { throw "BAP uninstaller was not found." }
$Uninstall = Start-Process -FilePath $Uninstaller -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -Wait -PassThru
if ($Uninstall.ExitCode -ne 0) { throw "BAP uninstaller exited with $($Uninstall.ExitCode)." }
if (Test-Path -LiteralPath $TempDir) { throw "The managed IMU temporary directory remains after uninstall." }

Write-Output "BAP installer smoke test passed."
