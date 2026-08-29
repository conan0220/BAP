[CmdletBinding()]
param([string]$Root = "C:\BAP", [switch]$Foreground)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Common-BapDeployment.ps1")
$Current = Join-Path $Root "current"
$Python = Join-Path $Current ".venv\Scripts\python.exe"
$PidFile = Join-Path $Root "run\bap-backend.pid"
$EnvFile = Join-Path $Root "config\.env"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Current release Python was not found." }
if (Test-Path -LiteralPath $PidFile) {
    $Existing = (Get-Content -LiteralPath $PidFile -Raw).Trim()
    if ($Existing -match "^\d+$" -and (Get-Process -Id ([int]$Existing) -ErrorAction SilentlyContinue)) {
        throw "BAP Backend already has a running PID."
    }
    Remove-Item -LiteralPath $PidFile -Force
}
Import-BapEnvironment -Path $EnvFile
$Manifest = Get-Content -LiteralPath (Join-Path $Current "deployment-manifest.json") -Raw | ConvertFrom-Json
$env:BAP_COMMIT_SHA = $Manifest.commit_sha
$Arguments = @("-m", "uvicorn", "bap_backend.app.main:app", "--host", "0.0.0.0", "--port", "12345")
if ($Foreground) {
    Push-Location $Current
    try { & $Python @Arguments } finally { Pop-Location }
    exit $LASTEXITCODE
}
$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Path $LogDir, (Split-Path $PidFile -Parent) -Force | Out-Null
$Process = Start-Process -FilePath $Python -ArgumentList $Arguments -WorkingDirectory $Current `
    -RedirectStandardOutput (Join-Path $LogDir "bap-backend.stdout.log") `
    -RedirectStandardError (Join-Path $LogDir "bap-backend.stderr.log") `
    -WindowStyle Hidden -PassThru
Set-Content -LiteralPath $PidFile -Value $Process.Id -Encoding Ascii
Write-Output ("BAP Backend started with PID " + $Process.Id)
