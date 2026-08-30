[CmdletBinding()]
param(
    [string]$Root = "C:\BAP",
    [string]$LocalUrl = "http://127.0.0.1:12345/health",
    [switch]$AsJson
)

$ErrorActionPreference = "Stop"
$State = "stopped"
$CommitSha = $null
try {
    $Response = Invoke-WebRequest -Uri $LocalUrl -UseBasicParsing -TimeoutSec 5
    $Payload = $Response.Content | ConvertFrom-Json
    if ($Response.StatusCode -eq 200 -and $Payload.status -eq "ok" -and $Payload.service -eq "bap-backend") {
        $State = "running"
        $CommitSha = $Payload.commit_sha
    } else {
        $State = "unexpected_response"
    }
} catch {
    $State = "stopped"
}
$Result = [ordered]@{ state = $State; commit_sha = $CommitSha }
if ($AsJson) { $Result | ConvertTo-Json -Compress } else { Write-Output ("BAP Backend: " + $State + $(if ($CommitSha) { " ($CommitSha)" } else { "" })) }
