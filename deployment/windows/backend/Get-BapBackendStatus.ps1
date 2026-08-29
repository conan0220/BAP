[CmdletBinding()]
param([string]$Root = "C:\BAP", [switch]$AsJson)

$ErrorActionPreference = "Stop"
$PidFile = Join-Path $Root "run\bap-backend.pid"
$State = "stopped"
$ProcessId = $null
if (Test-Path -LiteralPath $PidFile -PathType Leaf) {
    $Text = (Get-Content -LiteralPath $PidFile -Raw).Trim()
    if ($Text -match "^\d+$") {
        $ProcessId = [int]$Text
        $Process = Get-CimInstance Win32_Process -Filter ("ProcessId = " + $ProcessId) -ErrorAction SilentlyContinue
        if ($Process -and $Process.CommandLine -like "*bap_backend.app.main*") { $State = "running" }
        else { $State = "stale_pid" }
    } else { $State = "stale_pid" }
}
$Result = [ordered]@{ state = $State; pid = $ProcessId }
if ($AsJson) { $Result | ConvertTo-Json -Compress } else { Write-Output ("BAP Backend: " + $State + $(if ($ProcessId) { " (PID $ProcessId)" } else { "" })) }

