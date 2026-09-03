[CmdletBinding()]
param(
    [string]$Root = "C:\BAP",
    [string]$PreviousRelease,
    [string]$DatabaseBackup,
    [string]$TaskName = "BAPBackend",
    [switch]$SkipScheduledTaskForTesting,
    [switch]$SkipHealthCheckForTesting
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Common-BapDeployment.ps1")
if (-not $PreviousRelease) { $PreviousRelease = (Get-Content -LiteralPath (Join-Path $Root "run\previous-release.txt") -Raw).Trim() }
$PreviousRelease = Assert-BapReleasePath -Root $Root -ReleasePath $PreviousRelease
if (-not (Test-Path -LiteralPath $PreviousRelease -PathType Container)) { throw "Previous release does not exist." }

if (-not $SkipScheduledTaskForTesting) {
    Stop-BapBackendTaskAndListener -Root $Root -TaskName $TaskName
}
$Current = Join-Path $Root "current"
Remove-BapCurrentJunction -Root $Root
& "C:\WINDOWS\system32\cmd.exe" /d /c mklink /J $Current $PreviousRelease | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Unable to restore the previous current junction." }

if ($DatabaseBackup) {
    $DatabaseBackup = [IO.Path]::GetFullPath($DatabaseBackup)
    $BackupsRoot = [IO.Path]::GetFullPath((Join-Path $Root "backups")).TrimEnd("\") + "\"
    if (-not $DatabaseBackup.StartsWith($BackupsRoot, [StringComparison]::OrdinalIgnoreCase)) { throw "Database backup is outside the backups directory." }
    if (Test-Path -LiteralPath $DatabaseBackup -PathType Leaf) {
        Copy-Item -LiteralPath $DatabaseBackup -Destination (Join-Path $Root "data\bap.db") -Force
    }
}
if (-not $SkipScheduledTaskForTesting) { Start-ScheduledTask -TaskName $TaskName }
if (-not $SkipHealthCheckForTesting) {
    & (Join-Path $PreviousRelease "deployment\runtime\Test-BapBackendHealth.ps1")
    if ($LASTEXITCODE -ne 0) { throw "Rollback health check failed." }
}
Write-Output "BAP Backend rollback completed."
