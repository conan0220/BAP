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

function Invoke-BapAppCheck {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Label,
        [int]$TimeoutSeconds = 120
    )

    $Process = Start-Process -FilePath $AppExe -ArgumentList $Arguments -PassThru
    if (-not $Process.WaitForExit($TimeoutSeconds * 1000)) {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        throw "$Label timed out after $TimeoutSeconds seconds."
    }
    $Process.Refresh()
    if ($Process.ExitCode -ne 0) { throw "$Label exited with $($Process.ExitCode)." }
}

try {
    $Install = Start-Process -FilePath $InstallerPath -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER" -Wait -PassThru
    if ($Install.ExitCode -ne 0) { throw "BAP installer exited with $($Install.ExitCode)." }
    if (-not (Test-Path -LiteralPath $AppExe -PathType Leaf)) { throw "BAP.exe was not installed." }

    Invoke-BapAppCheck -Arguments @("--smoke-test") -Label "BAP launch smoke test" -TimeoutSeconds 60

    if ($ApiBaseUrl) {
        $PreviousApiBaseUrl = $env:BAP_API_BASE_URL
        try {
            $env:BAP_API_BASE_URL = $ApiBaseUrl
            Invoke-BapAppCheck -Arguments @("--api-e2e-test") -Label "Installed BAP API E2E" -TimeoutSeconds 120
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
