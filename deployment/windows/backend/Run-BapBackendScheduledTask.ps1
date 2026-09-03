[CmdletBinding()]
param([string]$Root = "C:\BAP")

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Common-BapDeployment.ps1")
$Current = Join-Path $Root "current"
$Python = Join-Path $Current ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Current release Python was not found." }
Import-BapEnvironment -Path (Join-Path $Root "config\.env")
$Promotion = Join-Path $Current "promotion-record.json"
if (Test-Path -LiteralPath $Promotion -PathType Leaf) {
    $Record = Get-Content -LiteralPath $Promotion -Raw | ConvertFrom-Json
    $env:BAP_COMMIT_SHA = $Record.master_commit_sha
}
Push-Location $Current
try {
    & $Python -m uvicorn "bap_backend.app.main:app" --host "0.0.0.0" --port "12345"
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
