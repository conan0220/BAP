[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ArtifactPath,
    [Parameter(Mandatory = $true)][string]$ChecksumPath,
    [Parameter(Mandatory = $true)][string]$ExpectedSourceTreeSha,
    [Parameter(Mandatory = $true)][string]$MasterCommitSha,
    [Parameter(Mandatory = $true)][string]$PromotionRecordPath,
    [string]$Root = "C:\BAP"
)

$ErrorActionPreference = "Stop"
foreach ($Sha in @($ExpectedSourceTreeSha, $MasterCommitSha)) {
    if ($Sha -notmatch "^[0-9a-f]{40}$") { throw "A required Git SHA is invalid." }
}
$Temp = Join-Path $Root ("incoming\bootstrap-" + [Guid]::NewGuid().ToString("N"))
try {
    $Expected = ((Get-Content -LiteralPath $ChecksumPath -Raw).Trim() -split "\s+")[0].ToLowerInvariant()
    $Actual = (Get-FileHash -LiteralPath $ArtifactPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Expected -notmatch "^[0-9a-f]{64}$" -or $Expected -ne $Actual) { throw "Candidate checksum validation failed." }

    $Promotion = Get-Content -LiteralPath $PromotionRecordPath -Raw | ConvertFrom-Json
    if (
        $Promotion.project -ne "BAP" -or
        $Promotion.master_commit_sha -ne $MasterCommitSha -or
        $Promotion.source_tree_sha -ne $ExpectedSourceTreeSha -or
        $Promotion.backend_sha256 -ne $Actual
    ) {
        throw "Promotion record does not match the requested Candidate."
    }

    New-Item -ItemType Directory -Path $Temp -Force | Out-Null
    Expand-Archive -LiteralPath $ArtifactPath -DestinationPath $Temp
    $Manifest = Get-Content -LiteralPath (Join-Path $Temp "deployment-manifest.json") -Raw | ConvertFrom-Json
    if ($Manifest.project -ne "BAP" -or $Manifest.component -ne "backend" -or $Manifest.source_tree_sha -ne $ExpectedSourceTreeSha) {
        throw "Candidate manifest validation failed."
    }
    $Allowed = @("bap_backend", "bap_common", "migrations", "deployment", "alembic.ini", "pyproject.toml", "uv.lock", ".python-version", "deployment-manifest.json")
    foreach ($Item in Get-ChildItem -LiteralPath $Temp -Force) {
        if ($Allowed -notcontains $Item.Name) { throw "Candidate contains an unexpected top-level path." }
    }
    $Runtime = Join-Path $Temp "deployment\runtime"
    foreach ($Name in @("Common-BapDeployment.ps1", "Deploy-BapBackendRelease.ps1", "Run-BapBackendScheduledTask.ps1", "Test-BapBackendHealth.ps1")) {
        $Path = Join-Path $Runtime $Name
        if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Candidate runtime deployment code is incomplete." }
        $Tokens = $null
        $Errors = $null
        [Management.Automation.Language.Parser]::ParseFile($Path, [ref]$Tokens, [ref]$Errors) | Out-Null
        if ($Errors.Count) { throw "Candidate runtime deployment code has invalid PowerShell syntax." }
    }
    & (Join-Path $Runtime "Deploy-BapBackendRelease.ps1") -ArtifactPath $ArtifactPath -ChecksumPath $ChecksumPath -ExpectedSourceTreeSha $ExpectedSourceTreeSha -MasterCommitSha $MasterCommitSha -PromotionRecordPath $PromotionRecordPath -Root $Root
    if ($LASTEXITCODE -ne 0) { throw "Candidate deployment failed." }
} finally {
    if (Test-Path -LiteralPath $Temp) { Remove-Item -LiteralPath $Temp -Recurse -Force }
}
