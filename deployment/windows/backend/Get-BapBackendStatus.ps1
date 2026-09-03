[CmdletBinding()]
param(
    [string]$Root = "C:\BAP",
    [string]$TaskName = "BAPBackend",
    [string]$LocalUrl = "http://127.0.0.1:12345/health",
    [switch]$AsJson
)

$Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
$Listener = Get-NetTCPConnection -LocalPort 12345 -State Listen -ErrorAction SilentlyContinue
$Health = $null
try { $Health = Invoke-RestMethod -Uri $LocalUrl -TimeoutSec 5 } catch {}
$Current = Join-Path $Root "current"
$Manifest = if (Test-Path -LiteralPath (Join-Path $Current "deployment-manifest.json")) { Get-Content -LiteralPath (Join-Path $Current "deployment-manifest.json") -Raw | ConvertFrom-Json } else { $null }
$Promotion = if (Test-Path -LiteralPath (Join-Path $Current "promotion-record.json")) { Get-Content -LiteralPath (Join-Path $Current "promotion-record.json") -Raw | ConvertFrom-Json } else { $null }
$Result = [ordered]@{
    task_state = if ($Task) { $Task.State.ToString().ToLowerInvariant() } else { "missing" }
    port_12345 = [bool]$Listener
    health = if ($Health) { $Health.status } else { "unavailable" }
    master_commit_sha = if ($Promotion) { $Promotion.master_commit_sha } else { $null }
    source_tree_sha = if ($Manifest) { $Manifest.source_tree_sha } else { $null }
    checksum = if ($Promotion) { $Promotion.backend_sha256 } else { $null }
    current_release = if (Test-Path -LiteralPath $Current) { (Get-Item -LiteralPath $Current -Force).Target } else { $null }
}
if ($AsJson) { $Result | ConvertTo-Json -Compress } else { [PSCustomObject]$Result }
