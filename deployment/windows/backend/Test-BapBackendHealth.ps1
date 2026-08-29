[CmdletBinding()]
param(
    [string]$LocalUrl = "http://127.0.0.1:12345/health",
    [string]$PublicUrl = "https://imuapp.lab2312.cs.nthu.edu.tw/health",
    [int]$Attempts = 12,
    [int]$DelaySeconds = 2,
    [switch]$SkipPublic
)

$ErrorActionPreference = "Stop"
function Test-HealthUrl {
    param([string]$Url)
    for ($Attempt = 1; $Attempt -le $Attempts; $Attempt++) {
        try {
            $Response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 10
            $Payload = $Response.Content | ConvertFrom-Json
            if ($Response.StatusCode -eq 200 -and $Payload.status -eq "ok" -and $Payload.service -eq "bap-backend") {
                return $true
            }
        } catch {
            if ($Attempt -eq $Attempts) { return $false }
        }
        Start-Sleep -Seconds $DelaySeconds
    }
    return $false
}

if (-not (Test-HealthUrl -Url $LocalUrl)) { throw "Local Backend health check failed." }
if (-not $SkipPublic -and -not (Test-HealthUrl -Url $PublicUrl)) { throw "Public Backend health check failed." }
Write-Output "BAP Backend health checks passed."

