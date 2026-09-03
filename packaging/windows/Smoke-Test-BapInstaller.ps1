[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$InstallerPath,
    [string]$ApiBaseUrl
)

$ErrorActionPreference = "Stop"
$InstallerPath = (Resolve-Path -LiteralPath $InstallerPath).Path
$InstallDir = Join-Path $env:LOCALAPPDATA "Programs\BAP"
$DataDir = Join-Path $env:LOCALAPPDATA "BAP"
$AppExe = Join-Path $InstallDir "BAP.exe"
$Uninstaller = Join-Path $InstallDir "unins000.exe"

try {
    $Install = Start-Process -FilePath $InstallerPath -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER" -Wait -PassThru
    if ($Install.ExitCode -ne 0) { throw "BAP installer exited with $($Install.ExitCode)." }
    if (-not (Test-Path -LiteralPath $AppExe -PathType Leaf)) { throw "BAP.exe was not installed." }

    $Smoke = Start-Process -FilePath $AppExe -ArgumentList "--smoke-test" -Wait -PassThru
    if ($Smoke.ExitCode -ne 0) { throw "BAP launch smoke test exited with $($Smoke.ExitCode)." }

    if ($ApiBaseUrl) {
        $PreviousApiBaseUrl = $env:BAP_API_BASE_URL
        try {
            $env:BAP_API_BASE_URL = $ApiBaseUrl
            $E2E = Start-Process -FilePath $AppExe -ArgumentList "--api-e2e-test" -Wait -PassThru
            if ($E2E.ExitCode -ne 0) { throw "Installed BAP API E2E exited with $($E2E.ExitCode)." }
        } finally {
            $env:BAP_API_BASE_URL = $PreviousApiBaseUrl
        }
    }

    $TempDir = Join-Path $DataDir "temp\imu-diagnostics"
    New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $TempDir "installer-smoke.csv") -Value "temporary" -Encoding UTF8
} finally {
    if (Test-Path -LiteralPath $Uninstaller -PathType Leaf) {
        $Uninstall = Start-Process -FilePath $Uninstaller -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -Wait -PassThru
        if ($Uninstall.ExitCode -ne 0) { throw "BAP uninstaller exited with $($Uninstall.ExitCode)." }
    }
}
if (Test-Path -LiteralPath (Join-Path $DataDir "temp\imu-diagnostics")) {
    throw "The managed IMU temporary directory remains after uninstall."
}
Write-Output "BAP installer smoke test passed."
