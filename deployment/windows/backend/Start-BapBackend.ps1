[CmdletBinding()]
param([string]$Root = "C:\BAP", [switch]$Foreground)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Common-BapDeployment.ps1")
$Current = Join-Path $Root "current"
$Python = Join-Path $Current ".venv\Scripts\python.exe"
$EnvFile = Join-Path $Root "config\.env"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Current release Python was not found." }
Import-BapEnvironment -Path $EnvFile
$Manifest = Get-Content -LiteralPath (Join-Path $Current "deployment-manifest.json") -Raw | ConvertFrom-Json
$env:BAP_COMMIT_SHA = $Manifest.commit_sha
$Arguments = @("-m", "uvicorn", "bap_backend.app.main:app", "--host", "0.0.0.0", "--port", "12345")
Write-Output "BAP Backend is starting in the foreground. Keep this Terminal open and press Ctrl+C to stop it."
Push-Location $Current
try {
    & $Python @Arguments
    $BackendExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $BackendExitCode
