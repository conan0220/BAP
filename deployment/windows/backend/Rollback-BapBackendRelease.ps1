[CmdletBinding()]
param(
    [string]$Root = "C:\BAP",
    [string]$PreviousRelease,
    [string]$DatabaseBackup,
    [switch]$SkipBackendStoppedCheckForTesting
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Common-BapDeployment.ps1")
if (-not $PreviousRelease) {
    $PreviousFile = Join-Path $Root "run\previous-release.txt"
    if (-not (Test-Path -LiteralPath $PreviousFile -PathType Leaf)) { throw "Previous release was not recorded." }
    $PreviousRelease = (Get-Content -LiteralPath $PreviousFile -Raw).Trim()
}
$PreviousRelease = Assert-BapReleasePath -Root $Root -ReleasePath $PreviousRelease
if (-not (Test-Path -LiteralPath $PreviousRelease -PathType Container)) { throw "Previous release does not exist." }
if (-not $SkipBackendStoppedCheckForTesting) {
    $Listener = Get-NetTCPConnection -LocalPort 12345 -State Listen -ErrorAction SilentlyContinue
    if ($Listener) {
        throw "Port 12345 is still in use. Stop the foreground BAP Backend with Ctrl+C before rollback."
    }
}
$Current = Join-Path $Root "current"
if (Test-Path -LiteralPath $Current) {
    $Item = Get-Item -LiteralPath $Current -Force
    if (-not ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "Current is not a junction." }
    Remove-Item -LiteralPath $Current -Force
}
& "C:\WINDOWS\system32\cmd.exe" /d /c mklink /J $Current $PreviousRelease | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Unable to restore the previous current junction." }
if ($DatabaseBackup) {
    $DatabaseBackup = [IO.Path]::GetFullPath($DatabaseBackup)
    $BackupsRoot = [IO.Path]::GetFullPath((Join-Path $Root "backups")).TrimEnd("\") + "\"
    if (-not $DatabaseBackup.StartsWith($BackupsRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Database backup is outside the backups directory."
    }
    if (Test-Path -LiteralPath $DatabaseBackup -PathType Leaf) {
        Copy-Item -LiteralPath $DatabaseBackup -Destination (Join-Path $Root "data\bap.db") -Force
    }
}
Write-Output "BAP Backend rollback completed."
Write-Output "Start the Backend manually in a foreground Terminal, then run Test-BapBackendHealth.ps1."
