[CmdletBinding()]
param([string]$Root = "C:\BAP")

$ErrorActionPreference = "Stop"
$PidFile = Join-Path $Root "run\bap-backend.pid"
if (-not (Test-Path -LiteralPath $PidFile -PathType Leaf)) { Write-Output "BAP Backend is not running."; exit 0 }
$Text = (Get-Content -LiteralPath $PidFile -Raw).Trim()
if ($Text -notmatch "^\d+$") { throw "PID file is invalid; no process was stopped." }
$ProcessId = [int]$Text
$Process = Get-CimInstance Win32_Process -Filter ("ProcessId = " + $ProcessId) -ErrorAction SilentlyContinue
if (-not $Process) { Remove-Item -LiteralPath $PidFile -Force; Write-Output "Removed stale PID file."; exit 0 }
$ExpectedPython = [IO.Path]::GetFullPath((Join-Path $Root "current\.venv\Scripts\python.exe"))
if (-not $Process.ExecutablePath -or -not $Process.ExecutablePath.Equals($ExpectedPython, [StringComparison]::OrdinalIgnoreCase) -or $Process.CommandLine -notlike "*bap_backend.app.main*") {
    throw "PID does not belong to the managed BAP Backend; no process was stopped."
}
Stop-Process -Id $ProcessId
Wait-Process -Id $ProcessId -Timeout 30 -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $PidFile -Force
Write-Output "BAP Backend stopped."

