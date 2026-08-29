[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ArtifactPath,
    [Parameter(Mandatory = $true)][string]$ChecksumPath,
    [Parameter(Mandatory = $true)][string]$ExpectedCommitSha,
    [string]$Root = "C:\BAP"
)

$ErrorActionPreference = "Stop"
function Remove-SafeIncomingTree {
    param([string]$PathToRemove)
    $IncomingRoot = [IO.Path]::GetFullPath((Join-Path $Root "incoming")).TrimEnd("\") + "\"
    $Candidate = [IO.Path]::GetFullPath($PathToRemove)
    if (-not $Candidate.StartsWith($IncomingRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a path outside the incoming directory."
    }
    if (Test-Path -LiteralPath $Candidate) { Remove-Item -LiteralPath $Candidate -Recurse -Force }
}
$ExpectedCommitSha = $ExpectedCommitSha.ToLowerInvariant()
if ($ExpectedCommitSha -notmatch "^[0-9a-f]{40}$") { throw "Expected commit SHA is invalid." }
if ([IO.Path]::GetFileName($ArtifactPath) -ne ("bap-deployment-scripts-" + $ExpectedCommitSha + ".zip")) {
    throw "Deployment script artifact filename does not match the expected commit SHA."
}
$ExpectedHash = ((Get-Content -LiteralPath $ChecksumPath -Raw).Trim() -split "\s+")[0].ToLowerInvariant()
$ActualHash = (Get-FileHash -LiteralPath $ArtifactPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ExpectedHash -ne $ActualHash) { throw "Deployment script artifact checksum does not match." }

$Allowed = @(
    "Common-BapDeployment.ps1", "Deploy-BapBackendRelease.ps1", "Rollback-BapBackendRelease.ps1",
    "Start-BapBackend.ps1", "Stop-BapBackend.ps1", "Get-BapBackendStatus.ps1",
    "Test-BapBackendHealth.ps1", "deployment-manifest.json"
)
$Temp = Join-Path $Root ("incoming\scripts-extract-" + [Guid]::NewGuid().ToString("N"))
$Target = Join-Path $Root ("scripts-releases\" + $ExpectedCommitSha)
if (Test-Path -LiteralPath $Target) { throw "Immutable deployment script release already exists." }
try {
    New-Item -ItemType Directory -Path $Temp -Force | Out-Null
    Expand-Archive -LiteralPath $ArtifactPath -DestinationPath $Temp
    foreach ($Item in Get-ChildItem -LiteralPath $Temp -Force) {
        if ($Allowed -notcontains $Item.Name) { throw "Deployment script artifact contains an unexpected file." }
    }
    foreach ($Required in $Allowed) {
        if (-not (Test-Path -LiteralPath (Join-Path $Temp $Required) -PathType Leaf)) { throw "Deployment script artifact is incomplete." }
    }
    $Manifest = Get-Content -LiteralPath (Join-Path $Temp "deployment-manifest.json") -Raw | ConvertFrom-Json
    if ($Manifest.project -ne "BAP" -or $Manifest.component -ne "deployment-scripts" -or $Manifest.commit_sha -ne $ExpectedCommitSha) {
        throw "Deployment script manifest does not match."
    }
    foreach ($Script in Get-ChildItem -LiteralPath $Temp -Filter "*.ps1") {
        $Tokens = $null; $Errors = $null
        [System.Management.Automation.Language.Parser]::ParseFile($Script.FullName, [ref]$Tokens, [ref]$Errors) | Out-Null
        if ($Errors.Count) { throw "Deployment script syntax validation failed." }
    }
    Move-Item -LiteralPath $Temp -Destination $Target
    $Scripts = Join-Path $Root "scripts"
    $NewLink = Join-Path $Root ("scripts-new-" + [Guid]::NewGuid().ToString("N"))
    & "C:\WINDOWS\system32\cmd.exe" /d /c mklink /J $NewLink $Target | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Unable to create the new scripts junction." }
    $OldPath = $null
    if (Test-Path -LiteralPath $Scripts) {
        $OldPath = Join-Path $Root ("scripts-old-" + [Guid]::NewGuid().ToString("N"))
        Move-Item -LiteralPath $Scripts -Destination $OldPath
    }
    try {
        Move-Item -LiteralPath $NewLink -Destination $Scripts
    } catch {
        if ($OldPath -and (Test-Path -LiteralPath $OldPath)) { Move-Item -LiteralPath $OldPath -Destination $Scripts }
        throw
    }
    if ($OldPath -and (Test-Path -LiteralPath $OldPath)) {
        $OldItem = Get-Item -LiteralPath $OldPath -Force
        if ($OldItem.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            Remove-Item -LiteralPath $OldPath -Force
        } else {
            Write-Warning ("Previous non-junction scripts directory was preserved at " + $OldPath)
        }
    }
    Write-Output ("BAP deployment scripts updated to " + $ExpectedCommitSha)
} finally {
    Remove-SafeIncomingTree -PathToRemove $Temp
}
